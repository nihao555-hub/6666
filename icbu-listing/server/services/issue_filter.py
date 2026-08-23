"""Keep audit/issue lists focused on what a person can and should fix.

Parsed Excel rows already carry seller evidence. Shop policy, habits and
templates fill freight, packaging and trade defaults. Validator noise such
as orphan schema keys must not look like hundreds of manual tasks in bulk.
"""

from __future__ import annotations

from typing import Any, Mapping

# Yellow warnings the platform ignores — never block bulk review UI.
_ORPHAN_HINTS = ("该类目没有这个字段", "提交时会被忽略")

# Filled by shop / category template / habits — not the Excel short table.
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
}


def is_actionable(issue: Mapping[str, Any]) -> bool:
    level = str(issue.get("level") or "")
    message = str(issue.get("message") or "")
    field_id = str(issue.get("field_id") or "")
    path = str(issue.get("path") or "")

    if level == "yellow" and any(hint in message for hint in _ORPHAN_HINTS):
        return False
    if field_id in _AUTO_TRADE_LOGISTICS or path in _AUTO_TRADE_LOGISTICS:
        return False
    if path.startswith("logistics."):
        return False
    if field_id == "productQuality":
        return False
    if field_id.startswith("productKeywords_") and "没有这个字段" in message:
        return False
    if field_id.startswith("customMoreProperty") and level == "yellow":
        return False
    return True


def for_user(issues: Any) -> list[dict[str, Any]]:
    if not isinstance(issues, list):
        return []
    return [dict(item) for item in issues if isinstance(item, Mapping) and is_actionable(item)]
