"""Submit a draft to Alibaba and turn whatever comes back into plain Chinese.

Publishing is deliberately two-speed: `draft` posts into the seller's official
draft box (nothing goes live, safe for a first run), `online` publishes for
real. The mode is a per-shop setting.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from gop_client import GopError  # noqa: E402
from icbu_api import IcbuApi  # noqa: E402
from schema import build_item_param, parse_schema, validate_values  # noqa: E402

# Documented ICBU publish error codes. The platform returns these verbatim and
# every competing tool just forwards the English string to the seller.
ERROR_CODES: dict[str, tuple[str, bool]] = {
    "CHK_IMAGE_FILE_COUNT_EXCEED": ("主图超过 6 张，多余的会被丢掉", True),
    "CHK_STEP_LADDER_PERIOD_VALUE_ERROR": ("阶梯交期的数量必须由小到大", True),
    "CHK_STEP_LADDER_PERIOD_QUANTITY_EMPTY_ERROR": ("阶梯交期缺少数量", True),
    "CHK_STEP_CATEGORY_QUALITY_MINSIZE_ERROR": ("这个类目对起订量有下限，调高一点", True),
    "PUB_BIZCHECK_SALE_PROPERTY_VALEU_IS_NOT_EXPECT": ("销售属性的取值不在官方选项里", True),
    "PUB_BIZCHECK_SALE_PROPERTY_IMAGE_ERROR": ("属性图链接不合法，要用图片银行的地址", True),
    "PUB_BIZCHECK_SKU_PRICE": ("SKU 价格不能是 0 或负数", True),
    "PUB_BIZCHECK_CAT_PUB_RESTRICT": ("这个类目不在店铺经营范围内，换类目或去后台申请", False),
    "PUB_BIZCHECK_SUSPICIOUS": ("店铺处于禁限售处罚中，发不了品", False),
    "PUB_BIZCHECK_COMP_PROMOTION_LOCK_ERROR": ("商品正在活动中，锁定期内不能改", False),
}

# Fallback keyword matching for anything not in the table above.
ERROR_HINTS: tuple[tuple[str, str], ...] = (
    ("title", "标题被拒：检查长度、是否有中文或特殊符号"),
    ("keyword", "关键词被拒：数量或格式不对"),
    ("image", "图片被拒：必须是图片银行里的图，且尺寸达标"),
    ("category", "类目不对：必须是最末级类目"),
    ("price", "价格不合法：检查区间、阶梯价和单位"),
    ("moq", "起订量不合法"),
    ("attribute", "类目属性缺失或取值不在官方选项里"),
    ("property", "类目属性缺失或取值不在官方选项里"),
    ("freight", "运费模板不可用，改成买卖双方协商或换一个模板"),
    ("shipping", "物流设置不完整"),
    ("permission", "这个店铺没有该接口权限，去开放平台申请"),
    ("token", "店铺授权失效，请重新授权"),
)

FIELD_IN_MESSAGE = re.compile(r"[\[「\"']?(p-\d+|[a-zA-Z]+[A-Za-z0-9_]{3,})[\]」\"']?")


@dataclass
class PublishOutcome:
    ok: bool
    product_id: str = ""
    error: str = ""
    error_fields: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


def humanise(message: str) -> str:
    text = message or ""
    for code, (hint, fixable) in ERROR_CODES.items():
        if code in text:
            suffix = "，可以改完直接重发" if fixable else "，需要先去卖家后台处理"
            return f"{hint}{suffix}（{code}）"
    lowered = text.lower()
    for needle, hint in ERROR_HINTS:
        if needle in lowered:
            return f"{hint}（平台原文：{text[:180]}）"
    return text[:300] or "平台没有给出原因"


def is_auto_fixable(message: str) -> bool:
    """Whether the seller can fix this in our UI, or has to leave the product."""
    for code, (_, fixable) in ERROR_CODES.items():
        if code in (message or ""):
            return fixable
    return True


def _dig(payload: Any, keys: tuple[str, ...]) -> str:
    """Find the first non-empty value for any of `keys`, at any depth."""
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            if key in keys and value not in (None, "", 0, "0"):
                return str(value)
            found = _dig(value, keys)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _dig(item, keys)
            if found:
                return found
    return ""


def parse_publish_response(payload: dict[str, Any]) -> PublishOutcome:
    product_id = _dig(payload, ("product_id", "productId", "productID", "id"))
    error_message = _dig(payload, ("error_message", "errorMessage", "error_msg", "message", "msg"))
    error_code = _dig(payload, ("error_code", "errorCode"))

    if product_id and not error_message:
        return PublishOutcome(ok=True, product_id=product_id, raw=payload)
    if error_message or error_code:
        text = " ".join(part for part in (error_code, error_message) if part)
        return PublishOutcome(ok=False, error=humanise(text), error_fields=guess_fields(text), raw=payload)
    if product_id:
        return PublishOutcome(ok=True, product_id=product_id, raw=payload)
    return PublishOutcome(ok=False, error="平台没有返回商品 ID，也没有返回错误，请到卖家后台确认", raw=payload)


def guess_fields(message: str) -> list[str]:
    return list(dict.fromkeys(FIELD_IN_MESSAGE.findall(message or "")))[:6]


def publish(
    api: IcbuApi,
    category_id: str,
    schema_xml: str,
    values: Mapping[str, Any],
    *,
    mode: str = "draft",
    language: str = "en_US",
) -> PublishOutcome:
    fields = parse_schema(schema_xml)
    blocking = [issue for issue in validate_values(fields, values) if issue.level == "red"]
    if blocking:
        summary = "；".join(f"{item.field_name or item.field_id}：{item.message}" for item in blocking[:4])
        return PublishOutcome(ok=False, error=f"提交前自检没过：{summary}", error_fields=[i.field_id for i in blocking])

    xml = build_item_param(fields, values)
    try:
        if mode == "online":
            payload = api.schema_add(int(category_id), xml, language)
        else:
            payload = api.schema_add_draft(int(category_id), xml, language)
    except GopError as exc:
        text = f"{exc.code or ''} {exc.msg}".strip()
        return PublishOutcome(ok=False, error=humanise(text), error_fields=guess_fields(json.dumps(exc.payload, ensure_ascii=False)), raw=exc.payload)

    return parse_publish_response(payload)
