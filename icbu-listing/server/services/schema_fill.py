"""Evidence-gated schema fill for any leaf category.

Red lines (never AI-invented): price, MOQ, brand, photos, category.
Official attrs: fill only when the seller could be 100% sure of the value
(options, text inputs, numbers — any field type) from facts + photos.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import requests
from ai import AiClient, AiUnavailable, Copy, ImageInput, Understanding  # noqa: E402
from schema import SchemaField, ValidationIssue, index_fields, parse_schema, validate_values  # noqa: E402

from . import defaults as defaults_service, quality, templates as template_service
from .excel_import import SPEC_LABELS
from .fact_bundle import FactBundle, Evidence
from .images import BankImage

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
DUAL_SIDE_HINTS = ("dual-side", "dual side", "double side", "double-sided", "双面", "双头", "双尖", "dual writing")
DUAL_TIP_CORPUS = ("dual tip", "dual side", "double tip", "double end", "double-sided", "双头", "双面", "双尖")
MULTICOLOR_LABELS = frozenset({"colored", "multi", "multicolor", "multi color", "multicolour", "multi-color"})

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
    "model": MODEL_HINTS,
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
        str(facts.get("sku") or ""),
        str(facts.get("name") or ""),
        str(facts.get("product_name") or ""),
        str(facts.get("category_hint") or ""),
        str(facts.get("material") or ""),
        str(facts.get("note") or ""),
        str(facts.get("brand") or ""),
        str(facts.get("price") or ""),
        str(facts.get("moq") or ""),
        str(facts.get("text_blob") or ""),
        " ".join(str(item) for item in facts.get("colors") or []),
        json.dumps(facts.get("specs") or {}, ensure_ascii=False),
        json.dumps(facts.get("specs_labeled") or {}, ensure_ascii=False),
        json.dumps(facts.get("vision") or {}, ensure_ascii=False),
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


def _coerce_images(images: Sequence[ImageInput | BankImage] | None) -> list[ImageInput]:
    out: list[ImageInput] = []
    for item in images or []:
        if isinstance(item, ImageInput):
            out.append(item)
        else:
            out.append(ImageInput(filename=item.file_name or "product.jpg", url=item.absolute_url))
    return out[:6]


def _is_generic_option(label: str) -> bool:
    return _norm(label) in GENERIC_OPTIONS


def _apply_option(spec: SchemaField, raw: str) -> Any | None:
    if not raw or _is_generic_option(raw):
        return None
    option = spec.option_by_label(raw)
    if option is None:
        return None
    return [option.value] if spec.type == "multiCheck" else option.value


def _merged_specs(bundle: FactBundle | None, understanding: Understanding) -> dict[str, str]:
    merged = dict(understanding.specs)
    if bundle:
        merged = {**bundle.specs, **merged}
    return {k: str(v).strip() for k, v in merged.items() if str(v).strip()}


def _field_related(spec: SchemaField, spec_key: str) -> bool:
    key_norm = _norm(spec_key)
    name_norm = _norm(spec.name)
    label_norm = _norm(SPEC_LABELS.get(spec_key, spec_key))
    hints = SPEC_KEY_HINTS.get(spec_key, ())
    return key_norm in name_norm or name_norm in key_norm or label_norm in name_norm or _wanted(spec.name, hints)


def _matching_options(spec: SchemaField, raw: str) -> list[Any]:
    needle = _norm(raw)
    if not needle or not spec.options:
        return []
    hits = []
    for option in spec.options:
        label = option.display_name.strip()
        if not label or _is_generic_option(label):
            continue
        label_norm = _norm(label)
        if label_norm == needle or label_norm in needle or needle in label_norm:
            hits.append(option)
        elif _tokens(label).issubset(_tokens(needle)) or _tokens(needle).issubset(_tokens(label)):
            hits.append(option)
    return hits


def _deterministic_certain(
    spec: SchemaField,
    answer: str,
    facts: Mapping[str, Any],
    understanding: Understanding,
    bundle: FactBundle | None,
) -> tuple[str, str] | None:
    """Narrow rules where one official option is the only sensible pick."""
    answer_norm = _norm(answer)
    specs = _merged_specs(bundle, understanding)
    name = _norm(
        " ".join(
            [
                str(facts.get("name") or ""),
                str(facts.get("product_name") or ""),
                understanding.product_name,
                bundle.name if bundle else "",
            ]
        )
    )

    if _wanted(spec.name, COLOR_HINTS):
        count_raw = str(specs.get("color_count") or "")
        match = re.search(r"\d+", count_raw)
        if match and int(match.group()) > 1 and answer_norm in MULTICOLOR_LABELS:
            if "色" in name or any(token in name for token in ("colored", "colour", "multicolor", "multi color", "彩色", "多色")):
                return "excel", f"color_count={match.group()}"
        if answer_norm == "colored" and any(token in name for token in ("彩色", "多色", "colored")):
            return "excel", str(facts.get("name") or understanding.product_name)
        explicit = str(specs.get("color") or "")
        if explicit and _apply_option(spec, re_split_first(explicit)) and answer_norm == _norm(re_split_first(explicit)):
            return "excel", explicit

    if _wanted(spec.name, DUAL_SIDE_HINTS) or ("dual" in _norm(spec.name) and "writing" in _norm(spec.name)):
        if answer_norm == "yes":
            corpus = _fact_corpus(facts, understanding, bundle)
            if any(token in corpus for token in DUAL_TIP_CORPUS):
                tip = str(specs.get("tip") or "")
                return "excel", tip or "dual tip"

    if _wanted(spec.name, HARDNESS_HINTS):
        hardness = str(specs.get("hardness") or "")
        if hardness and _norm(hardness) == answer_norm:
            return "excel", f"hardness={hardness}"

    return None


def _attr_fillable(spec: SchemaField) -> bool:
    if spec.type == "label":
        return False
    return spec.id not in USER_OR_SHOP_KEYS


def _is_certain_text_value(
    spec: SchemaField,
    text: str,
    facts: Mapping[str, Any],
    understanding: Understanding,
    bundle: FactBundle | None,
) -> tuple[bool, str, str]:
    raw = str(text or "").strip()
    if not raw:
        return False, "", ""

    if _wanted(spec.name, BRAND_HINTS):
        brand = str(facts.get("brand") or (bundle.brand if bundle else "") or "").strip()
        if brand and _norm(raw) == _norm(brand):
            return True, "excel", brand
        return False, "", ""

    corpus = _fact_corpus(facts, understanding, bundle)
    text_norm = _norm(raw)
    if text_norm in corpus:
        return True, "excel", raw
    for token in _tokens(raw):
        if len(token) >= 2 and token in _tokens(corpus):
            return True, "excel", raw

    for key, value in _merged_specs(bundle, understanding).items():
        if not _field_related(spec, key):
            continue
        if _norm(str(value)) == text_norm:
            return True, "excel", f"{SPEC_LABELS.get(key, key)} {value}"

    if _wanted(spec.name, MATERIAL_HINTS):
        material = str(facts.get("material") or understanding.material or "").strip()
        if material and _norm(material) == text_norm:
            src = "vision" if understanding.material else "excel"
            return True, src, material

    if _wanted(spec.name, MODEL_HINTS):
        model = str((facts.get("specs") or {}).get("model") or understanding.specs.get("model") or "").strip()
        if model and _norm(model) == text_norm:
            return True, "excel", model

    return False, "", ""


def _is_certain_fill(
    spec: SchemaField,
    answer: str,
    facts: Mapping[str, Any],
    understanding: Understanding,
    bundle: FactBundle | None,
) -> tuple[bool, str, str]:
    """True when the seller could pick this value with 100% confidence."""
    if not spec.options:
        return _is_certain_text_value(spec, answer, facts, understanding, bundle)

    if _is_generic_option(answer) or spec.option_by_label(answer) is None:
        return False, "", ""

    if _wanted(spec.name, BRAND_HINTS):
        brand = str(facts.get("brand") or (bundle.brand if bundle else "") or "").strip()
        if brand and _norm(answer) == _norm(brand):
            return True, "excel", brand
        return False, "", ""

    corpus = _fact_corpus(facts, understanding, bundle)
    answer_norm = _norm(answer)

    if _wanted(spec.name, ORIGIN_HINTS):
        origin = str((bundle.origin if bundle else "") or facts.get("origin") or "").strip()
        if origin and answer_norm == _norm(origin):
            src = "excel" if bundle and bundle.origin else "shop"
            return True, src, origin
        if answer_norm in corpus:
            return True, "shop", answer
        return False, "", ""

    if answer_norm in corpus:
        return True, "excel", answer
    for token in _tokens(answer):
        if len(token) >= 2 and token in _tokens(corpus):
            return True, "excel", answer

    specs = _merged_specs(bundle, understanding)
    for key, value in specs.items():
        if not _field_related(spec, key):
            continue
        if _norm(spec.option_by_label(value).display_name if spec.option_by_label(value) else "") == answer_norm:
            return True, "excel", f"{SPEC_LABELS.get(key, key)} {value}"
        matches = _matching_options(spec, value)
        if len(matches) == 1 and _norm(matches[0].display_name) == answer_norm:
            return True, "excel", f"{SPEC_LABELS.get(key, key)} {value}"

    for key, value in specs.items():
        matches = _matching_options(spec, value)
        if len(matches) == 1 and _norm(matches[0].display_name) == answer_norm:
            return True, "excel", f"{SPEC_LABELS.get(key, key)} {value}"

    if understanding.colors and _wanted(spec.name, COLOR_HINTS):
        for color in understanding.colors:
            if _norm(color) == answer_norm or _norm(color) in answer_norm:
                return True, "vision", color

    inferred = _deterministic_certain(spec, answer, facts, understanding, bundle)
    if inferred:
        return True, inferred[0], inferred[1]

    return False, "", ""


def _contradicts_facts(
    spec: SchemaField,
    answer: str,
    facts: Mapping[str, Any],
    bundle: FactBundle | None,
) -> bool:
    """Reject answers that invent or clash with seller-stated facts."""
    if _wanted(spec.name, BRAND_HINTS):
        brand = str(facts.get("brand") or (bundle.brand if bundle else "") or "").strip()
        if not brand:
            return True
        if _norm(answer) != _norm(brand):
            return True
    if _wanted(spec.name, ORIGIN_HINTS):
        origin = str((bundle.origin if bundle else "") or facts.get("origin") or "").strip()
        if origin and _norm(answer) != _norm(origin):
            return True
    return False


def _trust_ai_map_answer(
    spec: SchemaField,
    answer: str,
    facts: Mapping[str, Any],
    understanding: Understanding,
    bundle: FactBundle | None,
) -> tuple[bool, str, str]:
    """Multimodal AI path: valid official value + no contradiction with facts."""
    raw = str(answer or "").strip()
    if not raw or _is_generic_option(raw):
        return False, "", ""

    if _contradicts_facts(spec, raw, facts, bundle):
        return False, "", ""

    certain, source, quote = _is_certain_fill(spec, raw, facts, understanding, bundle)
    if certain:
        return True, source, quote

    if spec.options:
        if spec.option_by_label(raw) is None:
            return False, "", ""
        return True, "ai", raw

    return False, "", ""


def _fuzzy_option_match(
    spec: SchemaField,
    corpus: str,
    facts: Mapping[str, Any],
    understanding: Understanding,
    bundle: FactBundle | None,
) -> tuple[str, str, str] | None:
    if not spec.options:
        return None
    for option in spec.options[:80]:
        label = option.display_name.strip()
        if not label or _is_generic_option(label):
            continue
        certain, _, quote = _is_certain_fill(spec, label, facts, understanding, bundle)
        if certain:
            return label, quote, quote
    return None


def _infer_from_spec_keys(spec: SchemaField, bundle: FactBundle | None, understanding: Understanding) -> tuple[str, str, str]:
    specs = {**(bundle.specs if bundle else {}), **understanding.specs}
    for key, hints in SPEC_KEY_HINTS.items():
        value = str(specs.get(key) or "").strip()
        if not value:
            continue
        if not _wanted(spec.name, hints) and _norm(key) not in _norm(spec.name):
            continue
        if spec.options:
            applied = _apply_option(spec, value)
            if applied is not None:
                return value, "excel", f"{SPEC_LABELS.get(key, key)} {value}"
        elif _field_related(spec, key):
            return value, "excel", f"{SPEC_LABELS.get(key, key)} {value}"
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
        raw = str(
            (bundle.specs.get("model") if bundle else "")
            or understanding.specs.get("model")
            or defaults.get("model")
            or ""
        ).strip()
        return (raw, "excel", raw) if raw else ("", "", "")
    if _wanted(spec.name, COLOR_HINTS):
        if understanding.colors:
            return understanding.colors[0], "vision", understanding.colors[0]
        color = (bundle.specs.get("color") if bundle else "") or ""
        if color:
            return re_split_first(color), "excel", color
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
    facts: Mapping[str, Any],
) -> tuple[Any | None, str, str]:
    guess, src, quote = _local_guess(spec, understanding, defaults, bundle)
    if spec.options:
        if guess:
            certain, c_src, c_quote = _is_certain_fill(spec, guess, facts, understanding, bundle)
            if certain:
                applied = _apply_option(spec, guess)
                if applied is not None:
                    return applied, c_src or src, c_quote or quote
        fuzzy = _fuzzy_option_match(spec, "", facts, understanding, bundle)
        if fuzzy:
            applied = _apply_option(spec, fuzzy[0])
            if applied is not None:
                return applied, "excel", fuzzy[2]
        return None, "", ""
    if guess:
        certain, c_src, c_quote = _is_certain_fill(spec, guess, facts, understanding, bundle)
        if certain:
            return guess, c_src or src, c_quote or quote
    return None, "", ""


def align_attributes(
    group: SchemaField,
    understanding: Understanding,
    defaults: Mapping[str, Any],
    ai: AiClient | None,
    bundle: FactBundle | None,
    result: FillResult,
    images: Sequence[ImageInput | BankImage] | None = None,
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
        applied, src, quote = _resolve_spec(spec, group.id, understanding, defaults, bundle, facts)
        if applied is not None:
            values[spec.id] = applied
            result.record_evidence(f"{group.id}.{spec.id}", src, quote)

    unresolved: list[SchemaField] = []
    for spec in group.children:
        if spec.id in values:
            continue
        if not spec.required or not _attr_fillable(spec):
            continue
        unresolved.append(spec)

    unresolved.sort(key=lambda item: (not item.required, item.id))
    for batch_start in range(0, len(unresolved), AI_BATCH):
        batch = unresolved[batch_start : batch_start + AI_BATCH]
        if not batch or ai is None:
            break
        resolved = _ask_attributes(ai, batch, understanding, bundle, result, group.id, images)
        result.stats.ai_calls += 1
        for spec in batch:
            answer = resolved.get(spec.id, "")
            if not answer:
                continue
            if spec.options:
                applied = _apply_option(spec, answer)
            else:
                certain, _, _ = _is_certain_fill(spec, answer, facts, understanding, bundle)
                trusted, _, _ = _trust_ai_map_answer(spec, answer, facts, understanding, bundle)
                applied = answer if certain or trusted else None
            if applied is not None:
                values[spec.id] = applied

    for spec in unresolved:
        if spec.required and spec.id not in values:
            result.stats.blocked_no_evidence += 1
            result.add_issue_once(
                {
                    "field_id": spec.id,
                    "field_name": spec.name or spec.id,
                    "level": "red",
                    "message": "平台必填字段无法百分百确定，请补事实或人工填写",
                    "path": f"{group.id}.{spec.id}",
                    "options": [{"value": o.value, "label": o.display_name} for o in spec.options[:60]]
                    if spec.options
                    else [],
                }
            )

    return values


def _ask_attributes(
    ai: AiClient,
    specs: Sequence[SchemaField],
    understanding: Understanding,
    bundle: FactBundle | None,
    result: FillResult,
    group_id: str,
    images: Sequence[ImageInput | BankImage] | None = None,
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
            "field_type": spec.type,
            "options": [
                option.display_name for option in spec.options[:50] if not _is_generic_option(option.display_name)
            ],
        }
        for spec in specs
    }
    image_inputs = _coerce_images(images)
    try:
        if image_inputs:
            payload = ai.map_attributes(images=image_inputs, facts=facts, attributes=question)
        else:
            prompt = (
                "Map seller facts to official category fields (dropdown options OR text inputs).\n"
                "For option fields use exact option text; for text/input fields use the factual text.\n"
                "Only fill when the seller would be 100% sure from facts and photos.\n"
                "If ambiguous, leave empty. Never pick Other / 其他.\n\n"
                f"Facts: {json.dumps(facts, ensure_ascii=False)}\n"
                f"Fields: {json.dumps(question, ensure_ascii=False)}\n"
            )
            payload = ai.chat_json([{"role": "user", "content": prompt}], temperature=0.0)
    except (AiUnavailable, ValueError, requests.RequestException):
        return {}
    out: dict[str, str] = {}
    for spec in specs:
        answer = str(payload.get(spec.id) or "").strip()
        if not answer:
            continue
        trusted, source, quote = _trust_ai_map_answer(spec, answer, facts, understanding, bundle)
        if not trusted:
            continue
        out[spec.id] = answer
        result.record_evidence(f"{group_id}.{spec.id}", source, quote or answer)
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
    images: Sequence[ImageInput | BankImage] | None = None,
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
            chunk = align_attributes(group, understanding, layered, ai, bundle, result, images)
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
