"""Category tree and publish-rule caches.

Both are the same for every tenant, so they are cached globally and only paid
for once. The tree is walked lazily: a listing only ever needs one root-to-leaf
path, and after the first few products a shop's usual branches are warm.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any, Iterable

from sqlalchemy.orm import Session

from icbu_api import IcbuApi  # noqa: E402

from ..models import CategoryNode, SchemaCache

TREE_TTL = timedelta(days=30)
SCHEMA_TTL = timedelta(days=7)
ROOT_ID = "0"


def _unwrap(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("result")
    if isinstance(result, dict):
        inner = result.get("result")
        if isinstance(inner, dict):
            return inner
        return result
    return payload


def _store_node(db: Session, raw: dict[str, Any]) -> CategoryNode:
    import json

    category_id = str(raw.get("category_id", ""))
    parents = raw.get("parent_ids") or []
    node = db.get(CategoryNode, category_id)
    if node is None:
        node = CategoryNode(category_id=category_id)
        db.add(node)
    node.name = str(raw.get("name") or "")
    node.cn_name = str(raw.get("cn_name") or "")
    node.level = int(raw.get("level") or 0)
    node.is_leaf = bool(raw.get("leaf_category"))
    node.parent_id = str(parents[0]) if parents else ""
    node.child_ids_json = json.dumps([str(x) for x in (raw.get("child_ids") or [])])
    node.fetched_at = datetime.utcnow()
    return node


def get_node(db: Session, api: IcbuApi, category_id: str | int, *, fetch: bool = True) -> CategoryNode | None:
    category_id = str(category_id)
    node = db.get(CategoryNode, category_id)
    if node is not None and datetime.utcnow() - node.fetched_at < TREE_TTL:
        # A non-leaf with no children is a bad cache (empty picker). Refetch.
        if node.is_leaf or child_ids(node) or not fetch:
            return node
    elif node is not None and not fetch:
        return node
    if not fetch:
        return node
    last_node = node
    for attempt in range(3):
        try:
            raw = _unwrap(api.get_category(category_id))
        except Exception:
            if attempt < 2 and category_id == ROOT_ID:
                import time

                time.sleep(0.12 * (attempt + 1))
                continue
            if category_id == ROOT_ID:
                return None
            return last_node
        if not raw.get("category_id") and category_id != ROOT_ID:
            if category_id == ROOT_ID:
                return None
            return last_node
        child_list = raw.get("child_ids") or []
        if category_id == ROOT_ID and fetch and not child_list and attempt < 2:
            import time

            time.sleep(0.12 * (attempt + 1))
            continue
        node = _store_node(db, {**raw, "category_id": raw.get("category_id", category_id)})
        db.commit()
        if category_id == ROOT_ID and fetch and not child_ids(node):
            db.delete(node)
            db.commit()
            if attempt < 2:
                import time

                time.sleep(0.12 * (attempt + 1))
                continue
            return None
        return node
    if category_id == ROOT_ID:
        return None
    return last_node


def child_ids(node: CategoryNode) -> list[str]:
    import json

    try:
        return [str(x) for x in json.loads(node.child_ids_json or "[]")]
    except json.JSONDecodeError:
        return []


def children_from_db(db: Session, parent_id: str | int) -> list[CategoryNode]:
    """Return cached direct children without calling the category API."""
    parent_id = str(parent_id)
    parent = db.get(CategoryNode, parent_id)
    ids = child_ids(parent) if parent is not None else []
    if ids:
        cached = {item.category_id: item for item in db.query(CategoryNode).filter(CategoryNode.category_id.in_(ids)).all()}
        return [cached[cid] for cid in ids if cid in cached]
    return (
        db.query(CategoryNode)
        .filter(CategoryNode.parent_id == parent_id)
        .order_by(CategoryNode.name, CategoryNode.cn_name, CategoryNode.category_id)
        .all()
    )


def path_from_db(db: Session, category_id: str) -> list[CategoryNode]:
    """Root-to-leaf breadcrumb using only cached nodes."""
    chain: list[CategoryNode] = []
    current = db.get(CategoryNode, str(category_id))
    seen: set[str] = set()
    while current is not None and current.category_id not in seen and current.category_id != ROOT_ID:
        seen.add(current.category_id)
        chain.append(current)
        if not current.parent_id or current.parent_id == ROOT_ID:
            break
        current = db.get(CategoryNode, current.parent_id)
    return list(reversed(chain))


def get_children(
    db: Session,
    api: IcbuApi,
    node: CategoryNode,
    *,
    fetch_missing: bool = True,
) -> list[CategoryNode]:
    """Fetch (and cache) the direct children of a node, in parallel."""
    ids = child_ids(node)
    if not ids:
        return children_from_db(db, node.category_id)
    cached = {item.category_id: item for item in db.query(CategoryNode).filter(CategoryNode.category_id.in_(ids)).all()}
    if cached and not fetch_missing:
        return [cached[cid] for cid in ids if cid in cached]
    missing = [cid for cid in ids if cid not in cached or datetime.utcnow() - cached[cid].fetched_at >= TREE_TTL]

    if missing and fetch_missing:
        with ThreadPoolExecutor(max_workers=8) as pool:
            fetched = list(pool.map(lambda cid: _safe_get(api, cid), missing))
        for raw in fetched:
            if raw:
                stored = _store_node(db, raw)
                cached[stored.category_id] = stored
        db.commit()

    return [cached[cid] for cid in ids if cid in cached]


def _safe_get(api: IcbuApi, category_id: str) -> dict[str, Any] | None:
    try:
        return _unwrap(api.get_category(category_id))
    except Exception:  # a single unreachable node must not break the descent
        return None


def path_of(db: Session, api: IcbuApi, category_id: str, *, fetch: bool = True) -> list[CategoryNode]:
    """Root-to-leaf breadcrumb, used to show the seller where a product landed."""
    chain: list[CategoryNode] = []
    current = get_node(db, api, category_id, fetch=fetch)
    seen: set[str] = set()
    while current is not None and current.category_id not in seen and current.category_id != ROOT_ID:
        seen.add(current.category_id)
        chain.append(current)
        if not current.parent_id or current.parent_id == ROOT_ID:
            break
        current = get_node(db, api, current.parent_id, fetch=fetch)
    return list(reversed(chain))


def label(node: CategoryNode) -> str:
    if node.cn_name and node.cn_name != node.name:
        return f"{node.name} / {node.cn_name}"
    return node.name or node.category_id


def get_schema_xml(db: Session, api: IcbuApi, category_id: str, language: str = "en_US", *, fetch: bool = True) -> str:
    key = f"{category_id}:{language}"
    cached = db.get(SchemaCache, key)
    if cached is not None and datetime.utcnow() - cached.fetched_at < SCHEMA_TTL:
        return cached.xml
    if not fetch:
        raise RuntimeError(f"类目 {category_id} 的发布规则还没缓存")
    xml = api.schema_xml(int(category_id), language)
    if not xml:
        raise RuntimeError(f"类目 {category_id} 拿不到发布规则")
    if cached is None:
        cached = SchemaCache(id=key, category_id=str(category_id), language=language, xml=xml)
        db.add(cached)
    else:
        cached.xml = xml
        cached.fetched_at = datetime.utcnow()
    db.commit()
    return xml


def as_dict(node: CategoryNode) -> dict[str, Any]:
    return {
        "category_id": node.category_id,
        "name": node.name,
        "cn_name": node.cn_name,
        "level": node.level,
        "is_leaf": node.is_leaf,
        "label": label(node),
    }


def summarise(nodes: Iterable[CategoryNode]) -> list[dict[str, Any]]:
    return [as_dict(node) for node in nodes]
