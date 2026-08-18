"""Evidence-gated, iterative schema fill for any leaf category.

One fact table in, schema.get rules out. We do not materialise 7521 Excel forms.

Red lines (never AI-invented): price, MOQ, brand, photos, category.
Official attrs: AI + rules map facts/product name → platform options aggressively.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import requests
from ai import AiClient, AiUnavailable, Copy, Understanding  # noqa: E402
from schema import SchemaField, ValidationIssue, index_fields, parse_schema, validate_values  # noqa: E402

from . import defaults as defaults_service, quality, templates as template_service
from .excel_import import SPEC_LABELS
from .fact_bundle import FactBundle, Evidence

USER_OR_SHOP_KEYS = frozenset(
    {
        "ladderPrice",
        "scPrice",
        "fob",
        "minOrderQuantity",
        "priceUnit",
        "saleType",
        "shippingTemplate",
        "marketSample",
        "paymentMethod",
        "port",
        "market",
        "pkgMeasure",
        "pkgWeight",
        "logisticsMode",
        "logisticsProperty",
        "ladderPeriod",
        "origin",
        "brand",
        "catId",
        "scImages",
    }
)

ATTR_GROUPS = ("icbuCatProp", "saleProp")
AI_BATCH = 40
GENERIC_OPTIONS = {"other", "others", "custom", "customized", "其他", "其它"}

ORIGIN_HINTS = ("origin", "place of origin", "产地", "原产地")
BRAND_HINTS = ("brand", "品牌", "商标", "brand name")
MODEL_HINTS = ("model", "型号", "model number")
COLOR_HINTS = ("color", "colour", "颜色", "色号", "lead color", "铅芯颜色", "color number")
MATERIAL_HINTS = ("material", "材质", "面料", "毛材", "hair material", "笔杆", "barrel")
HARDNESS_HINTS = ("hardness", "硬度", "lead hardness", "笔芯硬度")
TIP_HINTS = ("tip", "笔尖", "nib", "笔头")
INK_HINTS = ("ink", "墨水", "墨型")
FORM_HINTS = ("form", "形态", "形状", "type", "类型")

SPEC_KEY_HINTS: dict[str, tuple[str, ...]] = {
    "color_count": COLOR_HINTS,
    "color": COLOR_HINTS,
    "material": MATERIAL_HINTS,
    "hardness": HARDNESS_HINTS,
    "tip": TIP_HINTS,
    "ink": INK_HINTS,
    "form": FORM_HINTS,
    "packaging": ("packaging", "包装", "pack"),
    "size": ("size", "尺寸", "length", "长度"),
    "pieces": ("pieces", "件数", "set", "套装"),
    "frame": ("frame", "框架", "骨架"),
    "grade": ("grade", "等级", "filter"),
}


@dataclass
class FillStats:
    required_total: int = 0
    filled: int = 0
    blocked_no_evidence: int = 0
    ai_calls: int = 0
    rounds: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "required_total": self.required_total,
            "filled": self.filled,
            "blocked_no_evidence": self.blocked_no_evidence,
            "ai_calls": self.ai_calls,
            "rounds": self.rounds,
        }


@dataclass
class FillResult:
    values: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Evidence] = field(default_factory=dict)
    issues: list[dict[str, Any]] = field(default_factory=list)
    stats: FillStats = field(default_factory=FillStats)
    ai_payload: dict[str, Any] = field(default_factory=dict)
    _issue_paths: set[str] = field(default_factory=set, repr=False)

    def record_evidence(self, path: str, source: str, quote: str = "") -> None:
        if path and source:
            self.evidence[path] = Evidence(source=source, quote=quote[:240])

    def add_issue_once(self, issue: dict[str, Any]) -> None:
        path = str(issue.get("path") or issue.get("field_id") or "")
        if path in self._issue_paths:
            return
        self._issue_paths.add(path)
        self.issues.append(issue)


def _norm(text: str) -> str:
    return " ".join((text or "").lower().replace("_", " ").replace("-", " ").split())


def _wanted(name: str, hints: tuple[str, ...]) -> bool:
    lowered = (name or "").lower()
    return any(hint in lowered for hint in hints)


def _tokens(text: str) -> set[str]:
    return {token for token in re.split(r"[\s,，/;；|]+", _norm(text)) if len(token) >= 2}


def re_split_first(text: str) -> str:
    for part in re.split(r"[,，/;；]", text):
        token = part.strip()
        if token:
            return token
    return text.strip()


def _fact_corpus(
    facts: Mapping[str, Any],
    understanding: Understanding,
    bundle: FactBundle | None,
) -> str:
    bits = [
        str(facts.get("product_name") or ""),
        str(facts.get("material") or ""),
        str(facts.get("note") or ""),
        str(facts.get("brand") or ""),
        " ".join(str(item) for item in facts.get("colors") or []),
        json.dumps(facts.get("specs") or {}, ensure_ascii=False),
        " ".join(str(v) for v in (facts.get("specs") or {}).values()),
        understanding.product_name,
        understanding.category_hint,
        understanding.material,
        " ".join(understanding.colors),
        " ".join(understanding.features),
        understanding.usage,
        " ".join(f"{SPEC_LABELS.get(k, k)} {v}" for k, v in understanding.specs.items()),
    ]
    if bundle:
        bits.append(bundle.text_blob())
        bits.append(bundle.name)
    return _norm(" ".join(bit for bit in bits if bit))


def _is_generic_option(label: str) -> bool:
    return _norm(label) in GENERIC_OPTIONS


def _apply_option(spec: SchemaField, raw: str) -> Any | None:
    if not raw or _is_generic_option(raw):
        return None
    option = spec.option_by_label(raw)
    if option is None:
        return None
    return [option.value] if spec.type == "multiCheck" else option.value


def _fuzzy_option_match(spec: SchemaField, corpus: str) -> tuple[str, str] | None:
    """Pick official option whose label tokens best overlap fact corpus."""
    if not spec.options:
        return None
    corpus_tokens = _tokens(corpus)
    best: tuple[int, str] | None = None
    for option in spec.options[:80]:
        label = option.display_name.strip()
        if not label or _is_generic_option(label):
            continue
        label_norm = _norm(label)
        if label_norm in corpus:
            return label, label
        overlap = len(_tokens(label) & corpus_tokens)
        if overlap <= 0:
            continue
        score = overlap * 10 + len(label_norm)
        if best is None or score > best[0]:
            best = (score, label)
    return (best[1], best[1]) if best else None


def _infer_color_option(spec: SchemaField, bundle: FactBundle | None, understanding: Understanding) -> tuple[str, str, str]:
    if not _wanted(spec.name, COLOR_HINTS):
        return "", "", ""
    specs = {**(bundle.specs if bundle else {}), **understanding.specs}
    count_raw = str(specs.get("color_count") or specs.get("colors") or "").strip()
    match = re.search(r"\d+", count_raw)
    if match and int(match.group()) > 1:
        for option in spec.options:
            label = option.display_name.lower()
            if label in {"colored", "multi", "multicolor", "multi color", "multi-color"}:
                return option.display_name, "excel", f"color_count={match.group()}"
    name_blob = _norm(f"{bundle.name if bundle else ''} {understanding.product_name}")
    if any(token in name_blob for token in ("彩色", "多色", "colored", "colour pencil", "color pencil")):
        for option in spec.options:
            if option.display_name.lower() in {"colored", "multi", "multicolor"}:
                return option.display_name, "excel", understanding.product_name or (bundle.name if bundle else "")
    return "", "", ""


def _infer_from_spec_keys(spec: SchemaField, bundle: FactBundle | None, understanding: Understanding) -> tuple[str, str, str]:
    specs = {**(bundle.specs if bundle else {}), **understanding.specs}
    for key, hints in SPEC_KEY_HINTS.items():
        value = str(specs.get(key) or "").strip()
        if not value:
            continue
        if not _wanted(spec.name, hints) and _norm(key) not in _norm(spec.name):
            continue
        applied = _apply_option(spec, value)
        if applied is not None:
            return value, "excel", f"{SPEC_LABELS.get(key, key)} {value}"
        fuzzy = _fuzzy_option_match(spec, _norm(value))
        if fuzzy:
            return fuzzy[0], "excel", value
    return "", "", ""


def _local_guess(
    spec: SchemaField,
    understanding: Understanding,
    defaults: Mapping[str, Any],
    bundle: FactBundle | None,
) -> tuple[str, str, str]:
    if _wanted(spec.name, ORIGIN_HINTS):
        raw = str((bundle.origin if bundle else "") or defaults.get("origin") or "").strip()
        if raw:
            return raw, "shop" if defaults.get("origin") else "excel", raw
    if _wanted(spec.name, BRAND_HINTS):
        raw = str((bundle.brand if bundle else "") or defaults.get("brand") or "").strip()
        if raw:
            return raw, "excel" if bundle and bundle.brand else "shop", raw
    if _wanted(spec.name, MODEL_HINTS):
        raw = str(defaults.get("model") or "").strip()
        return (raw, "shop", raw) if raw else ("", "", "")
    if _wanted(spec.name, COLOR_HINTS):
        if understanding.colors:
            return understanding.colors[0], "vision", understanding.colors[0]
        color = (bundle.specs.get("color") if bundle else "") or ""
        if color:
            return re_split_first(color), "excel", color
        inferred = _infer_color_option(spec, bundle, understanding)
        if inferred[0]:
            return inferred
    if _wanted(spec.name, MATERIAL_HINTS):
        raw = understanding.material or (bundle.specs.get("material") if bundle else "") or ""
        raw = str(raw).strip()
        if raw:
            src = "vision" if understanding.material else "excel"
            return raw, src, raw
    if _wanted(spec.name, HARDNESS_HINTS):
        raw = str((bundle.specs.get("hardness") if bundle else "") or understanding.specs.get("hardness") or "").strip()
        if raw:
            return raw, "excel", raw
    inferred = _infer_from_spec_keys(spec, bundle, understanding)
    if inferred[0]:
        return inferred
    for key, value in {**understanding.specs, **(bundle.specs if bundle else {})}.items():
        label = SPEC_LABELS.get(key, key)
        if _norm(key) == _norm(spec.name) or _norm(spec.name) in _norm(key) or _norm(label) in _norm(spec.name):
            text = str(value).strip()
            if text:
                return text, "excel", text
    return "", "", ""


def _resolve_spec(
    spec: SchemaField,
    group_id: str,
    understanding: Understanding,
    defaults: Mapping[str, Any],
    bundle: FactBundle | None,
    corpus: str,
) -> tuple[Any | None, str, str]:
    guess, src, quote = _local_guess(spec, understanding, defaults, bundle)
    if spec.options:
        applied = _apply_option(spec, guess)
        if applied is not None:
            return applied, src or "fact", quote or guess
        fuzzy = _fuzzy_option_match(spec, corpus)
        if fuzzy:
            applied = _apply_option(spec, fuzzy[0])
            if applied is not None:
                return applied, "fact", fuzzy[1]
        return None, "", ""
    if guess:
        return guess, src or "fact", quote or guess
    return None, "", ""


def align_attributes(
    group: SchemaField,
    understanding: Understanding,
    defaults: Mapping[str, Any],
    ai: AiClient | None,
    bundle: FactBundle | None,
    result: FillResult,
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    facts = bundle.facts_for_ai(understanding) if bundle else {
        "product_name": understanding.product_name,
        "material": understanding.material,
        "colors": understanding.colors,
        "specs": understanding.specs,
        "features": understanding.features,
        "usage": understanding.usage,
        "note": "",
        "brand": "",
    }
    corpus = _fact_corpus(facts, understanding, bundle)

    for spec in group.children:
        applied, src, quote = _resolve_spec(spec, group.id, understanding, defaults, bundle, corpus)
        if applied is not None:
            values[spec.id] = applied
            result.record_evidence(f"{group.id}.{spec.id}", src, quote)

    unresolved: list[SchemaField] = []
    for spec in group.children:
        if spec.id in values or not spec.options:
            continue
        if spec.required:
            unresolved.append(spec)

    unresolved.sort(key=lambda item: (not item.required, item.id))
    for batch_start in range(0, len(unresolved), AI_BATCH):
        batch = unresolved[batch_start : batch_start + AI_BATCH]
        if not batch or ai is None:
            break
        resolved = _ask_attributes(ai, batch, understanding, bundle, result, group.id)
        result.stats.ai_calls += 1
        for spec in batch:
            answer = resolved.get(spec.id, "")
            if not answer:
                continue
            applied = _apply_option(spec, answer)
            if applied is not None:
                values[spec.id] = applied
                result.record_evidence(f"{group.id}.{spec.id}", "ai", answer)

    for spec in unresolved:
        if spec.required and spec.id not in values:
            result.stats.blocked_no_evidence += 1
            result.add_issue_once(
                {
                    "field_id": spec.id,
                    "field_name": spec.name or spec.id,
                    "level": "red",
                    "message": "平台必填属性仍缺事实依据，请补规格或人工选择",
                    "path": f"{group.id}.{spec.id}",
                    "options": [{"value": o.value, "label": o.display_name} for o in spec.options[:60]],
                }
            )

    return values


def _ai_answer_allowed(
    spec: SchemaField,
    answer: str,
    facts: Mapping[str, Any],
    understanding: Understanding,
    bundle: FactBundle | None,
) -> bool:
    if _is_generic_option(answer):
        return False
    if spec.option_by_label(answer) is None:
        return False
    if _wanted(spec.name, BRAND_HINTS):
        brand = str(facts.get("brand") or (bundle.brand if bundle else "") or "").strip()
        return bool(brand) and _norm(answer) in (_norm(brand), *(_tokens(brand)))
    corpus = _fact_corpus(facts, understanding, bundle)
    answer_norm = _norm(answer)
    if answer_norm in corpus:
        return True
    for token in _tokens(answer):
        if token in _tokens(corpus):
            return True
    if _wanted(spec.name, COLOR_HINTS) and any(
        token in corpus for token in ("colored", "multi", "彩色", "多色", "colour", "color")
    ):
        return answer_norm in {"colored", "multi", "multicolor", "multi color", "multi-color"}
    if _wanted(spec.name, HARDNESS_HINTS):
        hardness = str((facts.get("specs") or {}).get("hardness") or understanding.specs.get("hardness") or "")
        if hardness and _norm(hardness) in answer_norm:
            return True
    fuzzy = _fuzzy_option_match(spec, corpus)
    if fuzzy and _norm(fuzzy[0]) == answer_norm:
        return True
    return False


def _ask_attributes(
    ai: AiClient,
    specs: Sequence[SchemaField],
    understanding: Understanding,
    bundle: FactBundle | None,
    result: FillResult,
    group_id: str,
) -> dict[str, str]:
    facts = bundle.facts_for_ai(understanding) if bundle else {
        "product_name": understanding.product_name,
        "material": understanding.material,
        "colors": understanding.colors,
        "specs": understanding.specs,
        "features": understanding.features,
        "usage": understanding.usage,
        "note": "",
        "brand": "",
    }
    question = {
        spec.id: {
            "attribute": spec.name or spec.id,
            "required": spec.required,
            "options": [option.display_name for option in spec.options[:50] if not _is_generic_option(option.display_name)],
        }
        for spec in specs
    }
    prompt = (
        "You map wholesale product facts onto Alibaba official attribute options.\n"
        "Goal: fill as many attributes as the facts reasonably support — this saves manual work.\n"
        "Rules:\n"
        "- Pick option text exactly from the options list when facts or product name imply it.\n"
        "- Reasonable inference OK for official attrs (e.g. 12-color pencil set → Lead Color colored).\n"
        "- Do NOT invent price, MOQ, brand, certifications, or origin not in facts.\n"
        "- Never pick Other / Custom / 其他.\n"
        "- Leave empty string only when facts truly give no clue.\n\n"
        f"Facts: {json.dumps(facts, ensure_ascii=False)}\n"
        f"Attributes: {json.dumps(question, ensure_ascii=False)}\n\n"
        'Return JSON only: {"p-1": "China", "p-9": "colored"}'
    )
    try:
        payload = ai.chat_json([{"role": "user", "content": prompt}], temperature=0.0)
    except (AiUnavailable, ValueError, requests.RequestException):
        return {}
    out: dict[str, str] = {}
    for spec in specs:
        answer = str(payload.get(spec.id) or "").strip()
        if not answer:
            continue
        if not _ai_answer_allowed(spec, answer, facts, understanding, bundle):
            continue
        out[spec.id] = answer
    return out


def apply_trade_from_facts(
    specs: Mapping[str, SchemaField],
    values: dict[str, Any],
    defaults: Mapping[str, Any],
    bundle: FactBundle | None,
    price: str,
    moq: str,
    result: FillResult,
) -> None:
    from .pipeline import apply_trade_terms  # local import avoids cycle at module load

    final_price = price or (bundle.price if bundle else "")
    final_moq = moq or (bundle.moq if bundle else "")
    ladder = bundle.ladder_values() if bundle else None
    apply_trade_terms(specs, values, defaults, final_price, final_moq, ladder=ladder)
    if ladder:
        values["ladderPrice"] = ladder
        for slot, payload in ladder.items():
            result.record_evidence(f"ladderPrice.{slot}", "excel", f"{payload['quantity']}@{payload['price']}")
    if final_price:
        result.record_evidence("price", "excel", final_price)
    if final_moq:
        result.record_evidence("moq", "excel", final_moq)


def fill_category_draft(
    xml: str,
    *,
    understanding: Understanding,
    bundle: FactBundle | None,
    defaults: Mapping[str, Any],
    category_values: Mapping[str, Any],
    price: str,
    moq: str,
    ai: AiClient | None,
    images_applied: bool,
    category_id: str = "",
    copy: Copy | None = None,
    title: str = "",
    keywords: Sequence[str] | None = None,
    highlights: str = "",
) -> FillResult:
    fields = parse_schema(xml)
    specs = index_fields(fields)
    layered = defaults_service.layer_defaults(defaults, category_values, None)
    cat_id = str(category_id or layered.get("catId") or category_values.get("catId") or "")
    result = FillResult(values={"catId": cat_id})
    keywords = list(keywords or [])

    max_rounds = 2
    for round_index in range(max_rounds):
        result.stats.rounds = round_index + 1
        values = result.values

        for group_id in ATTR_GROUPS:
            group = specs.get(group_id)
            if group is None or not group.children:
                continue
            chunk = align_attributes(group, understanding, layered, ai, bundle, result)
            if chunk:
                values[group_id] = {**(values.get(group_id) or {}), **chunk}

        apply_trade_from_facts(specs, values, layered, bundle, price, moq, result)

        from .pipeline import apply_content  # noqa: WPS433

        if copy or title or keywords or highlights:
            apply_content(
                specs,
                values,
                title or (copy.title if copy else ""),
                keywords or (copy.keywords if copy else []),
                highlights or (copy.highlights if copy else ""),
                images=[],
                copy=copy,
                understanding=understanding,
            )
            if title or (copy and copy.title):
                result.record_evidence("productTitle", "ai" if copy else "user", title or copy.title)
            if keywords or (copy and copy.keywords):
                result.record_evidence("productKeywords", "ai", ",".join(keywords or copy.keywords))

        issues = validate_values(fields, values)
        required_missing = [item for item in issues if item.level == "red" and "必填" in item.message]
        result.stats.required_total = max(result.stats.required_total, len(required_missing) + _count_filled_required(fields, values))
        result.stats.filled = _count_filled_required(fields, values)
        if not required_missing or round_index + 1 >= max_rounds:
            break

    if not images_applied:
        result.add_issue_once(
            {
                "field_id": "scImages",
                "field_name": "产品图片",
                "level": "red",
                "message": "至少要一张图片",
                "path": "scImages",
            }
        )

    return result


def _count_filled_required(fields: Sequence[SchemaField], values: Mapping[str, Any]) -> int:
    count = 0
    for spec in fields:
        if spec.type == "label" or spec.id in USER_OR_SHOP_KEYS:
            continue
        if not spec.required:
            continue
        if values.get(spec.id) not in (None, "", [], {}):
            count += 1
    return count


def validate_leaf_schema(xml: str) -> list[ValidationIssue]:
    return validate_values(parse_schema(xml), {})


def sample_fill_report(xml: str, bundle: FactBundle, understanding: Understanding | None = None) -> FillResult:
    u = bundle.enrich(understanding or Understanding(product_name=bundle.name))
    defaults = {
        "origin": bundle.origin or "China",
        "brand": bundle.brand,
        "priceUnit": "Piece/Pieces",
        "saleType": "Unit",
        "shippingTemplateId": "",
        "ladderPeriod": "15",
        "language": "en_US",
    }
    return fill_category_draft(
        xml,
        understanding=u,
        bundle=bundle,
        defaults=defaults,
        category_values={"catId": "21110712"},
        price=bundle.price,
        moq=bundle.moq,
        ai=None,
        images_applied=True,
        category_id="21110712",
        title=f"Wholesale {bundle.name or 'product'}",
        keywords=["wholesale", "factory", "bulk"],
        highlights=bundle.text_blob(),
    )
