"""Habits readiness: official options from schema.get, auto template, AI freight pick."""

from __future__ import annotations

import json
import logging
from typing import Any, Mapping, Sequence

from ai import AiClient, AiUnavailable
from sqlalchemy.orm import Session

from ..models import Shop, Template, User
from . import clone, defaults as defaults_service, template_suggest, templates as template_service
from .shop_client import shop_defaults

logger = logging.getLogger(__name__)

FREIGHT_PROMPT = """Pick one freight/shipping template for Alibaba.com wholesale listings.

Leaf category: {category_name} ({category_id})
Product context: {context}

Official options (pick exactly one id from this list):
{options}

Rules:
- Pick only from the list — never invent an id.
- Prefer templates whose name matches the product type (e.g. pencil → 画笔运费).
- If unsure, pick the one named like negotiated freight / 买卖双方协商物流.
- Return JSON only: {{"shipping_template_id": "...", "label": "...", "reasoning": "one short Chinese sentence", "confidence": "high|medium|low"}}
"""


def _filled(value: Any) -> bool:
    if value in (None, "", [], {}, ()):
        return False
    if isinstance(value, dict):
        if "$value" in value:
            return bool(str(value.get("$value") or "").strip())
        return any(_filled(item) for key, item in value.items() if key != "$attrs")
    return True


def _shipping_options(fields: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    for field in fields:
        if str(field.get("key") or "") == "shippingTemplateId":
            raw = field.get("options") or []
            return [
                {"value": str(item.get("value") or ""), "label": str(item.get("label") or item.get("value") or "")}
                for item in raw
                if str(item.get("value") or "").strip()
            ]
    return []


def _label_for_option(options: Sequence[Mapping[str, Any]], value: str) -> str:
    text = str(value or "").strip()
    for item in options:
        if str(item.get("value") or "") == text:
            return str(item.get("label") or text)
    return text


def _defaults_missing_shipping(defaults: Mapping[str, Any]) -> bool:
    value = str(defaults.get("shippingTemplateId") or "").strip()
    placeholders = defaults_service.PLACEHOLDERS.get("shippingTemplateId", {""})
    return not value or value in placeholders


def _find_listing_in_category(api: Any, category_id: str) -> tuple[str, str]:
    try:
        payload = api.list_products(1, 20, "onSelling")
    except Exception:
        return "", ""
    result = payload.get("result") if isinstance(payload, dict) else {}
    nested = result.get("product_list") if isinstance(result.get("product_list"), dict) else {}
    products = result.get("products")
    if not isinstance(products, list):
        products = nested.get("products") if isinstance(nested.get("products"), list) else []
    for item in products:
        if not isinstance(item, dict):
            continue
        product_id = str(item.get("product_id") or item.get("id") or "")
        cat = str(item.get("category_id") or "")
        if product_id and cat == str(category_id):
            return product_id, cat
    return "", ""


def _rule_pick_shipping(
    options: Sequence[Mapping[str, Any]],
    *,
    category_name: str = "",
    context: str = "",
) -> dict[str, str]:
    if not options:
        return {}
    corpus = f"{category_name} {context}".lower()
    for item in options:
        label = str(item.get("label") or "")
        if label and _best_label_token_match(label, corpus):
            return {
                "shipping_template_id": str(item["value"]),
                "label": label,
                "reasoning": f"根据品类/商品习惯匹配「{label}」",
                "confidence": "medium",
                "source": "rule",
            }
    for item in options:
        label = str(item.get("label") or "")
        if "协商" in label or "negotiat" in label.lower():
            return {
                "shipping_template_id": str(item["value"]),
                "label": label,
                "reasoning": "未明确匹配时默认用买卖双方协商物流",
                "confidence": "low",
                "source": "rule",
            }
    first = options[0]
    return {
        "shipping_template_id": str(first.get("value") or ""),
        "label": str(first.get("label") or first.get("value") or ""),
        "reasoning": "已选官方列表中的第一个运费模板",
        "confidence": "low",
        "source": "rule",
    }


def _best_label_token_match(label: str, corpus: str) -> bool:
    label_lower = label.lower()
    for token in ("铅笔", "画笔", "pencil", "colored", "彩铅"):
        if token in label_lower and token in corpus:
            return True
    return False


def recommend_shipping(
    ai: AiClient | None,
    options: Sequence[Mapping[str, Any]],
    *,
    category_id: str,
    category_name: str,
    context: str = "",
) -> dict[str, str]:
    if not options:
        return {}
    allowed = {str(item.get("value") or "") for item in options}
    if ai is not None:
        compact = [{"id": item.get("value"), "label": item.get("label")} for item in options]
        prompt = FREIGHT_PROMPT.format(
            category_name=category_name or category_id,
            category_id=category_id,
            context=context or "（暂无商品描述）",
            options=json.dumps(compact, ensure_ascii=False, indent=2),
        )
        try:
            picked = ai.chat_json([{"role": "user", "content": prompt}], temperature=0.1)
            tid = str(picked.get("shipping_template_id") or "").strip()
            if tid in allowed:
                return {
                    "shipping_template_id": tid,
                    "label": str(picked.get("label") or _label_for_option(options, tid)),
                    "reasoning": str(picked.get("reasoning") or "AI 已推荐运费模板").strip(),
                    "confidence": str(picked.get("confidence") or "medium").strip() or "medium",
                    "source": "ai",
                }
        except (AiUnavailable, ValueError, TypeError) as exc:
            logger.warning("freight AI fallback to rules: %s", exc)
    picked = _rule_pick_shipping(options, category_name=category_name, context=context)
    return picked


def ensure_category_template(
    db: Session,
    user: User | None,
    shop: Shop,
    api: Any,
    *,
    category_id: str,
    category_name: str,
    defaults: Mapping[str, Any],
    shipping_template_id: str = "",
) -> Template | None:
    """Ensure at least one listing template exists for this leaf category."""
    items = template_suggest.list_for_category(db, shop.id, category_id)
    if items:
        return items[0]

    if user is not None:
        product_id, cat = _find_listing_in_category(api, category_id)
        if product_id and cat:
            try:
                name = f"自动·{category_name or category_id}"
                return clone.learn_template(
                    db,
                    user,
                    shop,
                    product_id=product_id,
                    category_id=category_id,
                    name=name,
                )
            except Exception as exc:
                logger.warning("learn_template failed: %s", exc)

    if user is None:
        return None

    values: dict[str, Any] = {}
    for key in (
        "origin",
        "priceUnit",
        "saleType",
        "logisticsProperty",
        "marketSample",
        "paymentMethod",
        "port",
        "ladderPeriod",
        "pkgWeight",
        "pkgLength",
        "pkgWidth",
        "pkgHeight",
        "brand",
    ):
        raw = defaults.get(key)
        if _filled(raw):
            values[key] = raw
    if shipping_template_id:
        values["shippingTemplateId"] = shipping_template_id
        values["shippingTemplate"] = {"shippingTemplateId": shipping_template_id}

    row = Template(
        user_id=user.id,
        shop_id=shop.id,
        name=f"自动·{category_name or category_id}",
        category_id=category_id,
        values_json=json.dumps(values, ensure_ascii=False),
        is_auto=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def resolve_template_for_category(
    db: Session,
    shop: Shop,
    category_id: str,
    *,
    vision_summary: str = "",
    rows: Sequence[Mapping[str, Any]] | None = None,
    ai: AiClient | None = None,
    category_name: str = "",
) -> Template | None:
    items = template_suggest.list_for_category(db, shop.id, category_id)
    if not items:
        return None
    if len(items) == 1:
        return items[0]
    if rows:
        result = template_suggest.suggest(
            db,
            shop,
            category_id,
            list(rows),
            category_name=category_name,
            ai=ai,
        )
        tid = str((result.get("suggestion") or {}).get("template_id") or "").strip()
        if tid:
            row = db.get(Template, tid)
            if row is not None and row.shop_id == shop.id:
                return row
    return items[0]


def check_and_prepare(
    db: Session,
    api: Any,
    shop: Shop,
    user: User | None,
    *,
    category_id: str,
    category_name: str = "",
    ai: AiClient | None = None,
    vision_summary: str = "",
    vision_samples: Sequence[Mapping[str, Any]] | None = None,
    auto_fix: bool = True,
) -> dict[str, Any]:
    """Return habits payload; optionally auto-create template and recommend freight."""
    merged = dict(shop_defaults(shop))
    language = str(merged.get("language") or "en_US")

    try:
        view = defaults_service.options_view(
            db,
            api,
            shop,
            merged,
            category_id=category_id,
            language=language,
        )
    except Exception as exc:
        return {
            "status": "error",
            "ready": False,
            "error": str(exc),
            "checks": [],
            "shipping_options": [],
            "selected_template_id": "",
            "selected_template_name": "",
        }

    shipping_options = _shipping_options(view.get("fields") or [])
    context_parts = [vision_summary]
    for sample in vision_samples or []:
        context_parts.append(str(sample.get("product_name") or ""))
        context_parts.append(str(sample.get("material") or ""))
        context_parts.append(str(sample.get("usage") or ""))
    context = " ".join(part for part in context_parts if part).strip()

    recommendation = recommend_shipping(
        ai,
        shipping_options,
        category_id=category_id,
        category_name=category_name,
        context=context,
    )

    missing_shipping = _shipping_options and _defaults_missing_shipping(merged)
    current_shipping = str(merged.get("shippingTemplateId") or "").strip()
    if missing_shipping and recommendation.get("shipping_template_id"):
        recommended_id = str(recommendation["shipping_template_id"])
    else:
        recommended_id = current_shipping or str(recommendation.get("shipping_template_id") or "")

    template_row: Template | None = None
    if auto_fix and user is not None:
        template_row = ensure_category_template(
            db,
            user,
            shop,
            api,
            category_id=category_id,
            category_name=category_name,
            defaults=merged,
            shipping_template_id=recommended_id if missing_shipping else current_shipping,
        )
        if template_row is not None and missing_shipping and recommended_id:
            values = template_service.values_of(template_row)
            if not _filled(values.get("shippingTemplateId")) and not _filled(
                (values.get("shippingTemplate") or {}).get("shippingTemplateId")
                if isinstance(values.get("shippingTemplate"), dict)
                else None
            ):
                values["shippingTemplateId"] = recommended_id
                values["shippingTemplate"] = {"shippingTemplateId": recommended_id}
                template_row.values_json = json.dumps(values, ensure_ascii=False)
                db.commit()

    if template_row is None:
        template_row = resolve_template_for_category(
            db,
            shop,
            category_id,
            vision_summary=context,
            ai=ai,
            category_name=category_name,
        )

    checks: list[dict[str, Any]] = []
    checks.append(
        {
            "id": "origin",
            "label": "原产地",
            "ok": _filled(merged.get("origin")),
            "value": str(merged.get("origin") or ""),
            "source": "shop",
        }
    )
    checks.append(
        {
            "id": "priceUnit",
            "label": "计量单位",
            "ok": _filled(merged.get("priceUnit")),
            "value": str(merged.get("labels", {}).get("priceUnit") or merged.get("priceUnit") or ""),
            "source": "shop",
        }
    )
    checks.append(
        {
            "id": "logisticsProperty",
            "label": "物流属性",
            "ok": _filled(merged.get("logisticsProperty")),
            "value": str(merged.get("labels", {}).get("logisticsProperty") or merged.get("logisticsProperty") or ""),
            "source": "shop",
        }
    )

    shipping_ok = bool(current_shipping) or bool(recommended_id)
    checks.append(
        {
            "id": "shippingTemplateId",
            "label": "运费模板",
            "ok": shipping_ok,
            "value": _label_for_option(shipping_options, current_shipping)
            if current_shipping
            else str(recommendation.get("label") or ""),
            "source": "shop" if current_shipping else str(recommendation.get("source") or "recommend"),
            "needs_pick": missing_shipping,
        }
    )

    template_ok = template_row is not None
    checks.append(
        {
            "id": "listing_template",
            "label": "类目刊登模板",
            "ok": template_ok,
            "value": template_row.name if template_row else "",
            "source": "auto" if template_row and template_row.is_auto else "shop",
        }
    )

    needs_pick = missing_shipping and bool(recommendation.get("shipping_template_id"))
    ready = all(item.get("ok") for item in checks if item.get("id") != "shippingTemplateId") and (
        not needs_pick or bool(recommended_id)
    )
    status = "ready" if ready and not needs_pick else ("needs_pick" if needs_pick else "ready")

    return {
        "status": status,
        "ready": ready and not needs_pick,
        "checks": checks,
        "shipping_options": list(shipping_options),
        "shipping_recommendation": recommendation,
        "recommended_shipping_template_id": recommended_id,
        "selected_template_id": template_row.id if template_row else "",
        "selected_template_name": template_row.name if template_row else "",
        "selected_template_is_auto": bool(template_row.is_auto) if template_row else False,
        "category_id": category_id,
        "category_name": category_name or view.get("category_name") or category_id,
    }


def apply_habits(
    db: Session,
    shop: Shop,
    *,
    category_id: str,
    shipping_template_id: str = "",
    template_id: str = "",
    apply_shipping_to: str = "shop",
) -> dict[str, Any]:
    """Persist user-adopted freight template to shop defaults and/or category template."""
    tid = str(shipping_template_id or "").strip()
    target = str(apply_shipping_to or "shop").strip().lower()
    updated: list[str] = []

    if tid:
        if target in {"shop", "both"}:
            current = dict(shop_defaults(shop))
            current["shippingTemplateId"] = tid
            defaults_service.mark_user_keys(current, ["shippingTemplateId"])
            shop.defaults_json = json.dumps(current, ensure_ascii=False)
            updated.append("shop.shippingTemplateId")
        if target in {"template", "both"} and category_id:
            row = None
            if template_id:
                row = db.get(Template, template_id)
            if row is None:
                row = template_service.find_for(db, shop.id, category_id)
            if row is not None and row.shop_id == shop.id:
                values = template_service.values_of(row)
                values["shippingTemplateId"] = tid
                values["shippingTemplate"] = {"shippingTemplateId": tid}
                row.values_json = json.dumps(values, ensure_ascii=False)
                updated.append("template.shippingTemplateId")

    db.commit()
    return {"ok": True, "updated": updated}


def attach_to_plan(
    db: Session,
    api: Any,
    shop: Shop,
    user: User | None,
    plan: dict[str, Any],
    *,
    ai: AiClient | None = None,
    auto_fix: bool = True,
) -> dict[str, Any]:
    category_id = str(plan.get("category_id") or "")
    category_name = str(plan.get("category_name") or "")
    habits = check_and_prepare(
        db,
        api,
        shop,
        user,
        category_id=category_id,
        category_name=category_name,
        ai=ai,
        vision_summary=str(plan.get("vision_summary") or ""),
        vision_samples=plan.get("vision_samples") or [],
        auto_fix=auto_fix,
    )
    plan["habits"] = habits
    plan["selected_template_id"] = habits.get("selected_template_id") or ""
    plan["selected_template_name"] = habits.get("selected_template_name") or ""
    return plan
