"""Smart batch listing: sufficient evidence sheet → AI infers remaining required fields.

Flow:
1. Pull leaf schema (required + score-relevant optional fields).
2. Subtract shop defaults / category template coverage.
3. Download sheet = redlines + every fact the seller MUST provide — including
   required attrs that cannot be inferred — such that after upload the LLM can
   high-confidence infer ALL remaining official required fields.
4. After upload, AI reads filled cells and infers remaining required + score optionals.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from typing import Any, Mapping, Sequence

from ai import AiClient, AiUnavailable  # noqa: E402
from schema import SchemaField, index_fields, parse_schema  # noqa: E402
from sqlalchemy.orm import Session

from ..db import persist_database
from ..models import CategorySmartPlan, Shop, Template
from . import catalog, defaults as defaults_service, excel_import, schema_labels, templates as template_service
from .icbu_publishing_skill import checklist_for_review, skill_prompt_block
from .review_enrich import schema_inventory_summary, ai_target_columns
from .excel_import import SKIP_ATTR_IDS, USER_FILLS
from . import vision_plan

CORE_IDS = ("sku", "price", "moq")
CORE_OPTIONAL = ("images", "brand", "name", "note")
CORE_ALL = frozenset(CORE_IDS) | frozenset(CORE_OPTIONAL)

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

PLANNER_VERSION = "evidence-sufficient-v4"
PLANNER_LLM_TIMEOUT = float(os.environ.get("PLANNER_LLM_TIMEOUT", "28"))

logger = logging.getLogger(__name__)

MAX_EVIDENCE_ATTRS = 6
RULE_EVIDENCE_ATTRS = 3
MAX_USER_MUST_PROVIDE_ATTRS = 10

# Higher = better primary evidence anchor (seller-known facts that determine other attrs).
_ANCHOR_PRIORITY: list[tuple[re.Pattern[str], int]] = [
    (re.compile(r"材质|材料|material", re.I), 100),
    (re.compile(r"类型|type|款式|style", re.I), 90),
    (re.compile(r"色数|color count|pieces|支数", re.I), 85),
    (re.compile(r"型号|model", re.I), 80),
    (re.compile(r"规格|尺寸|size|capacity", re.I), 70),
    (re.compile(r"颜色|color", re.I), 60),
    (re.compile(r"硬度|hardness", re.I), 50),
]

PLANNER_PROMPT = """You plan a wholesale listing spreadsheet for Alibaba.com (ICBU).

Goal: user_columns = the set of per-SKU facts the seller MUST type so that, after upload,
the LLM can high-confidence infer ALL remaining official REQUIRED attributes.

Download sheet (user_columns) MUST contain:
- sku, price, moq, name, note, images (always)
- Every official REQUIRED attr (attr.*) the seller must physically provide because it
  cannot be inferred from other columns — e.g. free-text specs, unique identifiers.
- PLUS 2–6 PRIMARY evidence attrs the seller knows (material, product type, color count…)
  that together give the LLM enough context to infer the other required dropdown attrs.

Do NOT shrink the sheet for brevity. Omit a required attr from user_columns ONLY when
the chosen evidence columns + name/note/images make that attr deducible with high confidence.

Download sheet MUST NOT contain:
- productTitle, productKeywords, textDesc (AI review stage)
- quality-score OPTIONAL fields (schema.* — AI fills after upload when supported)
- logistics/trade fields already in shop defaults or template

After upload AI completes (must NOT be in user_columns):
{ai_completes}

Leaf category: {category_name} ({category_id})

Official schema inventory:
{schema_inventory}

Already covered by shop defaults or listing template:
{covered}

Template summary (reasoning only):
{template_summary}

Candidate columns (required attrs marked required=true; options truncated):
{candidates}

Product vision from seller's uploaded photos (attrs already resolved by vision — omit from user_columns):
{product_vision}

Hard rules:
- Sufficiency over brevity: together user_columns must enable inferring ALL remaining required attrs.
- Include any required attr the seller must type because vision/other columns cannot infer it.
- Never include schema_score / schema.* in user_columns.
- Never guess price, MOQ, brand, origin.

Publishing skill rules:
{skill_rules}

Return JSON only:
{{
  "user_columns": ["sku", "price", "moq", "name", "note", "images", "attr....", ...],
  "reasoning": "one short Chinese paragraph: what seller must provide vs what AI will infer",
  "tips": "one sentence: what to prepare per SKU"
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
        "productTitle, productKeywords, highlights, textDesc (English copy)",
        "remaining official REQUIRED attrs not on the download sheet — infer from user-provided evidence",
        "quality-score OPTIONAL attrs (schema.*) — infer from user evidence when supported",
    ]
    if covered_shop or covered_template:
        lines.append(f"trade/logistics already from shop/template: {', '.join([*covered_shop, *covered_template][:12])}")
    req = schema_inventory.get("required_count") or 0
    lines.append(f"official required fields in schema: {req}")
    return json.dumps(lines, ensure_ascii=False)


def _cached_plan_payload(row: CategorySmartPlan, *, category_name: str = "") -> dict[str, Any] | None:
    try:
        payload = json.loads(row.plan_json or "{}")
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or not payload.get("columns"):
        return None
    payload["cached"] = True
    payload["planner"] = row.planner or payload.get("planner") or "rules"
    if category_name and not payload.get("category_name"):
        payload["category_name"] = category_name
    return payload


def _is_core_only_plan(plan: Mapping[str, Any]) -> bool:
    """True when the download sheet has no category evidence attrs (likely stale cache)."""
    cols = plan.get("columns") or plan.get("download_columns") or []
    ids = [str(col.get("id") or "") for col in cols if col.get("id")]
    if not ids:
        return True
    return all(fid in CORE_ALL for fid in ids)


def _try_fast_cached_plan(
    db: Session,
    shop_id: str,
    category_id: str,
    *,
    category_name: str,
    refresh: bool,
) -> dict[str, Any] | None:
    """Return cached plan without fetching schema or calling LLM."""
    if refresh:
        return None
    row = db.get(CategorySmartPlan, {"shop_id": shop_id, "category_id": category_id})
    if row is None:
        return None
    payload = _cached_plan_payload(row, category_name=category_name)
    if payload is None or _is_core_only_plan(payload):
        return None
    return payload


def _try_user_category_cached_plan(
    db: Session,
    user_id: str,
    shop_id: str,
    category_id: str,
    *,
    category_name: str,
    refresh: bool,
) -> dict[str, Any] | None:
    """Reuse a plan from another shop when the same leaf category was planned before."""
    if refresh:
        return None
    row = (
        db.query(CategorySmartPlan)
        .join(Shop, Shop.id == CategorySmartPlan.shop_id)
        .filter(Shop.user_id == user_id, CategorySmartPlan.category_id == category_id, CategorySmartPlan.shop_id != shop_id)
        .order_by(CategorySmartPlan.updated_at.desc())
        .first()
    )
    if row is None:
        return None
    payload = _cached_plan_payload(row, category_name=category_name)
    if payload is None or _is_core_only_plan(payload):
        return None
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
        "hint": "官方必填，上传后 AI 也会读此列" if required else "影响信息分，按选项选",
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


def _is_score_column(col: Mapping[str, Any]) -> bool:
    col_id = str(col.get("id") or "")
    source = str(col.get("source") or "")
    return col_id.startswith("schema.") or source == "schema_score"


def _is_required_attr_column(col: Mapping[str, Any]) -> bool:
    col_id = str(col.get("id") or "")
    return bool(col.get("required")) and col_id.startswith("attr.")


def _anchor_priority(col: Mapping[str, Any]) -> int:
    if not _is_required_attr_column(col):
        return -1
    label = str(col.get("label") or col.get("header") or "")
    score = 1
    for pattern, pts in _ANCHOR_PRIORITY:
        if pattern.search(label):
            score = max(score, pts)
    return score


def _is_evidence_anchor(col: Mapping[str, Any]) -> bool:
    return _anchor_priority(col) > 0


def _evidence_anchor_ids(
    candidates: Sequence[Mapping[str, Any]],
    *,
    limit: int = RULE_EVIDENCE_ATTRS,
) -> list[str]:
    """Pick top primary required attrs; remaining required attrs go to AI infer."""
    ranked: list[tuple[int, str]] = []
    for col in candidates:
        score = _anchor_priority(col)
        if score > 0:
            ranked.append((score, str(col["id"])))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    anchors = [fid for _, fid in ranked[: max(1, limit)]]
    if not anchors:
        for col in candidates:
            if _is_required_attr_column(col):
                anchors.append(str(col["id"]))
            if len(anchors) >= 2:
                break
    return anchors[:MAX_EVIDENCE_ATTRS]


def _user_evidence_column_ids(
    candidates: Sequence[Mapping[str, Any]],
    *,
    vision_covered: set[str],
) -> list[str]:
    """Attrs the seller must type: primary evidence + required fields AI cannot infer."""
    anchors = [fid for fid in _evidence_anchor_ids(candidates) if fid not in vision_covered]
    must: list[str] = []
    seen: set[str] = set()
    for fid in anchors:
        if fid not in seen:
            must.append(fid)
            seen.add(fid)
    for col in candidates:
        if not _is_required_attr_column(col):
            continue
        cid = str(col["id"])
        if cid in vision_covered or cid in seen:
            continue
        options = col.get("options") or []
        # Freeform required — seller must provide; LLM cannot infer without it.
        if not options:
            must.append(cid)
            seen.add(cid)
            continue
        # Required attr with no anchor signal — treat as must-provide unless already covered.
        if _anchor_priority(col) <= 0:
            must.append(cid)
            seen.add(cid)
    return must[:MAX_USER_MUST_PROVIDE_ATTRS]


def _sanitize_user_column_ids(
    candidates: Sequence[Mapping[str, Any]],
    user_ids: Sequence[str],
) -> list[str]:
    """Download sheet: core + required evidence attrs only — never score optionals."""
    allowed = {str(col["id"]) for col in candidates if col.get("id")}
    required_attrs = {str(col["id"]) for col in candidates if _is_required_attr_column(col)}
    score_ids = {str(col["id"]) for col in candidates if _is_score_column(col)}
    core = set(CORE_IDS) | set(CORE_OPTIONAL)
    ordered: list[str] = []
    for field_id in user_ids:
        fid = str(field_id or "").strip()
        if not fid or fid not in allowed or fid in score_ids:
            continue
        if fid in core or fid in required_attrs:
            if fid not in ordered:
                ordered.append(fid)
    return ordered


def _rule_based_user_columns(
    candidates: Sequence[Mapping[str, Any]],
    *,
    vision_samples: Sequence[Mapping[str, Any]] | None = None,
) -> list[str]:
    """Sufficient evidence sheet: redlines + attrs seller must provide for LLM to infer the rest."""
    chosen: list[str] = list(CORE_IDS)
    for field_id in CORE_OPTIONAL:
        if field_id not in chosen:
            chosen.append(field_id)
    vision_covered = vision_plan.attr_ids_covered_by_vision(candidates, vision_samples or [])
    for field_id in _user_evidence_column_ids(candidates, vision_covered=vision_covered):
        if field_id not in chosen:
            chosen.append(field_id)
    for optional in ("name", "note"):
        if optional not in chosen:
            chosen.append(optional)
    return chosen


def _finalize_user_columns(
    candidates: Sequence[Mapping[str, Any]],
    user_ids: Sequence[str],
    *,
    vision_samples: Sequence[Mapping[str, Any]] | None = None,
) -> list[str]:
    """Merge LLM picks with rule minimum; never allow score columns on the download sheet."""
    sanitized = _sanitize_user_column_ids(candidates, user_ids)
    minimum = _rule_based_user_columns(candidates, vision_samples=vision_samples)
    allowed = {str(col["id"]) for col in candidates}
    ordered: list[str] = []
    for field_id in sanitized:
        if field_id in allowed and field_id not in ordered:
            ordered.append(field_id)
    for field_id in minimum:
        if field_id not in ordered:
            ordered.append(field_id)
    return ordered


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
    product_vision: str = "",
    vision_samples: Sequence[Mapping[str, Any]] | None = None,
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
        product_vision=product_vision or "（卖家尚未上传商品图）",
        skill_rules=skill_prompt_block(),
    )
    payload = ai.chat_json(
        [{"role": "user", "content": prompt}],
        temperature=0.1,
        timeout=PLANNER_LLM_TIMEOUT,
    )
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
    return _finalize_user_columns(candidates, chosen, vision_samples=vision_samples), reasoning, tips


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
    vision_samples: Sequence[Mapping[str, Any]] | None = None,
) -> str:
    blob = json.dumps(
        {
            "planner_version": PLANNER_VERSION,
            "schema": hashlib.sha256(schema_xml.encode("utf-8", errors="replace")).hexdigest(),
            "defaults": shop_defaults,
            "template": template_values,
            "vision": vision_plan.vision_summary_text(vision_samples or []),
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
    return _cached_plan_payload(row)


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
        persist_database()
    except Exception:
        db.rollback()


def _with_habits(plan: dict[str, Any], habits_pre: dict[str, Any] | None) -> dict[str, Any]:
    if not habits_pre:
        return plan
    out = dict(plan)
    out["habits"] = habits_pre
    out["selected_template_id"] = habits_pre.get("selected_template_id") or ""
    out["selected_template_name"] = habits_pre.get("selected_template_name") or ""
    return out


def build_plan(
    db: Session,
    api: Any,
    shop: Shop,
    *,
    category_id: str,
    category_name: str = "",
    ai: AiClient | None = None,
    refresh: bool = False,
    vision_samples: Sequence[Mapping[str, Any]] | None = None,
    user: Any | None = None,
) -> dict[str, Any]:
    if not category_id:
        raise ValueError("先选叶子类目")
    shop_defaults = _shop_defaults(shop)
    if not refresh and not vision_samples:
        fast = _try_fast_cached_plan(
            db,
            shop.id,
            category_id,
            category_name=category_name,
            refresh=refresh,
        )
        if fast is not None:
            return fast
        cross_shop = _try_user_category_cached_plan(
            db,
            shop.user_id,
            shop.id,
            category_id,
            category_name=category_name,
            refresh=refresh,
        )
        if cross_shop is not None:
            return cross_shop
    habits_pre: dict[str, Any] | None = None
    template_values: dict[str, Any] = {}
    if user is not None:
        from . import habits_ready

        product_vision = vision_plan.vision_summary_text(vision_samples or [])
        habits_pre = habits_ready.check_and_prepare(
            db,
            api,
            shop,
            user,
            category_id=category_id,
            category_name=category_name,
            ai=ai,
            vision_summary=product_vision,
            vision_samples=vision_samples or [],
            auto_fix=True,
        )
        tid = str(habits_pre.get("selected_template_id") or "").strip()
        if tid:
            row = db.get(Template, tid)
            if row is not None:
                template_values = template_service.values_of(row)
    if not template_values:
        template_values = _template_values(db, shop.id, category_id)
    habits_fp = _habits_fingerprint(shop_defaults, template_values)
    xml = catalog.get_schema_xml(db, api, category_id, "zh")
    fields = parse_schema(xml)
    fields_flat = excel_import.flatten_schema_fields(fields)
    schema_inventory = schema_inventory_summary(fields_flat)
    product_vision = vision_plan.vision_summary_text(vision_samples or [])
    input_hash = _plan_input_hash(xml, shop_defaults, template_values, vision_samples)
    if not refresh and not vision_samples:
        cached = _load_cached_plan(db, shop.id, category_id, input_hash)
        if cached is not None:
            if category_name and not cached.get("category_name"):
                cached["category_name"] = category_name
            return _with_habits(cached, habits_pre)
    candidates, covered_shop, covered_template = candidate_columns(
        fields,
        shop_defaults=shop_defaults,
        template_values=template_values,
    )
    planner = "rules"
    reasoning = (
        "填写表列 = 你必须提供的依据（含无法推断的必填项）；"
        "上传后 AI 读取这些单元格，高置信补全其余官方必填属性。"
    )
    tips = "价/量/货号必填；表格里其余列是你必须提供的商品事实，AI 据此推断官方属性。"
    template_summary = _template_summary(template_values)
    ai_completes = _ai_completes_block(
        covered_shop=covered_shop,
        covered_template=covered_template,
        schema_inventory=schema_inventory,
    )
    user_ids = _rule_based_user_columns(candidates, vision_samples=vision_samples)
    if ai is not None:
        try:
            user_ids, llm_reasoning, llm_tips = _llm_user_columns(
                ai,
                category_id=category_id,
                category_name=category_name,
                candidates=candidates,
                covered_shop=covered_shop,
                covered_template=covered_template,
                schema_inventory=schema_inventory,
                template_summary=template_summary,
                ai_completes=ai_completes,
                product_vision=product_vision,
                vision_samples=vision_samples,
            )
            planner = "llm+rules"
            if llm_reasoning:
                reasoning = llm_reasoning
            if llm_tips:
                tips = llm_tips
        except Exception as exc:
            logger.warning("smart plan LLM fallback to rules: %s", exc)
            user_ids = _finalize_user_columns(candidates, user_ids, vision_samples=vision_samples)
    else:
        user_ids = _finalize_user_columns(candidates, user_ids, vision_samples=vision_samples)
    columns = columns_for_ids(candidates, user_ids)
    user_id_set = set(user_ids)
    ai_fill_attrs = ai_target_columns(candidates, user_id_set)
    ai_fills: list[dict[str, Any]] = [
        {"id": "productTitle", "label": "英文标题", "group": "copy"},
        {"id": "productKeywords", "label": "关键词", "group": "copy"},
        {"id": "textDesc", "label": "详描", "group": "copy"},
        {"id": "highlights", "label": "卖点摘要", "group": "copy"},
    ]
    for col in ai_fill_attrs:
        ai_fills.append(
            {
                "id": col["id"],
                "label": col.get("label") or col["id"],
                "group": "schema",
                "required": bool(col.get("required")),
            }
        )
    required_attrs = [col for col in columns if str(col.get("id", "")).startswith("attr.") and col.get("required")]
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
        "ai_fill_attr_count": len(ai_fill_attrs),
        "covered_by_shop": covered_shop,
        "covered_by_template": covered_template,
        "shop_fills": [dict(item) for item in excel_import.SHOP_FILLS],
        "ai_fills": ai_fills,
        "ai_fill_attrs": ai_fill_attrs,
        "user_fill_contract": "填写表 = 用户必须提供的依据；提供后 LLM 高置信补全其余官方必填",
        "guarantee": (
            "下载表包含价/量/货号和你必须提供的商品事实（含无法推断的必填属性）。"
            "上传后 AI 读取表中全部已填单元格，高置信推断其余官方必填与影响信息分的选填；"
            "推断不确定则留空，价/量/品牌不代填。"
        ),
        "review_note": "审核表会展示 AI 推断出的全部官方字段，可改后再成稿。",
        "evidence_column_ids": [col["id"] for col in columns if str(col.get("id", "")).startswith("attr.")],
        "ai_infer_attr_count": len(ai_fill_attrs),
        "vision_samples": list(vision_samples or []),
        "vision_summary": product_vision,
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
    if user is not None and habits_pre is not None:
        plan = _with_habits(plan, habits_pre)
    elif user is not None:
        from . import habits_ready

        habits_ready.attach_to_plan(db, api, shop, user, plan, ai=ai, auto_fix=False)
    _save_cached_plan(db, shop.id, category_id, input_hash, planner, plan)
    return plan


def llm_memory_columns(
    fields: Sequence[SchemaField],
    user_column_ids: set[str],
) -> list[dict[str, Any]]:
    """Audit-only columns: every required schema field + score optionals for downstream LLM."""
    specs = index_fields(fields)
    targets: list[dict[str, Any]] = []
    seen: set[str] = set()

    for group_id in ("icbuCatProp", "saleProp"):
        group = specs.get(group_id)
        if group is None:
            continue
        group_name = str(group.name or group_id)
        for child in group.children or []:
            if child.type == "label" or child.id in SKIP_ATTR_IDS:
                continue
            col = _attr_column(group_id, group_name, child, required=bool(child.required))
            col_id = str(col["id"])
            if col_id in user_column_ids or col_id in seen:
                continue
            if child.required:
                col["source"] = "schema_required"
                col["llm_memory"] = True
                targets.append(col)
                seen.add(col_id)
            elif child.options:
                col = dict(col)
                col["required"] = False
                col["source"] = "schema_score"
                col["llm_memory"] = True
                targets.append(col)
                seen.add(col_id)

    for field_id in SCORE_OPTIONAL_TOP:
        spec = specs.get(field_id)
        if spec is None or spec.type == "label":
            continue
        col_id = f"schema.{field_id}"
        if col_id in user_column_ids or col_id in seen:
            continue
        col = _top_column(spec, required=False)
        col["llm_memory"] = True
        targets.append(col)
        seen.add(col_id)

    return targets


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
        ai_targets = llm_memory_columns(fields, user_ids)
        return review_enrich.audit_columns(plan_columns, ai_targets)
    except Exception:
        return review_enrich.order_review_columns(plan_columns)


def build_smart_template_bytes(
    plan: Mapping[str, Any],
    *,
    embed_image_files: Sequence[tuple[str, bytes]] | None = None,
) -> bytes:
    columns = list(plan.get("columns") or [])
    category_id = str(plan.get("category_id") or "")
    category_name = str(plan.get("category_name") or category_id)
    embed_rows = excel_import.plan_embedded_image_rows(embed_image_files or []) if embed_image_files else []
    return excel_import.build_smart_template(
        columns,
        category_id=category_id,
        category_name=category_name,
        embed_rows=embed_rows,
        plan_summary={
            "reasoning": plan.get("reasoning") or "",
            "tips": plan.get("tips") or "",
            "covered_by_shop": plan.get("covered_by_shop") or [],
            "covered_by_template": plan.get("covered_by_template") or [],
            "ai_fills": plan.get("ai_fills") or [],
            "ai_fill_attrs": plan.get("ai_fill_attrs") or [],
            "user_fill_contract": plan.get("user_fill_contract") or "",
        },
    )
