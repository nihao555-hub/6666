"""Turn seller documents into an editable product grid for batch listing.

Structured spreadsheets use the existing excel_import path. Photos, PDF scans,
quotation sheets, and free-form text go through one LLM extraction pass that
maps facts onto the same short-sheet columns the user would see after picking
a leaf category.
"""

from __future__ import annotations

import csv
import io
import json
import re
from typing import Any, Mapping, Sequence

from ai import AiClient, AiUnavailable, ImageInput  # noqa: E402

from . import excel_import
from .excel_import import ExcelRow, fill_headers, preview, read_sheet
from .grid_images import attach_row_images

SPREADSHEET_SUFFIXES = {".xlsx", ".xls", ".xlsm", ".csv"}
TEXT_SUFFIXES = {".txt", ".md", ".json"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}

DOC_EXTRACT_PROMPT = """You extract wholesale product rows from seller documents for Alibaba.com (ICBU).

Each output row is one SKU / one listing. Use ONLY facts visible in the documents.
Do not invent certifications, brands, prices, MOQ, or specifications.

Target columns — use these exact field ids as JSON keys in each row object:
{column_spec}

Rules:
- sku: seller product code when present; otherwise ROW-001, ROW-002, …
- price: unit price in USD (number string). If only tiered prices exist, put the first tier here
  and write all tiers in note like "500@1.80;2000@1.50"
- moq: minimum order quantity (integer string)
- images: filenames or URLs mentioned, semicolon-separated
- brand: only if explicitly stated; otherwise empty string
- name: Chinese product name when available
- note: remaining facts (material, size, color, packaging, tiered prices)
- For attr.* fields with options: pick the option label that exactly matches document facts;
  if ambiguous leave empty string

Return JSON only:
{{"rows": [{{...}}, ...], "warnings": ["optional notes about ambiguity"]}}
"""


def grid_columns(
    profile: Mapping[str, Any] | None,
    extra_columns: Sequence[Mapping[str, Any]] | None,
    *,
    plan_columns: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if plan_columns:
        return [dict(col) for col in plan_columns]
    extra_by_id = {item["id"]: dict(item) for item in (extra_columns or [])}
    columns: list[dict[str, Any]] = []
    for field_id, label, hint in fill_headers("simple", dict(profile or {})):
        required = field_id in {"sku", "price", "moq"}
        col: dict[str, Any] = {"id": field_id, "label": label, "required": required, "hint": hint}
        if field_id.startswith("attr."):
            spec = extra_by_id.get(field_id) or {}
            if spec.get("required"):
                col["required"] = True
            options = spec.get("options") or []
            if options:
                col["options"] = options
                col["kind"] = "select"
            else:
                col["kind"] = "text"
        elif field_id == "images":
            col["kind"] = "text"
        else:
            col["kind"] = "text"
        columns.append(col)
    return columns


def _option_label(value: str, options: Sequence[Mapping[str, Any]]) -> str:
    token = str(value or "").strip()
    if not token:
        return ""
    for item in options:
        if str(item.get("value") or "") == token:
            return str(item.get("label") or token)
        if str(item.get("label") or "").strip().lower() == token.lower():
            return str(item.get("label") or token)
    return token


def _option_value(label: str, options: Sequence[Mapping[str, Any]]) -> str:
    text = str(label or "").strip()
    if not text:
        return ""
    for item in options:
        if str(item.get("label") or "").strip().lower() == text.lower():
            return str(item.get("value") or text)
        if str(text).lower() == str(item.get("value") or "").lower():
            return str(item.get("value") or text)
    return excel_import._match_option(text, list(options)) or text


def row_to_grid_item(row: ExcelRow, columns: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    extra_by_id = {col["id"]: col for col in columns if str(col.get("id", "")).startswith(("attr.", "schema."))}
    item: dict[str, Any] = {"line": row.line}
    core = {
        "sku": row.sku,
        "price": row.price,
        "moq": row.moq,
        "images": ";".join(row.images),
        "brand": row.brand,
        "name": row.name,
        "note": row.note,
    }
    for col in columns:
        field_id = str(col["id"])
        if field_id in core:
            item[field_id] = core[field_id]
        elif field_id.startswith("attr."):
            spec = extra_by_id.get(field_id) or col
            group = spec.get("group") or field_id.split(".")[1]
            child = spec.get("field_id") or field_id.split(".")[-1]
            raw = (row.attributes.get(group) or {}).get(child, "")
            item[field_id] = _option_label(str(raw), spec.get("options") or [])
        elif field_id.startswith("schema."):
            parts = field_id.split(".")
            if len(parts) == 2:
                top_id = parts[1]
                raw = row.schema_top.get(top_id, "")
                item[field_id] = _option_label(str(raw), col.get("options") or [])
            elif len(parts) >= 3:
                group, child = parts[1], parts[2]
                raw = (row.attributes.get(group) or {}).get(child, "")
                item[field_id] = _option_label(str(raw), col.get("options") or [])
        elif field_id.startswith("spec."):
            key = field_id.split(".", 1)[1]
            item[field_id] = row.specs.get(key, "")
        else:
            item[field_id] = core.get(field_id, "")
    return attach_row_images(item)


def grid_item_to_row(
    item: Mapping[str, Any],
    columns: Sequence[Mapping[str, Any]],
    *,
    line: int,
    category_id: str = "",
) -> ExcelRow:
    extra_by_id = {col["id"]: col for col in columns if str(col.get("id", "")).startswith(("attr.", "schema."))}
    images = [part.strip() for part in re.split(r"[;；\n]+", str(item.get("images") or "")) if part.strip()]
    attributes: dict[str, dict[str, Any]] = {}
    schema_top: dict[str, str] = {}
    specs: dict[str, str] = {}
    for col in columns:
        field_id = str(col["id"])
        raw = str(item.get(field_id) or "").strip()
        if not raw:
            continue
        if field_id.startswith("attr."):
            spec = extra_by_id.get(field_id) or col
            group = str(spec.get("group") or field_id.split(".")[1])
            child = str(spec.get("field_id") or field_id.split(".")[-1])
            value = _option_value(raw, spec.get("options") or [])
            attributes.setdefault(group, {})[child] = value
        elif field_id.startswith("schema."):
            parts = field_id.split(".")
            if len(parts) == 2:
                top_id = parts[1]
                schema_top[top_id] = _option_value(raw, col.get("options") or []) or raw
            elif len(parts) >= 3:
                group, child = parts[1], parts[2]
                value = _option_value(raw, col.get("options") or []) or raw
                attributes.setdefault(group, {})[child] = value
        elif field_id.startswith("spec."):
            specs[field_id.split(".", 1)[1]] = raw

    return ExcelRow(
        sku=str(item.get("sku") or "").strip(),
        name=str(item.get("name") or "").strip(),
        price=str(item.get("price") or "").strip(),
        moq=str(item.get("moq") or "").strip(),
        images=images,
        brand=str(item.get("brand") or "").strip(),
        note=str(item.get("note") or "").strip(),
        category_id=category_id,
        specs=specs,
        line=int(item.get("line") or line),
        attributes=attributes,
        schema_top=schema_top,
        raw={
            **{str(col["id"]): str(item.get(col["id"]) or "") for col in columns},
            "image_job_id": str(item.get("image_job_id") or ""),
        },
    )


def grid_to_excel_rows(
    items: Sequence[Mapping[str, Any]],
    columns: Sequence[Mapping[str, Any]],
    *,
    category_id: str = "",
) -> list[ExcelRow]:
    rows: list[ExcelRow] = []
    for index, item in enumerate(items, start=2):
        if not isinstance(item, Mapping):
            continue
        if not any(str(item.get(col["id"]) or "").strip() for col in columns if col["id"] in {"sku", "price", "moq", "name", "note"}):
            continue
        rows.append(grid_item_to_row(item, columns, line=int(item.get("line") or index), category_id=category_id))
    return rows


def check_grid(
    items: Sequence[Mapping[str, Any]],
    columns: Sequence[Mapping[str, Any]],
    *,
    category_id: str = "",
    image_mode: str = "keep_draw",
) -> dict[str, Any]:
    rows = grid_to_excel_rows(items, columns, category_id=category_id)
    mode = excel_import.normalize_image_mode(image_mode)
    issues = excel_import.row_checks(rows, mode)
    blocked = {item["line"] for item in issues if item["level"] == "red"}
    return {
        "row_count": len(rows),
        "ready_count": len(rows) - len(blocked),
        "blocked_count": len(blocked),
        "row_issues": issues,
        "image_stats": excel_import.image_stats(rows),
    }


def _column_spec(columns: Sequence[Mapping[str, Any]]) -> str:
    lines: list[str] = []
    for col in columns:
        bit = f"- {col['id']}: {col.get('label') or col['id']}"
        if col.get("required"):
            bit += " (required)"
        options = col.get("options") or []
        if options:
            labels = [str(item.get("label") or item.get("value") or "") for item in options[:12]]
            bit += f" options: {', '.join(labels)}"
        lines.append(bit)
    return "\n".join(lines)


def _suffix(name: str) -> str:
    lower = (name or "").lower()
    if "." not in lower:
        return ""
    return lower[lower.rfind(".") :]


def _read_csv(content: bytes) -> list[list[str]]:
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    return [list(row) for row in reader if any(str(cell).strip() for cell in row)]


def _parse_spreadsheet(name: str, content: bytes, extra_columns: list[dict[str, Any]] | None) -> list[ExcelRow]:
    if _suffix(name) == ".csv":
        sheet_rows = _read_csv(content)
        if len(sheet_rows) < 1:
            return []
        header_index = excel_import.find_header_row(sheet_rows, "detect")
        headers = sheet_rows[header_index]
        mapping = excel_import.mapping_from_headers(headers, "detect", extra_columns)
        parsed, _ = excel_import.drop_samples(
            excel_import.parse_rows(sheet_rows, mapping, header_index, extra_columns)
        )
        return parsed
    preview_data = preview(content, "detect", extra_columns)
    mapping = preview_data.get("mapping") or {}
    return excel_import.apply_preview(content, mapping, preview_data.get("style_guess") or "detect", extra_columns)


def _llm_extract(
    ai: AiClient,
    files: Sequence[tuple[str, bytes]],
    columns: Sequence[Mapping[str, Any]],
    *,
    category_name: str = "",
) -> tuple[list[dict[str, Any]], list[str]]:
    column_spec = _column_spec(columns)
    prompt = DOC_EXTRACT_PROMPT.format(column_spec=column_spec)
    if category_name:
        prompt += f"\n\nLeaf category context: {category_name}"
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    text_bits: list[str] = []
    for name, raw in files:
        suffix = _suffix(name)
        if suffix in IMAGE_SUFFIXES:
            content.append({"type": "image_url", "image_url": {"url": ImageInput(filename=name, content=raw).as_data_url()}})
        elif suffix in TEXT_SUFFIXES or suffix in {".pdf"}:
            text_bits.append(f"--- {name} ---\n{raw.decode('utf-8', errors='replace')[:12000]}")
        elif suffix in SPREADSHEET_SUFFIXES:
            text_bits.append(f"--- {name} (tabular) ---\n{raw[:8000]!r}")
    if text_bits:
        content.append({"type": "text", "text": "\n\n".join(text_bits)[:24000]})
    payload = ai.chat_json([{"role": "user", "content": content}], temperature=0.1)
    rows = payload.get("rows") or []
    warnings = [str(item) for item in (payload.get("warnings") or []) if str(item).strip()]
    cleaned: list[dict[str, Any]] = []
    if isinstance(rows, list):
        for index, item in enumerate(rows, start=2):
            if isinstance(item, Mapping):
                row = attach_row_images(dict(item))
                row.setdefault("line", index)
                cleaned.append(row)
    return cleaned, warnings


def parse_documents(
    files: Sequence[tuple[str, bytes]],
    *,
    profile: Mapping[str, Any] | None,
    extra_columns: Sequence[Mapping[str, Any]] | None,
    category_id: str = "",
    category_name: str = "",
    image_mode: str = "keep_draw",
    ai: AiClient | None = None,
    plan_columns: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    if not files:
        raise ValueError("请先上传资料文件")

    columns = grid_columns(profile, extra_columns, plan_columns=plan_columns)
    extras = list(plan_columns or extra_columns or [])
    structured: list[ExcelRow] = []
    unstructured: list[tuple[str, bytes]] = []
    sources: list[str] = []

    for name, content in files:
        if not content:
            continue
        suffix = _suffix(name)
        if suffix in SPREADSHEET_SUFFIXES:
            rows = _parse_spreadsheet(name, content, extras)
            if rows:
                structured.extend(rows)
                sources.append(f"表格 {name}")
            else:
                unstructured.append((name, content))
        else:
            unstructured.append((name, content))

    grid_items: list[dict[str, Any]] = [row_to_grid_item(row, columns) for row in structured]
    warnings: list[str] = []

    if unstructured:
        if ai is None:
            if not grid_items:
                raise AiUnavailable("解析报价单/图片资料需要配置 AI。表格请直接上传 xlsx/csv。")
            warnings.append("部分文件需要 AI 解析，但未配置模型，已忽略。")
        else:
            extracted, llm_warnings = _llm_extract(ai, unstructured, columns, category_name=category_name)
            grid_items.extend(extracted)
            sources.append("AI 资料解析")
            warnings.extend(llm_warnings)

    if not grid_items:
        raise ValueError("没能从资料里识别出商品行，请换更完整的报价单或表格")

    grid_items = [attach_row_images(item) for item in grid_items]
    check = check_grid(grid_items, columns, category_id=category_id, image_mode=image_mode)
    return {
        "source": " + ".join(sources) if sources else "mixed",
        "columns": columns,
        "rows": grid_items,
        "row_count": check["row_count"],
        "ready_count": check["ready_count"],
        "blocked_count": check["blocked_count"],
        "row_issues": check["row_issues"],
        "warnings": warnings,
        "image_stats": check["image_stats"],
        "image_mode": excel_import.normalize_image_mode(image_mode),
        "category_id": category_id,
        "category_name": category_name,
    }
