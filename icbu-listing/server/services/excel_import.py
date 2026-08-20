"""Excel listing import, with the styles factories already know.

Four styles sit behind one preview → map → import path. The seller picks
the one that matches how their other ERP (or factory sheet) is laid out:

    lingxing     领星资料库：SKU / 价 / 图先入库，再铺店
    dianxiaomi   店小秘按刊登模板：表格只填差异字段，类目物流走模板
    detect       智能探测：任意表头（通途 / 马帮 / 自己的表），自动对列
    mabang       马帮库存SKU导出：按马帮列名预设映射

Detection is Lingxing's custom-template idea: find the header row by how
many aliases it matches, then propose a mapping the seller can edit.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from collections.abc import Callable
from typing import Any, Iterable
from urllib.parse import urlparse

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

# Official origin. Always a shop default, never a per-row column.
SKIP_ATTR_IDS = {"p-1"}

# Two axes, not a photo count: what to do when a row has shots, and when it does not.
# Legacy aliases: mixed=keep_draw, photos_only=keep_skip, generate_all=boost_draw.
PHOTO_POLICIES = ("keep", "complete", "boost")
EMPTY_POLICIES = ("draw", "skip")
IMAGE_MODES = tuple(f"{photo}_{empty}" for photo in PHOTO_POLICIES for empty in EMPTY_POLICIES)
IMAGE_MODE_ALIASES = {
    "mixed": "keep_draw",
    "photos_only": "keep_skip",
    "generate_all": "boost_draw",
    "keep": "keep_draw",
    "complete": "complete_draw",
    "boost": "boost_draw",
}

# Row 2 of every template we hand out is a worked example. Sellers overwrite
# it about half the time and append below it the other half, so it has to be
# recognisable on the way back in — otherwise the demo paint brush gets listed.
SAMPLE_MARK = "示例"
SAMPLE_PREFIXES = (SAMPLE_MARK, "范例", "sample", "example", "e.g.")

# Rows past this still import, but they queue behind one AI pass each.
BATCH_SOFT_LIMIT = 200

FIELDS: dict[str, str] = {
    "sku": "货号",
    "name": "品名（中文）",
    "title": "英文标题",
    "keywords": "关键词",
    "price": "单价 USD",
    "moq": "起订量",
    "images": "图片",
    "brand": "品牌",
    "note": "备注",
    "spec": "规格",
    "category_id": "叶子类目 ID",
    "origin": "产地",
}

ALIASES: dict[str, tuple[str, ...]] = {
    "sku": (
        "sku",
        "货号",
        "商家编码",
        "库存sku",
        "销售sku",
        "msku",
        "seller sku",
        "product sku",
        "sku编码",
        "商品sku",
        "原厂sku",
        "sku编号",
    ),
    "name": ("品名", "中文名称", "产品名称", "商品名称", "name", "中文品名", "品名中文"),
    "title": ("英文标题", "标题", "title", "product title", "producttitle", "英文名称", "商品标题"),
    "keywords": ("关键词", "keywords", "keyword", "关键字"),
    "price": ("单价", "价格", "售价", "price", "fob", "usd", "单价usd", "销售价", "零售价", "fob价格"),
    "moq": ("起订量", "moq", "min order", "最小起订", "起订", "minorderquantity", "最小订购量"),
    "images": (
        "图片",
        "图片链接",
        "主图",
        "images",
        "image",
        "image url",
        "图片url",
        "图片地址",
        "图片链接地址",
        "主图链接",
    ),
    "note": ("备注", "说明", "note", "描述", "中文描述", "补充说明"),
    "spec": ("规格", "可见规格", "spec"),
    "brand": ("品牌", "brand", "商标", "品牌名"),
    "category_id": ("类目id", "类目", "category", "category_id", "cateid", "叶子类目", "分类id"),
    "origin": ("产地", "origin", "place of origin", "原产地"),
}

# User fills a short sheet. When a leaf category is chosen, required official
# attributes from schema.get become columns on 填写 — one sheet shape per leaf.
USER_FILLS: list[dict[str, Any]] = [
    {"id": "sku", "label": "货号", "required": True, "hint": "你自己的编码"},
    {"id": "price", "label": "单价 USD", "required": True, "hint": "红线，AI 不准定价"},
    {"id": "moq", "label": "起订量", "required": True, "hint": "红线，AI 不准编"},
    {"id": "images", "label": "图片", "required": False, "hint": "选填。有图写链接或文件名；没图留空。导入时再选原图上架、补转化位或重画"},
    {"id": "brand", "label": "品牌", "required": False, "hint": "没有就留空，等于无品牌"},
    {"id": "name", "label": "品名（中文）", "required": False, "hint": "给自己看，也可当提示"},
    {"id": "note", "label": "备注", "required": False, "hint": "规格列已经分开写了就不用重复。其它和别的货不一样的事实写这里。AI 当提示，不编没写的数字。"},
]

SPEC_LABELS = {
    "color_count": "色数",
    "piece_count": "支数",
    "hardness": "硬度",
    "finish": "是否水溶",
    "size": "尺寸",
    "material": "材质",
    "port": "接口",
    "capacity": "容量",
    "color": "颜色",
    "weight": "克重",
    "voltage": "电压功率",
    "pack_count": "箱规",
    "age": "适用年龄",
    "generic": "规格",
}

SPEC_ALIASES: dict[str, tuple[str, ...]] = {
    "spec.color_count": ("色数", "颜色数", "colors", "color count"),
    "spec.piece_count": ("支数", "件数", "套装件数", "pcs", "pieces"),
    "spec.hardness": ("硬度", "铅芯硬度", "hardness"),
    "spec.finish": ("是否水溶", "水溶", "finish"),
    "spec.size": ("尺寸", "尺码", "规格尺寸", "size"),
    "spec.material": ("材质", "面料", "毛材", "material"),
    "spec.port": ("接口", "端口", "port"),
    "spec.capacity": ("容量", "容量规格", "capacity"),
    "spec.color": ("颜色", "色组", "colorway"),
    "spec.weight": ("克重", "重量", "weight"),
    "spec.voltage": ("电压", "功率", "电压功率", "voltage"),
    "spec.pack_count": ("箱规", "装箱量", "pack"),
    "spec.age": ("适用年龄", "年龄段", "age"),
    "spec.generic": ("规格", "可见规格"),
}

# Official trade/logistics are shop resources, not model output.
SHOP_FILLS: list[dict[str, Any]] = [
    {"id": "origin", "label": "原产地", "hint": "整店填一次"},
    {"id": "priceUnit", "label": "计量单位", "hint": "按支 / 按套 / 按盒。跟货走的兜底"},
    {"id": "saleType", "label": "询盘或一口价", "hint": "整店通用"},
    {"id": "shipping", "label": "运费模板", "hint": "店里建好，发品时引用"},
    {"id": "leadTime", "label": "交期", "hint": "跟货走的兜底"},
    {"id": "pack", "label": "包装重量尺寸", "hint": "跟货走的兜底"},
    {"id": "payment", "label": "付款 / 港口", "hint": "整店通用"},
]

AI_FILLS_BASE: list[dict[str, Any]] = [
    {"id": "productTitle", "label": "英文标题", "hint": "按官方字节限制写。人要核对"},
    {"id": "productKeywords", "label": "关键词", "hint": "1～3 个。人要核对"},
    {"id": "textDesc", "label": "详描", "hint": "按图写，不编认证"},
    {"id": "catAttrs", "label": "类目属性", "hint": "按官方选项选。铅笔是铅芯颜色、铅芯硬度。选错但合法的只能人审拦住"},
    {"id": "superText", "label": "详描 / FAQ", "hint": "按图写，不编认证"},
]

REDLINE: list[dict[str, str]] = [
    {"id": "price", "label": "售价", "reason": "生意决策，AI 不准定价"},
    {"id": "moq", "label": "起订量", "reason": "生意决策，AI 不准编数量"},
    {"id": "images", "label": "实拍图", "reason": "有实拍可原图上架、留下再补转化位、或只当参考重画。生成图必须标黄，不准冒充实拍"},
    {"id": "brand", "label": "品牌", "reason": "有品牌你填；空着=无品牌。AI 不准编品牌名"},
    {"id": "category_id", "label": "叶子类目", "reason": "整表选一次。猜错类目发不出去、属性全废"},
    {"id": "origin", "label": "原产地", "reason": "走店铺默认，AI 不准改"},
    {"id": "certs", "label": "证书 / 资质", "reason": "CE / FDA 等不准编"},
    {"id": "logistics", "label": "运费 / 付款 / 港口", "reason": "走店铺默认，填一次即可"},
]

# Extra aliases that only fire when the seller picked that style, so a
# generic "名称" column is not stolen from 马帮's 中文名称.
STYLE_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "mabang": {
        "sku": ("库存sku", "sku"),
        "name": ("中文名称", "商品名称"),
        "title": ("英文名称",),
        "price": ("售价", "销售价"),
        "images": ("图片地址", "图片"),
        "note": ("备注",),
    }
}

STYLES: dict[str, dict[str, Any]] = {
    "simple": {
        "id": "simple",
        "label": "短表批量上品",
        "summary": "填写页只收依据。价和起订量必填。图可选：原图上架、留下再补转化位、或当参考重画套图；没图可画可跳过。",
        "columns": ["sku", "price", "moq", "images", "brand", "name", "note"],
        "create_drafts_default": True,
        "primary": True,
    },
    "full_schema": {
        "id": "full_schema",
        "label": "官方完整表（完全自己填）",
        "summary": "按 schema.get 返回的全部必填+选填字段生成列。7521 类各不同，自己填完再导入。",
        "columns": ["sku", "price", "moq", "images", "brand", "name", "note"],
        "create_drafts_default": True,
        "needs_category": True,
    },
    "lingxing": {
        "id": "lingxing",
        "label": "领星资料库",
        "summary": "先入库再铺店。表格是商品资料，和店铺无关；图、价、货号进商品库，再勾店铺铺货。",
        "columns": ["sku", "name", "price", "moq", "images", "note", "category_id", "origin"],
        "create_drafts_default": False,
    },
    "dianxiaomi": {
        "id": "dianxiaomi",
        "label": "店小秘按刊登模板",
        "summary": "先选一个刊登模板。表格只填货号 / 标题 / 价格 / 起订量，类目和物流走模板，导入后直接进草稿箱。",
        "columns": ["sku", "title", "keywords", "price", "moq", "images", "note"],
        "create_drafts_default": True,
        "needs_listing_template": True,
    },
    "detect": {
        "id": "detect",
        "label": "智能探测",
        "summary": "通途 / 马帮 / 自己的表都行。系统找表头、对列，你确认映射后再导入。",
        "columns": list(FIELDS),
        "create_drafts_default": False,
    },
    "mabang": {
        "id": "mabang",
        "label": "马帮库存SKU导出",
        "summary": "按马帮「商品 → 库存SKU → 导出」的列名预设映射，粘贴或另存后直接导。",
        "columns": ["sku", "name", "title", "price", "images", "note"],
        "create_drafts_default": False,
    },
    "alibaba": {
        "id": "alibaba",
        "label": "阿里官方类目表",
        "summary": "官方批量上传同一思路，但我们不下 40 列红星表。你只填货号、价格、起订量和图，其余 AI + 店铺默认。",
        "columns": ["sku", "price", "moq", "images", "note"],
        "create_drafts_default": True,
        "needs_category": True,
    },
}


@dataclass
class ExcelRow:
    sku: str = ""
    name: str = ""
    title: str = ""
    keywords: str = ""
    price: str = ""
    moq: str = ""
    images: list[str] = field(default_factory=list)
    brand: str = ""
    note: str = ""
    category_id: str = ""
    origin: str = ""
    spec: str = ""
    specs: dict[str, str] = field(default_factory=dict)
    line: int = 0
    raw: dict[str, str] = field(default_factory=dict)
    attributes: dict[str, dict[str, Any]] = field(default_factory=dict)
    schema_top: dict[str, str] = field(default_factory=dict)
    is_sample: bool = False

    def fact_text(self) -> str:
        bits: list[str] = []
        if self.note.strip():
            bits.append(self.note.strip())
        if self.spec.strip():
            bits.append(self.spec.strip())
        for key, value in self.specs.items():
            if str(value).strip():
                bits.append(f"{SPEC_LABELS.get(key, key)} {str(value).strip()}")
        return "；".join(bits)

    def image_specs(self) -> dict[str, str]:
        out = {key: str(value).strip() for key, value in self.specs.items() if str(value).strip()}
        if self.spec.strip() and "generic" not in out:
            out["generic"] = self.spec.strip()
        return out

    def seed_values(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        if self.title:
            values["productTitle"] = self.title
        words = [item.strip() for item in re.split(r"[,，;；]", self.keywords) if item.strip()]
        if words:
            values["productKeywords"] = {f"productKeywords_{index}": word for index, word in enumerate(words[:3])}
        if self.price and self.moq:
            values["ladderPrice"] = {"ladderPrice_0": {"quantity": self.moq, "price": self.price}}
        if self.moq:
            values["minOrderQuantity"] = self.moq
        if self.origin:
            values["origin"] = self.origin
        if self.category_id:
            values["catId"] = self.category_id
        for group, children in self.attributes.items():
            filled = {key: item for key, item in children.items() if item not in (None, "")}
            if filled:
                values[group] = filled
        for key, raw in self.schema_top.items():
            if raw not in (None, ""):
                values[key] = raw
        return values

    def provided_sources(self) -> dict[str, str]:
        sources: dict[str, str] = {}
        if self.title:
            sources["productTitle"] = "excel"
        if self.keywords:
            sources["productKeywords"] = "excel"
        if self.price:
            sources["ladderPrice"] = "excel"
            sources["scPrice"] = "excel"
        if self.moq:
            sources["minOrderQuantity"] = "excel"
        if self.origin:
            sources["origin"] = "excel"
        if self.category_id:
            sources["catId"] = "excel"
        for group in self.attributes:
            sources[group] = "excel"
        for key in self.schema_top:
            sources[key] = "excel"
        return sources

    def extra_defaults(self) -> dict[str, str]:
        """Shop-default overrides that AI must not invent (brand)."""
        return {"brand": self.brand} if self.brand else {}


EXAMPLE_ROW: dict[str, str] = {
    "sku": f"{SAMPLE_MARK}SKU-1001",
    "name": "油漆刷套装",
    "title": "Paint Brush Set for Wall Painting",
    "keywords": "paint brush, wall brush, decorating",
    "price": "1.80",
    "moq": "500",
    "images": "SKU-1001_1.jpg;SKU-1001_2.jpg",
    "brand": "",
    "note": "这行是示例，导入时自动跳过。从下一行开始写你的货。",
    "category_id": "",
    "origin": "China",
}


def _spec_col(field: str, hint: str, example: str = "") -> dict[str, Any]:
    key = field if field.startswith("spec.") else f"spec.{field}"
    short = key.split(".", 1)[1]
    return {
        "id": key,
        "label": SPEC_LABELS.get(short, short),
        "hint": hint,
        "example": example,
        "required": False,
    }


FAMILY_SHEETS: dict[str, dict[str, Any]] = {
    "stationery": {
        "title": "文具 / 彩铅填写表",
        "filename": "文具彩铅上品表",
        "filename_id": "stationery",
        "guide": "这一类买手看色号、支数、能不能水溶。规格列只写你确定的数；出图和标题按这些来，不编没写的 24 色 / HB。",
        "note_hint": "规格列已经分开写了就不用重复。其它和别的货不一样的事实写这里。",
        "spec_columns": [
            _spec_col("color_count", "如 12 / 24 / 36。没写就不画色数", "24"),
            _spec_col("piece_count", "一盒几支。没写就不写支数", "24"),
            _spec_col("hardness", "HB / 2B。没写就不编", "HB"),
            _spec_col("finish", "水溶 / 不水溶。没写就不标", "水溶"),
        ],
        "example": {
            "sku": f"{SAMPLE_MARK}SKU-CP24",
            "name": "水溶彩铅套装",
            "price": "2.40",
            "moq": "200",
            "images": "CP24_1.jpg",
            "note": "这行是示例，导入时自动跳过。从下一行开始写你的货。",
            "spec.color_count": "24",
            "spec.piece_count": "24",
            "spec.hardness": "HB",
            "spec.finish": "水溶",
        },
    },
    "tools": {
        "title": "五金 / 工具填写表",
        "filename": "五金工具上品表",
        "filename_id": "tools",
        "guide": "这一类买手看尺寸、材质、一套几件。只写看得见的规格，出图按主图样子和这些数来。",
        "note_hint": "规格列已经分开写了就不用重复。",
        "spec_columns": [
            _spec_col("size", "如 25cm / 2 inch。没写则尺寸图不加数字", "25cm"),
            _spec_col("material", "如 猪鬃、铁皮箍。没写就不指定材质", "猪鬃"),
            _spec_col("piece_count", "一套几件。没写就不写件数", "3"),
        ],
        "example": {
            "sku": f"{SAMPLE_MARK}SKU-BR25",
            "name": "油漆刷套装",
            "price": "1.80",
            "moq": "500",
            "images": "BR25_1.jpg",
            "note": "这行是示例，导入时自动跳过。从下一行开始写你的货。",
            "spec.size": "25cm",
            "spec.material": "猪鬃",
            "spec.piece_count": "3",
        },
    },
    "electronics": {
        "title": "消费电子填写表",
        "filename": "消费电子上品表",
        "filename_id": "electronics",
        "guide": "这一类买手看接口、容量、盒内配件。没写的接口和续航一律不编。",
        "note_hint": "规格列已经分开写了就不用重复。",
        "spec_columns": [
            _spec_col("port", "如 USB-C / 3.5mm。没写就不画接口名", "USB-C"),
            _spec_col("capacity", "如 5000mAh。没写就不写容量", ""),
            _spec_col("piece_count", "盒内几件。没写就不编配件", "1"),
        ],
        "example": {
            "sku": f"{SAMPLE_MARK}SKU-EB01",
            "name": "无线蓝牙耳机",
            "price": "6.80",
            "moq": "200",
            "images": "EB01_1.jpg",
            "note": "这行是示例，导入时自动跳过。从下一行开始写你的货。",
            "spec.port": "USB-C",
            "spec.piece_count": "1",
        },
    },
    "apparel": {
        "title": "服装 / 鞋包填写表",
        "filename": "服装鞋包上品表",
        "filename_id": "apparel",
        "guide": "这一类买手看尺码、色组、面料。没给的尺码表和颜色不编。",
        "note_hint": "规格列已经分开写了就不用重复。",
        "spec_columns": [
            _spec_col("size", "如 S-XL / 36-40。没写则尺码图不加数字", "S-XL"),
            _spec_col("color", "可订颜色，逗号分隔。没写就不编色", "黑,白"),
            _spec_col("material", "如 纯棉 180gsm。没写就不指定面料", "纯棉"),
        ],
        "example": {
            "sku": f"{SAMPLE_MARK}SKU-TS01",
            "name": "纯棉短袖T恤",
            "price": "3.20",
            "moq": "300",
            "images": "TS01_1.jpg",
            "note": "这行是示例，导入时自动跳过。从下一行开始写你的货。",
            "spec.size": "S-XL",
            "spec.color": "黑,白",
            "spec.material": "纯棉",
        },
    },
    "beauty": {
        "title": "美妆 / 个护填写表",
        "filename": "美妆个护上品表",
        "filename_id": "beauty",
        "guide": "这一类买手看容量和质地。不编功效数字和认证。",
        "note_hint": "规格列已经分开写了就不用重复。",
        "spec_columns": [
            _spec_col("capacity", "如 50ml。没写就不写容量", "50ml"),
            _spec_col("material", "质地，如 乳液 / 膏体。没写就不指定", "乳液"),
        ],
        "example": {
            "sku": f"{SAMPLE_MARK}SKU-CR50",
            "name": "保湿面霜",
            "price": "2.10",
            "moq": "500",
            "images": "CR50_1.jpg",
            "note": "这行是示例，导入时自动跳过。从下一行开始写你的货。",
            "spec.capacity": "50ml",
            "spec.material": "乳液",
        },
    },
    "home": {
        "title": "家居 / 厨具填写表",
        "filename": "家居厨具上品表",
        "filename_id": "home",
        "guide": "这一类买手看尺寸、材质、是单件还是套装。没写的尺寸不加数字。",
        "note_hint": "规格列已经分开写了就不用重复。",
        "spec_columns": [
            _spec_col("size", "如 350ml / 80x80cm。没写则尺寸图不加数字", "350ml"),
            _spec_col("material", "如 陶瓷、橡木。没写就不指定", "陶瓷"),
            _spec_col("piece_count", "套装件数。没写就按单件", "1"),
        ],
        "example": {
            "sku": f"{SAMPLE_MARK}SKU-MG01",
            "name": "陶瓷马克杯",
            "price": "1.50",
            "moq": "500",
            "images": "MG01_1.jpg",
            "note": "这行是示例，导入时自动跳过。从下一行开始写你的货。",
            "spec.size": "350ml",
            "spec.material": "陶瓷",
            "spec.piece_count": "1",
        },
    },
    "toys": {
        "title": "玩具 / 母婴填写表",
        "filename": "玩具母婴上品表",
        "filename_id": "toys",
        "guide": "这一类买手看件数和适用年龄。不编安全认证。",
        "note_hint": "规格列已经分开写了就不用重复。",
        "spec_columns": [
            _spec_col("piece_count", "套装件数。没写就不编件数", "12"),
            _spec_col("age", "如 3+。没写就不标年龄", ""),
        ],
        "example": {
            "sku": f"{SAMPLE_MARK}SKU-PZ12",
            "name": "木制拼图",
            "price": "2.80",
            "moq": "200",
            "images": "PZ12_1.jpg",
            "note": "这行是示例，导入时自动跳过。从下一行开始写你的货。",
            "spec.piece_count": "12",
        },
    },
    "jewelry": {
        "title": "饰品 / 手表填写表",
        "filename": "饰品手表上品表",
        "filename_id": "jewelry",
        "guide": "这一类买手看材质、尺寸、克重。没写的克重和成色不编。",
        "note_hint": "规格列已经分开写了就不用重复。",
        "spec_columns": [
            _spec_col("material", "如 925银、不锈钢。没写就不指定", "不锈钢"),
            _spec_col("size", "如 16-18cm。没写则尺寸图不加数字", ""),
            _spec_col("weight", "克重。没写就不写克数", ""),
        ],
        "example": {
            "sku": f"{SAMPLE_MARK}SKU-RG01",
            "name": "不锈钢戒指",
            "price": "0.80",
            "moq": "200",
            "images": "RG01_1.jpg",
            "note": "这行是示例，导入时自动跳过。从下一行开始写你的货。",
            "spec.material": "不锈钢",
        },
    },
    "industrial": {
        "title": "机械 / 工业件填写表",
        "filename": "机械工业上品表",
        "filename_id": "industrial",
        "guide": "这一类买手看电压、接口、已知型号。没写的参数和认证不编。",
        "note_hint": "规格列已经分开写了就不用重复。",
        "spec_columns": [
            _spec_col("voltage", "如 220V / 1.5kW。没写就不写电参数", ""),
            _spec_col("port", "接口或法兰。没写就不画接口名", ""),
            _spec_col("generic", "已知型号，只写铭牌上有的", ""),
        ],
        "example": {
            "sku": f"{SAMPLE_MARK}SKU-PM01",
            "name": "小型水泵",
            "price": "28.00",
            "moq": "50",
            "images": "PM01_1.jpg",
            "note": "这行是示例，导入时自动跳过。从下一行开始写你的货。",
        },
    },
    "food": {
        "title": "食品 / 农产品填写表",
        "filename": "食品农产品上品表",
        "filename_id": "food",
        "guide": "这一类买手看克重和箱规。不编有机 / FDA 标志。",
        "note_hint": "规格列已经分开写了就不用重复。",
        "spec_columns": [
            _spec_col("weight", "如 250g。没写就不写克重", "250g"),
            _spec_col("pack_count", "如 20 bags / carton。没写则外箱不加数量", "20 bags / carton"),
        ],
        "example": {
            "sku": f"{SAMPLE_MARK}SKU-TEA01",
            "name": "绿茶袋泡茶",
            "price": "1.20",
            "moq": "500",
            "images": "TEA01_1.jpg",
            "note": "这行是示例，导入时自动跳过。从下一行开始写你的货。",
            "spec.weight": "250g",
            "spec.pack_count": "20 bags / carton",
        },
    },
    "sports": {
        "title": "运动 / 户外填写表",
        "filename": "运动户外上品表",
        "filename_id": "sports",
        "guide": "这一类买手看尺寸和材质。没写的尺码不加数字。",
        "note_hint": "规格列已经分开写了就不用重复。",
        "spec_columns": [
            _spec_col("size", "如 65cm。没写则尺寸图不加数字", ""),
            _spec_col("material", "如 尼龙、EVA。没写就不指定", ""),
        ],
        "example": {
            "sku": f"{SAMPLE_MARK}SKU-YG01",
            "name": "瑜伽垫",
            "price": "3.60",
            "moq": "200",
            "images": "YG01_1.jpg",
            "note": "这行是示例，导入时自动跳过。从下一行开始写你的货。",
        },
    },
    "general": {
        "title": "通用工业品填写表",
        "filename": "通用上品表",
        "filename_id": "general",
        "guide": "认不出更细的品类时用这张。规格列只写看得见的事实，出图按主图和这些依据来。",
        "note_hint": "规格列已经分开写了就不用重复。",
        "spec_columns": [
            _spec_col("generic", "只写看得见的规格，例如尺寸、件数。没写就不编", ""),
        ],
        "example": {
            "sku": f"{SAMPLE_MARK}SKU-1001",
            "name": "批发商品",
            "price": "1.80",
            "moq": "500",
            "images": "SKU-1001_1.jpg",
            "note": "这行是示例，导入时自动跳过。从下一行开始写你的货。",
        },
    },
}


FAMILY_HEADER_COLORS = {
    "stationery": "1D4ED8",
    "tools": "B45309",
    "electronics": "0F766E",
    "apparel": "7C3AED",
    "beauty": "BE185D",
    "home": "047857",
    "toys": "C2410C",
    "jewelry": "A16207",
    "industrial": "334155",
    "food": "15803D",
    "sports": "0369A1",
    "general": "334155",
}


def sheet_profile(
    category_name: str = "",
    product_hint: str = "",
    *,
    category_id: str = "",
    attr_columns: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Fill sheet profile: leaf schema columns when category_id is set, else family fallback."""
    hint = " / ".join(part for part in (category_name, product_hint) if str(part or "").strip())
    if category_id:
        short = (hint.split("/")[-1].strip() if hint else category_id)[:32]
        attrs = list(attr_columns or [])
        is_full = bool(attrs) and str(attrs[0].get("id", "")).startswith("schema.")
        if is_full:
            req = sum(1 for col in attrs if col.get("required"))
            opt = len(attrs) - req
            return {
                "family_id": "full_schema",
                "family_name": "官方完整表",
                "category_id": category_id,
                "title": f"完整填写表 · {short}" if short else f"完整填写表 · {category_id}",
                "filename": f"完整表-{category_id}",
                "filename_id": f"full-{category_id}",
                "guide": (
                    f"按 schema.get 生成：必填 {req} 列、选填 {opt} 列（共 {len(attrs)}）。"
                    "7521 个叶子类目各不同。带下拉的列请选官方选项。"
                ),
                "spec_columns": [],
                "attr_columns": attrs,
                "example": dict(EXAMPLE_ROW),
                "note_hint": "选填。官方字段列已经分开写了就不用重复。",
                "category_name": hint or category_id,
                "header_color": "7C3AED",
                "required_count": req,
                "optional_count": opt,
            }
        attrs = list(attr_columns or [])
        return {
            "family_id": "leaf",
            "family_name": "叶子类目",
            "category_id": category_id,
            "title": f"填写表 · {short}" if short else f"填写表 · {category_id}",
            "filename": f"填写表-{category_id}",
            "filename_id": category_id,
            "guide": (
                "这张表按所选叶子类目从官方 schema 生成列，7540 个叶子类目各有一套。"
                "货号、单价、起订量必填；带下拉的列必须选官方选项，不选 Other。"
            ),
            "spec_columns": [],
            "attr_columns": attrs,
            "example": dict(EXAMPLE_ROW),
            "note_hint": "选填。官方属性列已经分开写了就不用重复。",
            "category_name": hint or category_id,
            "header_color": "0F766E",
        }
    if not hint.strip():
        return {
            "family_id": "",
            "family_name": "",
            "title": "短表批量上品",
            "filename": "短表批量上品",
            "filename_id": "generic",
            "guide": "先选叶子类目，系统会按该类目的官方 schema 生成填写列。",
            "spec_columns": [],
            "attr_columns": [],
            "example": dict(EXAMPLE_ROW),
            "note_hint": USER_FILLS[-1]["hint"],
            "category_name": "",
            "header_color": "171717",
        }
    from .image_templates import pick_family

    family = pick_family(category_name, product_hint)
    preset = dict(FAMILY_SHEETS.get(family.id) or FAMILY_SHEETS["general"])
    short = (category_name or product_hint or "").split("/")[-1].strip()[:32]
    title = preset["title"] if not short else f"{preset['title']} · {short}"
    return {
        "family_id": family.id,
        "family_name": family.name,
        "title": title,
        "filename": preset["filename"],
        "filename_id": preset["filename_id"],
        "guide": preset["guide"],
        "spec_columns": [dict(item) for item in preset["spec_columns"]],
        "attr_columns": [],
        "example": dict(preset.get("example") or EXAMPLE_ROW),
        "note_hint": preset.get("note_hint") or USER_FILLS[-1]["hint"],
        "category_name": hint,
        "header_color": FAMILY_HEADER_COLORS.get(family.id, "171717"),
    }


def fill_headers(style: str, profile: dict[str, Any] | None = None) -> list[tuple[str, str, str]]:
    """(field_id, label, hint) for the fill sheet, including category spec columns."""
    spec = STYLES.get(style) or STYLES["simple"]
    hints = {
        "sku": "你自己的货号。一行一个商品，往下接着写就行，一张表可以写很多个。",
        "price": "红线。生意决策，AI 不准定价。",
        "moq": "红线。AI 不准编起订量。",
        "images": "选填。有图写文件名或 URL，分号分隔。没图留空。导入时再选原图上架、留下补转化位、或当参考重画套图。",
        "brand": "红线。有品牌就填；空着=无品牌。AI 不准编品牌名。",
        "name": "选填。给自己看，也可当中文提示。",
        "note": (profile or {}).get("note_hint")
        or "选填。规格列已经分开写了就不用重复。其它事实写这里。AI 当提示，不编没写的数字。",
        "title": "有现成英文标题才填。短表不用填，交给 AI。",
        "keywords": "有现成关键词才填。短表不用填，交给 AI。",
        "category_id": "红线。短表在下载时整表选定，不要每行让 AI 猜。",
        "origin": "红线。走店铺默认，不要填在短表里。",
        "spec": "只写看得见的规格。没写就不编。",
    }
    spec_cols = list((profile or {}).get("spec_columns") or [])
    attr_cols = list((profile or {}).get("attr_columns") or [])
    tail_cols = spec_cols or attr_cols
    core = [field_id for field_id in spec["columns"] if not tail_cols or field_id != "note"]
    rows: list[tuple[str, str, str]] = []
    for field_id in core:
        rows.append((field_id, FIELDS[field_id], hints.get(field_id) or f"系统字段：{field_id}"))
    for col in spec_cols:
        rows.append((col["id"], col["label"], col.get("hint") or "只写你确定的规格，没写就不编"))
    for col in attr_cols:
        label = _attr_label(str(col.get("header") or col.get("label") or col.get("field_id") or ""))
        options = col.get("options") or []
        opt_hint = " / ".join(str(item.get("label") or item.get("value") or "") for item in options[:8])
        hint = f"官方必填。按选项选，不选 Other。{('选项：' + opt_hint) if opt_hint else ''}"
        rows.append((col["id"], label, hint))
    if tail_cols:
        rows.append(("note", FIELDS["note"], hints["note"]))
    return rows


def sheet_preview(style: str = "simple", profile: dict[str, Any] | None = None) -> dict[str, Any]:
    """What the seller sees before they download: short headers + one example row.

    This is not the official 40-column form. With a leaf category, required
    attributes from schema.get appear as columns on the fill sheet.
    """
    spec = STYLES.get(style) or STYLES["simple"]
    example = dict(EXAMPLE_ROW)
    if profile and profile.get("example"):
        example.update(profile["example"])
    columns = [
        {
            "id": field_id,
            "label": label,
            "required": field_id in {"sku", "price", "moq"},
            "example": example.get(field_id, ""),
        }
        for field_id, label, _hint in fill_headers(style, profile)
    ]
    note = "不是阿里后台那张 40 列表。货号、单价、起订量必填；选了叶子类目后，官方必填属性会出现在填写页。"
    if profile and profile.get("family_id") == "leaf":
        note = (
            "按所选叶子类目从官方 schema 生成列，7540 个叶子类目各有一套。"
            "货号、单价、起订量必填；带下拉的列请选官方选项。"
        )
    if profile and profile.get("guide"):
        note = f"{profile['guide']} {note}"
    return {
        "style": spec["id"],
        "from_official_form": False,
        "note": note,
        "columns": columns,
        "example_skipped": True,
        "family_id": (profile or {}).get("family_id") or "",
        "title": (profile or {}).get("title") or spec["label"],
    }


ATTR_LABELS_ZH = {
    "lead color": "铅芯颜色",
    "lead hardness": "铅芯硬度",
    "origin": "原产地",
    "type": "类型",
    "color": "颜色",
}


def _attr_label(name: str) -> str:
    return ATTR_LABELS_ZH.get((name or "").strip().lower(), name)


def fill_policy(
    ai_attrs: list[dict[str, Any]] | None = None,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    extras = ai_attrs or []
    on_sheet = bool((profile or {}).get("attr_columns"))
    ai_fills = [item for item in AI_FILLS_BASE if item["id"] != "catAttrs" or (not extras and not on_sheet)]
    if not on_sheet:
        for extra in extras:
            raw = extra.get("header") or extra.get("label") or extra.get("name") or ""
            ai_fills.append(
                {
                    "id": extra.get("id") or extra.get("field_id") or extra.get("header"),
                    "label": _attr_label(str(raw)),
                    "hint": "按官方选项选，不选 Other。选错但合法的只能人审拦住",
                }
            )
    user_fills = [dict(item) for item in USER_FILLS]
    if profile and profile.get("attr_columns"):
        note = user_fills.pop() if user_fills and user_fills[-1]["id"] == "note" else None
        for col in profile["attr_columns"]:
            label = _attr_label(str(col.get("header") or col.get("label") or col.get("field_id") or ""))
            user_fills.append(
                {
                    "id": col["id"],
                    "label": label,
                    "required": bool(col.get("required", True)),
                    "hint": "官方必填，按选项选" if col.get("required", True) else "官方选填，按选项选",
                }
            )
        if note is not None:
            user_fills.append(note)
    elif profile and profile.get("spec_columns"):
        note = user_fills.pop() if user_fills and user_fills[-1]["id"] == "note" else None
        for col in profile["spec_columns"]:
            user_fills.append(
                {
                    "id": col["id"],
                    "label": col["label"],
                    "required": False,
                    "hint": col.get("hint") or "只写你确定的规格，没写就不编",
                }
            )
        if note is not None:
            note = dict(note)
            note["hint"] = profile.get("note_hint") or note.get("hint") or ""
            user_fills.append(note)
    return {
        "user_fills": user_fills,
        "shop_fills": [dict(item) for item in SHOP_FILLS],
        "ai_fills": ai_fills,
        "redline": [dict(item) for item in REDLINE],
        "guarantee": "不能保证 AI 零出错。能保证：红线不让它编；官方必填对不上发不出；没人审过发不出。选了错误但合法的选项（比如 HB 写成 2B），只能人看出来。",
    }


def styles_view() -> list[dict[str, Any]]:
    policy = fill_policy()
    rows = []
    for item in STYLES.values():
        row = dict(item)
        if item["id"] == "simple":
            row["policy"] = policy
        rows.append(row)
    return rows


def category_attr_columns(fields: Iterable[Any]) -> list[dict[str, Any]]:
    """Required attributes for this leaf, minus shop-default origin."""
    columns: list[dict[str, Any]] = []
    for group in fields:
        if getattr(group, "id", "") not in {"icbuCatProp", "saleProp"}:
            continue
        for child in getattr(group, "children", []):
            if not getattr(child, "required", False) or child.id in SKIP_ATTR_IDS:
                continue
            options = [
                {"value": option.value, "label": option.display_name}
                for option in (getattr(child, "options", None) or [])[:80]
            ]
            columns.append(
                {
                    "id": f"attr.{group.id}.{child.id}",
                    "header": child.name or child.id,
                    "label": _attr_label(child.name or child.id),
                    "group": group.id,
                    "field_id": child.id,
                    "required": True,
                    "options": options,
                }
            )
    return columns


def schema_field_columns(fields: Iterable[Any]) -> list[dict[str, Any]]:
    """All fillable fields from schema.get — required and optional."""
    columns: list[dict[str, Any]] = []

    def append_field(group_id: str, group_name: str, spec: Any) -> None:
        if getattr(spec, "type", "") == "label" or spec.id in SKIP_ATTR_IDS:
            return
        options = [
            {"value": option.value, "label": option.display_name}
            for option in (getattr(spec, "options", None) or [])[:80]
        ]
        label = _attr_label(str(getattr(spec, "name", "") or spec.id))
        header = str(getattr(spec, "name", "") or spec.id)
        if group_name and group_id != spec.id:
            header = f"{group_name} / {header}"
        field_path = f"{group_id}.{spec.id}" if group_id else spec.id
        columns.append(
            {
                "id": f"schema.{field_path}",
                "header": header,
                "label": label,
                "group": group_id or spec.id,
                "field_id": spec.id,
                "field_path": field_path,
                "required": bool(getattr(spec, "required", False)),
                "field_type": getattr(spec, "type", ""),
                "options": options,
            }
        )

    for group in fields:
        if getattr(group, "type", "") == "label":
            continue
        children = list(getattr(group, "children", None) or [])
        if children:
            group_name = str(getattr(group, "name", "") or group.id)
            for child in children:
                append_field(group.id, group_name, child)
        else:
            append_field("", "", group)
    return columns


def flatten_schema_fields(fields: Iterable[Any]) -> list[dict[str, Any]]:
    """Flat list for API/UI: every fillable field with required flag."""
    rows: list[dict[str, Any]] = []
    for col in schema_field_columns(fields):
        rows.append(
            {
                "group_id": col["group"],
                "field_id": col["field_id"],
                "field_path": col["field_path"],
                "name": col["header"],
                "label": col["label"],
                "required": col["required"],
                "field_type": col.get("field_type") or "",
                "option_count": len(col.get("options") or []),
                "options": col.get("options") or [],
            }
        )
    return rows


def _match_option(raw: str, options: list[dict[str, str]]) -> str:
    needle = _norm(raw)
    if not needle:
        return ""
    for option in options:
        if needle in {_norm(option.get("label") or ""), _norm(option.get("value") or "")}:
            return option.get("value") or raw
    return raw


def _norm(text: str) -> str:
    return re.sub(r"[\s_\-()/（）]+", "", (text or "").strip().lower())


def looks_like_sample(sku: str, name: str = "") -> bool:
    for text in (sku, name):
        stripped = (text or "").strip().lower()
        if any(stripped.startswith(prefix) for prefix in SAMPLE_PREFIXES):
            return True
    return False


def drop_samples(rows: list[ExcelRow]) -> tuple[list[ExcelRow], int]:
    kept = [row for row in rows if not row.is_sample]
    return kept, len(rows) - len(kept)


def guess_field(header: str, style: str = "detect") -> str:
    needle = _norm(header)
    if not needle:
        return ""
    extra = STYLE_ALIASES.get(style, {})
    for field_id, aliases in extra.items():
        if needle in {_norm(alias) for alias in aliases}:
            return field_id
    for field_id, aliases in ALIASES.items():
        if needle in {_norm(alias) for alias in aliases}:
            return field_id
    for field_id, aliases in SPEC_ALIASES.items():
        if needle in {_norm(alias) for alias in aliases}:
            return field_id
    return ""


def guess_style(headers: Iterable[str]) -> str:
    names = {_norm(item) for item in headers}
    if {"库存sku", "中文名称"} & names or "库存sku" in names:
        return "mabang"
    if "英文标题" in names and "关键词" in names:
        return "dianxiaomi"
    if {"货号", "单价usd", "起订量", "图片"} <= names and "英文标题" not in names:
        return "simple"
    if "货号" in names and ("单价usd" in names or "起订量" in names):
        return "lingxing"
    return "detect"


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def read_sheet(content: bytes) -> list[list[str]]:
    book = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    try:
        sheet = book[book.sheetnames[0]]
        rows: list[list[str]] = []
        for raw in sheet.iter_rows(values_only=True):
            rows.append([_cell(item) for item in raw])
        return rows
    finally:
        book.close()


def find_header_row(rows: list[list[str]], style: str = "detect") -> int:
    best_index, best_score = 0, -1
    for index, row in enumerate(rows[:20]):
        score = sum(1 for cell in row if guess_field(cell, style))
        if score > best_score:
            best_index, best_score = index, score
    return best_index


def mapping_from_headers(
    headers: list[str],
    style: str = "detect",
    extra_columns: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    used: set[str] = set()
    extras = {_norm(item["header"]): item["id"] for item in extra_columns or [] if item.get("header")}
    extras.update({_norm(item.get("label") or ""): item["id"] for item in extra_columns or [] if item.get("label")})
    extras.update({_norm(item.get("field_id") or ""): item["id"] for item in extra_columns or [] if item.get("field_id")})
    for header in headers:
        field_id = extras.get(_norm(header)) or guess_field(header, style)
        if field_id and field_id not in used:
            mapping[header] = field_id
            used.add(field_id)
    return mapping


def parse_rows(
    rows: list[list[str]],
    mapping: dict[str, str],
    header_index: int,
    extra_columns: list[dict[str, Any]] | None = None,
) -> list[ExcelRow]:
    if header_index >= len(rows):
        return []
    headers = rows[header_index]
    extra_by_id = {item["id"]: item for item in extra_columns or []}
    parsed: list[ExcelRow] = []
    for offset, raw in enumerate(rows[header_index + 1 :], start=header_index + 2):
        cells = {headers[index]: raw[index] if index < len(raw) else "" for index in range(len(headers))}
        values = {field_id: "" for field_id in FIELDS}
        attributes: dict[str, dict[str, Any]] = {}
        schema_top: dict[str, str] = {}
        specs: dict[str, str] = {}
        for header, field_id in mapping.items():
            cell = cells.get(header, "")
            if field_id in values:
                values[field_id] = cell
            elif field_id.startswith("spec.") and cell:
                specs[field_id.split(".", 1)[1]] = cell
            elif field_id.startswith("attr.") and cell:
                spec = extra_by_id.get(field_id)
                if spec:
                    attributes.setdefault(spec["group"], {})[spec["field_id"]] = _match_option(
                        cell, spec.get("options") or []
                    )
            elif field_id.startswith("schema.") and cell:
                spec = extra_by_id.get(field_id)
                parts = field_id.split(".")
                if len(parts) == 2:
                    top_id = parts[1]
                    if top_id == "productTitle":
                        values["title"] = cell
                    elif top_id.startswith("productKeywords"):
                        values["keywords"] = cell if not values["keywords"] else f"{values['keywords']},{cell}"
                    else:
                        schema_top[top_id] = _match_option(cell, (spec or {}).get("options") or []) or cell
                elif len(parts) >= 3:
                    group, child_id = parts[1], parts[2]
                    attributes.setdefault(group, {})[child_id] = _match_option(
                        cell, (spec or {}).get("options") or []
                    )
        if not any(values.values()) and not attributes and not schema_top:
            continue
        images = [item.strip() for item in re.split(r"[;；\n]+", values["images"]) if item.strip()]
        parsed.append(
            ExcelRow(
                sku=values["sku"],
                name=values["name"],
                title=values["title"],
                keywords=values["keywords"],
                price=values["price"],
                moq=values["moq"],
                images=images,
                brand=values.get("brand") or "",
                note=values["note"],
                category_id=values["category_id"],
                origin=values["origin"],
                spec=values.get("spec") or "",
                specs=specs,
                line=offset,
                raw=cells,
                attributes=attributes,
                schema_top=schema_top,
                is_sample=looks_like_sample(values["sku"], values["name"]),
            )
        )
    return parsed


def normalize_image_mode(value: str | None) -> str:
    mode = (value or "keep_draw").strip().lower().replace("-", "_")
    mode = IMAGE_MODE_ALIASES.get(mode, mode)
    return mode if mode in IMAGE_MODES else "keep_draw"


def split_image_mode(value: str | None) -> tuple[str, str]:
    mode = normalize_image_mode(value)
    photo, empty = mode.rsplit("_", 1)
    return photo, empty


def decide_image_action(has_photos: bool, mode: str | None) -> str:
    """use_photos | complete | generate | skip — after files have been resolved."""
    photo, empty = split_image_mode(mode)
    if has_photos:
        if photo == "keep":
            return "use_photos"
        if photo == "complete":
            return "complete"
        return "generate"
    if empty == "skip":
        return "skip"
    return "generate"


def image_stats(rows: list[ExcelRow]) -> dict[str, int]:
    counts = [len(row.images) for row in rows]
    return {
        "with_sheet_images": sum(1 for count in counts if count),
        "without_sheet_images": sum(1 for count in counts if not count),
        "partial_sheet_images": sum(1 for count in counts if 0 < count < 6),
        "full_sheet_images": sum(1 for count in counts if count >= 6),
        "single_sheet_image": sum(1 for count in counts if count == 1),
    }


def missing_image_message(mode: str | None) -> str:
    _photo, empty = split_image_mode(mode)
    if empty == "skip":
        return "表里没写图片。导入时若没拖进同货号的图，这行会跳过。"
    return "表里没写图片。导入时拖进同货号的图就用；否则按品名画一套并标黄。"


def preview(
    content: bytes,
    style: str = "detect",
    extra_columns: list[dict[str, Any]] | None = None,
    image_mode: str = "keep_draw",
) -> dict[str, Any]:
    rows = read_sheet(content)
    if not rows:
        return {"error": "表格是空的", "headers": [], "mapping": {}, "rows_preview": [], "row_count": 0}
    header_index = find_header_row(rows, style)
    headers = [item or f"列{index + 1}" for index, item in enumerate(rows[header_index])]
    guessed_style = style if style != "detect" else guess_style(headers)
    mapping = mapping_from_headers(headers, guessed_style if style == "detect" else style, extra_columns)
    parsed, sample_skipped = drop_samples(parse_rows(rows, mapping, header_index, extra_columns))
    mode = normalize_image_mode(image_mode)
    issues = row_checks(parsed, mode)
    blocked = {item["line"] for item in issues if item["level"] == "red"}
    return {
        "style": style,
        "style_guess": guessed_style,
        "header_row": header_index + 1,
        "headers": headers,
        "mapping": mapping,
        "fields": [{"id": key, "label": label} for key, label in FIELDS.items()],
        "rows_preview": [item.raw for item in parsed[:8]],
        "row_count": len(parsed),
        "sample_skipped": sample_skipped,
        "ready_count": len(parsed) - len(blocked),
        "blocked_count": len(blocked),
        "row_issues": issues,
        "mapped_count": len(mapping),
        "warnings": _preview_warnings(parsed, mapping, sample_skipped, mode),
        "image_mode": mode,
        "photo_policy": split_image_mode(mode)[0],
        "empty_policy": split_image_mode(mode)[1],
        "image_stats": image_stats(parsed),
    }


def row_checks(rows: list[ExcelRow], image_mode: str = "keep_draw") -> list[dict[str, Any]]:
    """Per-row problems, found before a single AI call is spent on the batch."""
    issues: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    mode = normalize_image_mode(image_mode)
    for row in rows:
        label = row.sku or row.name or f"第 {row.line} 行"
        if not row.price:
            issues.append({"line": row.line, "sku": label, "level": "red", "message": "缺单价。价格是红线，AI 不代填。"})
        if not row.moq:
            issues.append({"line": row.line, "sku": label, "level": "red", "message": "缺起订量。AI 不代填。"})
        if not row.images:
            issues.append({"line": row.line, "sku": label, "level": "yellow", "message": missing_image_message(mode)})
        key = _norm(row.sku)
        if key and key in seen:
            issues.append(
                {"line": row.line, "sku": label, "level": "yellow", "message": f"货号和第 {seen[key]} 行重复，会当成两个商品。"}
            )
        elif key:
            seen[key] = row.line
    return issues


def _preview_warnings(
    rows: list[ExcelRow],
    mapping: dict[str, str],
    sample_skipped: int = 0,
    image_mode: str = "keep_draw",
) -> list[str]:
    warnings: list[str] = []
    if sample_skipped:
        warnings.append(f"跳过 {sample_skipped} 行示例。模板第 2 行是样例，不会被当成你的货。")
    if "sku" not in mapping.values():
        warnings.append("没有对上货号列。没有货号时会用第 1 张图的文件名。")
    if "price" not in mapping.values():
        warnings.append("没有对上价格列。价格是生意决策，AI 不会代填。")
    if "images" not in mapping.values():
        warnings.append("没有对上图片列。有图可拖进来按货号匹配；没图的行按你选的规则画套图或跳过。")
    stats = image_stats(rows)
    photo, empty = split_image_mode(image_mode)
    if photo == "boost":
        warnings.append("有图的行只当参考，会重画 6 张转化套图并标黄，不当实拍。")
    elif photo == "complete" and stats["partial_sheet_images"]:
        warnings.append(
            f"{stats['partial_sheet_images']} 行图还不满 6 张。原图会留下，缺的按国际站转化位补上并标黄。"
        )
    elif photo == "keep" and stats["partial_sheet_images"]:
        warnings.append(
            f"{stats['partial_sheet_images']} 行图不满 6 张。选「原图上架」就有几张用几张；想提高转化可选补齐或重画套图。"
        )
    if empty == "skip" and stats["without_sheet_images"]:
        warnings.append(f"{stats['without_sheet_images']} 行表里没图，导入时若对不上文件会跳过。")
    elif empty == "draw" and stats["without_sheet_images"] and photo != "boost":
        warnings.append(f"{stats['without_sheet_images']} 行表里没图。对不上文件就按品名画一套并标黄。")
    empty_sku = sum(1 for item in rows if not item.sku)
    if empty_sku:
        warnings.append(f"{empty_sku} 行没有货号。")
    if len(rows) > BATCH_SOFT_LIMIT:
        warnings.append(f"{len(rows)} 行会排队成稿，一条一条过 AI，建议分批导。")
    return warnings


def apply_preview(
    content: bytes,
    mapping: dict[str, str],
    style: str = "detect",
    extra_columns: list[dict[str, Any]] | None = None,
) -> list[ExcelRow]:
    rows = read_sheet(content)
    header_index = find_header_row(rows, style)
    kept, _ = drop_samples(parse_rows(rows, mapping, header_index, extra_columns))
    return kept


def split_images(refs: list[str]) -> tuple[list[str], list[str]]:
    urls, names = [], []
    for item in refs:
        parsed = urlparse(item)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            urls.append(item)
        else:
            names.append(item.rsplit("/", 1)[-1])
    return urls, names


def resolve_row_files(
    row: ExcelRow,
    uploads: dict[str, bytes],
    fetch_url: Callable[[str], tuple[str, bytes] | None] | None = None,
) -> list[tuple[str, bytes]]:
    """Sheet links + dragged files. One match is enough; never pad to 6."""
    urls, names = split_images(row.images)
    files = match_uploads(row.sku, names, uploads)
    if fetch_url is not None:
        for url in urls[:6]:
            fetched = fetch_url(url)
            if fetched:
                files.append(fetched)
    return files[:6]


def match_uploads(sku: str, names: list[str], uploads: dict[str, bytes]) -> list[tuple[str, bytes]]:
    """Match extra files by exact name, then by SKU prefix (factory habit)."""
    matched: list[tuple[str, bytes]] = []
    used: set[str] = set()
    for name in names:
        key = name.lower()
        if key in uploads and key not in used:
            matched.append((name, uploads[key]))
            used.add(key)
    prefix = (sku or "").lower()
    if prefix:
        for filename, content in uploads.items():
            if filename in used:
                continue
            stem = filename.rsplit(".", 1)[0]
            if stem == prefix or stem.startswith(f"{prefix}_") or stem.startswith(f"{prefix}-"):
                matched.append((filename, content))
                used.add(filename)
    return matched


def who_fills(field_id: str) -> str:
    if field_id in {"productTitle", "productKeywords", "textDesc", "icbuCatProp", "saleProp", "superText"}:
        return "AI 生成（不进填写表）"
    if field_id in {"ladderPrice", "fob", "scPrice", "minOrderQuantity"}:
        return "红线：你在「填写」表填（价格、起订量）"
    if field_id in {"scImages"}:
        return "有图你填；导入时再选原图上架、补转化位或重画。生成图必须标黄"
    if field_id in {"brand"}:
        return "红线：有品牌你填；空着=无品牌。AI 不准编"
    if field_id in {"origin", "priceUnit", "paymentMethod", "port", "shippingTemplateId", "pkgMeasure", "pkgWeight", "logisticsMode", "logisticsProperty", "marketSample", "market"}:
        return "红线：店铺默认，AI 不准改"
    return "系统按官方 schema 补齐"


def build_template(
    style: str,
    listing_template: dict[str, Any] | None = None,
    official_required: list[dict[str, str]] | None = None,
    extra_columns: list[dict[str, Any]] | None = None,
    category_name: str = "",
    category_id: str = "",
) -> bytes:
    spec = STYLES.get(style) or STYLES["simple"]
    listing = listing_template or {}
    resolved_category_id = category_id or str(listing.get("category_id") or "")
    profile = None
    if style == "simple":
        if resolved_category_id:
            profile = sheet_profile(
                category_name or str(listing.get("name") or ""),
                category_id=resolved_category_id,
                attr_columns=list(extra_columns or []),
            )
        elif category_name or listing.get("name"):
            profile = sheet_profile(category_name or str(listing.get("name") or ""))
    book = Workbook()
    sheet = book.active
    tab = ((profile or {}).get("filename") or "填写").replace("/", "")[:31] or "填写"
    sheet.title = tab
    color = (profile or {}).get("header_color") or ("171717" if spec.get("primary") else "1D4ED8")
    fill = PatternFill("solid", fgColor=color)
    font = Font(color="FFFFFF", bold=True)
    example = {
        **EXAMPLE_ROW,
        "category_id": resolved_category_id,
        **((profile or {}).get("example") or {}),
    }
    headers = fill_headers(style, profile)
    attr_by_id = {col["id"]: col for col in (extra_columns or []) if col.get("id")}
    for index, (field_id, label, hint) in enumerate(headers, start=1):
        cell = sheet.cell(1, index, label)
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(wrap_text=True)
        cell.comment = Comment(hint or f"系统字段：{field_id}", "Auto Shoper")
        sample = sheet.cell(2, index, example.get(field_id, ""))
        sample.font = Font(color="9AA0A6", italic=True)
        width = 28
        if field_id.startswith("spec.") or field_id.startswith("attr."):
            width = 24
        sheet.column_dimensions[get_column_letter(index)].width = width
        meta = attr_by_id.get(field_id) or {}
        options = meta.get("options") or []
        if options:
            from openpyxl.worksheet.datavalidation import DataValidation

            labels = [str(item.get("label") or item.get("value") or "") for item in options[:40] if item]
            if labels:
                joined = ",".join(label.replace(",", " ") for label in labels)
                dv = DataValidation(type="list", formula1=f'"{joined}"', allow_blank=False)
                dv.error = "请从下拉选官方选项，不要手打 Other"
                dv.errorTitle = "选项无效"
                sheet.add_data_validation(dv)
                dv.add(f"{get_column_letter(index)}3:{get_column_letter(index)}1048576")
    extras = extra_columns or []
    sheet.row_dimensions[1].height = 22
    sheet.cell(1, 1).comment = Comment(
        "一行 = 一个商品。一张表可以写很多行，一次批量上品。\n第 2 行是示例，导入时自动跳过，也可以直接覆盖。",
        "Auto Shoper",
    )

    help_sheet = book.create_sheet("说明")
    help_sheet["A1"] = (profile or {}).get("title") or "这不是官方表"
    help_sheet["A1"].font = Font(bold=True, size=14)
    help_sheet["A2"] = (profile or {}).get("guide") or spec["summary"]
    help_sheet["A3"] = (
        "填写页列来自：核心字段 + 所选叶子类目的官方 schema 必填属性。"
        "交易物流走店铺默认。AI 会填标题和详描，成稿后要人核对。"
    )
    help_sheet["A4"] = "一行 = 一个商品。图片选填：有图写链接或文件名，没图留空。导入时再选原图上架、补转化位或重画。第 2 行灰色是示例，导入时自动跳过。"
    help_sheet["A4"].font = Font(bold=True)

    row = 5
    help_sheet.cell(row, 1, "你只填（填写页）")
    help_sheet.cell(row, 1).font = Font(bold=True)
    row += 1
    for field_id, label, hint in headers:
        help_sheet.cell(row, 1, label)
        help_sheet.cell(row, 2, hint)
        row += 1
    row += 1
    help_sheet.cell(row, 1, "店里套（店铺默认，不进填写页）")
    help_sheet.cell(row, 1).font = Font(bold=True)
    row += 1
    for item in SHOP_FILLS:
        help_sheet.cell(row, 1, item["label"])
        help_sheet.cell(row, 2, item.get("hint") or "店铺默认，AI 不准改")
        row += 1
    row += 1
    help_sheet.cell(row, 1, "AI 填（标题 / 详描，不进填写页）")
    help_sheet.cell(row, 1).font = Font(bold=True)
    row += 1
    leaf_mode = bool((profile or {}).get("family_id") == "leaf")
    for item in fill_policy(extras, profile)["ai_fills"]:
        help_sheet.cell(row, 1, item.get("label") or "")
        help_sheet.cell(row, 2, item.get("hint") or "AI 按图和官方选项填")
        row += 1
    if extras and not leaf_mode:
        row += 1
        help_sheet.cell(row, 1, "这个类目 AI 会补的官方属性")
        help_sheet.cell(row, 1).font = Font(bold=True)
        help_sheet.cell(row, 2, "来自 schema.get。按官方选项选，不选 Other。产地走店铺默认。")
        row += 1
        for extra in extras:
            help_sheet.cell(row, 1, extra.get("header") or extra.get("label") or "")
            help_sheet.cell(row, 2, " / ".join(opt.get("label") or "" for opt in extra.get("options") or [])[:120])
            row += 1
    row += 1
    help_sheet.cell(row, 1, "红线：这些不准交给 AI")
    help_sheet.cell(row, 1).font = Font(bold=True)
    row += 1
    for item in REDLINE:
        help_sheet.cell(row, 1, item["label"])
        help_sheet.cell(row, 2, item["reason"])
        row += 1
    if listing_template:
        row += 2
        help_sheet.cell(row, 1, "这批货的叶子类目")
        help_sheet.cell(row, 1).font = Font(bold=True)
        help_sheet.cell(row, 2, f"{listing_template.get('name')} · 类目 {listing_template.get('category_id')}")
        help_sheet.cell(row + 1, 1, "类目是红线，整表共用，不出现在填写页。")
        row += 2
    if official_required:
        row += 1
        help_sheet.cell(row, 1, "官方红星对照（谁来填）")
        help_sheet.cell(row, 1).font = Font(bold=True)
        help_sheet.cell(row, 2, "官方 Excel 要你全填。我们只标责任，不把列抄进填写页。")
        row += 1
        for item in official_required:
            help_sheet.cell(row, 1, item.get("name") or item.get("id"))
            help_sheet.cell(row, 2, item.get("who") or who_fills(item.get("id") or ""))
            row += 1
    row += 2
    help_sheet.cell(row, 1, "表头别名（智能探测会认）")
    help_sheet.cell(row, 1).font = Font(bold=True)
    row += 1
    for field_id, label, _hint in headers:
        aliases = ALIASES.get(field_id) or SPEC_ALIASES.get(field_id) or ()
        help_sheet.cell(row, 1, label)
        help_sheet.cell(row, 2, " / ".join(aliases[:8]))
        row += 1
    help_sheet.column_dimensions["A"].width = 28
    help_sheet.column_dimensions["B"].width = 80

    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()
