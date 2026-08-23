"""Turn a pile of photos and a price into a schema-valid draft.

The split matters: the model is used for the two things it is good at
(recognising the goods, writing English copy) and nothing else. Category
placement is a guided descent over the official tree, attribute values are
matched against the official option lists, and trade terms come from the shop's
own defaults. Anything that cannot be resolved becomes a red flag for the
seller instead of a guess sent to Alibaba.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from sqlalchemy import func
from sqlalchemy.orm import Session

from ai import AiClient, AiUnavailable, Copy, ImageInput, Understanding  # noqa: E402
from icbu_api import IcbuApi  # noqa: E402
from schema import (  # noqa: E402
    SchemaField,
    ValidationIssue,
    index_fields,
    parse_schema,
    validate_values,
)

from ..models import CategoryMemory, Shop
from . import audit_logistics, catalog, defaults as defaults_service, quality, templates as template_service
from .fact_bundle import FactBundle
from .images import BankImage
from .schema_fill import ATTR_GROUPS, FillResult, align_attributes, apply_trade_from_facts

MAX_DESCENT_DEPTH = 6
BEAM_WIDTH = 3
LEARNING_PRODUCTS = 20
CONFIDENT = 0.85
UNCERTAIN = 0.6


@dataclass
class DraftResult:
    category_id: str = ""
    category_name: str = ""
    category_confidence: float = 0.0
    category_candidates: list[dict[str, Any]] = field(default_factory=list)
    values: dict[str, Any] = field(default_factory=dict)
    issues: list[dict[str, Any]] = field(default_factory=list)
    ai: dict[str, Any] = field(default_factory=dict)
    title: str = ""
    status: str = "red"

    def add_issue(self, field_id: str, name: str, level: str, message: str) -> None:
        self.issues.append({"field_id": field_id, "field_name": name, "level": level, "message": message, "path": field_id})


def _norm(text: str) -> str:
    return re.sub(r"[\s/_-]+", "", (text or "").strip().lower())


def signature_of(understanding: Understanding) -> str:
    """Stable key for 'the shop already listed something like this'."""
    base = understanding.category_hint or understanding.product_name
    return _norm(base)[:180]


# --------------------------------------------------------------------------
# category
# --------------------------------------------------------------------------


def _match_child(children: Sequence[Any], text: str) -> Any | None:
    needle = _norm(text)
    if not needle:
        return None
    for node in children:
        if _norm(node.name) == needle or _norm(node.cn_name) == needle:
            return node
    # Substring matching only on names long enough to be meaningful; short
    # branch names like "Art" match far too much near the root.
    for node in children:
        name = _norm(node.name)
        if len(name) >= 5 and (name in needle or needle in name):
            return node
    return None


def _context_of(understanding: Understanding) -> dict[str, Any]:
    return {
        "product": understanding.product_name,
        "category_hint": understanding.category_hint,
        "material": understanding.material,
        "usage": understanding.usage,
        "features": understanding.features[:4],
    }


def _resolve_labels(nodes: Sequence[Any], picked: Sequence[str]) -> list[Any]:
    by_label = {catalog.label(node): node for node in nodes}
    chosen: list[Any] = []
    for label in picked:
        node = by_label.get(label)
        if node is None:
            node = _match_child(nodes, label)
        if node is not None and node not in chosen:
            chosen.append(node)
    return chosen


def collect_leaf_candidates(
    db: Session,
    api: IcbuApi,
    understanding: Understanding,
    ai: AiClient | None,
    beam_width: int = BEAM_WIDTH,
) -> list[Any]:
    """Walk down the official tree keeping several branches alive.

    Greedy descent cannot recover from a bad turn near the root — a paint brush
    that goes into «Home & Garden» at level one can only ever end up in the
    wrong leaf. Keeping a few branches and reranking the leaves at the end fixes
    the common failure without crawling the whole tree.
    """
    root = catalog.get_node(db, api, catalog.ROOT_ID)
    if root is None:
        return []

    context = _context_of(understanding)
    frontier = [root]
    leaves: list[Any] = []

    for _ in range(MAX_DESCENT_DEPTH):
        if not frontier:
            break
        children: list[Any] = []
        for node in frontier:
            children.extend(catalog.get_children(db, api, node))
        if not children:
            break

        direct = [
            node
            for node in (
                _match_child(children, understanding.category_hint),
                _match_child(children, understanding.product_name),
            )
            if node is not None
        ]
        picked: list[Any] = list(dict.fromkeys(direct))

        if len(picked) < beam_width and ai is not None:
            try:
                labels = ai.shortlist(
                    "Alibaba.com wholesale category tree", [catalog.label(c) for c in children], context, beam_width
                )
            except (AiUnavailable, ValueError):
                labels = []
            for node in _resolve_labels(children, labels):
                if node not in picked:
                    picked.append(node)

        picked = picked[:beam_width]
        if not picked:
            break

        leaves.extend(node for node in picked if node.is_leaf and node not in leaves)
        frontier = [node for node in picked if not node.is_leaf]

    return leaves


def shop_category_hints(db: Session, api: IcbuApi, shop: Shop, limit: int = 8) -> list[Any]:
    """Categories this shop already sells in — a strong prior for the next product."""
    remembered = (
        db.query(CategoryMemory)
        .filter(CategoryMemory.shop_id == shop.id)
        .order_by(CategoryMemory.hits.desc())
        .limit(limit)
        .all()
    )
    nodes = []
    for row in remembered:
        node = catalog.get_node(db, api, row.category_id)
        if node is not None and node.is_leaf:
            nodes.append(node)
    return nodes


def resolve_category(
    db: Session,
    api: IcbuApi,
    shop: Shop,
    understanding: Understanding,
    ai: AiClient | None,
    forced_category_id: str = "",
) -> tuple[str, str, float, list[dict[str, Any]]]:
    """Return (category_id, display name, confidence, other plausible leaves)."""
    if forced_category_id:
        node = catalog.get_node(db, api, forced_category_id)
        if node is not None:
            return node.category_id, catalog.label(node), 1.0, []

    signature = signature_of(understanding)
    if signature:
        remembered = (
            db.query(CategoryMemory)
            .filter(CategoryMemory.shop_id == shop.id, CategoryMemory.signature == signature)
            .one_or_none()
        )
        if remembered is not None:
            remembered.hits += 1
            db.commit()
            return remembered.category_id, remembered.category_name, 0.95, []

    candidates = collect_leaf_candidates(db, api, understanding, ai)
    for node in shop_category_hints(db, api, shop):
        if node not in candidates:
            candidates.append(node)
    if not candidates:
        return "", "", 0.0, []

    # English leaf names are often ambiguous ("Paint Brushes" is both an
    # artist's brush and a decorator's brush), so the Chinese name goes into the
    # candidate text as well — it disambiguates most of those pairs.
    paths = {}
    for node in candidates:
        trail = catalog.path_of(db, api, node.category_id)
        text = " > ".join(catalog.label(item) for item in trail) or catalog.label(node)
        paths[text] = node

    if len(candidates) == 1 or ai is None:
        node = candidates[0]
        return node.category_id, catalog.label(node), 0.5 if ai is None else 0.7, catalog.summarise(candidates)

    try:
        answer = ai.rank_categories(list(paths), _context_of(understanding))
    except (AiUnavailable, ValueError):
        answer = {}

    chosen = paths.get(str(answer.get("choice") or ""))
    confidence = float(answer.get("confidence") or 0.0)
    if chosen is None:
        chosen, confidence = candidates[0], min(confidence, 0.5)

    return chosen.category_id, catalog.label(chosen), confidence, catalog.summarise(candidates)


def _still_learning(db: Session, shop: Shop) -> bool:
    confirmed = (
        db.query(func.coalesce(func.sum(CategoryMemory.hits), 0))
        .filter(CategoryMemory.shop_id == shop.id)
        .scalar()
        or 0
    )
    return int(confirmed) < LEARNING_PRODUCTS


def remember_category(db: Session, shop: Shop, understanding: Understanding, category_id: str, category_name: str) -> None:
    signature = signature_of(understanding)
    if not signature or not category_id:
        return
    row = (
        db.query(CategoryMemory)
        .filter(CategoryMemory.shop_id == shop.id, CategoryMemory.signature == signature)
        .one_or_none()
    )
    if row is None:
        db.add(CategoryMemory(shop_id=shop.id, signature=signature, category_id=category_id, category_name=category_name))
    else:
        row.category_id = category_id
        row.category_name = category_name
        row.hits += 1
    db.commit()


# --------------------------------------------------------------------------
# trade terms from shop defaults
# --------------------------------------------------------------------------


def _option_value(spec: SchemaField | None, label: str, fallback_first: bool = False) -> str:
    if spec is None:
        return ""
    option = spec.option_by_label(label) if label else None
    if option is not None:
        return option.value
    if fallback_first and spec.options:
        return spec.options[0].value
    return ""


def apply_trade_terms(
    specs: Mapping[str, SchemaField],
    values: dict[str, Any],
    defaults: Mapping[str, Any],
    price: str,
    moq: str,
    ladder: Mapping[str, dict[str, str]] | None = None,
) -> None:
    unit = _option_value(specs.get("priceUnit"), str(defaults.get("priceUnit") or "Piece/Pieces"), fallback_first=True)
    if unit:
        values["priceUnit"] = unit

    sale_type = _option_value(specs.get("saleType"), str(defaults.get("saleType") or "Unit"), fallback_first=True)
    if sale_type:
        values["saleType"] = sale_type

    # Tiered pricing is the shape that matches "one price plus a MOQ".
    price_setting = _option_value(specs.get("scPrice"), "Tiered pricing by quantity")
    if price_setting:
        values["scPrice"] = price_setting
    if ladder:
        values["ladderPrice"] = dict(ladder)
    elif price and moq:
        values["ladderPrice"] = {"ladderPrice_0": {"quantity": moq, "price": price}}
    if moq:
        values["minOrderQuantity"] = moq

    shipping = specs.get("shippingTemplate")
    if shipping is not None:
        template_id = str(defaults.get("shippingTemplateId") or "")
        child = shipping.child("shippingTemplateId")
        if template_id and child is not None and child.has_option(template_id):
            values["shippingTemplate"] = {
                "templateType": _option_value(shipping.child("templateType"), "MERCHANT_OWN_TEMPLATE"),
                "shippingTemplateId": template_id,
            }
        else:
            negotiated = _option_value(shipping.child("templateType"), "FREIGHT_NEGOTIATION", fallback_first=True)
            if negotiated:
                values["shippingTemplate"] = {"templateType": negotiated}

    # Goods with batteries need several attributes at once, and the option
    # labels are translated per language, so match on the official value too.
    _apply_listed_option(specs, values, "logisticsProperty", defaults.get("logisticsProperty") or "general_cargo_0")

    for key, field_id in (("pkgWeight", "pkgWeight"), ("semiManagedPeriod", "semiManagedPeriod")):
        if defaults.get(key) and field_id in specs:
            values[field_id] = str(defaults[key])

    measure = specs.get("pkgMeasure")
    dimensions = {
        "length": defaults.get("pkgLength"),
        "width": defaults.get("pkgWidth"),
        "height": defaults.get("pkgHeight"),
    }
    if measure is not None and all(dimensions.values()):
        values["pkgMeasure"] = {key: str(value) for key, value in dimensions.items()}

    sample = specs.get("marketSample")
    if sample is not None:
        chosen = _option_value(sample, str(defaults.get("marketSample") or "Unavailable"))
        if chosen:
            values["marketSample"] = chosen

    # Trade fields the official score counts. Values come from shop defaults,
    # never from the model inventing a port or payment method.
    _apply_listed_option(specs, values, "paymentMethod", defaults.get("paymentMethod") or "T/T")
    _apply_listed_option(specs, values, "port", defaults.get("port") or "")
    _apply_listed_option(specs, values, "market", defaults.get("market") or "询盘")
    _apply_ladder_period(specs, values, defaults, moq)


def _apply_listed_option(
    specs: Mapping[str, SchemaField],
    values: dict[str, Any],
    field_id: str,
    wanted: Any,
) -> None:
    spec = specs.get(field_id)
    if spec is None or wanted in (None, ""):
        return
    labels = [item.strip() for item in re.split(r"[,，;|]+", str(wanted)) if item.strip()]
    if spec.type in {"multiCheck", "multiInput"}:
        picked = []
        for label in labels:
            option = spec.option_by_label(label)
            if option is not None:
                picked.append(option.value)
        if picked:
            values[field_id] = picked
        return
    if spec.options:
        chosen = _option_value(spec, labels[0] if labels else str(wanted))
        if chosen:
            values[field_id] = chosen
        return
    values[field_id] = str(wanted)


def _apply_ladder_period(
    specs: Mapping[str, SchemaField],
    values: dict[str, Any],
    defaults: Mapping[str, Any],
    moq: str,
) -> None:
    spec = specs.get("ladderPeriod")
    days = str(defaults.get("ladderPeriod") or "15").strip()
    if spec is None or not days:
        return
    slot = spec.children[0] if spec.children else None
    if slot is None:
        values["ladderPeriod"] = days
        return
    children = list(slot.children or [])
    payload: dict[str, Any] = {}
    if children:
        for child in children:
            name = f"{child.id} {child.name}".lower()
            if "quant" in name or child.id.endswith("quantity"):
                payload[child.id] = moq or "1"
            elif any(token in name for token in ("period", "time", "day", "lead")):
                payload[child.id] = days
        if not payload and len(children) >= 2:
            payload[children[0].id] = moq or "1"
            payload[children[1].id] = days
        elif not payload:
            payload[children[0].id] = days
        values["ladderPeriod"] = {slot.id: payload}
        return
    values["ladderPeriod"] = {slot.id: {"quantity": moq or "1", "period": days}}


def apply_content(
    specs: Mapping[str, SchemaField],
    values: dict[str, Any],
    title: str,
    keywords: Sequence[str],
    highlights: str,
    images: Sequence[BankImage],
    copy: Copy | None = None,
    understanding: Understanding | None = None,
) -> None:
    if title and "productTitle" in specs:
        values["productTitle"] = title

    keyword_spec = specs.get("productKeywords")
    if keyword_spec is not None and keywords:
        slots = [child.id for child in keyword_spec.children] or ["productKeywords_0"]
        limit = keyword_spec.max_items or len(slots)
        values["productKeywords"] = {
            slot: keyword for slot, keyword in zip(slots[:limit], keywords)
        }

    image_spec = specs.get("scImages")
    if image_spec is not None and images:
        limit = image_spec.max_items or 6
        slots = [child.id for child in image_spec.children] or [f"scImages_{i}" for i in range(limit)]
        values["scImages"] = {
            slot: image.as_schema_value() for slot, image in zip(slots[:limit], images)
        }

    if highlights and "textDesc" in specs:
        values["textDesc"] = highlights

    rich = _super_text(copy, understanding, highlights)
    if rich and "superText" in specs:
        values["superText"] = rich
        desc_type = specs.get("productDescType")
        if desc_type is not None:
            chosen = _option_value(desc_type, "富文本") or _option_value(desc_type, "普通编辑", fallback_first=True)
            if chosen:
                values["productDescType"] = chosen
    else:
        desc_type = specs.get("productDescType")
        if desc_type is not None:
            chosen = _option_value(desc_type, "普通编辑", fallback_first=True)
            if chosen:
                values["productDescType"] = chosen

    faqs = list(copy.faqs) if copy is not None else []
    faq_spec = specs.get("companyFaqDesc")
    if faq_spec is not None and faqs:
        values["companyFaqDesc"] = [
            {"question": item.get("question") or "", "answers": item.get("answer") or item.get("answers") or ""}
            for item in faqs
            if item.get("question") and (item.get("answer") or item.get("answers"))
        ]

    detail = specs.get("detailImage")
    if detail is not None and images:
        gallery = _option_value(detail.child("gallery"), "Detail shot", fallback_first=True)
        values["detailImage"] = [
            {
                "gallery": gallery,
                "images": [image.as_schema_value() for image in images],
            }
        ]


def _super_text(copy: Copy | None, understanding: Understanding | None, highlights: str) -> str:
    """Rich detail from evidence only. No certs, no invented brand."""
    blocks: list[str] = []
    lead = (copy.highlights if copy else "") or highlights
    if lead:
        blocks.append(f"<p>{html.escape(lead)}</p>")
    points = list(copy.selling_points) if copy else []
    if points:
        items = "".join(f"<li>{html.escape(item)}</li>" for item in points)
        blocks.append(f"<ul>{items}</ul>")
    specs = dict(understanding.specs) if understanding else {}
    if understanding and understanding.material:
        specs.setdefault("Material", understanding.material)
    if understanding and understanding.colors:
        specs.setdefault("Color", ", ".join(understanding.colors))
    if specs:
        items = "".join(f"<li>{html.escape(str(key))}: {html.escape(str(value))}</li>" for key, value in specs.items())
        blocks.append(f"<ul>{items}</ul>")
    return "".join(blocks)


# --------------------------------------------------------------------------
# assembly
# --------------------------------------------------------------------------


def _aligned_attribute_labels(
    specs: Mapping[str, SchemaField],
    values: Mapping[str, Any],
) -> dict[str, str]:
    labels: dict[str, str] = {}
    for group_id in ATTR_GROUPS:
        group = specs.get(group_id)
        if group is None:
            continue
        bucket = values.get(group_id)
        if not isinstance(bucket, Mapping):
            continue
        for child_id, raw in bucket.items():
            if raw in (None, "", [], {}):
                continue
            child = group.child(str(child_id))
            if child is None:
                continue
            name = child.name or child.id
            if child.options:
                option = child.option_by_value(str(raw))
                labels[name] = option.display_name if option is not None else str(raw)
            else:
                labels[name] = str(raw)
    return labels


def copy_facts_for_write(
    understanding: Understanding,
    *,
    category_name: str,
    price: str,
    moq: str,
    specs: Mapping[str, SchemaField],
    values: Mapping[str, Any],
    fact_bundle: FactBundle | None = None,
) -> dict[str, Any]:
    facts: dict[str, Any] = {
        "product_name": understanding.product_name,
        "material": understanding.material,
        "colors": understanding.colors,
        "style": understanding.style,
        "usage": understanding.usage,
        "audience": understanding.audience,
        "features": understanding.features,
        "specs": understanding.specs,
        "is_set": understanding.is_set,
        "category": category_name,
        "moq": moq,
        "unit_price": price,
    }
    if fact_bundle is not None:
        bundle_facts = fact_bundle.facts_for_ai(understanding)
        for key in (
            "note",
            "brand",
            "origin",
            "text_blob",
            "specs_labeled",
            "price_tiers",
            "sku",
            "name",
        ):
            value = bundle_facts.get(key)
            if value not in (None, "", [], {}):
                facts[key] = value
    aligned = _aligned_attribute_labels(specs, values)
    if aligned:
        facts["official_attributes"] = aligned
    return facts


def rescore_draft(draft: Any, xml: str, *, db: Session | None = None, shop: Shop | None = None) -> None:
    """Refresh local quality estimate and issues after a manual edit."""
    values = json.loads(getattr(draft, "values_json", None) or "{}")
    fields = parse_schema(xml)
    images = json.loads(getattr(draft, "images_json", None) or "[]")
    ai_payload = json.loads(getattr(draft, "ai_json", None) or "{}")
    if not isinstance(ai_payload, dict):
        ai_payload = {}
    report = quality.score_listing(
        values=values,
        fields=fields,
        image_count=len(images) if isinstance(images, list) else 0,
        price=str(getattr(draft, "price", "") or ""),
        moq=str(getattr(draft, "moq", "") or ""),
        category_id=str(getattr(draft, "category_id", "") or ""),
    )
    ai_payload["quality"] = report
    draft.ai_json = json.dumps(ai_payload, ensure_ascii=False)

    issues = [issue.as_dict() for issue in validate_values(fields, values)]
    logistics_panel = audit_logistics.panel_for_draft(db, shop, draft, xml=xml, values=values) if shop is not None and db is not None else {"items": []}
    for item in logistics_panel.get("items") or []:
        if item.get("ok"):
            continue
        issues.append(
            {
                "field_id": str(item.get("id") or "logistics"),
                "field_name": str(item.get("label") or "物流"),
                "level": "red",
                "message": str(item.get("missing_hint") or "物流信息不完整"),
                "path": f"logistics.{item.get('id')}",
            }
        )
    gap = quality.quality_issue(report)
    if gap:
        logistics_labels = {"运费模板", "物流属性", "包装重量", "包装尺寸"}
        other_missing = [label for label in (report.get("missing") or []) if label not in logistics_labels]
        if other_missing:
            gap = dict(gap)
            gap["message"] = (
                f"预估 {report.get('score')} / 5.0（至少 {quality.MIN_QUALITY_SCORE} 可发），"
                f"还差：{'、'.join(other_missing)}。"
            )
            issues.append(gap)
    if not getattr(draft, "price", None):
        issues.append({"field_id": "price", "field_name": "价格", "level": "red", "message": "价格要你来定"})
    if not getattr(draft, "moq", None):
        issues.append({"field_id": "minOrderQuantity", "field_name": "起订量", "level": "red", "message": "起订量要你来定"})
    draft.issues_json = json.dumps(issues, ensure_ascii=False)
    draft.status = status_of(issues)


def understand(ai: AiClient | None, images: Sequence[ImageInput], note: str) -> tuple[Understanding, str]:
    if ai is None:
        return Understanding(product_name=note, category_hint=note, confidence=0.0), "没有配置模型，AI 成稿已跳过"
    try:
        return ai.understand(images, note), ""
    except (AiUnavailable, ValueError) as exc:
        return Understanding(product_name=note, category_hint=note, confidence=0.0), str(exc)


def build_draft(
    db: Session,
    api: IcbuApi,
    shop: Shop,
    *,
    understanding: Understanding,
    images: Sequence[BankImage],
    price: str,
    moq: str,
    defaults: Mapping[str, Any],
    ai: AiClient | None,
    forced_category_id: str = "",
    language: str = "en_US",
    copy_angle: str = "",
    extra_defaults: Mapping[str, Any] | None = None,
    fact_bundle: FactBundle | None = None,
) -> DraftResult:
    result = DraftResult(ai={"understanding": understanding.raw})
    if fact_bundle is not None:
        understanding = fact_bundle.enrich(understanding)
        result.ai["fact_bundle"] = fact_bundle.as_dict()

    category_id, category_name, confidence, candidates = resolve_category(
        db, api, shop, understanding, ai, forced_category_id
    )
    result.category_id = category_id
    result.category_name = category_name
    result.category_confidence = confidence
    result.category_candidates = candidates

    if not category_id:
        result.add_issue("category", "商品类目", "red", "没能定位到叶子类目，请手动选择")
        return result

    node = catalog.get_node(db, api, category_id)
    if node is not None and not node.is_leaf:
        result.add_issue("category", "商品类目", "red", "停在了非叶子类目，必须选到最末级才能发布")
        return result

    xml = catalog.get_schema_xml(db, api, category_id, language)
    fields = parse_schema(xml)
    specs = index_fields(fields)

    category_values = {}
    template = template_service.find_for(db, shop.id, category_id)
    if template is not None:
        category_values = template_service.values_of(template)
    layered = defaults_service.layer_defaults(defaults, category_values, extra_defaults)

    fill_state = FillResult(values={"catId": category_id})
    for group_id in ATTR_GROUPS:
        group = specs.get(group_id)
        if group is None or not group.children:
            continue
        chunk = align_attributes(group, understanding, layered, ai, fact_bundle, fill_state, images)
        if chunk:
            fill_state.values[group_id] = {**(fill_state.values.get(group_id) or {}), **chunk}
    apply_trade_from_facts(specs, fill_state.values, layered, fact_bundle, price, moq, fill_state)
    values = fill_state.values
    result.issues.extend(fill_state.issues)
    result.ai["fill_stats"] = fill_state.stats.as_dict()
    result.ai["evidence"] = {path: ev.as_dict() for path, ev in fill_state.evidence.items()}

    title_spec = specs.get("productTitle")
    keyword_spec = specs.get("productKeywords")
    title_limit = (title_spec.max_length if title_spec else None) or 128
    keyword_count = (keyword_spec.max_items if keyword_spec else None) or 3
    if keyword_spec is not None and keyword_spec.min_items:
        keyword_count = max(keyword_count, keyword_spec.min_items)
    keyword_count = max(keyword_count, 3)

    copy_facts = copy_facts_for_write(
        understanding,
        category_name=category_name,
        price=price,
        moq=moq,
        specs=specs,
        values=values,
        fact_bundle=fact_bundle,
    )

    copy_confidence = 0.0
    if ai is not None:
        try:
            copy = ai.write_copy(
                understanding,
                title_limit=title_limit,
                keyword_count=keyword_count,
                extra_facts=copy_facts,
                angle=copy_angle,
            )
            copy_confidence = copy.confidence
            if len(copy.keywords) < keyword_count:
                result.add_issue(
                    "productKeywords",
                    "关键词",
                    "red",
                    f"AI 只生成了 {len(copy.keywords)} 个关键词，需要 {keyword_count} 个 factual 词组，请重成稿或手改",
                )
            if not copy.title.strip():
                result.add_issue("productTitle", "商品标题", "red", "AI 没生成英文标题，请重成稿或手改")
            result.ai["copy"] = {
                "title": copy.title,
                "keywords": copy.keywords,
                "highlights": copy.highlights,
                "selling_points": copy.selling_points,
                "faqs": copy.faqs,
                "facts_used": copy_facts,
            }
            apply_content(
                specs, values, copy.title, copy.keywords, copy.highlights, images, copy=copy, understanding=understanding
            )
            result.title = copy.title
        except (AiUnavailable, ValueError) as exc:
            result.add_issue("productTitle", "商品标题", "red", f"AI 文案没生成成功：{exc}")
            apply_content(specs, values, "", [], "", images, understanding=understanding)
    else:
        apply_content(specs, values, "", [], "", images, understanding=understanding)

    result.values = values
    report = quality.score_listing(
        values=values,
        fields=fields,
        image_count=len(images),
        price=price,
        moq=moq,
        category_id=category_id,
    )
    result.ai["quality"] = report
    gap = quality.quality_issue(report)
    if gap:
        result.issues.append(gap)

    # Attribute alignment already reported the unresolved required attributes,
    # with their option lists attached; the generic "required and empty" row
    # from the validator would only duplicate them.
    reported = {issue["path"] for issue in result.issues}
    for issue in validate_values(fields, values):
        if issue.path not in reported:
            result.issues.append(issue.as_dict())

    if not images:
        result.add_issue("scImages", "产品图片", "red", "至少要一张图片")
    if not price:
        result.add_issue("price", "价格", "red", "价格要你来定，AI 不代填")
    if not moq:
        result.add_issue("minOrderQuantity", "起订量", "red", "起订量要你来定")

    if category_id and confidence < UNCERTAIN:
        result.add_issue("category", "商品类目", "red", f"类目「{category_name}」置信度只有 {confidence:.0%}，确认一下")
    elif category_id and confidence < CONFIDENT:
        result.add_issue("category", "商品类目", "yellow", f"类目「{category_name}」置信度 {confidence:.0%}")
    elif category_id and not forced_category_id and _still_learning(db, shop):
        # A wrong category invalidates every attribute under it, and the model
        # is confidently wrong often enough that a new shop should eyeball the
        # first listings. Once the shop has confirmed enough, this stops.
        result.add_issue("category", "商品类目", "yellow", f"新店铺前 {LEARNING_PRODUCTS} 条建议核对类目：{category_name}")

    if understanding.image_quality not in {"ok", ""}:
        result.add_issue("scImages", "产品图片", "yellow", f"图片质量提示：{understanding.image_quality}")
    if 0 < copy_confidence < UNCERTAIN:
        result.add_issue("productTitle", "商品标题", "yellow", "AI 对文案不太确定，扫一眼标题")

    result.status = status_of(result.issues)
    if result.status != "red":
        remember_category(db, shop, understanding, category_id, category_name)
    return result


def status_of(issues: Sequence[Mapping[str, Any]]) -> str:
    levels = {str(issue.get("level")) for issue in issues}
    if "red" in levels:
        return "red"
    if "yellow" in levels:
        return "yellow"
    return "green"


def revalidate(xml: str, values: Mapping[str, Any]) -> list[ValidationIssue]:
    return validate_values(parse_schema(xml), values)
