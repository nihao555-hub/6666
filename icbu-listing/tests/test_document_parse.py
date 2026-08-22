"""Document parse grid: roundtrip, CSV ingest, and validation."""

import csv
import io
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from openpyxl import Workbook  # noqa: E402

from server.services import document_parse  # noqa: E402
from server.services.excel_import import ExcelRow, sheet_profile  # noqa: E402


class DocumentParseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = sheet_profile("Paint Brushes", category_id="123456")
        self.columns = document_parse.grid_columns(self.profile, [])

    def test_grid_columns_match_short_sheet(self) -> None:
        labels = [col["label"] for col in self.columns]
        self.assertEqual(labels[:4], ["货号", "单价 USD", "起订量", "图片"])

    def test_row_roundtrip_preserves_core_fields(self) -> None:
        row = ExcelRow(
            sku="BR-01",
            price="1.80",
            moq="500",
            images=["a.jpg", "b.jpg"],
            brand="OEM",
            name="油漆刷",
            note="猪鬃",
            line=2,
        )
        item = document_parse.row_to_grid_item(row, self.columns)
        self.assertEqual(item["sku"], "BR-01")
        self.assertEqual(item["images"], "a.jpg;b.jpg")
        back = document_parse.grid_item_to_row(item, self.columns, line=2, category_id="123456")
        self.assertEqual(back.sku, "BR-01")
        self.assertEqual(back.price, "1.80")
        self.assertEqual(back.moq, "500")
        self.assertEqual(back.images, ["a.jpg", "b.jpg"])
        self.assertEqual(back.category_id, "123456")

    def test_csv_spreadsheet_parses_without_llm(self) -> None:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["货号", "单价 USD", "起订量", "图片", "品牌", "品名（中文）", "备注"])
        writer.writerow(["示例", "9.99", "100", "", "", "示例品", ""])
        writer.writerow(["SKU-9", "2.50", "200", "sku9.jpg", "", "测试品", ""])
        content = buffer.getvalue().encode("utf-8-sig")
        result = document_parse.parse_documents(
            [("products.csv", content)],
            profile=self.profile,
            extra_columns=[],
            category_id="123456",
            ai=None,
        )
        self.assertIn("表格", result["source"])
        self.assertEqual(result["row_count"], 1)
        self.assertEqual(result["rows"][0]["sku"], "SKU-9")
        self.assertEqual(result["rows"][0]["price"], "2.50")

    def test_xlsx_spreadsheet_parses_without_llm(self) -> None:
        wb = Workbook()
        ws = wb.active
        ws.append(["货号", "单价 USD", "起订量", "图片", "品牌", "品名（中文）", "备注"])
        ws.append(["示例", "9.99", "100", "", "", "示例品", ""])
        ws.append(["XL-1", "3.00", "100", "", "", "Excel 品", ""])
        payload = io.BytesIO()
        wb.save(payload)
        result = document_parse.parse_documents(
            [("batch.xlsx", payload.getvalue())],
            profile=self.profile,
            extra_columns=[],
            category_id="123456",
            ai=None,
        )
        self.assertEqual(result["row_count"], 1)
        self.assertEqual(result["rows"][0]["sku"], "XL-1")

    def test_co_uploaded_images_match_by_sku_prefix(self) -> None:
        wb = Workbook()
        ws = wb.active
        ws.append(["货号", "单价 USD", "起订量", "图片", "品牌", "品名（中文）", "备注"])
        ws.append(["示例", "9.99", "100", "", "", "示例品", ""])
        ws.append(["SKU-9", "2.50", "200", "", "", "测试品", ""])
        payload = io.BytesIO()
        wb.save(payload)
        fake_jpg = b"\xff\xd8\xff\xe0" + b"0" * 32
        result = document_parse.parse_documents(
            [
                ("batch.xlsx", payload.getvalue()),
                ("SKU-9.jpg", fake_jpg),
                ("SKU-9_2.jpg", fake_jpg),
            ],
            profile=self.profile,
            extra_columns=[],
            category_id="123456",
            ai=None,
        )
        self.assertEqual(result["rows"][0]["sku"], "SKU-9")
        self.assertIn("sku-9.jpg", result["rows"][0]["images"].lower())

    def test_check_grid_flags_missing_price(self) -> None:
        items = [{"line": 2, "sku": "A-1", "price": "", "moq": "100", "images": "", "brand": "", "name": "", "note": ""}]
        check = document_parse.check_grid(items, self.columns, category_id="123456")
        self.assertEqual(check["row_count"], 1)
        self.assertLess(check["ready_count"], check["row_count"])
        self.assertTrue(any(issue["level"] == "red" for issue in check["row_issues"]))

    def test_empty_upload_raises(self) -> None:
        with self.assertRaises(ValueError):
            document_parse.parse_documents([], profile=self.profile, extra_columns=[])


if __name__ == "__main__":
    unittest.main()
