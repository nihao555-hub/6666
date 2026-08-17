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

from ..models import CategoryMemory, Draft, Shop, Template
from . import catalog

# product.list has no "distinct categories" filter. A few pages is enough to
# surface the shop's usual leaves without walking every listing.
_LIST_PAGES = 4
_LIST_PAGE_SIZE = 50
_CACHE_SECONDS = 30 * 60
_ONLINE_CACHE: dict[str, tuple[float, Counter[str]]] = {}


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


def _online_counts(api: IcbuApi, shop_id: str) -> Counter[str]:
    cached = _ONLINE_CACHE.get(shop_id)
    if cached and time.time() - cached[0] < _CACHE_SECONDS:
        return cached[1]
    counts: Counter[str] = Counter()
    try:
        for page in range(1, _LIST_PAGES + 1):
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


def used_leaves(db: Session, api: IcbuApi, shop: Shop, *, limit: int = 12) -> list[dict[str, Any]]:
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

    online = _online_counts(api, shop.id)
    for cid, n in online.items():
        _add(counts, sources, cid, "online", n)

    ranked = [cid for cid, _ in counts.most_common(limit)]
    items: list[dict[str, Any]] = []
    for cid in ranked:
        node = catalog.get_node(db, api, cid)
        if node is None:
            continue
        row = catalog.as_dict(node)
        row["count"] = int(counts[cid])
        row["source"] = sources.get(cid, "online")
        items.append(row)
    return items
