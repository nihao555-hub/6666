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
    "brand": ("品牌", "brand", "商标", "品牌名"),
    "category_id": ("类目id", "类目", "category", "category_id", "cateid", "叶子类目", "分类id"),
    "origin": ("产地", "origin", "place of origin", "原产地"),
}

# User fills a short sheet. Official 40-column / per-category attribute
# sheets are not copied onto 填写 — those go to AI, except the red line.
USER_FILLS: list[dict[str, Any]] = [
    {"id": "sku", "label": "货号", "required": True, "hint": "你自己的编码"},
    {"id": "price", "label": "单价 USD", "required": True, "hint": "红线，AI 不准定价"},
    {"id": "moq", "label": "起订量", "required": True, "hint": "红线，AI 不准编"},
    {"id": "images", "label": "图片", "required": False, "hint": "选填。有图写链接或文件名；没图留空。导入时再选原图上架、补转化位或重画"},
    {"id": "brand", "label": "品牌", "required": False, "hint": "没有就留空，等于无品牌"},
    {"id": "name", "label": "品名（中文）", "required": False, "hint": "给自己看，也可当提示"},
    {"id": "note", "label": "备注", "required": False, "hint": "色数、是否水溶、硬度若和别的货不一样，写这里。AI 当提示，不编 24 色 / HB"},
]

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
    line: int = 0
    raw: dict[str, str] = field(default_factory=dict)
    attributes: dict[str, dict[str, Any]] = field(default_factory=dict)
    is_sample: bool = False

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


def sheet_preview(style: str = "simple") -> dict[str, Any]:
    """What the seller sees before they download: short headers + one example row.

    This is not the official 40-column form. Category attributes come from
    Alibaba schema.get and stay off the fill sheet.
    """
    spec = STYLES.get(style) or STYLES["simple"]
    columns = [
        {
            "id": field_id,
            "label": FIELDS[field_id],
            "required": field_id in {"sku", "price", "moq"},
            "example": EXAMPLE_ROW.get(field_id, ""),
        }
        for field_id in spec["columns"]
    ]
    return {
        "style": spec["id"],
        "from_official_form": False,
        "note": "不是阿里后台那张 40 列表。货号、单价、起订量必填；图片选填。导入时再选原图上架、补转化位或重画套图。标题和类目属性按这家店的官方发布规则由 AI 补。",
        "columns": columns,
        "example_skipped": True,
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


def fill_policy(ai_attrs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    extras = ai_attrs or []
    ai_fills = [item for item in AI_FILLS_BASE if item["id"] != "catAttrs" or not extras]
    for extra in extras:
        raw = extra.get("header") or extra.get("label") or extra.get("name") or ""
        ai_fills.append(
            {
                "id": extra.get("id") or extra.get("field_id") or extra.get("header"),
                "label": _attr_label(str(raw)),
                "hint": "按官方选项选，不选 Other。选错但合法的只能人审拦住",
            }
        )
    return {
        "user_fills": [dict(item) for item in USER_FILLS],
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
                    "group": group.id,
                    "field_id": child.id,
                    "options": options,
                }
            )
    return columns


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
        for header, field_id in mapping.items():
            cell = cells.get(header, "")
            if field_id in values:
                values[field_id] = cell
            elif field_id.startswith("attr.") and cell:
                spec = extra_by_id.get(field_id)
                if spec:
                    attributes.setdefault(spec["group"], {})[spec["field_id"]] = _match_option(
                        cell, spec.get("options") or []
                    )
        if not any(values.values()) and not attributes:
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
                line=offset,
                raw=cells,
                attributes=attributes,
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
) -> bytes:
    spec = STYLES.get(style) or STYLES["simple"]
    book = Workbook()
    sheet = book.active
    sheet.title = "填写"
    headers = list(spec["columns"])
    fill = PatternFill("solid", fgColor="171717" if spec.get("primary") else "1D4ED8")
    font = Font(color="FFFFFF", bold=True)
    example = {
        **EXAMPLE_ROW,
        "category_id": (listing_template or {}).get("category_id") or "",
    }
    header_hints = {
        "sku": "你自己的货号。一行一个商品，往下接着写就行，一张表可以写很多个。",
        "price": "红线。生意决策，AI 不准定价。",
        "moq": "红线。AI 不准编起订量。",
        "images": "选填。有图写文件名或 URL，分号分隔。没图留空。导入时再选原图上架、留下补转化位、或当参考重画套图。",
        "brand": "红线。有品牌就填；空着=无品牌。AI 不准编品牌名。",
        "name": "选填。给自己看，也可当中文提示。",
        "note": "选填。色数、是否水溶、硬度若和别的货不一样，写这里。AI 当提示，不编数字。",
        "title": "有现成英文标题才填。短表不用填，交给 AI。",
        "keywords": "有现成关键词才填。短表不用填，交给 AI。",
        "category_id": "红线。短表在下载时整表选定，不要每行让 AI 猜。",
        "origin": "红线。走店铺默认，不要填在短表里。",
    }
    for index, field_id in enumerate(headers, start=1):
        cell = sheet.cell(1, index, FIELDS[field_id])
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(wrap_text=True)
        cell.comment = Comment(header_hints.get(field_id) or f"系统字段：{field_id}", "Auto Shoper")
        sample = sheet.cell(2, index, example.get(field_id, ""))
        sample.font = Font(color="9AA0A6", italic=True)
        sheet.column_dimensions[get_column_letter(index)].width = 28
    # Official required attributes stay off the fill sheet. Dumping Type /
    # Color / Hair Material here would recreate the official form.
    extras = extra_columns or []
    sheet.row_dimensions[1].height = 22
    sheet.cell(1, 1).comment = Comment(
        "一行 = 一个商品。一张表可以写很多行，一次批量上品。\n第 2 行是示例，导入时自动跳过，也可以直接覆盖。",
        "Auto Shoper",
    )

    help_sheet = book.create_sheet("说明")
    help_sheet["A1"] = "这不是官方表"
    help_sheet["A1"].font = Font(bold=True, size=14)
    help_sheet["A2"] = spec["summary"]
    help_sheet["A3"] = "填写页只给人填。官方 40 列和类目属性不抄过来。交易物流走店铺默认，不是 AI 编的。红线字段不准给 AI。AI 会选错，成稿后要人核对。"
    help_sheet["A4"] = "一行 = 一个商品。图片选填：有图写链接或文件名，没图留空。导入时再选原图上架、补转化位或重画。第 2 行灰色是示例，导入时自动跳过。"
    help_sheet["A4"].font = Font(bold=True)

    row = 5
    help_sheet.cell(row, 1, "你只填（填写页）")
    help_sheet.cell(row, 1).font = Font(bold=True)
    row += 1
    hints_by_id = {item["id"]: item.get("hint") or "" for item in USER_FILLS}
    for field_id in headers:
        help_sheet.cell(row, 1, FIELDS[field_id])
        help_sheet.cell(row, 2, hints_by_id.get(field_id) or header_hints.get(field_id) or "")
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
    help_sheet.cell(row, 1, "AI 填（不要写进填写页，人要核对）")
    help_sheet.cell(row, 1).font = Font(bold=True)
    row += 1
    for item in fill_policy(extras)["ai_fills"]:
        help_sheet.cell(row, 1, item.get("label") or "")
        help_sheet.cell(row, 2, item.get("hint") or "AI 按图和官方选项填")
        row += 1
    if extras:
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
    for field_id in headers:
        help_sheet.cell(row, 1, FIELDS[field_id])
        help_sheet.cell(row, 2, " / ".join(ALIASES[field_id][:8]))
        row += 1
    help_sheet.column_dimensions["A"].width = 28
    help_sheet.column_dimensions["B"].width = 80

    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()
