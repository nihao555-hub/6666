"""Keep audit/issue lists focused on what a person can and should fix.

Bulk listings: shop policy, habits and templates fill trade/logistics; orphan
schema keys and soft warnings are noise. Default to showing RED blockers only.
"""

from __future__ import annotations

from typing import Any, Mapping

_ORPHAN_HINTS = ("该类目没有这个字段", "提交时会被忽略", "会被忽略")

_AUTO_TRADE_LOGISTICS = {
    "shippingTemplate",
    "shippingTemplateId",
    "logisticsProperty",
    "pkgWeight",
    "pkgMeasure",
    "paymentMethod",
    "port",
    "market",
    "marketSample",
    "priceUnit",
    "saleType",
    "scPrice",
    "ladderPeriod",
    "ladderPrice",
    "minOrderQuantity",
    "productQuality",
    "detailImage",
    "companyFaqDesc",
    "superText",
    "textDesc",
    "productDescType",
}

_SOFT_MESSAGE_HINTS = (
    "图片质量",
    "不太确定",
    "置信度",
    "新店铺前",
    "示例",
    "关键词超过",
    "最多 1 项",
    "最多 3 项",
    "FREIGHT_NEGOTIATION",
    "不在平台可选值里",
)

_USER_RED_IDS = {
    "price",
    "moq",
    "minOrderQuantity",
    "category",
    "scImages",
    "ai",
}


def is_actionable(issue: Mapping[str, Any]) -> bool:
    level = str(issue.get("level") or "")
    message = str(issue.get("message") or "")
    field_id = str(issue.get("field_id") or "")
    field_name = str(issue.get("field_name") or "")
    path = str(issue.get("path") or "")

    if any(hint in message for hint in _ORPHAN_HINTS):
        return False
    if field_id in _AUTO_TRADE_LOGISTICS or path in _AUTO_TRADE_LOGISTICS:
        return False
    if path.startswith("logistics."):
        return False
    if field_id.startswith("productKeywords") or path.startswith("productKeywords"):
        return False
    if field_id.startswith("customMoreProperty"):
        return False
    if any(hint in message for hint in _SOFT_MESSAGE_HINTS):
        return False

    # Drop all yellow — informational only in bulk flow.
    if level == "yellow":
        return False

    if level != "red":
        return False

    if field_id in _USER_RED_IDS or path in _USER_RED_IDS:
        return True
    if "必填" in message or "必填项" in message:
        return True
    if path.startswith(("icbuCatProp.", "saleProp.")):
        return "必填" in message or "还没有值" in message
    if field_id == "ai" and "没生成" in message:
        return True
    return False


def for_user(issues: Any) -> list[dict[str, Any]]:
    if not isinstance(issues, list):
        return []
    return [dict(item) for item in issues if isinstance(item, Mapping) and is_actionable(item)]


def row_issues_for_user(issues: Any) -> list[dict[str, Any]]:
    """Pre-import grid: only hard blockers (price/moq) surface as row issues."""
    if not isinstance(issues, list):
        return []
    out: list[dict[str, Any]] = []
    for item in issues:
        if not isinstance(item, Mapping):
            continue
        level = str(item.get("level") or "")
        message = str(item.get("message") or "")
        if level != "red":
            continue
        if "单价" in message or "起订" in message or "MOQ" in message.upper():
            out.append(dict(item))
    return out
