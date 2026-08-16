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
from openpyxl.worksheet.datavalidation import DataValidation

# Official origin. Always a shop default, never a per-row column.
SKIP_ATTR_IDS = {"p-1"}

FIELDS: dict[str, str] = {
    "sku": "货号",
    "name": "品名（中文）",
    "title": "英文标题",
    "keywords": "关键词",
    "price": "单价 USD",
    "moq": "起订量",
    "images": "图片",
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
    "simple": {
        "id": "simple",
        "label": "必填表批量上品",
        "summary": "先选叶子类目，下载该类目的必填表。共同列是货号、价、起订量、图；后面是这类官方必填属性。标题和产地不用填。",
        "columns": ["sku", "name", "price", "moq", "images", "note"],
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
        "summary": "官方：选叶子类目 → 下模板 → 图先入图片银行 → 检测再导入。我们同样按类目出表，但标题/属性/物流由 AI 和店铺默认填，你只填货号、价格、起订量和图。",
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
    note: str = ""
    category_id: str = ""
    origin: str = ""
    line: int = 0
    raw: dict[str, str] = field(default_factory=dict)
    attributes: dict[str, dict[str, Any]] = field(default_factory=dict)

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


def styles_view() -> list[dict[str, Any]]:
    return [dict(item) for item in STYLES.values()]


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
                note=values["note"],
                category_id=values["category_id"],
                origin=values["origin"],
                line=offset,
                raw=cells,
                attributes=attributes,
            )
        )
    return parsed


def preview(
    content: bytes,
    style: str = "detect",
    extra_columns: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    rows = read_sheet(content)
    if not rows:
        return {"error": "表格是空的", "headers": [], "mapping": {}, "rows_preview": [], "row_count": 0}
    header_index = find_header_row(rows, style)
    headers = [item or f"列{index + 1}" for index, item in enumerate(rows[header_index])]
    guessed_style = style if style != "detect" else guess_style(headers)
    mapping = mapping_from_headers(headers, guessed_style if style == "detect" else style, extra_columns)
    parsed = parse_rows(rows, mapping, header_index, extra_columns)
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


def apply_preview(
    content: bytes,
    mapping: dict[str, str],
    style: str = "detect",
    extra_columns: list[dict[str, Any]] | None = None,
) -> list[ExcelRow]:
    rows = read_sheet(content)
    header_index = find_header_row(rows, style)
    return parse_rows(rows, mapping, header_index, extra_columns)


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


def who_fills(field_id: str) -> str:
    if field_id in {"productTitle", "productKeywords", "textDesc", "icbuCatProp", "saleProp", "superText"}:
        return "AI 生成"
    if field_id in {"ladderPrice", "fob", "scPrice", "minOrderQuantity", "scImages"}:
        return "你在「填写」表填（价格、起订量、图）"
    if field_id in {"origin", "priceUnit", "paymentMethod", "port", "shippingTemplateId", "pkgMeasure", "pkgWeight", "logisticsMode", "logisticsProperty", "marketSample", "market"}:
        return "店铺默认 / 刊登模板"
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
        "sku": "SKU-1001",
        "name": "油漆刷套装",
        "title": "Paint Brush Set for Wall Painting",
        "keywords": "paint brush, wall brush, decorating",
        "price": "1.80",
        "moq": "500",
        "images": "SKU-1001_1.jpg;SKU-1001_2.jpg",
        "note": "加厚款，可定制 logo",
        "category_id": (listing_template or {}).get("category_id") or "",
        "origin": "China",
    }
    for index, field_id in enumerate(headers, start=1):
        cell = sheet.cell(1, index, FIELDS[field_id])
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(wrap_text=True)
        hint = "URL 或文件名，分号分隔。官方要求先入图片银行；这里也可以导入时把图一起拖进来。" if field_id == "images" else f"系统字段：{field_id}"
        cell.comment = Comment(hint, "Auto Shoper")
        sheet.cell(2, index, example.get(field_id, ""))
        sheet.column_dimensions[get_column_letter(index)].width = 28
    extras = extra_columns or []
    for offset, extra in enumerate(extras, start=len(headers) + 1):
        cell = sheet.cell(1, offset, extra["header"])
        cell.fill = fill
        cell.font = font
        labels = [item.get("label") or item.get("value") or "" for item in extra.get("options") or []]
        hint = "官方必填属性。可留空让 AI 选；要手填请用官方选项：" + " / ".join(labels[:12])
        cell.comment = Comment(hint[:200], "Auto Shoper")
        if labels:
            sheet.cell(2, offset, labels[0])
        sheet.column_dimensions[get_column_letter(offset)].width = 22
        joined = ",".join(labels[:25])
        if labels and len(joined) < 240:
            dropdown = DataValidation(type="list", formula1=f'"{joined}"', allow_blank=True)
            dropdown.add(f"{get_column_letter(offset)}2:{get_column_letter(offset)}200")
            sheet.add_data_validation(dropdown)
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
        help_sheet.cell(row, 1, "绑定的类目 / 模板")
        help_sheet.cell(row, 2, f"{listing_template.get('name')} · 类目 {listing_template.get('category_id')}")
        help_sheet.cell(row + 1, 1, "类目和物流不用填在表里，导入时套用。")
        row += 2
    if extras:
        row += 1
        help_sheet.cell(row, 1, "这个类目多出来的列")
        help_sheet.cell(row, 2, "来自官方 schema.get 的必填属性。产地走店铺默认，不出现在表里。可留空给 AI。")
        row += 1
        for extra in extras:
            help_sheet.cell(row, 1, extra["header"])
            help_sheet.cell(row, 2, " / ".join(item.get("label") or "" for item in extra.get("options") or [])[:120])
            row += 1
    if official_required:
        row += 1
        help_sheet.cell(row, 1, "官方红星必填对照")
        help_sheet.cell(row, 2, "官方 Excel 要你全填。这里只标谁来填，减少时间。")
        row += 1
        for item in official_required:
            help_sheet.cell(row, 1, item.get("name") or item.get("id"))
            help_sheet.cell(row, 2, item.get("who") or who_fills(item.get("id") or ""))
            row += 1
    help_sheet.column_dimensions["A"].width = 24
    help_sheet.column_dimensions["B"].width = 80

    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()
