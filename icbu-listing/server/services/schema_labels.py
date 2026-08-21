"""Chinese labels for ICBU schema fields shown to sellers."""

from __future__ import annotations

import re
from typing import Any, Mapping

# Group ids from schema XML
GROUP_ID_LABELS: dict[str, str] = {
    "icbuCatProp": "类目属性",
    "saleProp": "销售属性",
    "productTitle": "英文标题",
    "productKeywords": "关键词",
    "textDesc": "卖点描述",
    "superText": "详情描述",
    "scImages": "商品图片",
    "detailImage": "详情图片",
    "minOrderQuantity": "起订量",
    "ladderPrice": "阶梯价",
    "scPrice": "售价",
    "fob": "FOB 价格",
    "priceUnit": "价格单位",
    "catId": "叶子类目",
    "market": "目标市场",
    "paymentMethod": "付款方式",
    "port": "港口",
    "ladderPeriod": "交期",
    "shippingTemplateId": "运费模板",
    "pkgMeasure": "包装尺寸",
    "pkgWeight": "包装重量",
    "logisticsMode": "物流方式",
    "logisticsProperty": "物流属性",
    "productDescType": "详情类型",
    "brand": "品牌",
}

# English group / field names from schema.get (en_US or zh payloads)
NAME_LABELS: dict[str, str] = {
    "product feature": "类目属性",
    "sales property": "销售属性",
    "sku": "SKU 规格",
    "single piece price": "单件价格",
    "logistics supply mode": "物流供应模式",
    "details of the picture": "详情图片",
    "company picture": "公司图片",
    "faqs": "常见问题",
    "product specification component": "产品规格",
    "product images": "商品图片",
    "product video": "商品视频",
    "additional videos": "附加视频",
    "product keywords": "关键词",
    "dimensions": "尺寸",
    "volume and weight (including logistics packaging)": "体积重量（含物流包装）",
    "shipping": "发货",
    "semi-managed": "半托管",
    "product group": "产品分组",
    "quantity price": "数量价格",
    "more details": "更多详情",
    "product quality": "商品质量",
    "sample service": "样品服务",
    "us hs code maintenance": "美国 HS 编码",
    "lead color": "铅芯颜色",
    "lead hardness": "铅芯硬度",
    "sample price (usd)": "样品价（USD）",
    "sample price": "样品价",
    "product name": "英文标题",
    "unit": "单位",
    "templatetype": "模板类型",
    "range_max": "价格上限",
    "range_min": "价格下限",
    "unit_type": "单位类型",
    "sell product by": "销售方式",
    "price setting": "价格设置",
    "gallery": "图库",
    "images": "图片",
    "question": "问题",
    "answers": "答案",
    "productfeature": "产品特点",
    "catid": "类目 ID",
    "soluble or not": "是否可溶",
    "model number": "型号",
    "brand name": "品牌名",
    "printing": "印刷",
    "lead diameter": "笔芯直径",
    "hair material": "笔毛材质",
    "number of colors": "颜色数量",
    "commodity code": "商品编码",
    "props": "属性值",
    "inventory": "库存",
    "single piece price (usd)": "单件价（USD）",
    "skuid": "SKU 编号",
    "supply id": "供应编号",
    "length": "长度",
    "width": "宽度",
    "height": "高度",
    "box gauge": "箱规",
    "box gauge sku": "箱规 SKU",
    "ladderperiod": "交期",
    "shippingtemplateid": "运费模板",
    "first_group_id": "一级分组",
    "second_group_id": "二级分组",
    "third_group_id": "三级分组",
    "set quantity for batch sales": "批量销售数量",
    "minimum order quantity (moq)": "起订量",
    "product description": "商品描述",
    "product highlights": "产品亮点",
    "company introduction": "公司介绍",
    "basic information": "基本信息",
    "trade information": "贸易信息",
    "logistics and shipping": "物流与发货",
    "universal services/capabilities": "通用服务/能力",
    "commodity details": "商品详情",
    "commodity category": "商品类别",
    "maximum samples per order": "每单最大样品数",
    "logistics attribute": "物流属性",
    "weight": "重量",
    "sku long": "SKU 长",
    "sku wide": "SKU 宽",
    "sku high": "SKU 高",
    "supportlogisticssku": "支持物流 SKU",
    "semi-managed shipment period": "半托管发货期",
    "tocountry": "目的国",
    "hscode": "HS 编码",
    "apipostlevelattradapter": "发布适配字段",
    "origin": "原产地",
    "type": "类型",
    "color": "颜色",
    "material": "材质",
    "size": "尺寸",
    "certification": "认证",
    "warranty": "质保",
    "power": "功率",
    "voltage": "电压",
    "frequency": "频率",
    "gender": "适用性别",
    "age group": "适用年龄",
    "season": "季节",
    "fabric": "面料",
    "composition": "成分",
    "success": "完成度",
    "0": "质量项",
}

FIELD_ID_LABELS: dict[str, str] = dict(GROUP_ID_LABELS)
FIELD_ID_LABELS.update(
    {
        "p-1": "原产地",
        "productFeature": "产品特点",
        "templateType": "模板类型",
        "range_max": "价格上限",
        "range_min": "价格下限",
        "unit_type": "单位类型",
        "supportLogisticsSku": "支持物流 SKU",
        "ApiPostLevelAttrAdapter": "发布适配字段",
    }
)

FIELD_TYPE_LABELS: dict[str, str] = {
    "input": "文本",
    "singleCheck": "单选",
    "multiCheck": "多选",
    "multiInput": "多行文本",
    "complex": "组合字段",
    "multiComplex": "组合多行",
    "label": "说明",
}


def _has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def _key(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _by_name(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return raw
    if _has_cjk(raw):
        return raw
    hit = NAME_LABELS.get(_key(raw))
    if hit:
        return hit
    hit = NAME_LABELS.get(_key(raw).replace("_", " "))
    return hit or raw


def _by_field_id(field_id: str) -> str | None:
    fid = (field_id or "").strip()
    if not fid:
        return None
    if fid in FIELD_ID_LABELS:
        return FIELD_ID_LABELS[fid]
    ladder = re.fullmatch(r"ladderPrice_(\d+)", fid)
    if ladder:
        return f"阶梯价第 {int(ladder.group(1)) + 1} 档"
    period = re.fullmatch(r"ladderPeriod_(\d+)", fid)
    if period:
        return f"交期第 {int(period.group(1)) + 1} 档"
    custom = re.fullmatch(r"customMoreProperty_(\d+)", fid)
    if custom:
        return f"自定义属性 {int(custom.group(1)) + 1}"
    return None


def group_label(group_id: str, group_name: str = "") -> str:
    if group_id in GROUP_ID_LABELS:
        return GROUP_ID_LABELS[group_id]
    return _by_name(group_name or group_id)


def field_label(field_id: str, field_name: str) -> str:
    by_id = _by_field_id(field_id)
    if by_id:
        return by_id
    return _by_name(field_name or field_id)


def header_label(group_id: str, group_name: str, field_id: str, field_name: str) -> str:
    group = group_label(group_id, group_name)
    field = field_label(field_id, field_name)
    if group_id and group_id != field_id:
        return f"{group} / {field}"
    return field


def column_label(col: Mapping[str, Any]) -> str:
    header = str(col.get("header") or "").strip()
    short = str(col.get("label") or "").strip()
    if header and _has_cjk(header):
        return header
    if short and _has_cjk(short):
        return short
    return field_label(str(col.get("field_id") or ""), header or short)


def field_type_label(field_type: str) -> str:
    return FIELD_TYPE_LABELS.get((field_type or "").strip(), field_type or "文本")
