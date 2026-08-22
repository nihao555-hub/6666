"""Pick a listing template during batch review — one shop may have several per category."""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from ai import AiClient, AiUnavailable  # noqa: E402
from sqlalchemy.orm import Session

from ..models import Shop, Template
from . import templates as template_service

SUMMARY_KEYS = (
    "origin",
    "priceUnit",
    "paymentMethod",
    "port",
    "logisticsProperty",
    "logisticsMode",
    "pkgWeight",
    "ladderPeriod",
    "saleType",
    "brand",
    "marketSample",
    "shippingTemplateId",
)

PICK_PROMPT = """You pick listing templates for an Alibaba.com wholesale batch.

Leaf category: {category_name} ({category_id})

Each template stores trade/logistics defaults (units, freight, payment, packaging) for this shop.
Products in the batch only vary by SKU facts — templates do NOT set title, price, or images.

Available templates:
{templates}

Sample rows (facts the seller typed):
{samples}

Rules:
- Prefer one template for the whole batch when trade terms clearly match.
- Use row_overrides only when two product groups need different freight/payment habits.
- Never invent a template id — pick from the list only.
- If one template is obviously the shop default for this product type, pick it.

Return JSON only:
{{
  "template_id": "default template id for most rows",
  "reasoning": "one short Chinese sentence for the seller",
  "confidence": "high|medium|low",
  "row_overrides": {{ "SKU-1001": "other_template_id" }}
}}
"""


def list_for_category(db: Session, shop_id: str, category_id: str) -> list[Template]:
    if not shop_id or not category_id:
        return []
    return (
        db.query(Template)
        .filter(Template.shop_id == shop_id, Template.category_id == category_id)
        .order_by(Template.created_at.desc())
        .all()
    )


def _flat_value(values: Mapping[str, Any], key: str) -> str:
    raw = values.get(key)
    if isinstance(raw, dict):
        if "$value" in raw:
            return str(raw.get("$value") or "").strip()
        nested = raw.get(key)
        if isinstance(nested, dict) and "$value" in nested:
            return str(nested.get("$value") or "").strip()
        for item in raw.values():
            if isinstance(item, dict) and "$value" in item:
                return str(item.get("$value") or "").strip()
            if item not in (None, "", [], {}):
                return str(item).strip()
        return ""
    if raw in (None, "", [], {}):
        shipping = values.get("shippingTemplate")
        if key == "shippingTemplateId" and isinstance(shipping, dict):
            return str(shipping.get("shippingTemplateId") or "").strip()
        return ""
    return str(raw).strip()


def summarize_values(values: Mapping[str, Any]) -> dict[str, str]:
    bits: dict[str, str] = {}
    for key in SUMMARY_KEYS:
        value = _flat_value(values, key)
        if value:
            bits[key] = value
    return bits


def _row_sample(row: Mapping[str, Any]) -> dict[str, Any]:
    attrs = {
        str(key): str(value).strip()
        for key, value in row.items()
        if str(key).startswith("attr.") and str(value or "").strip()
    }
    return {
        "line": row.get("line"),
        "sku": str(row.get("sku") or "").strip(),
        "name": str(row.get("name") or "").strip(),
        "price": str(row.get("price") or "").strip(),
        "moq": str(row.get("moq") or "").strip(),
        "brand": str(row.get("brand") or "").strip(),
        "note": str(row.get("note") or "").strip()[:240],
        "attributes": attrs,
    }


def _rule_pick(
    templates: Sequence[Template],
    rows: Sequence[Mapping[str, Any]],
) -> tuple[str, str, dict[str, str]]:
    """Score templates from row facts; fall back to newest."""
    if not templates:
        return "", "还没有匹配类目的刊登模板", {}
    if len(templates) == 1:
        return templates[0].id, "这个类目只有一个刊登模板", {}

    scores = {item.id: 0 for item in templates}
    for row in rows[:12]:
        sample = _row_sample(row)
        corpus = " ".join(
            part
            for part in (
                sample["name"],
                sample["note"],
                sample["brand"],
                " ".join(sample["attributes"].values()),
            )
            if part
        ).lower()
        moq = sample["moq"]
        for item in templates:
            summary = summarize_values(template_service.values_of(item))
            summary_text = " ".join(summary.values()).lower()
            if corpus and summary_text and any(token in corpus for token in summary_text.split() if len(token) > 3):
                scores[item.id] += 2
            if moq and summary.get("saleType"):
                scores[item.id] += 1
    best_id = max(scores, key=scores.get)
    if scores[best_id] <= 0:
        best_id = templates[0].id
        return best_id, "按最近使用的模板匹配（可在下方改选）", {}
    return best_id, "根据商品备注和模板习惯自动匹配（可在下方改选）", {}


def suggest(
    db: Session,
    shop: Shop,
    category_id: str,
    rows: Sequence[Mapping[str, Any]],
    *,
    category_name: str = "",
    ai: AiClient | None = None,
) -> dict[str, Any]:
    items = list_for_category(db, shop.id, category_id)
    payload_templates = [template_service.as_dict(item) for item in items]
    for item in payload_templates:
        item["summary"] = summarize_values(item.get("values") or {})

    if not payload_templates:
        return {
            "templates": [],
            "suggestion": {
                "template_id": "",
                "template_name": "",
                "reasoning": "还没有这个类目的刊登模板。可在「发品习惯 → 类目模板」新建，或从在线商品学习。",
                "source": "none",
                "confidence": "low",
            },
            "row_suggestions": [],
        }

    samples = [_row_sample(row) for row in rows[:8] if _row_sample(row).get("sku") or _row_sample(row).get("name")]
    suggestion: dict[str, Any]
    row_overrides: dict[str, str] = {}

    if len(payload_templates) == 1:
        only = payload_templates[0]
        suggestion = {
            "template_id": only["id"],
            "template_name": only["name"],
            "reasoning": "这个类目只有一个刊登模板，成稿时会自动套用。",
            "source": "single",
            "confidence": "high",
        }
    elif ai is not None and samples:
        compact = [
            {
                "id": item["id"],
                "name": item["name"],
                "is_auto": item.get("is_auto"),
                "summary": item.get("summary") or {},
            }
            for item in payload_templates
        ]
        prompt = PICK_PROMPT.format(
            category_name=category_name or category_id,
            category_id=category_id,
            templates=json.dumps(compact, ensure_ascii=False, indent=2),
            samples=json.dumps(samples, ensure_ascii=False, indent=2),
        )
        try:
            picked = ai.chat_json([{"role": "user", "content": prompt}], temperature=0.1)
            template_id = str(picked.get("template_id") or "").strip()
            allowed = {item["id"] for item in payload_templates}
            if template_id not in allowed:
                template_id, reasoning, row_overrides = _rule_pick(items, rows)
                source = "rule"
                confidence = "medium"
            else:
                reasoning = str(picked.get("reasoning") or "").strip() or "AI 已根据本批商品选定模板"
                source = "ai"
                confidence = str(picked.get("confidence") or "medium").strip() or "medium"
                overrides = picked.get("row_overrides") or {}
                if isinstance(overrides, dict):
                    row_overrides = {
                        str(sku).strip(): str(tid).strip()
                        for sku, tid in overrides.items()
                        if str(sku).strip() and str(tid).strip() in allowed
                    }
            by_id = {item["id"]: item["name"] for item in payload_templates}
            suggestion = {
                "template_id": template_id,
                "template_name": by_id.get(template_id, ""),
                "reasoning": reasoning,
                "source": source,
                "confidence": confidence,
            }
        except (AiUnavailable, json.JSONDecodeError, ValueError, TypeError):
            template_id, reasoning, row_overrides = _rule_pick(items, rows)
            by_id = {item["id"]: item["name"] for item in payload_templates}
            suggestion = {
                "template_id": template_id,
                "template_name": by_id.get(template_id, ""),
                "reasoning": reasoning,
                "source": "rule",
                "confidence": "medium",
            }
    else:
        template_id, reasoning, row_overrides = _rule_pick(items, rows)
        by_id = {item["id"]: item["name"] for item in payload_templates}
        suggestion = {
            "template_id": template_id,
            "template_name": by_id.get(template_id, ""),
            "reasoning": reasoning,
            "source": "rule",
            "confidence": "medium",
        }

    row_suggestions: list[dict[str, Any]] = []
    default_id = str(suggestion.get("template_id") or "")
    by_id = {item["id"]: item["name"] for item in payload_templates}
    for row in rows:
        sku = str(row.get("sku") or "").strip()
        line = int(row.get("line") or 0)
        override_id = row_overrides.get(sku) if sku else ""
        chosen = override_id or default_id
        if not chosen:
            continue
        if override_id:
            reason = f"AI 为 {sku or line} 行单独选了「{by_id.get(chosen, chosen)}」"
        else:
            reason = suggestion.get("reasoning") or ""
        row_suggestions.append(
            {
                "line": line,
                "sku": sku,
                "template_id": chosen,
                "template_name": by_id.get(chosen, ""),
                "reasoning": reason,
            }
        )
    return {
        "templates": payload_templates,
        "suggestion": suggestion,
        "row_suggestions": row_suggestions,
    }


def apply_row_suggestions(
    rows: list[dict[str, Any]],
    suggestion: Mapping[str, Any],
    row_suggestions: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Write `_template_id` / `_template_name` onto grid rows."""
    default_id = str(suggestion.get("template_id") or "").strip()
    default_name = str(suggestion.get("template_name") or "").strip()
    by_line = {int(item.get("line") or 0): item for item in row_suggestions if int(item.get("line") or 0)}
    by_sku = {str(item.get("sku") or "").strip(): item for item in row_suggestions if str(item.get("sku") or "").strip()}
    updated: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        line = int(item.get("line") or 0)
        sku = str(item.get("sku") or "").strip()
        pick = by_line.get(line) or (by_sku.get(sku) if sku else None)
        if pick:
            item["_template_id"] = str(pick.get("template_id") or default_id)
            item["_template_name"] = str(pick.get("template_name") or default_name)
            item["_template_reason"] = str(pick.get("reasoning") or suggestion.get("reasoning") or "")
        elif default_id:
            item["_template_id"] = default_id
            item["_template_name"] = default_name
            item["_template_reason"] = str(suggestion.get("reasoning") or "")
        updated.append(item)
    return updated
