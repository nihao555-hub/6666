"""Review-stage enrichment: AI copy/keywords and column ordering for the batch grid.

Download sheet stays minimal (facts the seller knows). After parse, this layer
adds editable title/keyword/selling-point columns at the front of the review
grid — similar to ICBU 生意助手 letting merchants tune copy before publish.

Title/keyword rules follow vendor/alibaba-icbu-publishing (aidi1723 skill, MIT).
"""

from __future__ import annotations

import json
import re
from typing import Any, Mapping, Sequence

from ai import AiClient, AiUnavailable, Understanding  # noqa: E402

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
) -> dict[str, str]:
    understanding = _understanding_from_row(row, category_name=category_name)
    publishing_rules = skill_prompt_block()
    if ecosystem_brief:
        publishing_rules = ecosystem_prompt_block(ecosystem_brief)
    extra = {
        "brand": str(row.get("brand") or "").strip(),
        "price": str(row.get("price") or "").strip(),
        "moq": str(row.get("moq") or "").strip(),
        "category": category_name,
        "title_formula": TITLE_FORMULA,
        "publishing_skill_rules": publishing_rules,
        "alibaba_ecosystem_tips": str((ecosystem_brief or {}).get("tips") or ""),
        "shop_golden_title_examples": (ecosystem_brief or {}).get("golden_titles") or [],
    }
    copy = ai.write_copy(understanding, extra_facts=extra)
    result = {
        "title": copy.title,
        "keywords": ", ".join(copy.keywords[:3]),
        "highlights": copy.highlights or "; ".join(copy.selling_points[:3]),
    }
    limits = (ecosystem_brief or {}).get("schema_limits") or {}
    title_limit = int((limits.get("productTitle") or {}).get("max_length") or 128)
    result["_copy_score"] = score_copy_row(result, title_byte_limit=title_limit)
    return result


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
            suggested = suggest_copy_for_row(
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


def _row_corpus(row: Mapping[str, Any]) -> str:
    bits = [
        str(row.get("name") or ""),
        str(row.get("note") or ""),
        str(row.get("brand") or ""),
    ]
    for key, value in row.items():
        if str(key).startswith(("attr.", "schema.")) and str(value or "").strip():
            bits.append(str(value))
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


def infer_fields_for_row(
    row: Mapping[str, Any],
    columns: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, str], list[str]]:
    """Fill empty grid columns when note/name gives unambiguous evidence."""
    corpus = _row_corpus(row)
    if not corpus.strip():
        return {}, []
    filled: dict[str, str] = {}
    hints: list[str] = []
    for col in columns:
        col_id = str(col.get("id") or "")
        if not col_id or col_id in SKIP_INFER_IDS:
            continue
        if str(row.get(col_id) or "").strip():
            continue
        options = col.get("options") or []
        if not options:
            continue
        match = _match_option_from_corpus(corpus, options)
        if match:
            filled[col_id] = match
            hints.append(f"{col.get('label') or col_id} ← {match}")
    return filled, hints


def infer_fields_for_rows(
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[Mapping[str, Any]],
    *,
    lines: set[int] | None = None,
) -> tuple[list[dict[str, Any]], list[str], int]:
    updated: list[dict[str, Any]] = []
    errors: list[str] = []
    filled_count = 0
    for row in rows:
        item = dict(row)
        line = int(item.get("line") or 0)
        if lines and line not in lines:
            updated.append(item)
            continue
        patch, hints = infer_fields_for_row(item, columns)
        if patch:
            item.update(patch)
            item["_infer_fields"] = patch
            filled_count += len(patch)
        if hints:
            item["_infer_hint"] = "; ".join(hints[:4])
        updated.append(item)
    return updated, errors, filled_count


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
