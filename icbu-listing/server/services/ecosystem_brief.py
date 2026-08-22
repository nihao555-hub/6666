"""Alibaba ICBU ecosystem context for AI fill — 生意助手-style brief.

Builds a shop+category brief from GOP online listings, schema, habits, and the
vendored ICBU publishing skill so copy/attrs align with platform search logic.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from sqlalchemy.orm import Session

from schema import extract_values  # noqa: E402

from ..models import Shop
from . import catalog, templates
from .clone import images_from_values, price_moq, render_xml
from .icbu_publishing_skill import KEYWORD_RULES, TITLE_RULES, checklist_for_review, skill_prompt_block
from .shop_categories import _listing_products
from .shop_client import ShopNotConnected, shop_api, shop_defaults

INQUIRY_TERMS = (
    "oem",
    "odm",
    "custom",
    "customized",
    "wholesale",
    "bulk",
    "factory",
    "private label",
    "sample",
    "moq",
)

SPAM_PHRASES = (
    "hot sale",
    "best seller",
    "top quality",
    "high quality",
    "100% new",
    "free shipping",
    "lowest price",
)


def _utf8_len(text: str) -> int:
    return len(str(text or "").encode("utf-8"))


def _scalar_text(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("$value") or value.get("value") or "").strip()
    return str(value or "").strip()


def _keywords_from_values(values: Mapping[str, Any]) -> list[str]:
    block = values.get("productKeywords") or {}
    if not isinstance(block, dict):
        return []
    words: list[str] = []
    for key in sorted(block.keys()):
        text = _scalar_text(block[key])
        if text:
            words.append(text)
    return words[:3]


def _attrs_snapshot(values: Mapping[str, Any], *, limit: int = 6) -> dict[str, str]:
    out: dict[str, str] = {}
    for group in ("icbuCatProp", "saleProp"):
        block = values.get(group) or {}
        if not isinstance(block, dict):
            continue
        for key, raw in block.items():
            if len(out) >= limit:
                return out
            token = str(key or "")
            if token.startswith("@") or token.endswith("_$"):
                continue
            text = _scalar_text(raw)
            if not text:
                continue
            label = token.split("_")[-1] if "_" in token else token
            out[label] = text
    return out


def _subject_score(subject: str, *, category_match: bool) -> int:
    title = str(subject or "").strip()
    if not title:
        return 0
    score = 10 if category_match else 0
    lower = title.lower()
    if 24 <= len(title) <= 120:
        score += 12
    elif len(title) >= 16:
        score += 6
    if any(term in lower for term in INQUIRY_TERMS):
        score += 10
    if not any(phrase in lower for phrase in SPAM_PHRASES):
        score += 8
    return score


def _listing_example_score(values: Mapping[str, Any], *, subject: str = "") -> int:
    title = str(values.get("productTitle") or subject or "").strip()
    if not title:
        return 0
    score = _subject_score(title, category_match=True)
    keywords = _keywords_from_values(values)
    if len(keywords) >= 2:
        score += 20
    elif keywords:
        score += 10
    attrs = _attrs_snapshot(values, limit=8)
    if len(attrs) >= 4:
        score += 18
    elif len(attrs) >= 2:
        score += 10
    image_count = len(images_from_values(values))
    if image_count >= 6:
        score += 16
    elif image_count >= 3:
        score += 8
    highlights = _scalar_text(values.get("textDesc") or values.get("superText") or "")
    if len(highlights) >= 40:
        score += 8
    price, moq = price_moq(values)
    if price and moq:
        score += 6
    return score


def _example_from_values(
    *,
    product_id: str,
    category_id: str,
    subject: str,
    values: Mapping[str, Any],
    score: int,
) -> dict[str, Any]:
    title = str(values.get("productTitle") or subject or "").strip()
    price, moq = price_moq(values)
    return {
        "product_id": product_id,
        "category_id": category_id,
        "title": title,
        "keywords": _keywords_from_values(values),
        "moq": moq,
        "price": price,
        "highlights": _scalar_text(values.get("textDesc") or values.get("superText") or "")[:240],
        "key_attrs": _attrs_snapshot(values),
        "image_count": len(images_from_values(values)),
        "quality_score": score,
        "source": "shop_online",
    }


def _sample_golden_listings(
    api: Any,
    shop: Shop,
    *,
    category_id: str,
    limit: int = 3,
    scan_pages: int = 3,
    render_candidates: int = 8,
) -> list[dict[str, Any]]:
    """Pull full listing examples from this shop's on-selling products in the same leaf."""
    language = str(shop_defaults(shop).get("language") or "en_US")
    candidates: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for page in range(1, scan_pages + 1):
        try:
            payload = api.list_products(page, 30, "onSelling")
        except Exception:
            break
        items, _total = _listing_products(payload if isinstance(payload, dict) else {})
        for item in items:
            if not isinstance(item, Mapping):
                continue
            product_id = str(item.get("product_id") or item.get("id") or "").strip()
            cid = str(item.get("category_id") or "").strip()
            subject = str(item.get("subject") or "").strip()
            if not product_id or product_id in seen_ids or not subject:
                continue
            category_match = not category_id or cid == str(category_id)
            if category_id and cid and cid != str(category_id):
                continue
            seen_ids.add(product_id)
            candidates.append(
                {
                    "product_id": product_id,
                    "category_id": cid or category_id,
                    "subject": subject,
                    "pref_score": _subject_score(subject, category_match=category_match),
                }
            )
    candidates.sort(key=lambda row: row["pref_score"], reverse=True)
    examples: list[dict[str, Any]] = []
    for candidate in candidates[:render_candidates]:
        pid = candidate["product_id"]
        cid = candidate["category_id"] or category_id
        subject = candidate["subject"]
        try:
            xml = render_xml(api, cid, pid, language)
            values = extract_values(xml)
        except Exception:
            values = {}
        if values:
            score = _listing_example_score(values, subject=subject)
            if score < 35:
                continue
            examples.append(_example_from_values(product_id=pid, category_id=cid, subject=subject, values=values, score=score))
        elif candidate["pref_score"] >= 18:
            examples.append(
                {
                    "product_id": pid,
                    "category_id": cid,
                    "title": subject,
                    "keywords": [],
                    "moq": "",
                    "price": "",
                    "highlights": "",
                    "key_attrs": {},
                    "image_count": 0,
                    "quality_score": candidate["pref_score"],
                    "source": "shop_online_subject",
                }
            )
    examples.sort(key=lambda row: int(row.get("quality_score") or 0), reverse=True)
    deduped: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for item in examples:
        token = str(item.get("title") or "").strip().lower()
        if not token or token in seen_titles:
            continue
        seen_titles.add(token)
        deduped.append(item)
        if len(deduped) >= limit:
            break
    return deduped


def _sample_online_titles(golden_listings: Sequence[Mapping[str, Any]], *, limit: int = 5) -> list[str]:
    titles: list[str] = []
    seen: set[str] = set()
    for item in golden_listings:
        title = str(item.get("title") or "").strip()
        if not title or title.lower() in seen:
            continue
        seen.add(title.lower())
        titles.append(title)
        if len(titles) >= limit:
            break
    return titles


def build_brief(
    db: Session,
    shop: Shop,
    *,
    category_id: str,
    category_name: str = "",
    api: Any | None = None,
) -> dict[str, Any]:
    """Human + LLM-facing Alibaba ecosystem brief for one leaf category."""
    resolved_api = api
    if resolved_api is None:
        try:
            resolved_api = shop_api(shop)
        except ShopNotConnected:
            resolved_api = None

    golden_listings: list[dict[str, Any]] = []
    online_count = int(shop.online_count or -1)
    if resolved_api is not None:
        golden_listings = _sample_golden_listings(
            resolved_api,
            shop,
            category_id=category_id,
            limit=3,
        )
    golden_titles = _sample_online_titles(golden_listings)

    shop_policy = shop_defaults(shop)
    template_row = templates.find_for(db, shop.id, category_id)
    template_name = str(template_row.name if template_row else "") or ""
    template_fields = templates.values_of(template_row) if template_row else {}

    schema_limits: dict[str, Any] = {}
    if category_id and resolved_api is not None:
        try:
            xml = catalog.get_schema_xml(db, resolved_api, category_id, "en")
            from schema import parse_schema  # noqa: E402

            fields = parse_schema(xml)
            by_id = {item.id: item for item in fields if getattr(item, "id", None)}
            for field_id in ("productTitle", "productKeywords"):
                spec = by_id.get(field_id)
                if spec is not None:
                    schema_limits[field_id] = {
                        "name": spec.name,
                        "max_length": getattr(spec, "max_length", None),
                        "required": bool(getattr(spec, "required", False)),
                    }
        except Exception:
            schema_limits = {}

    keyword_strategy = [
        {"tier": "S", "label": "核心询盘词", "hint": "产品词+规格/材质，与标题、属性一致，供应能力真实"},
        {"tier": "A", "label": "测试拓展词", "hint": "场景/买家角色词，有图有属性支撑时可试"},
        {"tier": "B", "label": "覆盖长尾", "hint": "包装、批量、定制类支持词，勿堆砌"},
        {"tier": "C", "label": "避免", "hint": "泛流量词、无法证实的认证/夸大词、与类目不符的词"},
    ]

    assistant_steps = [
        "合规：标题/关键词/属性/图片讲同一个产品故事",
        "匹配：核心品名靠前，官方属性选项合法，六图与文案一致",
        "询盘：1～3 个买家会搜的英文词，偏 OEM/批量/场景，非广告口号",
        "习惯：店铺默认与类目模板已覆盖的字段，填写表不必重复填",
        "质量：必填属性有依据再填；价/量/品牌红线由你定",
    ]

    return {
        "category_id": category_id,
        "category_name": category_name,
        "online_count": online_count,
        "golden_titles": golden_titles,
        "golden_listings": golden_listings,
        "template_name": template_name,
        "shop_policy_keys": [key for key, value in shop_policy.items() if str(value or "").strip()],
        "template_field_keys": [key for key, value in template_fields.items() if str(value or "").strip()],
        "schema_limits": schema_limits,
        "title_formula": "Core Product + Type + Performance/Scene + OEM/Custom support",
        "keyword_strategy": keyword_strategy,
        "assistant_steps": assistant_steps,
        "review_checklist": checklist_for_review(),
        "publishing_skill": "aidi1723/alibaba-icbu-publishing-skill",
        "tips": _tips_for_shop(online_count, golden_listings, template_name, category_name),
    }


def _tips_for_shop(
    online_count: int,
    golden_listings: Sequence[Mapping[str, Any]],
    template_name: str,
    category_name: str,
) -> str:
    bits: list[str] = []
    label = category_name or "本类目"
    if golden_listings:
        bits.append(f"已采样 {len(golden_listings)} 条店里同品类顶级上品案例供 AI 学习（标题/关键词/属性/六图结构）")
    elif online_count > 0:
        bits.append("店里有在售商品，可先上「在线商品」页学成模板/默认")
    else:
        bits.append("新店优先把必填属性+六图+询盘向标题做齐，再扩 SKU 覆盖")
    if template_name:
        bits.append(f"已匹配类目模板「{template_name}」")
    bits.append(f"{label}：AI 写标题/关键词时会按阿里搜索三层逻辑（合规→匹配→询盘）")
    return "；".join(bits)


def prompt_block(brief: Mapping[str, Any]) -> str:
    """Compact block injected into COPY_PROMPT facts."""
    lines = [
        skill_prompt_block(),
        TITLE_RULES.strip(),
        KEYWORD_RULES.strip(),
        "Alibaba ecosystem brief (use for B2B inquiry optimization, not hype):",
        f"- Category: {brief.get('category_name') or brief.get('category_id') or ''}",
    ]
    titles = brief.get("golden_titles") or []
    if titles:
        lines.append("- Shop's live listing title patterns on Alibaba (match tone/structure, do not copy verbatim):")
        for title in titles[:5]:
            lines.append(f"  · {title}")
    listings = brief.get("golden_listings") or []
    if listings:
        lines.append(
            "- Top reference listings from this shop on Alibaba International "
            "(match depth, keyword tiers, attribute coverage, and image completeness — never copy verbatim):"
        )
        for index, item in enumerate(listings[:3], start=1):
            lines.append(f"  Example {index}:")
            if item.get("title"):
                lines.append(f"    title: {item['title']}")
            keywords = item.get("keywords") or []
            if keywords:
                lines.append(f"    keywords: {', '.join(str(word) for word in keywords[:3])}")
            attrs = item.get("key_attrs") or {}
            if attrs:
                pairs = ", ".join(f"{key}={value}" for key, value in list(attrs.items())[:5])
                lines.append(f"    key_attrs: {pairs}")
            if item.get("highlights"):
                lines.append(f"    highlights: {str(item['highlights'])[:160]}")
            if item.get("moq") or item.get("price"):
                lines.append(f"    trade: MOQ {item.get('moq') or '?'} @ USD {item.get('price') or '?'}")
            if item.get("image_count"):
                lines.append(f"    images: {item['image_count']} filled slots")
    limits = brief.get("schema_limits") or {}
    title_spec = limits.get("productTitle") or {}
    if title_spec.get("max_length"):
        lines.append(f"- Official productTitle max length hint: {title_spec['max_length']} chars")
    strategy = brief.get("keyword_strategy") or []
    if strategy:
        lines.append("- Keyword tiers: " + "; ".join(f"{item['tier']}={item['hint']}" for item in strategy[:4]))
    steps = brief.get("assistant_steps") or []
    if steps:
        lines.append("- Assistant focus: " + " | ".join(steps[:3]))
    return "\n".join(lines)


def score_copy_row(row: Mapping[str, Any], *, title_byte_limit: int = 128) -> dict[str, Any]:
    """Lightweight 生意助手-style score for audit UI."""
    title = str(row.get("title") or "").strip()
    keywords_raw = str(row.get("keywords") or "").strip()
    keywords = [part.strip() for part in re.split(r"[,，;；]", keywords_raw) if part.strip()]
    issues: list[str] = []
    score = 100

    byte_len = _utf8_len(title)
    if not title:
        issues.append("缺英文标题")
        score -= 40
    elif byte_len > title_byte_limit:
        issues.append(f"标题超长（{byte_len}/{title_byte_limit} 字节）")
        score -= 15

    lower = title.lower()
    for phrase in SPAM_PHRASES:
        if phrase in lower:
            issues.append(f"标题含平台反感词：{phrase}")
            score -= 20
            break

    if not keywords:
        issues.append("缺关键词")
        score -= 25
    elif len(keywords) > 3:
        issues.append("关键词超过 3 个")
        score -= 10

    inquiry_hits = sum(1 for kw in keywords if any(term in kw.lower() for term in INQUIRY_TERMS))
    if keywords and inquiry_hits == 0 and not any(term in lower for term in INQUIRY_TERMS):
        issues.append("可增加 OEM/批量/场景类询盘词")
        score -= 8

    tier = "S" if score >= 85 else "A" if score >= 70 else "B" if score >= 50 else "C"
    return {
        "score": max(0, min(100, score)),
        "tier": tier,
        "title_bytes": byte_len,
        "keyword_count": len(keywords),
        "issues": issues,
    }
