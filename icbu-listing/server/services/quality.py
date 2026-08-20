"""Local Product Information Score, aligned to official ICBU buckets.

Alibaba computes `productQuality` after publish (0–5). We cannot write that
field. We can fill every inferable schema field from seller evidence and score
the same six buckets the platform shows: 类目 / 基本信息 / 交易 / 物流 / 服务 / 详情.

5.0 here means those buckets are complete enough that a typical listing lands
at official 5.0. Video is not inferred (no fake clips) and is not required
for this gate. Certs, brand, price, photos stay on the red line.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from schema import SchemaField, index_fields  # noqa: E402

BUCKETS: tuple[tuple[str, str], ...] = (
    ("category", "商品类目"),
    ("basic", "基本信息"),
    ("trade", "交易信息"),
    ("logistics", "物流信息"),
    ("service", "通用服务/能力"),
    ("detail", "商品详情"),
)


def _has(values: Mapping[str, Any], key: str) -> bool:
    value = values.get(key)
    if value in (None, "", [], {}, ()):
        return False
    if isinstance(value, dict):
        if "$value" in value:
            return bool(value.get("$value"))
        return any(_has({child: item}, child) for child, item in value.items() if child != "$attrs")
    return True


def _required_attr_ids(fields: Sequence[SchemaField] | None) -> list[tuple[str, str, str]]:
    needed: list[tuple[str, str, str]] = []
    if not fields:
        return needed
    specs = index_fields(fields)
    for group_id in ("icbuCatProp", "saleProp"):
        group = specs.get(group_id)
        if group is None:
            continue
        for child in group.children:
            if child.required:
                needed.append((group_id, child.id, child.name or child.id))
    return needed


def score_listing(
    *,
    values: Mapping[str, Any],
    fields: Sequence[SchemaField] | None = None,
    image_count: int = 0,
    price: str = "",
    moq: str = "",
    category_id: str = "",
) -> dict[str, Any]:
    specs = index_fields(fields) if fields else {}
    checks: list[tuple[str, str, bool]] = []

    checks.append(("category", "叶子类目", bool(category_id or values.get("catId"))))

    checks.append(("basic", "英文标题", _has(values, "productTitle")))
    keywords = values.get("productKeywords") or {}
    checks.append(("basic", "关键词", isinstance(keywords, dict) and len([item for item in keywords.values() if item]) >= 3))
    attrs = values.get("icbuCatProp") or {}
    sale = values.get("saleProp") or {}
    checks.append(("basic", "类目属性", bool(attrs or sale)))
    for group_id, child_id, name in _required_attr_ids(fields):
        group = values.get(group_id) or {}
        checks.append(("basic", f"必填属性 {name}", _has(group, child_id) if isinstance(group, dict) else False))

    checks.append(("trade", "售价", bool(str(price or "").strip()) or _has(values, "ladderPrice") or _has(values, "scPrice")))
    checks.append(("trade", "起订量", bool(str(moq or "").strip()) or _has(values, "minOrderQuantity")))
    checks.append(("trade", "计量单位", _has(values, "priceUnit")))
    checks.append(("trade", "售卖方式", _has(values, "saleType")))
    checks.append(("trade", "价格设置", _has(values, "scPrice") or _has(values, "ladderPrice")))
    if "paymentMethod" in specs:
        checks.append(("trade", "付款方式", _has(values, "paymentMethod")))
    if "port" in specs:
        checks.append(("trade", "港口", _has(values, "port")))
    if "ladderPeriod" in specs:
        checks.append(("trade", "发货期", _has(values, "ladderPeriod")))

    if "shippingTemplate" in specs:
        checks.append(("logistics", "运费模板", _has(values, "shippingTemplate")))
    if "logisticsProperty" in specs:
        checks.append(("logistics", "物流属性", _has(values, "logisticsProperty")))
    if "pkgWeight" in specs:
        checks.append(("logistics", "包装重量", _has(values, "pkgWeight")))
    if "pkgMeasure" in specs:
        checks.append(("logistics", "包装尺寸", _has(values, "pkgMeasure")))

    if "marketSample" in specs:
        checks.append(("service", "样品服务", _has(values, "marketSample")))

    checks.append(("detail", "实拍图至少 3 张", image_count >= 3))
    checks.append(("detail", "商品描述", _has(values, "textDesc") or _has(values, "superText")))
    if "superText" in specs:
        checks.append(("detail", "详描", _has(values, "superText")))
    if "detailImage" in specs:
        checks.append(("detail", "详情图", _has(values, "detailImage")))
    if "companyFaqDesc" in specs:
        checks.append(("detail", "常见问题", _has(values, "companyFaqDesc")))

    by_bucket: dict[str, list[tuple[str, bool]]] = {key: [] for key, _ in BUCKETS}
    for bucket, label, ok in checks:
        by_bucket.setdefault(bucket, []).append((label, ok))

    buckets = []
    missing: list[str] = []
    passed = 0
    for key, name in BUCKETS:
        items = by_bucket.get(key) or []
        if not items:
            buckets.append({"id": key, "name": name, "ok": True, "missing": []})
            continue
        gaps = [label for label, ok in items if not ok]
        ok = not gaps
        if ok:
            passed += 1
        missing.extend(gaps)
        buckets.append({"id": key, "name": name, "ok": ok, "missing": gaps})

    scored = [key for key, _ in BUCKETS if by_bucket.get(key)]
    total = len(scored) or 1
    score = round(5.0 * passed / total, 1)
    return {
        "score": score,
        "ready": score >= 5.0 and not missing,
        "buckets": buckets,
        "missing": missing,
        "note": "按官方六桶预估。上架后以阿里 productQuality 为准。视频不能从实拍推断，不计入。",
    }


def quality_issue(report: Mapping[str, Any]) -> dict[str, Any] | None:
    if report.get("ready"):
        return None
    gaps = "、".join(report.get("missing") or []) or "信息还不完整"
    return {
        "field_id": "productQuality",
        "field_name": "信息质量分",
        "level": "red",
        "message": f"预估 {report.get('score')} / 5.0，还差：{gaps}。补齐后重成稿或改店铺默认，到 5.0 才能发。",
        "path": "productQuality",
    }


def quality_report_from_draft(draft: Any) -> Mapping[str, Any] | None:
    """Read the cached local quality estimate stored on a draft."""
    raw = getattr(draft, "ai_json", None)
    if not raw:
        return None
    try:
        import json

        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    report = payload.get("quality") if isinstance(payload, dict) else None
    return report if isinstance(report, dict) else None


def quality_ready(draft: Any) -> tuple[bool, str]:
    report = quality_report_from_draft(draft)
    if report is None:
        return False, "信息质量分未评估，请重成稿或保存一次草稿"
    if report.get("ready"):
        return True, ""
    score = report.get("score")
    gaps = "、".join(report.get("missing") or []) or "信息还不完整"
    if score is not None:
        return False, f"信息质量分 {score} / 5.0，还差：{gaps}"
    return False, f"信息质量分未到 5.0，还差：{gaps}"
