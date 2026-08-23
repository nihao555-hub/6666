"""Logistics block for draft review: status + what to do next.

Official ICBU expects the seller to pick freight per listing (shop template,
smart freight, or negotiated). Packaging is per SKU. The audit page shows a
compact card — green when complete, actionable when something is missing.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from schema import SchemaField, index_fields, parse_schema  # noqa: E402
from sqlalchemy.orm import Session

from ..models import Draft, Shop
from . import defaults as defaults_service, templates as template_service
from .habits_ready import _shipping_options
from .shop_client import shop_api, shop_defaults

NEGOTIATED_TYPES = frozenset(
    {
        "FREIGHT_NEGOTIATION",
        "freight_negotiation",
        "smartEntrust",
        "SMART_ENTRUST",
    }
)


def _filled(value: Any) -> bool:
    if value in (None, "", [], {}, ()):
        return False
    if isinstance(value, dict):
        if "$value" in value:
            return bool(str(value.get("$value") or "").strip())
        return any(_filled(item) for key, item in value.items() if key != "$attrs")
    return True


def _scalar(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, dict):
        if value.get("$value") not in (None, ""):
            return str(value.get("$value")).strip()
        for key in ("value", "period", "time", "days"):
            if value.get(key) not in (None, ""):
                return str(value[key]).strip()
        return ""
    if isinstance(value, list):
        parts = [_scalar(item) for item in value]
        return ",".join(part for part in parts if part)
    return str(value).strip()


def _shipping_id(values: Mapping[str, Any]) -> str:
    shipping = values.get("shippingTemplate")
    if isinstance(shipping, Mapping):
        nested = shipping.get("shippingTemplateId")
        if nested not in (None, ""):
            return str(nested).strip()
    return str(values.get("shippingTemplateId") or "").strip()


def _shipping_type(values: Mapping[str, Any]) -> str:
    shipping = values.get("shippingTemplate")
    if isinstance(shipping, Mapping):
        return str(shipping.get("templateType") or "").strip()
    return ""


def shipping_ok(values: Mapping[str, Any], *, has_field: bool) -> bool:
    if not has_field:
        return True
    if _shipping_id(values):
        return True
    template_type = _shipping_type(values)
    return bool(template_type)


def shipping_label(values: Mapping[str, Any], options: list[dict[str, str]]) -> str:
    template_id = _shipping_id(values)
    if template_id:
        for item in options:
            if str(item.get("value") or "") == template_id:
                return str(item.get("label") or template_id)
        return template_id
    template_type = _shipping_type(values)
    if template_type in NEGOTIATED_TYPES or template_type:
        if template_type in {"FREIGHT_NEGOTIATION", "freight_negotiation"}:
            return "运费面议"
        if template_type in {"smartEntrust", "SMART_ENTRUST"}:
            return "智能运费"
        return template_type
    return ""


def packaging_ok(values: Mapping[str, Any], specs: Mapping[str, SchemaField]) -> tuple[bool, bool, bool]:
    weight_ok = True
    measure_ok = True
    if "pkgWeight" in specs:
        weight_ok = _filled(values.get("pkgWeight"))
    if "pkgMeasure" in specs:
        measure = values.get("pkgMeasure")
        if isinstance(measure, Mapping):
            measure_ok = all(_filled(measure.get(key)) for key in ("length", "width", "height"))
        else:
            measure_ok = False
    return weight_ok and measure_ok, weight_ok, measure_ok


def _measure_text(measure: Mapping[str, Any] | None) -> str:
    if not isinstance(measure, Mapping):
        return ""
    length = _scalar(measure.get("length"))
    width = _scalar(measure.get("width"))
    height = _scalar(measure.get("height"))
    if length and width and height:
        return f"{length}×{width}×{height} cm"
    return ""


def _template_packaging_hint(template_values: Mapping[str, Any]) -> dict[str, str]:
    extracted = defaults_service.extract_listing_defaults(template_values)
    measure = template_values.get("pkgMeasure") if isinstance(template_values.get("pkgMeasure"), Mapping) else {}
    return {
        "pkgWeight": extracted.get("pkgWeight") or _scalar(template_values.get("pkgWeight")),
        "pkgLength": extracted.get("pkgLength") or _scalar(measure.get("length")),
        "pkgWidth": extracted.get("pkgWidth") or _scalar(measure.get("width")),
        "pkgHeight": extracted.get("pkgHeight") or _scalar(measure.get("height")),
        "shippingTemplateId": extracted.get("shippingTemplateId") or _shipping_id(template_values),
    }


def _logistics_property_label(values: Mapping[str, Any], specs: Mapping[str, SchemaField]) -> str:
    spec = specs.get("logisticsProperty")
    raw = values.get("logisticsProperty")
    if spec is None or not _filled(raw):
        return ""
    wanted = _scalar(raw)
    if spec.options:
        for option in spec.options:
            if option.value == wanted or option.display_name == wanted:
                return option.display_name
    return wanted


def panel_for_draft(
    db: Session,
    shop: Shop,
    draft: Draft,
    *,
    xml: str = "",
    values: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(values or {})
    if not payload:
        try:
            payload = json.loads(getattr(draft, "values_json", None) or "{}")
        except (json.JSONDecodeError, TypeError):
            payload = {}
    if not isinstance(payload, dict):
        payload = {}

    category_id = str(getattr(draft, "category_id", "") or payload.get("catId") or "")
    fields = parse_schema(xml) if xml else []
    specs = index_fields(fields)

    form_fields: list[dict[str, Any]] = []
    if category_id and db is not None and shop is not None:
        try:
            view = defaults_service.options_view(db, shop_api(shop), shop, shop_defaults(shop), category_id)
            form_fields = view.get("fields") or []
        except Exception:
            form_fields = []

    shipping_options = _shipping_options(form_fields)
    has_shipping = "shippingTemplate" in specs
    has_property = "logisticsProperty" in specs
    has_weight = "pkgWeight" in specs
    has_measure = "pkgMeasure" in specs

    template = template_service.find_for(db, shop.id, category_id) if db is not None and category_id else None
    template_name = str(getattr(template, "name", "") or "") if template is not None else ""
    template_values = template_service.values_of(template) if template is not None else {}
    template_hint = _template_packaging_hint(template_values) if template_values else {}

    shipping_is_ok = shipping_ok(payload, has_field=has_shipping)
    pack_ok, weight_ok, measure_ok = packaging_ok(payload, specs)
    property_ok = not has_property or _filled(payload.get("logisticsProperty"))

    items: list[dict[str, Any]] = []
    if has_shipping:
        items.append(
            {
                "id": "shippingTemplate",
                "label": "运费模板",
                "ok": shipping_is_ok,
                "value": shipping_label(payload, shipping_options),
                "missing_hint": "选店里运费模板，或去发品习惯给这类目设一次",
            }
        )
    if has_property:
        items.append(
            {
                "id": "logisticsProperty",
                "label": "物流属性",
                "ok": property_ok,
                "value": _logistics_property_label(payload, specs) or _scalar(payload.get("logisticsProperty")),
                "missing_hint": "在发品习惯里设常用物流属性",
            }
        )
    if has_weight or has_measure:
        measure = payload.get("pkgMeasure") if isinstance(payload.get("pkgMeasure"), Mapping) else {}
        weight_text = f"{_scalar(payload.get('pkgWeight'))} kg" if _scalar(payload.get("pkgWeight")) else ""
        measure_text = _measure_text(measure)
        pack_value = " · ".join(part for part in (weight_text, measure_text) if part)
        items.append(
            {
                "id": "packaging",
                "label": "包装",
                "ok": pack_ok,
                "value": pack_value,
                "missing_hint": "套用类目模板，或本条手动填重量和尺寸",
                "weight_ok": weight_ok,
                "measure_ok": measure_ok,
            }
        )

    summary_parts = []
    for item in items:
        if item.get("ok") and item.get("value"):
            summary_parts.append(str(item["value"]))
    source = template_name if template_name else ("店铺兜底" if items else "")
    ready = all(item.get("ok") for item in items) if items else True

    measure = payload.get("pkgMeasure") if isinstance(payload.get("pkgMeasure"), Mapping) else {}
    edit_values = {
        "shippingTemplateId": _shipping_id(payload),
        "shippingTemplateType": _shipping_type(payload),
        "pkgWeight": _scalar(payload.get("pkgWeight")),
        "pkgLength": _scalar(measure.get("length")),
        "pkgWidth": _scalar(measure.get("width")),
        "pkgHeight": _scalar(measure.get("height")),
    }

    return {
        "ready": ready,
        "summary": " · ".join(summary_parts),
        "source": source,
        "items": items,
        "shipping_options": shipping_options,
        "template_hint": template_hint,
        "template_name": template_name,
        "category_id": category_id,
        "shop_id": getattr(shop, "id", "") if shop is not None else "",
        "has_fields": {
            "shippingTemplate": has_shipping,
            "pkgWeight": has_weight,
            "pkgMeasure": has_measure,
            "logisticsProperty": has_property,
        },
        "values": edit_values,
    }


def apply_shipping(values: dict[str, Any], template_id: str, *, negotiated: bool = False) -> None:
    text = str(template_id or "").strip()
    if negotiated or not text:
        values["shippingTemplate"] = {"templateType": text or "FREIGHT_NEGOTIATION"}
        values.pop("shippingTemplateId", None)
        return
    values["shippingTemplate"] = {
        "templateType": "MERCHANT_OWN_TEMPLATE",
        "shippingTemplateId": text,
    }
    values["shippingTemplateId"] = text


def apply_packaging(
    values: dict[str, Any],
    *,
    pkg_weight: str = "",
    pkg_length: str = "",
    pkg_width: str = "",
    pkg_height: str = "",
) -> None:
    weight = str(pkg_weight or "").strip()
    if weight:
        values["pkgWeight"] = weight
    length = str(pkg_length or "").strip()
    width = str(pkg_width or "").strip()
    height = str(pkg_height or "").strip()
    if length and width and height:
        values["pkgMeasure"] = {"length": length, "width": width, "height": height}


def apply_template_hint(values: dict[str, Any], hint: Mapping[str, str]) -> None:
    shipping_id = str(hint.get("shippingTemplateId") or "").strip()
    if shipping_id and not _shipping_id(values):
        apply_shipping(values, shipping_id)
    if not _scalar(values.get("pkgWeight")) and str(hint.get("pkgWeight") or "").strip():
        values["pkgWeight"] = str(hint["pkgWeight"]).strip()
    measure = values.get("pkgMeasure") if isinstance(values.get("pkgMeasure"), Mapping) else {}
    merged = dict(measure) if isinstance(measure, Mapping) else {}
    for key, hint_key in (("length", "pkgLength"), ("width", "pkgWidth"), ("height", "pkgHeight")):
        if not _scalar(merged.get(key)) and str(hint.get(hint_key) or "").strip():
            merged[key] = str(hint[hint_key]).strip()
    if all(_scalar(merged.get(key)) for key in ("length", "width", "height")):
        values["pkgMeasure"] = merged
