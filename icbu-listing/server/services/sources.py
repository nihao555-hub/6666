"""Field-level provenance so regenerate cannot clobber a person or an Excel.

Leading listing tools (Lingxing in particular) treat a draft as layered
sources, not a single blob. We keep the same idea, with a small set of
origins the seller can see:

    user     typed or confirmed in the review screen
    excel    came in from a spreadsheet
    ai       model-generated copy / attributes
    template listing template (fill-blank only)
    shop     shop-wide defaults
    system   image bank, category id written by the pipeline

`user` and `excel` are locked: AI regenerate and templates skip them.
An explicit user edit is the only thing that may overwrite a lock.
Changing category unlocks attribute groups, because those options belong
to the old leaf and would be illegal on the new one.
"""

from __future__ import annotations

from typing import Any, Mapping

LOCKED = {"user", "excel", "clone"}

LABELS = {
    "user": "手改",
    "excel": "Excel",
    "clone": "复制自在线",
    "ai": "AI",
    "template": "模板",
    "shop": "店铺默认",
    "system": "系统",
}

SHOP_KEYS = {
    "origin",
    "priceUnit",
    "paymentMethod",
    "port",
    "ladderPeriod",
    "shippingTemplateId",
    "pkgMeasure",
    "pkgWeight",
    "logisticsMode",
    "logisticsProperty",
    "marketSample",
    "market",
    "brand",
}
COPY_KEYS = {"productTitle", "productKeywords", "textDesc", "superText"}
TRADE_KEYS = {"ladderPrice", "fob", "scPrice", "minOrderQuantity"}
SYSTEM_KEYS = {"scImages", "detailImage", "catId"}
ATTR_KEYS = {"icbuCatProp", "saleProp"}
CATEGORY_RESET = {"icbuCatProp", "saleProp", "catId"}


def empty(value: Any) -> bool:
    return value in (None, "", [], {})


def parse(raw: str | None) -> dict[str, str]:
    import json

    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key): str(value) for key, value in payload.items() if value}


def dump(sources: Mapping[str, str]) -> str:
    import json

    return json.dumps(dict(sources), ensure_ascii=False)


def infer_initial(values: Mapping[str, Any], provided: Mapping[str, str] | None = None) -> dict[str, str]:
    sources: dict[str, str] = {}
    for key in values:
        if key in TRADE_KEYS:
            sources[key] = "user"
        elif key in COPY_KEYS:
            sources[key] = "ai"
        elif key in SHOP_KEYS:
            sources[key] = "shop"
        elif key in SYSTEM_KEYS:
            sources[key] = "system"
        elif key in ATTR_KEYS:
            sources[key] = "ai"
        else:
            sources[key] = "shop"
    if provided:
        for key, origin in provided.items():
            if origin:
                sources[key] = origin
    return sources


def mark_user_edits(old: Mapping[str, Any], incoming: Mapping[str, Any], sources: dict[str, str]) -> dict[str, str]:
    updated = dict(sources)
    for key, value in incoming.items():
        if value != old.get(key):
            updated[key] = "user"
    return updated


def mark_template_fills(before: Mapping[str, Any], after: Mapping[str, Any], sources: dict[str, str]) -> dict[str, str]:
    updated = dict(sources)
    for key, value in after.items():
        if empty(before.get(key)) and not empty(value) and updated.get(key) not in LOCKED:
            updated[key] = "template"
    return updated


def keep_locked(old: Mapping[str, Any], new: Mapping[str, Any], sources: Mapping[str, str]) -> dict[str, Any]:
    """Start from the regenerated values, then put locked fields back."""
    merged = dict(new)
    for key, origin in sources.items():
        if origin in LOCKED and key in old and not empty(old.get(key)):
            merged[key] = old[key]
    return merged


def unlock_for_category_change(sources: Mapping[str, str]) -> dict[str, str]:
    return {key: origin for key, origin in sources.items() if key not in CATEGORY_RESET}


def apply_incoming(
    base: Mapping[str, Any],
    incoming: Mapping[str, Any],
    sources: dict[str, str],
    origin: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Write incoming values. Locked keys stay unless the writer is the seller."""
    merged = dict(base)
    updated = dict(sources)
    for key, value in incoming.items():
        if empty(value):
            continue
        if updated.get(key) in LOCKED and origin != "user":
            continue
        merged[key] = value
        updated[key] = origin
    return merged, updated


def view(sources: Mapping[str, str]) -> dict[str, dict[str, str]]:
    return {
        key: {"origin": origin, "label": LABELS.get(origin, origin), "locked": origin in LOCKED}
        for key, origin in sources.items()
    }
