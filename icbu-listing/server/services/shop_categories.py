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

from ..models import CategoryMemory, CategoryRecentPick, Draft, Shop, Template, User, utcnow
from . import catalog

# product.list has no "distinct categories" filter. Sidebar only needs one page;
# full scans stay available for other callers via online_pages.
_LIST_PAGES = 4
_SIDEBAR_ONLINE_PAGES = 1
_LIST_PAGE_SIZE = 50
_CACHE_SECONDS = 30 * 60
_SIDEBAR_CACHE_SECONDS = 5 * 60
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


def _online_counts(api: IcbuApi, shop_id: str, *, max_pages: int = _LIST_PAGES) -> Counter[str]:
    cached = _ONLINE_CACHE.get(shop_id)
    if cached and time.time() - cached[0] < _CACHE_SECONDS:
        return cached[1]
    counts: Counter[str] = Counter()
    try:
        for page in range(1, max(1, max_pages) + 1):
            payload = api.list_products(page, _LIST_PAGE_SIZE, "onSelling")
            products, total = _listing_products(payload if isinstance(payload, dict) else {})
            for item in products:
                cid = str(item.get("category_id") or "").strip()
                if cid:
                    counts[cid] += 1
            if not products or page * _LIST_PAGE_SIZE >= total:
                break
    except Exception:
        counts = cached[1] if cached else counts
    _ONLINE_CACHE[shop_id] = (time.time(), counts)
    return counts


def _label_hints(db: Session, shop: Shop) -> dict[str, str]:
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
    return hints


def _leaf_row(
    db: Session,
    api: IcbuApi,
    cid: str,
    *,
    fetch: bool,
    extra: dict[str, Any] | None = None,
    label_hint: str = "",
) -> dict[str, Any]:
    hint = str(label_hint or "").strip()
    node = catalog.get_node(db, api, cid, fetch=False)
    if node is None and fetch and not hint:
        node = catalog.get_node(db, api, cid, fetch=True)
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
        crumbs = [catalog.label(item) for item in catalog.path_of(db, api, cid, fetch=False)]
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


def sidebar(
    db: Session,
    api: IcbuApi,
    shop: Shop,
    user: User,
) -> dict[str, Any]:
    """Fast sidebar payload: recent picks + ranked used leaves, cached briefly."""
    key = f"{shop.id}:{user.id}"
    cached = _SIDEBAR_CACHE.get(key)
    if cached and time.time() - cached[0] < _SIDEBAR_CACHE_SECONDS:
        return cached[1]
    payload = {
        "recent": recent_picks(db, api, shop, user, fetch=False),
        "used": used_leaves(
            db,
            api,
            shop,
            include_online=True,
            fetch=False,
            online_pages=_SIDEBAR_ONLINE_PAGES,
        ),
    }
    _SIDEBAR_CACHE[key] = (time.time(), payload)
    return payload


def recent_picks(
    db: Session,
    api: IcbuApi,
    shop: Shop,
    user: User,
    *,
    limit: int = 8,
    fetch: bool = False,
) -> list[dict[str, Any]]:
    rows = (
        db.query(CategoryRecentPick)
        .filter(CategoryRecentPick.shop_id == shop.id, CategoryRecentPick.user_id == user.id)
        .order_by(CategoryRecentPick.picked_at.desc())
        .limit(limit)
        .all()
    )
    items: list[dict[str, Any]] = []
    for row in rows:
        cached_label = str(row.category_name or "").strip()
        item = _leaf_row(
            db,
            api,
            row.category_id,
            fetch=fetch,
            extra={"source": "recent", "picked_at": row.picked_at.isoformat() if row.picked_at else ""},
        )
        if cached_label:
            item["path_label"] = cached_label
            item["label"] = cached_label.split(" / ")[-1] if " / " in cached_label else cached_label
        items.append(item)
    return items


def used_leaves(
    db: Session,
    api: IcbuApi,
    shop: Shop,
    *,
    limit: int = 12,
    include_online: bool = True,
    fetch: bool = True,
    online_pages: int = _LIST_PAGES,
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

    if include_online:
        online = _online_counts(api, shop.id, max_pages=online_pages)
        for cid, n in online.items():
            _add(counts, sources, cid, "online", n)

    ranked = [cid for cid, _ in counts.most_common(limit)]
    hints = _label_hints(db, shop) if not fetch else {}
    items: list[dict[str, Any]] = []
    for cid in ranked:
        items.append(
            _leaf_row(
                db,
                api,
                cid,
                fetch=fetch,
                label_hint=hints.get(cid, ""),
                extra={"count": int(counts[cid]), "source": sources.get(cid, "online")},
            )
        )
    return items
