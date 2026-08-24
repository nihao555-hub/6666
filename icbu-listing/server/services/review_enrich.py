"""Review-stage enrichment: AI copy/keywords and column ordering for the batch grid.

Download sheet carries evidence the seller types (official attrs + redlines). After parse,
this layer adds editable title/keyword columns and fills any official/score cells still
empty when derivable from the filled sheet.
"""

from __future__ import annotations

import json
import re
from typing import Any, Mapping, Sequence

from ai import AiClient, AiUnavailable, TokenUsage, Understanding  # noqa: E402

from .ecosystem_brief import build_brief, prompt_block as ecosystem_prompt_block, score_copy_row
from .icbu_publishing_skill import KEYWORD_RULES, TITLE_RULES, skill_prompt_block

TITLE_FORMULA = (
    "Core Product + Structure/Type + 1-2 Performance Words + Scene + Custom/OEM support word"
)

COPY_REVIEW_COLUMNS: list[dict[str, Any]] = [
    {
        "id": "title",
        "label": "英文标题",
        "header": "英文标题",
        "required": False,
        "hint": "审核时可改。公式：核心品名+类型+性能/场景+OEM。生意助手同款思路。",
        "kind": "textarea",
        "source": "ai_review",
        "group": "copy",
    },
    {
        "id": "keywords",
        "label": "关键词",
        "header": "关键词",
        "required": False,
        "hint": "1～3 个买家搜索词，逗号分隔。可手改或点「AI 重写关键词」。",
        "kind": "text",
        "source": "ai_review",
        "group": "copy",
    },
    {
        "id": "highlights",
        "label": "卖点摘要",
        "header": "卖点摘要",
        "required": False,
        "hint": "给审核看的中文/英文卖点，不进官方表，帮助核对标题方向。",
        "kind": "textarea",
        "source": "ai_review",
        "group": "copy",
    },
]

REVIEW_COLUMN_ORDER = (
    "title",
    "keywords",
    "highlights",
    "name",
    "sku",
    "price",
    "moq",
)


def _understanding_from_row(row: Mapping[str, Any], *, category_name: str = "") -> Understanding:
    name = str(row.get("name") or row.get("sku") or row.get("note") or "").strip()
    note = str(row.get("note") or "").strip()
    attrs = []
    for key, value in row.items():
        if str(key).startswith("attr.") and str(value or "").strip():
            attrs.append(f"{key.split('.')[-1]}={value}")
    if attrs:
        note = f"{note} {'; '.join(attrs)}".strip()
    return Understanding(
        product_name=name,
        category_hint=category_name,
        usage=note[:200] if note else "",
        features=[part for part in note.split(";") if part.strip()][:6],
        raw={"row": dict(row), "note": note},
    )


def suggest_copy_for_row(
    ai: AiClient,
    row: Mapping[str, Any],
    *,
    category_name: str = "",
    ecosystem_brief: Mapping[str, Any] | None = None,
    timeout: float | None = None,
) -> tuple[dict[str, str], TokenUsage]:
    understanding = _understanding_from_row(row, category_name=category_name)
    publishing_rules = skill_prompt_block()
    if ecosystem_brief:
        publishing_rules = ecosystem_prompt_block(ecosystem_brief)
    extra = {
        "brand": str(row.get("brand") or "").strip(),
        "price": str(row.get("price") or "").strip(),
        "moq": str(row.get("moq") or "").strip(),
        "category": category_name,
        "images": str(row.get("images") or "").strip(),
        "title_formula": TITLE_FORMULA,
        "publishing_skill_rules": publishing_rules,
        "alibaba_ecosystem_tips": str((ecosystem_brief or {}).get("tips") or ""),
        "shop_golden_title_examples": (ecosystem_brief or {}).get("golden_titles") or [],
        "shop_golden_listing_examples": (ecosystem_brief or {}).get("golden_listings") or [],
    }
    copy, usage = ai.write_copy_with_usage(understanding, extra_facts=extra, timeout=timeout)
    result = {
        "title": copy.title,
        "keywords": ", ".join(copy.keywords[:3]),
        "highlights": copy.highlights or "; ".join(copy.selling_points[:3]),
    }
    limits = (ecosystem_brief or {}).get("schema_limits") or {}
    title_limit = int((limits.get("productTitle") or {}).get("max_length") or 128)
    result["_copy_score"] = score_copy_row(result, title_byte_limit=title_limit)
    return result, usage


def enrich_rows(
    rows: Sequence[Mapping[str, Any]],
    plan_columns: Sequence[Mapping[str, Any]],
    *,
    category_name: str = "",
    ai: AiClient | None = None,
    ecosystem_brief: Mapping[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Return review columns (copy first), enriched rows, warnings."""
    warnings: list[str] = []
    enriched: list[dict[str, Any]] = [dict(row) for row in rows]
    if ai is None:
        warnings.append("未配置 AI，审核表只展示解析结果，标题/关键词需成稿时生成或手填。")
        for row in enriched:
            row.setdefault("title", str(row.get("title") or ""))
            row.setdefault("keywords", str(row.get("keywords") or ""))
            row.setdefault("highlights", str(row.get("highlights") or ""))
        return order_review_columns(plan_columns), enriched, warnings

    for row in enriched:
        if str(row.get("title") or "").strip() and str(row.get("keywords") or "").strip():
            row.setdefault("highlights", str(row.get("highlights") or ""))
            continue
        try:
            suggested, _usage = suggest_copy_for_row(
                ai,
                row,
                category_name=category_name,
                ecosystem_brief=ecosystem_brief,
            )
            row.setdefault("title", suggested["title"])
            row.setdefault("keywords", suggested["keywords"])
            row.setdefault("highlights", suggested["highlights"])
            row["_copy_source"] = "ai"
        except AiUnavailable:
            warnings.append("AI 文案暂不可用，部分行未预填标题/关键词。")
            break
        except Exception as exc:
            warnings.append(f"第 {row.get('line', '?')} 行文案预填失败：{exc}")
    return order_review_columns(plan_columns), enriched, warnings


def order_review_columns(plan_columns: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Copy/keyword columns first, then fact columns from the download plan."""
    by_id = {str(col.get("id") or ""): dict(col) for col in plan_columns if col.get("id")}
    ordered: list[dict[str, Any]] = [dict(col) for col in COPY_REVIEW_COLUMNS]
    seen = {col["id"] for col in ordered}
    for field_id in REVIEW_COLUMN_ORDER:
        if field_id in seen:
            continue
        col = by_id.get(field_id)
        if col is not None:
            ordered.append(col)
            seen.add(field_id)
    for col in plan_columns:
        fid = str(col.get("id") or "")
        if not fid or fid in seen or fid == "images":
            continue
        ordered.append(dict(col))
        seen.add(fid)
    return ordered


SKIP_INFER_IDS = frozenset(
    {
        "sku",
        "price",
        "moq",
        "images",
        "brand",
        "name",
        "note",
        "title",
        "keywords",
        "highlights",
    }
)

GENERIC_OPTIONS = frozenset({"other", "others", "custom", "customized", "其他", "其它"})


def _norm_corpus(text: str) -> str:
    return " ".join((text or "").lower().replace("_", " ").replace("-", " ").split())


def _facts_from_row_memory(
    row: Mapping[str, Any],
    columns: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Serialize every filled audit cell so later LLM steps inherit this grid state."""
    understanding = _understanding_from_row(row)
    by_id = {str(col.get("id") or ""): col for col in columns if col.get("id")}
    facts: dict[str, Any] = {
        "product_name": understanding.product_name,
        "note": str(row.get("note") or ""),
        "brand": str(row.get("brand") or ""),
        "price": str(row.get("price") or ""),
        "moq": str(row.get("moq") or ""),
        "sku": str(row.get("sku") or ""),
        "name": str(row.get("name") or ""),
    }
    for copy_key, label in (
        ("title", "英文标题"),
        ("keywords", "关键词"),
        ("highlights", "卖点摘要"),
    ):
        text = str(row.get(copy_key) or "").strip()
        if text:
            facts[copy_key] = text
            facts[label] = text
    for col_id, col in by_id.items():
        if col_id in SKIP_INFER_IDS:
            continue
        text = str(row.get(col_id) or "").strip()
        if not text:
            continue
        label = str(col.get("label") or col_id)
        facts[col_id] = text
        facts[label] = text
    raw_cells = row.get("_raw_cells")
    if isinstance(raw_cells, Mapping):
        facts["_raw_cells"] = {str(k): str(v) for k, v in raw_cells.items() if v not in (None, "")}
    infer_patch = row.get("_infer_fields")
    if isinstance(infer_patch, Mapping):
        facts["_infer_fields"] = {str(k): str(v) for k, v in infer_patch.items() if v not in (None, "")}
    images = str(row.get("images") or "").strip()
    if images:
        facts["images"] = images
    return facts


def _facts_from_user_columns(
    row: Mapping[str, Any],
    columns: Sequence[Mapping[str, Any]],
    *,
    user_column_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Serialize audit grid state for attribute inference (inherits prior fills + user sheet)."""
    del user_column_ids  # full grid memory — download sheet + AI fills + inferred attrs
    return _facts_from_row_memory(row, columns)


def _row_corpus(row: Mapping[str, Any], user_column_ids: set[str] | None = None) -> str:
    """Build searchable text from filled audit cells for high-confidence option matching."""
    bits: list[str] = []
    skip_output_only = {"title", "keywords", "highlights"}
    for key, value in row.items():
        key_text = str(key)
        if key_text.startswith("_") or key_text in skip_output_only:
            continue
        text = str(value or "").strip()
        if text:
            bits.append(text)
    return _norm_corpus(" ".join(bits))


def _match_option_from_corpus(corpus: str, options: Sequence[Mapping[str, Any]]) -> str | None:
    matches: list[str] = []
    compact = corpus.replace(" ", "")
    for opt in options[:80]:
        label = str(opt.get("label") or opt.get("value") or "").strip()
        if not label or len(label) < 2:
            continue
        norm = _norm_corpus(label)
        if not norm or norm in GENERIC_OPTIONS:
            continue
        if norm in corpus or norm.replace(" ", "") in compact:
            matches.append(label)
            continue
        for token in re.split(r"[\s,，/;；|]+", norm):
            if len(token) >= 2 and token in corpus:
                matches.append(label)
                break
    unique = list(dict.fromkeys(matches))
    return unique[0] if len(unique) == 1 else None


def ai_target_columns(
    candidates: Sequence[Mapping[str, Any]],
    user_column_ids: set[str],
) -> list[dict[str, Any]]:
    """Schema fields AI should fill at review — not already on the download sheet."""
    targets: list[dict[str, Any]] = []
    for col in candidates:
        col_id = str(col.get("id") or "")
        if not col_id or col_id in user_column_ids:
            continue
        if col_id in SKIP_INFER_IDS or col_id in {"title", "keywords", "highlights", "images"}:
            continue
        if col.get("required") or col.get("source") in ("schema_required", "schema_score"):
            item = dict(col)
            item.setdefault("source", "ai_fill")
            targets.append(item)
    return targets


def audit_columns(
    plan_columns: Sequence[Mapping[str, Any]],
    ai_targets: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Review grid = copy columns + download columns + AI-fill schema columns."""
    ordered = order_review_columns(plan_columns)
    seen = {str(col.get("id") or "") for col in ordered}
    for col in ai_targets:
        col_id = str(col.get("id") or "")
        if col_id and col_id not in seen:
            ordered.append(dict(col))
            seen.add(col_id)
    return ordered


def fillable_infer_columns(columns: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for col in columns:
        col_id = str(col.get("id") or "")
        if not col_id or col_id in SKIP_INFER_IDS:
            continue
        if col.get("options") or col.get("required") or col.get("source") in (
            "schema_required",
            "schema_score",
            "ai_fill",
        ):
            out.append(col)
    return out


def _apply_column_answer(col: Mapping[str, Any], answer: Any) -> str | None:
    raw = str(answer or "").strip()
    if not raw or raw.lower() in GENERIC_OPTIONS:
        return None
    options = col.get("options") or []
    if not options:
        return raw
    labels = [str(item.get("label") or item.get("value") or "").strip() for item in options]
    if raw in labels:
        return raw
    norm = _norm_corpus(raw)
    for label in labels:
        if label and _norm_corpus(label) == norm:
            return label
    return _match_option_from_corpus(norm, options)


def _ai_fill_empty_columns(
    ai: AiClient,
    row: Mapping[str, Any],
    columns: Sequence[Mapping[str, Any]],
    already: Mapping[str, str],
    *,
    user_column_ids: set[str] | None = None,
    category_name: str = "",
) -> tuple[dict[str, str], list[str], TokenUsage]:
    facts = _facts_from_user_columns(row, columns, user_column_ids=user_column_ids)
    by_id = {str(col.get("id") or ""): col for col in columns if col.get("id")}
    question: dict[str, Any] = {}
    for col_id, col in by_id.items():
        if col_id in SKIP_INFER_IDS or col_id in already:
            continue
        if str(row.get(col_id) or "").strip():
            continue
        if not (col.get("required") or col.get("source") in ("schema_required", "schema_score", "ai_fill")):
            continue
        options = col.get("options") or []
        question[col_id] = {
            "label": col.get("label") or col_id,
            "required": bool(col.get("required")),
            "options": [str(item.get("label") or item.get("value") or "") for item in options[:40] if item],
        }
    if not question:
        return {}, [], TokenUsage()
    category_line = f"Leaf category: {category_name}\n" if category_name else ""
    prompt = (
        "You are an Alibaba.com (ICBU) wholesale listing attribute specialist.\n"
        "The seller filled an evidence sheet with facts they must provide. Infer empty fields in fields_to_fill.\n\n"
        f"{category_line}"
        "Rules (follow strictly for high accuracy):\n"
        "1. user_facts = every cell the seller typed on the download sheet (including name, note, filled attrs).\n"
        "2. Use EXACT option label from fields_to_fill.options — copy character-for-character.\n"
        "3. REQUIRED empty fields: fill ONLY when user_facts uniquely support ONE option.\n"
        "4. If two or more options are plausible, return empty string for that field.\n"
        "5. Score optional fields: fill only with strong, unambiguous evidence.\n"
        "6. Values must be logically consistent across fields (e.g. 12-color set ↔ color count 12).\n"
        "7. Never guess price, MOQ, brand, origin, or certifications.\n"
        "8. Never pick Other/其他/Custom unless user_facts explicitly say custom/OEM.\n\n"
        f"user_facts: {json.dumps(facts, ensure_ascii=False)}\n"
        f"fields_to_fill: {json.dumps(question, ensure_ascii=False)}\n"
        'Return JSON only: {"column_id": "exact option label or empty string"}'
    )
    try:
        payload, usage = ai.chat_json_with_usage([{"role": "user", "content": prompt}], temperature=0.0)
    except (AiUnavailable, ValueError, TypeError):
        return {}, [], TokenUsage()
    if not isinstance(payload, dict):
        return {}, [], usage
    filled: dict[str, str] = {}
    hints: list[str] = []
    for col_id, answer in payload.items():
        col = by_id.get(str(col_id))
        if col is None:
            continue
        applied = _apply_column_answer(col, answer)
        if applied:
            filled[str(col_id)] = applied
            hints.append(f"{col.get('label') or col_id} ← AI")
    return filled, hints, usage


def _apply_shop_defaults(row: Mapping[str, Any], columns: Sequence[Mapping[str, Any]], shop_defaults: Mapping[str, Any]) -> tuple[dict[str, str], list[str]]:
    filled: dict[str, str] = {}
    hints: list[str] = []
    for col in columns:
        col_id = str(col.get("id") or "")
        if not col_id.startswith("schema.") or str(row.get(col_id) or "").strip():
            continue
        field_id = col_id.split(".", 1)[-1]
        raw = shop_defaults.get(field_id)
        if raw is None or not str(raw).strip():
            continue
        filled[col_id] = str(raw).strip()
        hints.append(f"{col.get('label') or col_id} ← 店铺默认")
    return filled, hints


def infer_fields_for_row(
    row: Mapping[str, Any],
    columns: Sequence[Mapping[str, Any]],
    *,
    ai: AiClient | None = None,
    shop_defaults: Mapping[str, Any] | None = None,
    user_column_ids: set[str] | None = None,
    category_name: str = "",
) -> tuple[dict[str, str], list[str], TokenUsage]:
    """Fill empty required/score columns from shop defaults, user row corpus, then AI."""
    filled: dict[str, str] = {}
    hints: list[str] = []
    usage = TokenUsage()

    if shop_defaults:
        shop_patch, shop_hints = _apply_shop_defaults(row, columns, shop_defaults)
        filled.update(shop_patch)
        hints.extend(shop_hints)

    corpus = _row_corpus(row, user_column_ids)
    for col in columns:
        col_id = str(col.get("id") or "")
        if not col_id or col_id in SKIP_INFER_IDS or col_id in filled:
            continue
        if str(row.get(col_id) or "").strip():
            continue
        options = col.get("options") or []
        if not options or not corpus.strip():
            continue
        match = _match_option_from_corpus(corpus, options)
        if match:
            filled[col_id] = match
            hints.append(f"{col.get('label') or col_id} ← {match}")

    if ai is not None:
        ai_patch, ai_hints, ai_usage = _ai_fill_empty_columns(
            ai,
            row,
            columns,
            filled,
            user_column_ids=user_column_ids,
            category_name=category_name,
        )
        usage.add(ai_usage)
        for key, value in ai_patch.items():
            if key not in filled:
                filled[key] = value
        hints.extend(ai_hints)

    return filled, hints, usage


def count_missing_required_cells(rows: Sequence[Mapping[str, Any]], columns: Sequence[Mapping[str, Any]]) -> int:
    required_cols = [
        col
        for col in columns
        if col.get("required")
        and str(col.get("id") or "").startswith(("attr.", "schema."))
    ]
    if not required_cols:
        return 0
    missing = 0
    for row in rows:
        for col in required_cols:
            if not str(row.get(str(col.get("id") or "")) or "").strip():
                missing += 1
    return missing


def infer_fields_for_rows(
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[Mapping[str, Any]],
    *,
    lines: set[int] | None = None,
    ai: AiClient | None = None,
    shop_defaults: Mapping[str, Any] | None = None,
    user_column_ids: set[str] | None = None,
    category_name: str = "",
) -> tuple[list[dict[str, Any]], list[str], int, dict[str, Any]]:
    updated: list[dict[str, Any]] = []
    errors: list[str] = []
    filled_count = 0
    fillable = len(fillable_infer_columns(columns))
    usage = TokenUsage()
    for row in rows:
        item = dict(row)
        line = int(item.get("line") or 0)
        if lines and line not in lines:
            updated.append(item)
            continue
        patch, hints, row_usage = infer_fields_for_row(
            item,
            columns,
            ai=ai,
            shop_defaults=shop_defaults,
            user_column_ids=user_column_ids,
            category_name=category_name,
        )
        usage.add(row_usage)
        if patch:
            item.update(patch)
            item["_infer_fields"] = patch
            filled_count += len(patch)
        if hints:
            item["_infer_hint"] = "; ".join(hints[:6])
        updated.append(item)
    meta = {
        "fillable_columns": fillable,
        "missing_required_cells": count_missing_required_cells(updated, columns),
        "token_usage": usage.as_dict(),
    }
    return updated, errors, filled_count, meta


def schema_inventory_summary(fields_flat: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    required = [item for item in fields_flat if item.get("required")]
    optional = [item for item in fields_flat if not item.get("required")]
    copy_ids = {"productTitle", "productKeywords", "textDesc", "superText", "companyFaqDesc"}
    copy_fields = [item for item in fields_flat if str(item.get("field_id") or "") in copy_ids]

    def _compact(item: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "field_id": item.get("field_id"),
            "name": item.get("name"),
            "group_id": item.get("group_id"),
        }

    return {
        "total": len(fields_flat),
        "required_count": len(required),
        "optional_count": len(optional),
        "required_fields": [_compact(item) for item in required],
        "optional_fields": [_compact(item) for item in optional],
        "copy_fields": [item.get("name") or item.get("field_id") for item in copy_fields],
        "sent_to_planner": "all_required_names_and_all_optional_names",
    }
