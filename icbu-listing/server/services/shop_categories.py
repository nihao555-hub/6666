"""Leaves this shop already uses — there is no official category-history API.

The tree from /icbu/product/category/get is the platform-wide ICBU catalog,
same for every shop. Suggestion endpoints are not on this AppKey. The shop's
own leaves come from product.list (each row has category_id), plus drafts,
templates, and what this shop already confirmed locally.
"""

from __future__ import annotations

import time
from collections import Counter
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from icbu_api import IcbuApi  # noqa: E402

from ..models import CategoryMemory, CategoryRecentPick, CategoryNode, Draft, Shop, Template, User, utcnow
from . import catalog

# product.list has no "distinct categories" filter. Sidebar only needs one page;
# full scans stay available for other callers via online_pages.
_LIST_PAGES = 4
_SIDEBAR_ONLINE_PAGES = 1
_LIST_PAGE_SIZE = 50
_CACHE_SECONDS = 30 * 60
_SIDEBAR_CACHE_SECONDS = 30 * 60
_ONLINE_CACHE: dict[str, tuple[float, Counter[str]]] = {}
_SIDEBAR_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _listing_products(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    nested = result.get("product_list") if isinstance(result.get("product_list"), dict) else {}
    products = result.get("products")
    if not isinstance(products, list):
        products = nested.get("products") if isinstance(nested.get("products"), list) else []
    total = result.get("total_item") or nested.get("total_item") or 0
    return products, int(total or 0)


def _add(counts: Counter[str], sources: dict[str, str], category_id: str, source: str, n: int = 1) -> None:
    cid = str(category_id or "").strip()
    if not cid or cid == "0":
        return
    counts[cid] += n
    sources.setdefault(cid, source)


def _online_counts(
    api: IcbuApi,
    shop_id: str,
    *,
    max_pages: int = _LIST_PAGES,
    cache_only: bool = False,
) -> Counter[str]:
    cached = _ONLINE_CACHE.get(shop_id)
    if cached:
        age = time.time() - cached[0]
        if age < _CACHE_SECONDS or cache_only:
            return cached[1]
    if cache_only or max_pages <= 0:
        return cached[1] if cached else Counter()
    counts: Counter[str] = Counter()
    fetched = False
    try:
        for page in range(1, max(1, max_pages) + 1):
            payload = api.list_products(page, _LIST_PAGE_SIZE, "onSelling")
            products, total = _listing_products(payload if isinstance(payload, dict) else {})
            for item in products:
                cid = str(item.get("category_id") or "").strip()
                if cid:
                    counts[cid] += 1
            fetched = True
            if not products or page * _LIST_PAGE_SIZE >= total:
                break
    except Exception:
        return cached[1] if cached else Counter()
    if fetched:
        _ONLINE_CACHE[shop_id] = (time.time(), counts)
    return counts


def _label_hints(db: Session, shop: Shop, category_ids: list[str] | None = None) -> dict[str, str]:
    hints: dict[str, str] = {}
    for cid, name in (
        db.query(CategoryMemory.category_id, CategoryMemory.category_name)
        .filter(CategoryMemory.shop_id == shop.id, CategoryMemory.category_name != "")
        .order_by(CategoryMemory.hits.desc())
        .all()
    ):
        key = str(cid or "").strip()
        if key and key not in hints:
            hints[key] = str(name or "").strip()
    for cid, name in (
        db.query(Draft.category_id, Draft.category_name)
        .filter(Draft.shop_id == shop.id, Draft.category_id != "", Draft.category_name != "")
        .all()
    ):
        key = str(cid or "").strip()
        label = str(name or "").strip()
        if key and label and key not in hints:
            hints[key] = label
    for cid, name in (
        db.query(CategoryRecentPick.category_id, CategoryRecentPick.category_name)
        .filter(CategoryRecentPick.shop_id == shop.id, CategoryRecentPick.category_name != "")
        .order_by(CategoryRecentPick.picked_at.desc())
        .all()
    ):
        key = str(cid or "").strip()
        label = str(name or "").strip()
        if key and label and key not in hints:
            hints[key] = label
    wanted = [str(item).strip() for item in (category_ids or []) if str(item).strip()]
    if wanted:
        rows = db.query(CategoryNode).filter(CategoryNode.category_id.in_(wanted)).all()
        for row in rows:
            key = str(row.category_id or "").strip()
            if key and key not in hints:
                hints[key] = catalog.label(row)
    return hints


def _leaf_row(
    db: Session,
    cid: str,
    *,
    extra: dict[str, Any] | None = None,
    label_hint: str = "",
    node_map: dict[str, CategoryNode] | None = None,
) -> dict[str, Any]:
    hint = str(label_hint or "").strip()
    node = (node_map or {}).get(cid)
    if node is None:
        node = db.get(CategoryNode, cid)
    if node is None:
        label = hint.split(" / ")[-1] if " / " in hint else (hint or cid)
        row = {
            "category_id": cid,
            "name": label,
            "cn_name": "",
            "label": label,
            "is_leaf": True,
            "level": 0,
        }
    else:
        row = catalog.as_dict(node)
        crumbs = [catalog.label(item) for item in catalog.path_from_db(db, cid)]
        row["path_label"] = " / ".join(crumbs) or row.get("label") or cid
    row.setdefault("path_label", row.get("label") or cid)
    if hint:
        row["path_label"] = hint
        row["label"] = hint.split(" / ")[-1] if " / " in hint else hint
    if extra:
        row.update(extra)
    return row


def record_recent_pick(
    db: Session,
    shop: Shop,
    user: User,
    category_id: str,
    category_name: str = "",
) -> None:
    cid = str(category_id or "").strip()
    if not cid or cid == "0":
        return
    row = (
        db.query(CategoryRecentPick)
        .filter(
            CategoryRecentPick.shop_id == shop.id,
            CategoryRecentPick.user_id == user.id,
            CategoryRecentPick.category_id == cid,
        )
        .one_or_none()
    )
    label = str(category_name or "").strip()
    now = utcnow()
    if row is None:
        db.add(
            CategoryRecentPick(
                shop_id=shop.id,
                user_id=user.id,
                category_id=cid,
                category_name=label,
                picked_at=now,
            )
        )
    else:
        if label:
            row.category_name = label
        row.picked_at = now
    db.commit()
    excess = (
        db.query(CategoryRecentPick.id)
        .filter(CategoryRecentPick.shop_id == shop.id, CategoryRecentPick.user_id == user.id)
        .order_by(CategoryRecentPick.picked_at.desc())
        .offset(24)
        .all()
    )
    if excess:
        db.query(CategoryRecentPick).filter(CategoryRecentPick.id.in_([item[0] for item in excess])).delete(
            synchronize_session=False
        )
        db.commit()
    _SIDEBAR_CACHE.pop(f"{shop.id}:{user.id}", None)


def invalidate_sidebar_cache(shop_id: str, user_id: str = "") -> None:
    if user_id:
        _SIDEBAR_CACHE.pop(f"{shop_id}:{user_id}", None)
    else:
        prefix = f"{shop_id}:"
        for key in list(_SIDEBAR_CACHE):
            if key.startswith(prefix):
                _SIDEBAR_CACHE.pop(key, None)
    _ONLINE_CACHE.pop(shop_id, None)


def _local_used_counts(db: Session, shop: Shop) -> Counter[str]:
    counts: Counter[str] = Counter()
    for cid, hits in (
        db.query(CategoryMemory.category_id, func.sum(CategoryMemory.hits))
        .filter(CategoryMemory.shop_id == shop.id)
        .group_by(CategoryMemory.category_id)
        .all()
    ):
        cid = str(cid or "").strip()
        if cid:
            counts[cid] += int(hits or 1)
    for (cid,) in db.query(Draft.category_id).filter(Draft.shop_id == shop.id, Draft.category_id != "").all():
        cid = str(cid or "").strip()
        if cid:
            counts[cid] += 1
    for (cid,) in db.query(Template.category_id).filter(Template.shop_id == shop.id, Template.category_id != "").all():
        cid = str(cid or "").strip()
        if cid:
            counts[cid] += 1
    return counts


def _online_cache_fresh(shop_id: str) -> bool:
    cached = _ONLINE_CACHE.get(shop_id)
    return bool(cached and time.time() - cached[0] < _CACHE_SECONDS)


def sidebar(
    db: Session,
    api: IcbuApi,
    shop: Shop,
    user: User,
    *,
    refresh_online: bool = False,
) -> dict[str, Any]:
    """Fast sidebar payload: recent picks + ranked used leaves, cached briefly."""
    key = f"{shop.id}:{user.id}"
    if refresh_online:
        invalidate_sidebar_cache(shop.id, user.id)
    cached = _SIDEBAR_CACHE.get(key)
    if cached and time.time() - cached[0] < _SIDEBAR_CACHE_SECONDS and not refresh_online:
        payload = cached[1]
        if payload.get("used") or payload.get("recent"):
            return payload

    recent = recent_picks(db, shop, user)
    online_fresh = _online_cache_fresh(shop.id)
    local_counts = _local_used_counts(db, shop)
    used = used_leaves(
        db,
        shop,
        api=api,
        include_online=True,
        cache_only=False,
        online_pages=_SIDEBAR_ONLINE_PAGES if refresh_online or not online_fresh or not local_counts else 0,
    )
    payload = {"recent": recent, "used": used}
    if used or recent:
        _SIDEBAR_CACHE[key] = (time.time(), payload)
    return payload


def recent_picks(
    db: Session,
    shop: Shop,
    user: User,
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    rows = (
        db.query(CategoryRecentPick)
        .filter(CategoryRecentPick.shop_id == shop.id, CategoryRecentPick.user_id == user.id)
        .order_by(CategoryRecentPick.picked_at.desc())
        .limit(limit)
        .all()
    )
    cids = [str(row.category_id) for row in rows]
    hints = _label_hints(db, shop, cids)
    node_map = {
        item.category_id: item
        for item in db.query(CategoryNode).filter(CategoryNode.category_id.in_(cids)).all()
    }
    items: list[dict[str, Any]] = []
    for row in rows:
        cached_label = str(row.category_name or "").strip() or hints.get(row.category_id, "")
        items.append(
            _leaf_row(
                db,
                row.category_id,
                extra={"source": "recent", "picked_at": row.picked_at.isoformat() if row.picked_at else ""},
                label_hint=cached_label,
                node_map=node_map,
            )
        )
    return items


def _ensure_node_labels(
    db: Session,
    api: IcbuApi,
    category_ids: list[str],
    hints: dict[str, str],
    *,
    max_fetch: int = 8,
) -> None:
    missing = [cid for cid in category_ids if not hints.get(cid) or hints.get(cid) == cid][:max_fetch]
    for cid in missing:
        if db.get(CategoryNode, cid) is not None:
            continue
        try:
            catalog.get_node(db, api, cid, fetch=True)
        except Exception:
            continue


def used_leaves(
    db: Session,
    shop: Shop,
    *,
    api: IcbuApi | None = None,
    limit: int = 12,
    include_online: bool = True,
    fetch: bool = True,
    online_pages: int = _LIST_PAGES,
    cache_only: bool = False,
) -> list[dict[str, Any]]:
    """Ranked leaves this shop already sells or has drafted."""
    counts: Counter[str] = Counter()
    sources: dict[str, str] = {}

    for cid, hits in (
        db.query(CategoryMemory.category_id, func.sum(CategoryMemory.hits))
        .filter(CategoryMemory.shop_id == shop.id)
        .group_by(CategoryMemory.category_id)
        .all()
    ):
        _add(counts, sources, str(cid), "memory", int(hits or 1))

    for (cid,) in db.query(Draft.category_id).filter(Draft.shop_id == shop.id, Draft.category_id != "").all():
        _add(counts, sources, str(cid), "draft")

    for (cid,) in db.query(Template.category_id).filter(Template.shop_id == shop.id, Template.category_id != "").all():
        _add(counts, sources, str(cid), "template")

    if include_online and api is not None:
        pages = online_pages if online_pages > 0 else (_SIDEBAR_ONLINE_PAGES if not cache_only else 0)
        online = _online_counts(
            api,
            shop.id,
            max_pages=pages,
            cache_only=cache_only,
        )
        for cid, n in online.items():
            _add(counts, sources, cid, "online", n)

    ranked = [cid for cid, _ in counts.most_common(limit)]
    hints = _label_hints(db, shop, ranked)
    if api is not None and not cache_only:
        _ensure_node_labels(db, api, ranked, hints)
        hints = _label_hints(db, shop, ranked)
    node_map = {
        item.category_id: item
        for item in db.query(CategoryNode).filter(CategoryNode.category_id.in_(ranked)).all()
    }
    items: list[dict[str, Any]] = []
    for cid in ranked:
        items.append(
            _leaf_row(
                db,
                cid,
                label_hint=hints.get(cid, ""),
                node_map=node_map,
                extra={"count": int(counts[cid]), "source": sources.get(cid, "online")},
            )
        )
    return items
