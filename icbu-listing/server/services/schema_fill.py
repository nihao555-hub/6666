"""Evidence-gated, iterative schema fill for any leaf category.

One fact table in, schema.get rules out. We do not materialise 7521 Excel forms.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import requests
from ai import AiClient, AiUnavailable, Copy, Understanding  # noqa: E402
from schema import SchemaField, ValidationIssue, index_fields, parse_schema, validate_values  # noqa: E402

from . import defaults as defaults_service, quality, templates as template_service
from .fact_bundle import FactBundle, Evidence

# Fields the seller or shop must supply — AI must never invent these.
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

ORIGIN_HINTS = ("origin", "place of origin", "产地", "原产地")
BRAND_HINTS = ("brand", "品牌", "商标")
MODEL_HINTS = ("model", "型号", "model number")
COLOR_HINTS = ("color", "colour", "颜色", "色号", "lead color", "铅芯颜色")
MATERIAL_HINTS = ("material", "材质", "面料", "毛材", "hair material")


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

    def record_evidence(self, path: str, source: str, quote: str = "") -> None:
        if path and source:
            self.evidence[path] = Evidence(source=source, quote=quote[:240])


def _norm(text: str) -> str:
    return " ".join((text or "").lower().replace("_", " ").split())


def _wanted(name: str, hints: tuple[str, ...]) -> bool:
    lowered = (name or "").lower()
    return any(hint in lowered for hint in hints)


def _local_guess(
    spec: SchemaField,
    understanding: Understanding,
    defaults: Mapping[str, Any],
    bundle: FactBundle | None,
) -> tuple[str, str, str]:
    """Return (guess, evidence_source, quote). Empty guess means no evidence."""
    if _wanted(spec.name, ORIGIN_HINTS):
        raw = str((bundle.origin if bundle else "") or defaults.get("origin") or "").strip()
        if raw:
            return raw, "shop" if defaults.get("origin") else "excel", raw
        return "", "", ""
    if _wanted(spec.name, BRAND_HINTS):
        raw = str((bundle.brand if bundle else "") or defaults.get("brand") or "").strip()
        if raw:
            return raw, "excel" if bundle and bundle.brand else "shop", raw
        return "", "", ""
    if _wanted(spec.name, MODEL_HINTS):
        raw = str(defaults.get("model") or "").strip()
        return (raw, "shop", raw) if raw else ("", "", "")
    if _wanted(spec.name, COLOR_HINTS):
        if understanding.colors:
            return understanding.colors[0], "vision", understanding.colors[0]
        color = (bundle.specs.get("color") if bundle else "") or ""
        if color:
            first = re_split_first(color)
            return first, "excel", color
    if _wanted(spec.name, MATERIAL_HINTS):
        raw = understanding.material or (bundle.specs.get("material") if bundle else "") or ""
        raw = str(raw).strip()
        if raw:
            src = "vision" if understanding.material else "excel"
            return raw, src, raw
    for key, value in {**understanding.specs, **(bundle.specs if bundle else {})}.items():
        if _norm(key) == _norm(spec.name) or _norm(spec.name) in _norm(key):
            text = str(value).strip()
            if text:
                return text, "excel", text
    return "", "", ""


def re_split_first(text: str) -> str:
    import re

    for part in re.split(r"[,，/;；]", text):
        token = part.strip()
        if token:
            return token
    return text.strip()


def _apply_option(spec: SchemaField, raw: str) -> Any | None:
    if not raw:
        return None
    option = spec.option_by_label(raw)
    if option is None:
        return None
    return [option.value] if spec.type == "multiCheck" else option.value


def align_attributes(
    group: SchemaField,
    understanding: Understanding,
    defaults: Mapping[str, Any],
    ai: AiClient | None,
    bundle: FactBundle | None,
    result: FillResult,
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    unresolved: list[SchemaField] = []

    for spec in group.children:
        guess, src, quote = _local_guess(spec, understanding, defaults, bundle)
        if spec.options:
            applied = _apply_option(spec, guess)
            if applied is not None:
                values[spec.id] = applied
                result.record_evidence(f"{group.id}.{spec.id}", src or "fact", quote or guess)
                continue
            if spec.required or guess:
                unresolved.append(spec)
            continue
        if guess:
            values[spec.id] = guess
            result.record_evidence(f"{group.id}.{spec.id}", src or "fact", quote or guess)

    unresolved.sort(key=lambda item: (not item.required, item.id))
    unresolved = unresolved[:24]
    if unresolved and ai is not None:
        resolved = _ask_attributes(ai, unresolved, understanding, bundle, result)
        result.stats.ai_calls += 1
        for spec in unresolved:
            answer = resolved.get(spec.id, "")
            if not answer:
                continue
            applied = _apply_option(spec, answer)
            if applied is not None:
                values[spec.id] = applied

    for spec in group.children:
        if spec.required and spec.id not in values:
            result.stats.blocked_no_evidence += 1
            if spec.id in {u.id for u in unresolved}:
                result.issues.append(
                    {
                        "field_id": spec.id,
                        "field_name": spec.name or spec.id,
                        "level": "red",
                        "message": "平台必填属性缺少依据，AI 未填。请补事实或手动选择",
                        "path": f"{group.id}.{spec.id}",
                        "options": [{"value": o.value, "label": o.display_name} for o in spec.options[:60]],
                    }
                )

    return values


def _ask_attributes(
    ai: AiClient,
    specs: Sequence[SchemaField],
    understanding: Understanding,
    bundle: FactBundle | None,
    result: FillResult,
) -> dict[str, str]:
    facts = bundle.facts_for_ai(understanding) if bundle else {
        "product_name": understanding.product_name,
        "material": understanding.material,
        "colors": understanding.colors,
        "specs": understanding.specs,
        "features": understanding.features,
        "usage": understanding.usage,
    }
    question = {
        spec.id: {
            "attribute": spec.name or spec.id,
            "options": [option.display_name for option in spec.options[:40]],
        }
        for spec in specs
    }
    prompt = (
        "Map seller facts to official attribute options.\n"
        "Rules:\n"
        "- Only pick option text that matches seller facts verbatim or obviously.\n"
        "- If facts do not support an attribute, return empty string for that id.\n"
        "- Never pick Other / Custom / 其他. Never invent certifications or brands.\n\n"
        f"Facts: {json.dumps(facts, ensure_ascii=False)}\n"
        f"Attributes: {json.dumps(question, ensure_ascii=False)}\n\n"
        'Return JSON only: {"p-1": "China"}'
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
        if not _answer_supported(answer, facts, understanding):
            continue
        out[spec.id] = answer
        result.record_evidence(spec.id, "ai", answer)
    return out


def _answer_supported(answer: str, facts: Mapping[str, Any], understanding: Understanding) -> bool:
    blob = json.dumps(facts, ensure_ascii=False).lower() + " " + understanding.product_name.lower()
    blob += " " + " ".join(understanding.colors).lower()
    blob += " " + " ".join(str(v) for v in understanding.specs.values()).lower()
    needle = answer.lower().strip()
    if not needle:
        return False
    if needle in blob:
        return True
    for token in needle.replace("/", " ").split():
        if len(token) >= 2 and token in blob:
            return True
    return False


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
    apply_trade_terms(specs, values, defaults, final_price, final_moq)
    if bundle and bundle.ladder_values():
        values["ladderPrice"] = bundle.ladder_values()
        for slot, payload in bundle.ladder_values().items():
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
    """Iteratively fill values for one leaf schema from facts + gated AI."""
    fields = parse_schema(xml)
    specs = index_fields(fields)
    layered = defaults_service.layer_defaults(defaults, category_values, None)
    cat_id = str(category_id or layered.get("catId") or category_values.get("catId") or "")
    result = FillResult(values={"catId": cat_id})
    keywords = list(keywords or [])

    max_rounds = 3
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

    # Hallucination guard: AI-sourced attrs must appear in evidence with fact/vision/excel/shop
    for path, ev in list(result.evidence.items()):
        if ev.source == "ai" and not ev.quote:
            result.issues.append(
                {
                    "field_id": path,
                    "field_name": path,
                    "level": "red",
                    "message": "AI 填了但没有依据，已拦截",
                    "path": path,
                }
            )

    if not images_applied:
        result.issues.append(
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
    """Cheap contract check: schema XML must parse."""
    return validate_values(parse_schema(xml), {})


def sample_fill_report(xml: str, bundle: FactBundle, understanding: Understanding | None = None) -> FillResult:
    """Deterministic fill for contract tests — no live AI."""
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
