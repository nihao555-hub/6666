"""Turn a pile of photos and a price into a schema-valid draft.

The split matters: the model is used for the two things it is good at
(recognising the goods, writing English copy) and nothing else. Category
placement is a guided descent over the official tree, attribute values are
matched against the official option lists, and trade terms come from the shop's
own defaults. Anything that cannot be resolved becomes a red flag for the
seller instead of a guess sent to Alibaba.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from sqlalchemy import func
from sqlalchemy.orm import Session

from ai import AiClient, AiUnavailable, ImageInput, Understanding  # noqa: E402
from icbu_api import IcbuApi  # noqa: E402
from schema import (  # noqa: E402
    SchemaField,
    ValidationIssue,
    index_fields,
    parse_schema,
    validate_values,
)

from ..models import CategoryMemory, Shop
from . import catalog
from .images import BankImage

MAX_DESCENT_DEPTH = 6
BEAM_WIDTH = 3
LEARNING_PRODUCTS = 20
CONFIDENT = 0.85
UNCERTAIN = 0.6

# Category attribute names we can answer without asking the model.
ORIGIN_HINTS = ("place of origin", "origin", "产地", "原产地")
COLOR_HINTS = ("color", "colour", "颜色")
MATERIAL_HINTS = ("material", "材质", "材料")
BRAND_HINTS = ("brand", "品牌")
MODEL_HINTS = ("model number", "model", "型号")


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
# attributes
# --------------------------------------------------------------------------


def _wanted(name: str, hints: tuple[str, ...]) -> bool:
    lowered = (name or "").lower()
    return any(hint in lowered for hint in hints)


def _local_guess(spec: SchemaField, understanding: Understanding, defaults: Mapping[str, Any]) -> str:
    """Answer an attribute from facts we already hold, no model call."""
    if _wanted(spec.name, ORIGIN_HINTS):
        return str(defaults.get("origin") or "China")
    if _wanted(spec.name, BRAND_HINTS):
        return str(defaults.get("brand") or "")
    if _wanted(spec.name, MODEL_HINTS):
        return str(defaults.get("model") or "")
    if _wanted(spec.name, COLOR_HINTS) and understanding.colors:
        return understanding.colors[0]
    if _wanted(spec.name, MATERIAL_HINTS) and understanding.material:
        return understanding.material
    for key, value in understanding.specs.items():
        if _norm(key) == _norm(spec.name):
            return str(value)
    return ""


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
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Map what we know onto one attribute group (icbuCatProp / saleProp)."""
    values: dict[str, Any] = {}
    unresolved: list[SchemaField] = []
    issues: list[dict[str, Any]] = []

    for spec in group.children:
        guess = _local_guess(spec, understanding, defaults)
        if spec.options:
            applied = _apply_option(spec, guess)
            if applied is not None:
                values[spec.id] = applied
                continue
            if spec.required or guess:
                unresolved.append(spec)
            continue
        if guess:
            values[spec.id] = guess

    if unresolved and ai is not None:
        resolved = _ask_attributes(ai, unresolved, understanding)
        for spec in unresolved:
            answer = resolved.get(spec.id)
            applied = _apply_option(spec, answer or "")
            if applied is not None:
                values[spec.id] = applied

    for spec in unresolved:
        if spec.id in values or not spec.required:
            continue
        issues.append(
            {
                "field_id": spec.id,
                "field_name": spec.name or spec.id,
                "level": "red",
                "message": "平台必填属性，AI 没能对上官方选项，请选一个",
                "path": f"{group.id}.{spec.id}",
                "options": [{"value": o.value, "label": o.display_name} for o in spec.options[:60]],
            }
        )

    return values, issues


def _ask_attributes(ai: AiClient, specs: Sequence[SchemaField], understanding: Understanding) -> dict[str, str]:
    """One model call for every attribute fuzzy matching could not settle."""
    question = {
        spec.id: {
            "attribute": spec.name or spec.id,
            "options": [option.display_name for option in spec.options[:40]],
        }
        for spec in specs
    }
    product = {
        "product_name": understanding.product_name,
        "material": understanding.material,
        "colors": understanding.colors,
        "specs": understanding.specs,
        "features": understanding.features,
        "usage": understanding.usage,
    }
    prompt = (
        "Choose the best option for each wholesale product attribute.\n"
        "Only use text that appears verbatim in that attribute's options. "
        "If nothing fits, use an empty string.\n\n"
        f"Product: {json.dumps(product, ensure_ascii=False)}\n"
        f"Attributes: {json.dumps(question, ensure_ascii=False)}\n\n"
        'Return JSON only, mapping attribute id to chosen option text: {"p-1": "China"}'
    )
    try:
        payload = ai.chat_json([{"role": "user", "content": prompt}], temperature=0.0)
    except (AiUnavailable, ValueError):
        return {}
    return {str(key): str(value) for key, value in payload.items() if isinstance(value, (str, int, float))}


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
    if price and moq:
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

    logistics = specs.get("logisticsProperty")
    if logistics is not None:
        wanted = str(defaults.get("logisticsProperty") or "普货")
        option = logistics.option_by_label(wanted)
        if option is not None:
            values["logisticsProperty"] = [option.value]

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


def apply_content(
    specs: Mapping[str, SchemaField],
    values: dict[str, Any],
    title: str,
    keywords: Sequence[str],
    highlights: str,
    images: Sequence[BankImage],
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

    desc_type = specs.get("productDescType")
    if desc_type is not None:
        chosen = _option_value(desc_type, "普通编辑", fallback_first=True)
        if chosen:
            values["productDescType"] = chosen

    detail = specs.get("detailImage")
    if detail is not None and images:
        gallery = _option_value(detail.child("gallery"), "Detail shot", fallback_first=True)
        values["detailImage"] = [
            {
                "gallery": gallery,
                "images": [{"imageURL": image.url} for image in images],
            }
        ]


# --------------------------------------------------------------------------
# assembly
# --------------------------------------------------------------------------


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
) -> DraftResult:
    result = DraftResult(ai={"understanding": understanding.raw})

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
    values: dict[str, Any] = {"catId": category_id}

    for group_id in ("icbuCatProp", "saleProp"):
        group = specs.get(group_id)
        if group is None or not group.children:
            continue
        group_values, group_issues = align_attributes(group, understanding, defaults, ai)
        if group_values:
            values[group_id] = group_values
        result.issues.extend(group_issues)

    apply_trade_terms(specs, values, defaults, price, moq)

    title_spec = specs.get("productTitle")
    keyword_spec = specs.get("productKeywords")
    title_limit = (title_spec.max_length if title_spec else None) or 128
    keyword_count = (keyword_spec.max_items if keyword_spec else None) or 3

    copy_confidence = 0.0
    if ai is not None:
        try:
            copy = ai.write_copy(
                understanding,
                title_limit=title_limit,
                keyword_count=keyword_count,
                extra_facts={"category": category_name, "moq": moq, "unit_price": price},
                angle=copy_angle,
            )
            copy_confidence = copy.confidence
            result.ai["copy"] = {
                "title": copy.title,
                "keywords": copy.keywords,
                "highlights": copy.highlights,
                "selling_points": copy.selling_points,
                "faqs": copy.faqs,
            }
            apply_content(specs, values, copy.title, copy.keywords, copy.highlights, images)
            result.title = copy.title
        except (AiUnavailable, ValueError) as exc:
            result.add_issue("productTitle", "商品标题", "red", f"AI 文案没生成成功：{exc}")
            apply_content(specs, values, "", [], "", images)
    else:
        apply_content(specs, values, "", [], "", images)

    result.values = values

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
