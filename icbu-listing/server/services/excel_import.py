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
from typing import Any, Iterable
from urllib.parse import urlparse

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

FIELDS: dict[str, str] = {
    "sku": "货号",
    "name": "品名（中文）",
    "title": "英文标题",
    "keywords": "关键词",
    "price": "单价 USD",
    "moq": "起订量",
    "images": "图片（URL 或文件名，分号分隔）",
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
    "category_id": ("类目id", "类目", "category", "category_id", "cateid", "叶子类目", "分类id"),
    "origin": ("产地", "origin", "place of origin", "原产地"),
}

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
    note: str = ""
    category_id: str = ""
    origin: str = ""
    line: int = 0
    raw: dict[str, str] = field(default_factory=dict)

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


def styles_view() -> list[dict[str, Any]]:
    return [dict(item) for item in STYLES.values()]


def _norm(text: str) -> str:
    return re.sub(r"[\s_\-()/（）]+", "", (text or "").strip().lower())


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


def mapping_from_headers(headers: list[str], style: str = "detect") -> dict[str, str]:
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for header in headers:
        field_id = guess_field(header, style)
        if field_id and field_id not in used:
            mapping[header] = field_id
            used.add(field_id)
    return mapping


def parse_rows(rows: list[list[str]], mapping: dict[str, str], header_index: int) -> list[ExcelRow]:
    if header_index >= len(rows):
        return []
    headers = rows[header_index]
    parsed: list[ExcelRow] = []
    for offset, raw in enumerate(rows[header_index + 1 :], start=header_index + 2):
        cells = {headers[index]: raw[index] if index < len(raw) else "" for index in range(len(headers))}
        values = {field_id: "" for field_id in FIELDS}
        for header, field_id in mapping.items():
            if field_id in values:
                values[field_id] = cells.get(header, "")
        if not any(values.values()):
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
                note=values["note"],
                category_id=values["category_id"],
                origin=values["origin"],
                line=offset,
                raw=cells,
            )
        )
    return parsed


def preview(content: bytes, style: str = "detect") -> dict[str, Any]:
    rows = read_sheet(content)
    if not rows:
        return {"error": "表格是空的", "headers": [], "mapping": {}, "rows_preview": [], "row_count": 0}
    header_index = find_header_row(rows, style)
    headers = [item or f"列{index + 1}" for index, item in enumerate(rows[header_index])]
    guessed_style = style if style != "detect" else guess_style(headers)
    mapping = mapping_from_headers(headers, guessed_style if style == "detect" else style)
    parsed = parse_rows(rows, mapping, header_index)
    return {
        "style": style,
        "style_guess": guessed_style,
        "header_row": header_index + 1,
        "headers": headers,
        "mapping": mapping,
        "fields": [{"id": key, "label": label} for key, label in FIELDS.items()],
        "rows_preview": [item.raw for item in parsed[:8]],
        "row_count": len(parsed),
        "mapped_count": len(mapping),
        "warnings": _preview_warnings(parsed, mapping),
    }


def _preview_warnings(rows: list[ExcelRow], mapping: dict[str, str]) -> list[str]:
    warnings: list[str] = []
    if "sku" not in mapping.values():
        warnings.append("没有对上货号列。没有货号时会用第 1 张图的文件名。")
    if "price" not in mapping.values():
        warnings.append("没有对上价格列。价格是生意决策，AI 不会代填。")
    if "images" not in mapping.values():
        warnings.append("没有对上图片列。可以在导入时把图一起拖进来，按货号匹配。")
    empty_sku = sum(1 for item in rows if not item.sku)
    if empty_sku:
        warnings.append(f"{empty_sku} 行没有货号。")
    return warnings


def apply_preview(content: bytes, mapping: dict[str, str], style: str = "detect") -> list[ExcelRow]:
    rows = read_sheet(content)
    header_index = find_header_row(rows, style)
    return parse_rows(rows, mapping, header_index)


def split_images(refs: list[str]) -> tuple[list[str], list[str]]:
    urls, names = [], []
    for item in refs:
        parsed = urlparse(item)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            urls.append(item)
        else:
            names.append(item.rsplit("/", 1)[-1])
    return urls, names


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


def build_template(style: str, listing_template: dict[str, Any] | None = None) -> bytes:
    spec = STYLES.get(style) or STYLES["lingxing"]
    book = Workbook()
    sheet = book.active
    sheet.title = "填写"
    headers = spec["columns"]
    fill = PatternFill("solid", fgColor="1D4ED8")
    font = Font(color="FFFFFF", bold=True)
    example = {
        "sku": "SKU-1001",
        "name": "油漆刷套装",
        "title": "Paint Brush Set for Wall Painting",
        "keywords": "paint brush, wall brush, decorating",
        "price": "1.80",
        "moq": "500",
        "images": "SKU-1001_1.jpg;SKU-1001_2.jpg",
        "note": "加厚款，可定制 logo",
        "category_id": (listing_template or {}).get("category_id") or "21111112",
        "origin": "China",
    }
    for index, field_id in enumerate(headers, start=1):
        cell = sheet.cell(1, index, FIELDS[field_id])
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(wrap_text=True)
        cell.comment = Comment(f"系统字段：{field_id}", "Auto Shoper")
        sheet.cell(2, index, example.get(field_id, ""))
        sheet.column_dimensions[get_column_letter(index)].width = 28
    sheet.row_dimensions[1].height = 22

    help_sheet = book.create_sheet("说明")
    help_sheet["A1"] = spec["label"]
    help_sheet["A1"].font = Font(bold=True, size=14)
    help_sheet["A2"] = spec["summary"]
    help_sheet["A4"] = "表头可用这些别名（智能探测会认）："
    row = 5
    for field_id in headers:
        help_sheet.cell(row, 1, FIELDS[field_id])
        help_sheet.cell(row, 2, " / ".join(ALIASES[field_id][:8]))
        row += 1
    row += 1
    help_sheet.cell(row, 1, "图片")
    help_sheet.cell(row, 2, "填 http(s) 链接，或文件名。导入时把图一起拖进来，按货号前缀匹配，例如 SKU-1001_1.jpg。")
    if listing_template:
        row += 2
        help_sheet.cell(row, 1, "绑定的刊登模板")
        help_sheet.cell(row, 2, f"{listing_template.get('name')} · 类目 {listing_template.get('category_id')}")
        help_sheet.cell(row + 1, 1, "类目和物流不用填在表里，导入时套模板。")
    help_sheet.column_dimensions["A"].width = 24
    help_sheet.column_dimensions["B"].width = 80

    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()
