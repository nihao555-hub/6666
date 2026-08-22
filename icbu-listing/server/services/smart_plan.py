"""Smart batch listing: decide minimal user columns, then build a tailored XLSX.

Flow:
1. Pull leaf schema (required + score-relevant optional fields).
2. Subtract what the shop defaults and category template already cover.
3. Ask the LLM which remaining fields sellers must type per SKU.
4. Build a download sheet + reuse the same columns for parse / grid / import.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from ai import AiClient, AiUnavailable  # noqa: E402
from schema import SchemaField, index_fields, parse_schema  # noqa: E402
from sqlalchemy.orm import Session

from ..models import CategorySmartPlan, Shop
from . import catalog, defaults as defaults_service, excel_import, schema_labels, templates as template_service
from .icbu_publishing_skill import checklist_for_review, skill_prompt_block
from .review_enrich import schema_inventory_summary
from .excel_import import SKIP_ATTR_IDS, USER_FILLS

CORE_IDS = ("sku", "price", "moq")
CORE_OPTIONAL = ("images", "brand", "name", "note")

# Optional schema fields that affect the local 5.0 quality score when present.
SCORE_OPTIONAL_TOP = (
    "paymentMethod",
    "port",
    "ladderPeriod",
    "shippingTemplate",
    "logisticsProperty",
    "pkgWeight",
    "pkgMeasure",
    "marketSample",
    "priceUnit",
    "saleType",
)

PLANNER_PROMPT = """You plan a minimal wholesale listing spreadsheet for Alibaba.com (ICBU).

Goal: the seller fills ONLY facts they know per SKU. After upload, AI must be able to
fill every remaining official REQUIRED field and quality-relevant OPTIONAL field that
has evidence in name/note/images/specs — never guess.

Business goal: attract qualified wholesale buyers (inquiry-ready search language), not
generic traffic. User columns should capture facts that unlock good titles, keywords,
and attribute inference later.

Leaf category: {category_name} ({category_id})

Step 1 — full official schema inventory (every fillable field name; required list is complete):
{schema_inventory}

Step 2 — already covered by this shop's defaults or category listing template (seller must NOT re-type):
{covered}

Shop/category template values summary (for your reasoning only):
{template_summary}

Step 3 — candidate columns the seller might still need per SKU (pre-filtered shortlist with options):
{candidates}

Fields AI will complete AFTER upload (do NOT put in user_columns unless seller must supply source text):
{ai_completes}

Hard rules:
- Always include sku, price, moq in user_columns.
- Almost always include name and note — they are evidence for AI title/keywords/attrs.
- Include images when sellers attach filenames or URLs in bulk sheets.
- Include every official REQUIRED attribute not covered by shop/template when the seller must pick per SKU.
- Include optional columns only when facts typically vary per SKU and cannot be inferred from note/photos.
- Do NOT include productTitle/productKeywords/textDesc in user_columns (review stage handles copy).
- Prefer fewer columns; never ask for logistics/trade fields already in shop defaults or template.

Title/keyword guidance (for reasoning only): Core Product + Type + Performance + Scene + OEM — inquiry-qualified B2B search terms.

Publishing skill rules:
{skill_rules}

Return JSON only:
{{
  "user_columns": ["sku", "price", "moq", "name", "note", ...],
  "reasoning": "one short Chinese paragraph: what you kept vs what shop/template/AI covers",
  "tips": "one sentence telling the seller what to prepare (报价单/规格/图片命名)"
}}
"""


def _filled(value: Any) -> bool:
    if value in (None, "", [], {}, ()):
        return False
    if isinstance(value, dict):
        if "$value" in value:
            return bool(str(value.get("$value") or "").strip())
        return any(_filled(item) for key, item in value.items() if key != "$attrs")
    return True


def _habits_fingerprint(shop_defaults: Mapping[str, Any], template_values: Mapping[str, Any]) -> str:
    blob = json.dumps(
        {"shop": shop_defaults, "template": template_values},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _template_summary(template_values: Mapping[str, Any]) -> dict[str, str]:
    from . import template_suggest

    return template_suggest.summarize_values(template_values)


def _ai_completes_block(
    *,
    covered_shop: Sequence[str],
    covered_template: Sequence[str],
    schema_inventory: Mapping[str, Any],
) -> str:
    lines = [
        "productTitle, productKeywords, highlights (review stage, B2B inquiry-oriented copy)",
        "remaining required attrs when name/note/images give unambiguous option match",
        "score-relevant optional attrs with evidence in note or specs",
    ]
    if covered_shop or covered_template:
        lines.append(f"trade/logistics already from shop/template: {', '.join([*covered_shop, *covered_template][:12])}")
    req = schema_inventory.get("required_count") or 0
    lines.append(f"official required fields in schema: {req}")
    return json.dumps(lines, ensure_ascii=False)


def _try_fast_cached_plan(
    db: Session,
    shop_id: str,
    category_id: str,
    *,
    category_name: str,
    habits_fp: str,
    refresh: bool,
) -> dict[str, Any] | None:
    """Return cached plan without fetching schema or calling LLM."""
    if refresh:
        return None
    row = db.get(CategorySmartPlan, {"shop_id": shop_id, "category_id": category_id})
    if row is None:
        return None
    try:
        payload = json.loads(row.plan_json or "{}")
    except json.JSONDecodeError:
        return None
    if not payload.get("columns"):
        return None
    stored_fp = str(payload.get("habits_fingerprint") or "")
    if stored_fp and stored_fp != habits_fp:
        return None
    payload["cached"] = True
    payload["planner"] = row.planner or payload.get("planner") or "rules"
    if category_name and not payload.get("category_name"):
        payload["category_name"] = category_name
    return payload


def _shop_defaults(shop: Shop) -> dict[str, Any]:
    try:
        payload = json.loads(shop.defaults_json or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _template_values(db: Session, shop_id: str, category_id: str) -> dict[str, Any]:
    row = template_service.find_for(db, shop_id, category_id)
    if row is None:
        return {}
    return template_service.values_of(row)


def _shop_covers_attr(defaults: Mapping[str, Any], group_id: str, field_id: str) -> bool:
    if field_id in SKIP_ATTR_IDS:
        return _filled(defaults.get("origin"))
    if group_id == "icbuCatProp" and field_id in SKIP_ATTR_IDS:
        return _filled(defaults.get("origin"))
    return False


def _template_covers_attr(template: Mapping[str, Any], group_id: str, field_id: str) -> bool:
    group = template.get(group_id)
    if not isinstance(group, dict):
        return False
    return _filled(group.get(field_id))


def _shop_covers_top(defaults: Mapping[str, Any], field_id: str) -> bool:
    key_map = {
        "shippingTemplate": "shippingTemplateId",
        "shippingTemplate.shippingTemplateId": "shippingTemplateId",
    }
    key = key_map.get(field_id, field_id)
    value = defaults.get(key)
    if not _filled(value):
        return False
    placeholders = defaults_service.PLACEHOLDERS.get(key, set())
    return str(value).strip() not in placeholders


def _template_covers_top(template: Mapping[str, Any], field_id: str) -> bool:
    if field_id == "shippingTemplate":
        nested = template.get("shippingTemplate")
        if isinstance(nested, dict):
            return _filled(nested.get("shippingTemplateId"))
        return _filled(template.get("shippingTemplateId"))
    return _filled(template.get(field_id))


def _core_column(field_id: str) -> dict[str, Any]:
    spec = next((item for item in USER_FILLS if item["id"] == field_id), None)
    label = str((spec or {}).get("label") or field_id)
    hint = str((spec or {}).get("hint") or "")
    required = field_id in CORE_IDS or bool((spec or {}).get("required"))
    return {
        "id": field_id,
        "header": label,
        "label": label,
        "required": required,
        "hint": hint,
        "kind": "text",
        "source": "core",
        "options": [],
    }


def _attr_column(group_id: str, group_name: str, child: SchemaField, *, required: bool) -> dict[str, Any]:
    options = [
        {"value": option.value, "label": option.display_name}
        for option in (child.options or [])[:80]
    ]
    header = schema_labels.header_label(group_id, group_name, child.id, child.name or child.id)
    label = schema_labels.field_label(child.id, child.name or child.id)
    field_id = f"attr.{group_id}.{child.id}"
    return {
        "id": field_id,
        "header": header,
        "label": label,
        "group": group_id,
        "field_id": child.id,
        "required": required,
        "hint": "官方必填，按选项选" if required else "影响信息分，按选项选",
        "kind": "select" if options else "text",
        "source": "schema_required" if required else "schema_score",
        "options": options,
    }


def _top_column(spec: SchemaField, *, required: bool) -> dict[str, Any]:
    options = [{"value": option.value, "label": option.display_name} for option in (spec.options or [])[:80]]
    label = str(spec.name or spec.id)
    return {
        "id": f"schema.{spec.id}",
        "header": label,
        "label": label,
        "group": spec.id,
        "field_id": spec.id,
        "required": required,
        "hint": "官方字段，按选项选" if options else "跟货走的规格",
        "kind": "select" if options else "text",
        "source": "schema_score",
        "options": options,
    }


def candidate_columns(
    fields: Sequence[SchemaField],
    *,
    shop_defaults: Mapping[str, Any],
    template_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Build candidate user columns and what shop/template already cover."""
    specs = index_fields(fields)
    candidates: list[dict[str, Any]] = [_core_column(field_id) for field_id in CORE_IDS]
    candidates.extend(_core_column(field_id) for field_id in CORE_OPTIONAL)

    covered_shop: list[str] = []
    covered_template: list[str] = []

    for group_id in ("icbuCatProp", "saleProp"):
        group = specs.get(group_id)
        if group is None:
            continue
        group_name = str(group.name or group_id)
        for child in group.children or []:
            if child.type == "label":
                continue
            if child.id in SKIP_ATTR_IDS:
                if _shop_covers_attr(shop_defaults, group_id, child.id):
                    covered_shop.append(f"{group_name}/{child.name or child.id}")
                elif _template_covers_attr(template_values, group_id, child.id):
                    covered_template.append(f"{group_name}/{child.name or child.id}")
                continue
            required = bool(child.required)
            if not required:
                continue
            if _template_covers_attr(template_values, group_id, child.id):
                covered_template.append(f"{group_name}/{child.name or child.id}")
                continue
            if _shop_covers_attr(shop_defaults, group_id, child.id):
                covered_shop.append(f"{group_name}/{child.name or child.id}")
                continue
            candidates.append(_attr_column(group_id, group_name, child, required=True))

    for field_id in SCORE_OPTIONAL_TOP:
        spec = specs.get(field_id)
        if spec is None or spec.type == "label":
            continue
        label = str(spec.name or field_id)
        if _template_covers_top(template_values, field_id):
            covered_template.append(label)
            continue
        if _shop_covers_top(shop_defaults, field_id):
            covered_shop.append(label)
            continue
        candidates.append(_top_column(spec, required=False))

    return candidates, covered_shop, covered_template


def _rule_based_user_columns(candidates: Sequence[Mapping[str, Any]]) -> list[str]:
    chosen = list(CORE_IDS)
    for col in candidates:
        field_id = str(col["id"])
        if field_id in chosen:
            continue
        if field_id in CORE_OPTIONAL:
            if field_id in {"name", "note", "images"}:
                chosen.append(field_id)
            continue
        if col.get("required") or col.get("source") == "schema_required":
            chosen.append(field_id)
    return chosen


def _llm_user_columns(
    ai: AiClient,
    *,
    category_id: str,
    category_name: str,
    candidates: Sequence[Mapping[str, Any]],
    covered_shop: Sequence[str],
    covered_template: Sequence[str],
    schema_inventory: Mapping[str, Any],
    template_summary: Mapping[str, str],
    ai_completes: str,
) -> tuple[list[str], str, str]:
    compact = []
    for col in candidates:
        bit = {
            "id": col["id"],
            "label": col.get("label") or col["id"],
            "required": bool(col.get("required")),
            "source": col.get("source") or "",
        }
        options = col.get("options") or []
        if options:
            bit["options"] = [str(item.get("label") or item.get("value") or "") for item in options[:8]]
        compact.append(bit)
    prompt = PLANNER_PROMPT.format(
        category_name=category_name or category_id,
        category_id=category_id,
        schema_inventory=json.dumps(schema_inventory, ensure_ascii=False),
        covered=json.dumps(
            {"shop": list(covered_shop), "template": list(covered_template)},
            ensure_ascii=False,
        ),
        template_summary=json.dumps(template_summary, ensure_ascii=False),
        ai_completes=ai_completes,
        candidates=json.dumps(compact, ensure_ascii=False),
        skill_rules=skill_prompt_block(),
    )
    payload = ai.chat_json([{"role": "user", "content": prompt}], temperature=0.1)
    raw_ids = payload.get("user_columns") or []
    chosen: list[str] = []
    allowed = {str(col["id"]) for col in candidates}
    for item in raw_ids:
        field_id = str(item or "").strip()
        if field_id in allowed and field_id not in chosen:
            chosen.append(field_id)
    for required in CORE_IDS:
        if required not in chosen:
            chosen.insert(0, required)
    reasoning = str(payload.get("reasoning") or "").strip()
    tips = str(payload.get("tips") or "").strip()
    return chosen, reasoning, tips


def columns_for_ids(candidates: Sequence[Mapping[str, Any]], user_ids: Sequence[str]) -> list[dict[str, Any]]:
    by_id = {str(col["id"]): dict(col) for col in candidates}
    ordered: list[dict[str, Any]] = []
    for field_id in user_ids:
        col = by_id.get(field_id)
        if col is not None:
            ordered.append(col)
    return ordered


def _plan_input_hash(
    schema_xml: str,
    shop_defaults: Mapping[str, Any],
    template_values: Mapping[str, Any],
) -> str:
    blob = json.dumps(
        {
            "schema": hashlib.sha256(schema_xml.encode("utf-8", errors="replace")).hexdigest(),
            "defaults": shop_defaults,
            "template": template_values,
        },
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def _load_cached_plan(db: Session, shop_id: str, category_id: str, input_hash: str) -> dict[str, Any] | None:
    row = db.get(CategorySmartPlan, {"shop_id": shop_id, "category_id": category_id})
    if row is None or row.input_hash != input_hash:
        return None
    try:
        payload = json.loads(row.plan_json or "{}")
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or not payload.get("columns"):
        return None
    payload["cached"] = True
    payload["planner"] = row.planner or payload.get("planner") or "rules"
    return payload


def _save_cached_plan(
    db: Session,
    shop_id: str,
    category_id: str,
    input_hash: str,
    planner: str,
    plan: Mapping[str, Any],
) -> None:
    stored = {key: value for key, value in plan.items() if key != "cached"}
    row = db.get(CategorySmartPlan, {"shop_id": shop_id, "category_id": category_id})
    payload = json.dumps(stored, ensure_ascii=False)
    if row is None:
        db.add(
            CategorySmartPlan(
                shop_id=shop_id,
                category_id=category_id,
                input_hash=input_hash,
                planner=planner,
                plan_json=payload,
            )
        )
    else:
        row.input_hash = input_hash
        row.planner = planner
        row.plan_json = payload
    try:
        db.commit()
    except Exception:
        db.rollback()


def build_plan(
    db: Session,
    api: Any,
    shop: Shop,
    *,
    category_id: str,
    category_name: str = "",
    ai: AiClient | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    if not category_id:
        raise ValueError("先选叶子类目")
    shop_defaults = _shop_defaults(shop)
    template_values = _template_values(db, shop.id, category_id)
    habits_fp = _habits_fingerprint(shop_defaults, template_values)
    if not refresh:
        fast = _try_fast_cached_plan(
            db,
            shop.id,
            category_id,
            category_name=category_name,
            habits_fp=habits_fp,
            refresh=refresh,
        )
        if fast is not None:
            return fast
    xml = catalog.get_schema_xml(db, api, category_id, "zh")
    fields = parse_schema(xml)
    fields_flat = excel_import.flatten_schema_fields(fields)
    schema_inventory = schema_inventory_summary(fields_flat)
    input_hash = _plan_input_hash(xml, shop_defaults, template_values)
    if not refresh:
        cached = _load_cached_plan(db, shop.id, category_id, input_hash)
        if cached is not None:
            if category_name and not cached.get("category_name"):
                cached["category_name"] = category_name
            return cached
    candidates, covered_shop, covered_template = candidate_columns(
        fields,
        shop_defaults=shop_defaults,
        template_values=template_values,
    )
    planner = "rules"
    reasoning = "按官方必填项和店铺/模板覆盖情况生成最短填写表。"
    tips = "每行一个 SKU。价格、起订量必填；有报价单可直接上传，不必手填每一列。"
    template_summary = _template_summary(template_values)
    ai_completes = _ai_completes_block(
        covered_shop=covered_shop,
        covered_template=covered_template,
        schema_inventory=schema_inventory,
    )
    user_ids = _rule_based_user_columns(candidates)
    if ai is not None:
        try:
            user_ids, reasoning, tips = _llm_user_columns(
                ai,
                category_id=category_id,
                category_name=category_name,
                candidates=candidates,
                covered_shop=covered_shop,
                covered_template=covered_template,
                schema_inventory=schema_inventory,
                template_summary=template_summary,
                ai_completes=ai_completes,
            )
            planner = "llm"
        except AiUnavailable:
            planner = "rules"
    columns = columns_for_ids(candidates, user_ids)
    ai_fills = [
        {"id": "productTitle", "label": "英文标题"},
        {"id": "productKeywords", "label": "关键词"},
        {"id": "textDesc", "label": "详描"},
        {"id": "superText", "label": "详描/FAQ"},
    ]
    required_attrs = [col for col in columns if str(col.get("id", "")).startswith("attr.") and col.get("required")]
    optional_user = [col for col in columns if col["id"] in CORE_OPTIONAL or col.get("source") == "schema_score"]
    plan = {
        "category_id": category_id,
        "category_name": category_name,
        "planner": planner,
        "reasoning": reasoning,
        "tips": tips,
        "schema_inventory": schema_inventory,
        "download_columns": columns,
        "columns": columns,
        "column_count": len(columns),
        "required_attr_count": len(required_attrs),
        "covered_by_shop": covered_shop,
        "covered_by_template": covered_template,
        "shop_fills": [dict(item) for item in excel_import.SHOP_FILLS],
        "ai_fills": ai_fills,
        "guarantee": excel_import.fill_policy([], {"attr_columns": required_attrs})["guarantee"],
        "review_note": "标题/关键词/卖点在审核表前几列由 AI 预填，可手改；下载表只填事实字段。",
        "review_checklist": checklist_for_review(),
        "publishing_skill": "aidi1723/alibaba-icbu-publishing-skill",
        "planner_input": {
            "schema_fields_sent": schema_inventory.get("total", 0),
            "required_fields_sent": schema_inventory.get("required_count", 0),
            "optional_fields_sent": schema_inventory.get("optional_count", 0),
            "candidate_columns_sent": len(candidates),
            "mode": "llm reads full field-name inventory + candidate shortlist with options",
        },
        "habits_fingerprint": habits_fp,
        "cached": False,
    }
    _save_cached_plan(db, shop.id, category_id, input_hash, planner, plan)
    return plan


def expand_audit_columns(
    db: Session,
    api: Any,
    shop: Shop,
    category_id: str,
    plan_columns: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Add AI-fill schema columns to the review grid (not on the download sheet)."""
    from . import review_enrich

    if not category_id:
        return review_enrich.order_review_columns(plan_columns)
    try:
        xml = catalog.get_schema_xml(db, api, category_id, "zh")
        fields = parse_schema(xml)
        shop_defaults = _shop_defaults(shop)
        template_values = _template_values(db, shop.id, category_id)
        candidates, _, _ = candidate_columns(
            fields,
            shop_defaults=shop_defaults,
            template_values=template_values,
        )
        user_ids = {str(col.get("id") or "") for col in plan_columns if col.get("id")}
        ai_targets = review_enrich.ai_target_columns(candidates, user_ids)
        return review_enrich.audit_columns(plan_columns, ai_targets)
    except Exception:
        return review_enrich.order_review_columns(plan_columns)


def build_smart_template_bytes(plan: Mapping[str, Any]) -> bytes:
    columns = list(plan.get("columns") or [])
    category_id = str(plan.get("category_id") or "")
    category_name = str(plan.get("category_name") or category_id)
    return excel_import.build_smart_template(
        columns,
        category_id=category_id,
        category_name=category_name,
        plan_summary={
            "reasoning": plan.get("reasoning") or "",
            "tips": plan.get("tips") or "",
            "covered_by_shop": plan.get("covered_by_shop") or [],
            "covered_by_template": plan.get("covered_by_template") or [],
            "ai_fills": plan.get("ai_fills") or [],
        },
    )
