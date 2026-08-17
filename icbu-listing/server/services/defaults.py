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

from sqlalchemy import func
from sqlalchemy.orm import Session

from icbu_api import IcbuApi  # noqa: E402
from schema import SchemaField, parse_schema  # noqa: E402

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
