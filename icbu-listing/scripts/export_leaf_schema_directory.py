#!/usr/bin/env python3
"""Export every leaf category's schema.get fields (required + optional).

Builds a browsable workbook from cached or live schema XML:
  - 类目索引   one row per leaf
  - 字段明细   one row per fillable field
  - 必填一览   category_id + required field list
  - 选填一览   category_id + optional field list

Usage (from icbu-listing/):
  PYTHONPATH=backend:server python3 scripts/export_leaf_schema_directory.py
  PYTHONPATH=backend:server python3 scripts/export_leaf_schema_directory.py --fetch
  PYTHONPATH=backend:server python3 scripts/export_leaf_schema_directory.py --limit 50
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "server"))

from dotenv import load_dotenv  # noqa: E402
from openpyxl import Workbook  # noqa: E402
from openpyxl.styles import Alignment, Font, PatternFill  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

load_dotenv(ROOT / ".env")

from schema import SchemaField, parse_schema  # noqa: E402

from server.config import settings  # noqa: E402
from server.models import Shop  # noqa: E402
from server.services import catalog  # noqa: E402
from server.services.shop_client import shop_api, shop_defaults  # noqa: E402

SKIP_TYPES = {"label"}


def collect_field_rows(spec: SchemaField, *, group_id: str = "", path_parts: list[str] | None = None) -> list[dict[str, Any]]:
    parts = list(path_parts or [])
    current_path = ".".join([*parts, spec.id]) if parts else spec.id
    group = group_id or spec.id
    rows: list[dict[str, Any]] = []

    if spec.type in SKIP_TYPES:
        return rows

    if spec.children:
        for child in spec.children:
            rows.extend(collect_field_rows(child, group_id=group, path_parts=[*parts, spec.id]))
        return rows

    options = [opt.display_name or opt.value for opt in (spec.options or []) if (opt.display_name or opt.value)]
    preview = " | ".join(options[:12])
    if len(options) > 12:
        preview = f"{preview} | …(+{len(options) - 12})"

    rows.append(
        {
            "group_id": group,
            "field_id": spec.id,
            "field_path": current_path,
            "field_name": spec.name or spec.id,
            "required": spec.required,
            "field_type": spec.type,
            "value_type": spec.value_type,
            "max_length": spec.max_length or "",
            "option_count": len(options),
            "options_preview": preview,
            "supports_custom": spec.supports_custom_value,
        }
    )
    return rows


def load_leaves(session: Session, limit: int = 0) -> list[dict[str, str]]:
    sql = (
        "SELECT category_id, COALESCE(NULLIF(cn_name, ''), name) AS label, name, cn_name "
        "FROM category_nodes WHERE is_leaf = 1 ORDER BY category_id"
    )
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = session.execute(text(sql)).fetchall()
    return [
        {
            "category_id": str(row[0]),
            "label": str(row[1] or row[0]),
            "name": str(row[2] or ""),
            "cn_name": str(row[3] or ""),
        }
        for row in rows
    ]


def category_path(session: Session, api, category_id: str) -> str:
    try:
        crumbs = [catalog.label(item) for item in catalog.path_of(session, api, category_id, fetch=False)]
        return " / ".join(crumbs) if crumbs else category_id
    except Exception:
        return category_id


def schema_for_leaf(
    session: Session,
    api,
    category_id: str,
    language: str,
    *,
    fetch: bool,
) -> tuple[list[SchemaField] | None, str]:
    try:
        xml = catalog.get_schema_xml(session, api, category_id, language, fetch=fetch)
        return parse_schema(xml), ""
    except Exception as exc:
        return None, str(exc)


def write_workbook(output: Path, index_rows: list[dict], detail_rows: list[dict]) -> None:
    book = Workbook()
    header_fill = PatternFill("solid", fgColor="1D4ED8")
    header_font = Font(color="FFFFFF", bold=True)

    def style_header(sheet, headers: list[str]) -> None:
        for col, title in enumerate(headers, start=1):
            cell = sheet.cell(1, col, title)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(wrap_text=True)
        sheet.freeze_panes = "A2"

    idx = book.active
    idx.title = "类目索引"
    index_headers = [
        "category_id",
        "叶子名称",
        "类目路径",
        "schema状态",
        "必填字段数",
        "选填字段数",
        "总字段数",
        "必填字段",
        "选填字段",
        "错误信息",
    ]
    style_header(idx, index_headers)
    for row_no, row in enumerate(index_rows, start=2):
        idx.cell(row_no, 1, row["category_id"])
        idx.cell(row_no, 2, row["label"])
        idx.cell(row_no, 3, row["path"])
        idx.cell(row_no, 4, row["status"])
        idx.cell(row_no, 5, row["required_count"])
        idx.cell(row_no, 6, row["optional_count"])
        idx.cell(row_no, 7, row["total_count"])
        idx.cell(row_no, 8, row["required_names"])
        idx.cell(row_no, 9, row["optional_names"])
        idx.cell(row_no, 10, row.get("error") or "")

    detail = book.create_sheet("字段明细")
    detail_headers = [
        "category_id",
        "叶子名称",
        "类目路径",
        "分组",
        "field_id",
        "field_path",
        "字段名",
        "必填",
        "类型",
        "值类型",
        "最大长度",
        "选项数",
        "选项预览",
        "可填Other",
    ]
    style_header(detail, detail_headers)
    for row_no, row in enumerate(detail_rows, start=2):
        detail.cell(row_no, 1, row["category_id"])
        detail.cell(row_no, 2, row["label"])
        detail.cell(row_no, 3, row["path"])
        detail.cell(row_no, 4, row["group_id"])
        detail.cell(row_no, 5, row["field_id"])
        detail.cell(row_no, 6, row["field_path"])
        detail.cell(row_no, 7, row["field_name"])
        detail.cell(row_no, 8, "是" if row["required"] else "否")
        detail.cell(row_no, 9, row["field_type"])
        detail.cell(row_no, 10, row["value_type"])
        detail.cell(row_no, 11, row["max_length"])
        detail.cell(row_no, 12, row["option_count"])
        detail.cell(row_no, 13, row["options_preview"])
        detail.cell(row_no, 14, "是" if row["supports_custom"] else "否")

    req = book.create_sheet("必填一览")
    style_header(req, ["category_id", "叶子名称", "类目路径", "必填字段（名）", "必填 field_path"])
    opt = book.create_sheet("选填一览")
    style_header(opt, ["category_id", "叶子名称", "类目路径", "选填字段（名）", "选填 field_path"])

    req_row = 2
    opt_row = 2
    for row in index_rows:
        if row["status"] != "ok":
            continue
        req.cell(req_row, 1, row["category_id"])
        req.cell(req_row, 2, row["label"])
        req.cell(req_row, 3, row["path"])
        req.cell(req_row, 4, row["required_names"])
        req.cell(req_row, 5, row["required_paths"])
        req_row += 1
        opt.cell(opt_row, 1, row["category_id"])
        opt.cell(opt_row, 2, row["label"])
        opt.cell(opt_row, 3, row["path"])
        opt.cell(opt_row, 4, row["optional_names"])
        opt.cell(opt_row, 5, row["optional_paths"])
        opt_row += 1

    for sheet in (idx, detail, req, opt):
        for col in range(1, sheet.max_column + 1):
            letter = get_column_letter(col)
            width = 18 if col <= 3 else 28
            if sheet.title == "字段明细" and col in {7, 13}:
                width = 36
            sheet.column_dimensions[letter].width = width

    output.parent.mkdir(parents=True, exist_ok=True)
    book.save(output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export leaf schema directory (required + optional fields)")
    parser.add_argument("--fetch", action="store_true", help="Fetch missing schemas from Alibaba API")
    parser.add_argument("--limit", type=int, default=0, help="Only process first N leaves (0 = all)")
    parser.add_argument("--language", default="en_US")
    parser.add_argument("--output", default=str(ROOT / "samples" / "leaf_schema_directory.xlsx"))
    parser.add_argument("--json", default=str(ROOT / "samples" / "leaf_schema_directory.json"))
    parser.add_argument("--sleep", type=float, default=0.15, help="Pause between live schema.get calls")
    args = parser.parse_args()

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    shop = session.query(Shop).first()
    if shop is None:
        raise SystemExit("数据库里没有店铺，无法调 schema.get")
    api = shop_api(shop)
    language = str(shop_defaults(shop).get("language") or args.language)

    leaves = load_leaves(session, args.limit)
    index_rows: list[dict[str, Any]] = []
    detail_rows: list[dict[str, Any]] = []

    started = time.time()
    for index, leaf in enumerate(leaves, start=1):
        cid = leaf["category_id"]
        path = category_path(session, api, cid)
        fields, error = schema_for_leaf(session, api, cid, language, fetch=args.fetch)
        if fields is None and args.fetch and "还没缓存" in error:
            time.sleep(args.sleep)
            fields, error = schema_for_leaf(session, api, cid, language, fetch=True)

        if fields is None:
            index_rows.append(
                {
                    "category_id": cid,
                    "label": leaf["label"],
                    "path": path,
                    "status": "missing",
                    "required_count": 0,
                    "optional_count": 0,
                    "total_count": 0,
                    "required_names": "",
                    "optional_names": "",
                    "required_paths": "",
                    "optional_paths": "",
                    "error": error,
                }
            )
        else:
            rows = []
            for top in fields:
                rows.extend(collect_field_rows(top))
            required = [row for row in rows if row["required"]]
            optional = [row for row in rows if not row["required"]]
            index_rows.append(
                {
                    "category_id": cid,
                    "label": leaf["label"],
                    "path": path,
                    "status": "ok",
                    "required_count": len(required),
                    "optional_count": len(optional),
                    "total_count": len(rows),
                    "required_names": "；".join(row["field_name"] for row in required),
                    "optional_names": "；".join(row["field_name"] for row in optional),
                    "required_paths": "；".join(row["field_path"] for row in required),
                    "optional_paths": "；".join(row["field_path"] for row in optional),
                    "error": "",
                }
            )
            for row in rows:
                detail_rows.append(
                    {
                        "category_id": cid,
                        "label": leaf["label"],
                        "path": path,
                        **row,
                    }
                )

        if args.fetch and index % 20 == 0:
            session.commit()
        if index % 100 == 0 or index == len(leaves):
            ok = sum(1 for row in index_rows if row["status"] == "ok")
            print(f"… {index}/{len(leaves)} leaves ({ok} ok, {len(detail_rows)} field rows)", flush=True)

    session.commit()
    session.close()

    output = Path(args.output)
    write_workbook(output, index_rows, detail_rows)

    summary = {
        "leaf_count": len(leaves),
        "ok": sum(1 for row in index_rows if row["status"] == "ok"),
        "missing": sum(1 for row in index_rows if row["status"] != "ok"),
        "field_rows": len(detail_rows),
        "elapsed_seconds": round(time.time() - started, 1),
        "output_xlsx": str(output),
    }
    Path(args.json).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
