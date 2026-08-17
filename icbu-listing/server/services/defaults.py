"""Shop defaults, resolved against the official publish rules.

Every field on the shop-defaults form exists in `schema.get` for the shop's own
categories, so almost none of it has to be typed. Units, logistics attributes
and sample policy come back as option lists, and — the one nobody can guess —
`shippingTemplate.shippingTemplateId` comes back as *this shop's* freight
templates, by name. Asking a seller to type `2041723009` was never reasonable.

Two things the form must also get right: fields the category does not have
(payment method and port are absent from plenty of leaves) are reported as
unsupported instead of quietly ignored at publish time, and the value we store
stays the same shape the pipeline already resolves — a display label for most
fields, the raw id for the freight template.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

import json
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from icbu_api import IcbuApi  # noqa: E402
from schema import SchemaField, extract_values, parse_schema  # noqa: E402

from ..models import CategoryMemory, Shop
from . import catalog

ORIGIN_HINTS = ("place of origin", "origin", "产地", "原产地")

# key: the shop-default we store. path: where it lives in the official schema.
# The form always stores the official option value, never the display name:
# the same option comes back as «普货» or «Ordinary goods» depending on the
# language of the call, so a saved label stops matching as soon as the shop
# switches language. Values are stable, and `option_by_label` resolves either,
# which keeps defaults saved before this change working.
SPECS: list[dict[str, Any]] = [
    {"key": "origin", "label": "产地", "path": ("icbuCatProp", "@origin")},
    {"key": "priceUnit", "label": "计量单位", "path": ("priceUnit",)},
    {"key": "saleType", "label": "售卖方式", "path": ("saleType",)},
    {
        "key": "shippingTemplateId",
        "label": "运费模板",
        "path": ("shippingTemplate", "shippingTemplateId"),
        "hint": "店铺自己的模板，接口直接拉。留空走买卖双方协商。",
    },
    {"key": "logisticsProperty", "label": "物流属性", "path": ("logisticsProperty",)},
    {"key": "marketSample", "label": "样品服务", "path": ("marketSample",)},
    {"key": "paymentMethod", "label": "付款方式", "path": ("paymentMethod",)},
    {"key": "port", "label": "出运港口", "path": ("port",)},
    {"key": "market", "label": "市场", "path": ("market",)},
]

# Stock placeholders from DEFAULT_TEMPLATE. Auto-pull may replace these
# until the seller saves the field themselves.
PLACEHOLDERS: dict[str, set[str]] = {
    "origin": {"", "China"},
    "priceUnit": {"", "Piece/Pieces"},
    "saleType": {"", "Unit"},
    "logisticsProperty": {"", "general_cargo_0"},
    "marketSample": {"", "Unavailable"},
    "shippingTemplateId": {""},
    "paymentMethod": {"", "T/T"},
    "port": {""},
    "market": {"", "询盘"},
    "ladderPeriod": {"", "15"},
    "pkgWeight": {""},
    "pkgLength": {""},
    "pkgWidth": {""},
    "pkgHeight": {""},
    "brand": {""},
}

PULLABLE = tuple(PLACEHOLDERS)

# Free text, but still worth showing so the form is one list instead of two.
FREE_TEXT: list[dict[str, str]] = [
    {"key": "ladderPeriod", "label": "交期（天）", "hint": "起订量对应的备货天数。"},
    {"key": "pkgWeight", "label": "包装重量 kg", "hint": "官方物流分算这一桶。"},
    {"key": "pkgLength", "label": "包装长 cm", "hint": ""},
    {"key": "pkgWidth", "label": "包装宽 cm", "hint": ""},
    {"key": "pkgHeight", "label": "包装高 cm", "hint": ""},
    {"key": "brand", "label": "品牌", "hint": "红线。没有就留空，等于无品牌，AI 不准编。"},
]


def _find(specs: Mapping[str, SchemaField], path: Iterable[str]) -> SchemaField | None:
    steps = list(path)
    node = specs.get(steps[0])
    for step in steps[1:]:
        if node is None:
            return None
        if step == "@origin":
            node = _by_name(node.children or [], ORIGIN_HINTS)
        else:
            node = node.child(step)
    return node


def _by_name(fields: Iterable[SchemaField], hints: tuple[str, ...]) -> SchemaField | None:
    for item in fields:
        name = (item.name or "").strip().lower()
        if any(hint in name for hint in hints):
            return item
    return None


def reference_category(db: Session, api: IcbuApi, shop: Shop) -> str:
    """A leaf whose rules stand in for the shop's own defaults.

    Trade and logistics fields barely move between leaves, and freight
    templates are shop-level, so the shop's most-used category is a fine
    stand-in. A brand-new shop falls back to whatever it already sells.
    """
    row = (
        db.query(CategoryMemory.category_id, func.sum(CategoryMemory.hits).label("hits"))
        .filter(CategoryMemory.shop_id == shop.id)
        .group_by(CategoryMemory.category_id)
        .order_by(func.sum(CategoryMemory.hits).desc())
        .first()
    )
    if row is not None and row[0]:
        return str(row[0])

    payload = api.list_products(1, 1, "onSelling")
    result = payload.get("result") or {}
    products = (result.get("product_list") or {}).get("products") or result.get("products") or []
    if products:
        return str(products[0].get("category_id") or "")
    return ""


def _meta(defaults: Mapping[str, Any]) -> dict[str, Any]:
    raw = defaults.get("_meta")
    return dict(raw) if isinstance(raw, dict) else {}


def user_keys(defaults: Mapping[str, Any]) -> set[str]:
    return {str(item) for item in (_meta(defaults).get("user_keys") or []) if item}


def mark_user_keys(defaults: dict[str, Any], keys: Iterable[str]) -> None:
    meta = _meta(defaults)
    meta["user_keys"] = sorted(user_keys(defaults) | {str(item) for item in keys if item})
    defaults["_meta"] = meta


def _scalar(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, dict):
        if value.get("$value") not in (None, ""):
            return str(value.get("$value"))
        for key in ("value", "period", "time", "days", "leadTime"):
            if value.get(key) not in (None, ""):
                return str(value[key])
        return ""
    if isinstance(value, list):
        return ",".join(part for part in (_scalar(item) for item in value) if part)
    return str(value).strip()


def _nested(values: Mapping[str, Any], *keys: str) -> Any:
    current: Any = values
    for key in keys:
        if not isinstance(current, Mapping):
            return ""
        current = current.get(key)
    return current


def extract_listing_defaults(values: Mapping[str, Any]) -> dict[str, str]:
    """Pull shop-default fields out of one schema.render payload."""
    measure = values.get("pkgMeasure") if isinstance(values.get("pkgMeasure"), Mapping) else {}
    origin = _scalar(values.get("origin"))
    if not origin:
        props = values.get("icbuCatProp") if isinstance(values.get("icbuCatProp"), Mapping) else {}
        origin = _scalar(props.get("p-1") or props.get("origin"))
    period = _nested(values, "ladderPeriod", "ladderPeriod_0") or values.get("ladderPeriod")
    return {
        "origin": origin,
        "priceUnit": _scalar(values.get("priceUnit")),
        "saleType": _scalar(values.get("saleType")),
        "shippingTemplateId": _scalar(
            _nested(values, "shippingTemplate", "shippingTemplateId") or values.get("shippingTemplateId")
        ),
        "logisticsProperty": _scalar(values.get("logisticsProperty")),
        "marketSample": _scalar(values.get("marketSample")),
        "paymentMethod": _scalar(values.get("paymentMethod")),
        "port": _scalar(values.get("port")),
        "market": _scalar(values.get("market")),
        "pkgWeight": _scalar(values.get("pkgWeight")),
        "pkgLength": _scalar(measure.get("length") or measure.get("pkgLength")),
        "pkgWidth": _scalar(measure.get("width") or measure.get("pkgWidth")),
        "pkgHeight": _scalar(measure.get("height") or measure.get("pkgHeight")),
        "brand": _scalar(values.get("brand")),
        "ladderPeriod": _scalar(period),
    }


def _can_write(current: Mapping[str, Any], key: str, *, refresh: bool) -> bool:
    if key in user_keys(current):
        return False
    if refresh:
        return True
    value = str(current.get(key) or "").strip()
    return value in PLACEHOLDERS.get(key, {""})


def apply_extracted(
    current: Mapping[str, Any],
    extracted: Mapping[str, Any],
    *,
    refresh: bool = False,
) -> tuple[dict[str, Any], list[str]]:
    merged = dict(current)
    filled: list[str] = []
    for key in PULLABLE:
        value = extracted.get(key)
        if isinstance(value, dict):
            value = _scalar(value)
        text = str(value or "").strip()
        if not text or not _can_write(merged, key, refresh=refresh):
            continue
        merged[key] = text
        filled.append(key)
    if filled:
        meta = _meta(merged)
        meta["pulled_at"] = datetime.utcnow().isoformat()
        meta["pulled_keys"] = sorted(set(meta.get("pulled_keys") or []) | set(filled))
        merged["_meta"] = meta
    return merged, filled


def _first_listing(api: IcbuApi) -> tuple[str, str]:
    payload = api.list_products(1, 5, "onSelling")
    result = payload.get("result") if isinstance(payload, dict) else {}
    if not isinstance(result, dict):
        result = {}
    nested = result.get("product_list") if isinstance(result.get("product_list"), dict) else {}
    products = result.get("products")
    if not isinstance(products, list):
        products = nested.get("products") if isinstance(nested.get("products"), list) else []
    for item in products:
        if not isinstance(item, dict):
            continue
        product_id = str(item.get("product_id") or item.get("id") or "")
        category_id = str(item.get("category_id") or "")
        if product_id and category_id:
            return product_id, category_id
    return "", ""


def pull_from_listing(
    api: IcbuApi,
    *,
    product_id: str,
    category_id: str,
    language: str = "en_US",
) -> dict[str, str]:
    payload = api.schema_render(int(category_id), int(product_id), language)
    result = payload.get("result") or payload
    xml = str((result or {}).get("data") or "")
    return extract_listing_defaults(extract_values(xml))


def pull_from_shop(
    db: Session,
    api: IcbuApi,
    shop: Shop,
    *,
    product_id: str = "",
    category_id: str = "",
    refresh: bool = False,
) -> dict[str, Any]:
    """Fill pullable defaults from a live listing. Never overwrite seller edits."""
    current = {}
    try:
        loaded = json.loads(shop.defaults_json or "{}")
        if isinstance(loaded, dict):
            current = loaded
    except json.JSONDecodeError:
        current = {}
    language = str(current.get("language") or "en_US")
    if not refresh and not any(_can_write(current, key, refresh=False) for key in PULLABLE):
        return {"defaults": current, "filled": [], "source_product_id": "", "reason": "already_set"}
    if not product_id or not category_id:
        product_id, category_id = _first_listing(api)
    if not product_id or not category_id:
        return {"defaults": current, "filled": [], "source_product_id": "", "reason": "no_listing"}
    extracted = pull_from_listing(api, product_id=product_id, category_id=category_id, language=language)
    merged, filled = apply_extracted(current, extracted, refresh=refresh)
    if filled:
        shop.defaults_json = json.dumps(merged, ensure_ascii=False)
        db.commit()
    return {"defaults": merged, "filled": filled, "source_product_id": product_id}


def options_view(
    db: Session,
    api: IcbuApi,
    shop: Shop,
    defaults: Mapping[str, Any],
    category_id: str = "",
    language: str = "en_US",
) -> dict[str, Any]:
    category_id = category_id or reference_category(db, api, shop)
    if not category_id:
        return {"category_id": "", "fields": _free_text_only(defaults), "note": "店里还没有商品，拉不到官方选项，先手填。"}

    xml = catalog.get_schema_xml(db, api, category_id, language)
    specs = {item.id: item for item in parse_schema(xml)}
    node = catalog.get_node(db, api, category_id)

    fields: list[dict[str, Any]] = []
    for spec in SPECS:
        found = _find(specs, spec["path"])
        options = [{"value": option.value, "label": option.display_name} for option in (found.options if found is not None else [])]
        fields.append(
            {
                "key": spec["key"],
                "label": spec["label"],
                "hint": spec.get("hint", ""),
                "value": _stored_value(found, defaults.get(spec["key"], "")),
                "kind": "select" if options else ("text" if found is not None else "unsupported"),
                "multiple": bool(found is not None and found.type.startswith("multi")),
                "required": bool(found is not None and found.required),
                "options": options,
            }
        )
    fields.extend(_free_text_only(defaults))
    return {
        "category_id": category_id,
        "category_name": catalog.label(node) if node is not None else category_id,
        "fields": fields,
    }


def _stored_value(found: SchemaField | None, saved: Any) -> Any:
    """Show a saved default as the option value the select binds to.

    Defaults written before the form used official values hold a display name,
    which no longer matches any option once the language differs.
    """
    if found is None or not saved or not found.options:
        return saved
    option = found.option_by_label(str(saved))
    return option.value if option is not None else saved


def remember_option_labels(defaults: Mapping[str, Any], fields: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    """Keep the names the seller saw, so the shop list does not show raw ids."""
    labels = dict(defaults.get("labels") or {})
    for field in fields:
        if field.get("kind") != "select":
            continue
        raw = field.get("value")
        if raw in (None, "", []):
            continue
        items = raw if isinstance(raw, list) else str(raw).split(",")
        names: list[str] = []
        options = field.get("options") or []
        for item in items:
            text = str(item).strip()
            if not text:
                continue
            match = next(
                (option for option in options if str(option.get("value")) == text or str(option.get("label")) == text),
                None,
            )
            names.append(str(match["label"]) if match else text)
        if names:
            labels[str(field["key"])] = "、".join(names)
    return labels


def _free_text_only(defaults: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "key": item["key"],
            "label": item["label"],
            "hint": item["hint"],
            "value": defaults.get(item["key"], ""),
            "kind": "text",
            "multiple": False,
            "required": False,
            "options": [],
        }
        for item in FREE_TEXT
    ]
