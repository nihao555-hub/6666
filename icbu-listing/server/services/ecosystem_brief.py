"""Alibaba ICBU ecosystem context for AI fill — 生意助手-style brief.

Builds a shop+category brief from GOP online listings, schema, habits, and the
vendored ICBU publishing skill so copy/attrs align with platform search logic.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from sqlalchemy.orm import Session

from ..models import Shop
from . import catalog, templates
from .icbu_publishing_skill import KEYWORD_RULES, TITLE_RULES, checklist_for_review, skill_prompt_block
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


def _sample_online_titles(
    api: Any,
    *,
    category_id: str,
    limit: int = 5,
    pages: int = 2,
) -> list[str]:
    """Pull subject lines from this shop's on-selling listings (same leaf when possible)."""
    titles: list[str] = []
    seen: set[str] = set()
    for page in range(1, pages + 1):
        try:
            payload = api.list_products(page, 30, "onSelling")
        except Exception:
            break
        nested = payload.get("product_list") if isinstance(payload.get("product_list"), dict) else {}
        items = nested.get("products") or payload.get("products") or []
        for item in items:
            if not isinstance(item, Mapping):
                continue
            cid = str(item.get("category_id") or "")
            subject = str(item.get("subject") or "").strip()
            if not subject or subject.lower() in seen:
                continue
            if category_id and cid and cid != str(category_id):
                continue
            seen.add(subject.lower())
            titles.append(subject)
            if len(titles) >= limit:
                return titles
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

    golden_titles: list[str] = []
    online_count = int(shop.online_count or -1)
    if resolved_api is not None:
        golden_titles = _sample_online_titles(resolved_api, category_id=category_id, limit=5)

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
        "template_name": template_name,
        "shop_policy_keys": [key for key, value in shop_policy.items() if str(value or "").strip()],
        "template_field_keys": [key for key, value in template_fields.items() if str(value or "").strip()],
        "schema_limits": schema_limits,
        "title_formula": "Core Product + Type + Performance/Scene + OEM/Custom support",
        "keyword_strategy": keyword_strategy,
        "assistant_steps": assistant_steps,
        "review_checklist": checklist_for_review(),
        "publishing_skill": "aidi1723/alibaba-icbu-publishing-skill",
        "tips": _tips_for_shop(online_count, golden_titles, template_name, category_name),
    }


def _tips_for_shop(
    online_count: int,
    golden_titles: Sequence[str],
    template_name: str,
    category_name: str,
) -> str:
    bits: list[str] = []
    label = category_name or "本类目"
    if golden_titles:
        bits.append(f"参考店里同品类在售标题写法（已采样 {len(golden_titles)} 条）")
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
