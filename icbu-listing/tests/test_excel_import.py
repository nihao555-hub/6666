"""Excel styles, header detection, and official templates."""

import io
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from schema import parse_schema  # noqa: E402
from server.services.excel_import import (  # noqa: E402
    ExcelRow,
    apply_preview,
    build_template,
    category_attr_columns,
    fill_policy,
    find_header_row,
    guess_field,
    guess_style,
    mapping_from_headers,
    match_uploads,
    parse_rows,
    preview,
    split_images,
)


class AliasTests(unittest.TestCase):
    def test_lingxing_and_mabang_headers_map(self) -> None:
        self.assertEqual(guess_field("货号"), "sku")
        self.assertEqual(guess_field("单价USD"), "price")
        self.assertEqual(guess_field("库存SKU", "mabang"), "sku")
        self.assertEqual(guess_field("中文名称", "mabang"), "name")
        self.assertEqual(guess_field("图片地址", "mabang"), "images")

    def test_style_guess_from_headers(self) -> None:
        self.assertEqual(guess_style(["库存SKU", "中文名称", "售价"]), "mabang")
        self.assertEqual(guess_style(["货号", "单价USD", "起订量"]), "lingxing")
        self.assertEqual(guess_style(["货号", "单价 USD", "起订量", "图片", "品牌"]), "simple")
        self.assertEqual(guess_style(["货号", "英文标题", "关键词"]), "dianxiaomi")


class ParseTests(unittest.TestCase):
    def test_skips_title_rows_to_find_the_real_header(self) -> None:
        rows = [
            ["马帮库存导出", "", ""],
            ["导出时间", "2026-08-16", ""],
            ["库存SKU", "售价", "图片地址"],
            ["BRUSH-01", "1.8", "a.jpg;b.jpg"],
        ]
        index = find_header_row(rows, "mabang")
        self.assertEqual(index, 2)
        mapping = mapping_from_headers(rows[index], "mabang")
        parsed = parse_rows(rows, mapping, index)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].sku, "BRUSH-01")
        self.assertEqual(parsed[0].price, "1.8")
        self.assertEqual(parsed[0].images, ["a.jpg", "b.jpg"])

    def test_excel_row_marks_seed_fields_as_excel(self) -> None:
        row = ExcelRow(title="Paint Brush Set", price="1.80", moq="500", origin="Vietnam")
        self.assertEqual(row.seed_values()["productTitle"], "Paint Brush Set")
        self.assertEqual(row.provided_sources()["productTitle"], "excel")
        self.assertEqual(row.provided_sources()["ladderPrice"], "excel")
        self.assertEqual(row.provided_sources()["origin"], "excel")

    def test_image_refs_split_urls_from_filenames(self) -> None:
        urls, names = split_images(["https://img.example.com/a.jpg", "SKU-1_1.jpg", "not a url"])
        self.assertEqual(urls, ["https://img.example.com/a.jpg"])
        self.assertEqual(names, ["SKU-1_1.jpg", "not a url"])

    def test_uploads_match_sku_prefix(self) -> None:
        uploads = {
            "sku-1001_1.jpg": b"one",
            "sku-1001-2.jpg": b"two",
            "other.jpg": b"nope",
        }
        matched = match_uploads("SKU-1001", [], uploads)
        self.assertEqual({name for name, _ in matched}, {"sku-1001_1.jpg", "sku-1001-2.jpg"})


class TemplateTests(unittest.TestCase):
    def test_generated_lingxing_template_round_trips(self) -> None:
        payload = build_template("lingxing")
        result = preview(payload, "lingxing")
        self.assertGreaterEqual(result["row_count"], 1)
        self.assertEqual(result["mapping"]["货号"], "sku")
        self.assertEqual(result["mapping"]["单价 USD"], "price")
        rows = apply_preview(payload, result["mapping"], "lingxing")
        self.assertEqual(rows[0].sku, "SKU-1001")
        self.assertEqual(rows[0].price, "1.80")

    def test_required_attribute_columns_differ_by_category(self) -> None:
        brushes = parse_schema(
            """<?xml version="1.0"?><itemSchema>
              <field id="icbuCatProp" type="complex"><fields>
                <field id="p-1" name="Place of Origin" type="singleCheck"><rules><rule name="requiredRule" value="true"/></rules></field>
                <field id="p-type" name="Type" type="singleCheck"><rules><rule name="requiredRule" value="true"/></rules>
                  <options><option displayName="Oil Brush" value="1"/></options>
                </field>
              </fields></field>
              <field id="saleProp" type="complex"><fields>
                <field id="p-color" name="Color" type="singleCheck"><rules><rule name="requiredRule" value="true"/></rules>
                  <options><option displayName="Black" value="9"/></options>
                </field>
              </fields></field>
            </itemSchema>"""
        )
        pens = parse_schema(
            """<?xml version="1.0"?><itemSchema>
              <field id="icbuCatProp" type="complex"><fields>
                <field id="p-1" name="Place of Origin" type="singleCheck"><rules><rule name="requiredRule" value="true"/></rules></field>
                <field id="p-hair" name="Hair Material" type="singleCheck"><rules><rule name="requiredRule" value="true"/></rules>
                  <options><option displayName="Wolf Hair" value="2"/></options>
                </field>
              </fields></field>
            </itemSchema>"""
        )
        brush_cols = {item["header"] for item in category_attr_columns(brushes)}
        pen_cols = {item["header"] for item in category_attr_columns(pens)}
        self.assertEqual(brush_cols, {"Type", "Color"})
        self.assertEqual(pen_cols, {"Hair Material"})
        self.assertNotIn("Place of Origin", brush_cols)
        payload = build_template(
            "simple",
            {"name": "Paint Brushes", "category_id": "21111112"},
            extra_columns=category_attr_columns(brushes),
        )
        result = preview(payload, "simple")
        self.assertNotIn("Type", result["headers"])
        self.assertNotIn("Color", result["headers"])
        self.assertNotIn("英文标题", result["headers"])
        from openpyxl import load_workbook

        book = load_workbook(io.BytesIO(payload))
        help_text = " ".join(
            str(cell or "")
            for row in book["说明"].iter_rows(values_only=True)
            for cell in row
        )
        self.assertIn("Type", help_text)
        self.assertIn("Color", help_text)
        self.assertIn("红线", help_text)
        policy = fill_policy(category_attr_columns(brushes))
        self.assertIn("Type", {item["label"] for item in policy["ai_fills"]})
        self.assertTrue(any(item["id"] == "price" for item in policy["redline"]))

    def test_uploaded_official_attr_columns_still_parse(self) -> None:
        extras = category_attr_columns(
            parse_schema(
                """<?xml version="1.0"?><itemSchema>
                  <field id="icbuCatProp" type="complex"><fields>
                    <field id="p-type" name="Type" type="singleCheck"><rules><rule name="requiredRule" value="true"/></rules>
                      <options><option displayName="Oil Brush" value="1"/></options>
                    </field>
                  </fields></field>
                </itemSchema>"""
            )
        )
        from openpyxl import Workbook

        book = Workbook()
        sheet = book.active
        sheet.append(["货号", "单价 USD", "起订量", "图片", "Type"])
        sheet.append(["SKU-1001", "1.80", "500", "a.jpg", "Oil Brush"])
        buffer = io.BytesIO()
        book.save(buffer)
        rows = apply_preview(buffer.getvalue(), {"货号": "sku", "单价 USD": "price", "Type": "attr.icbuCatProp.p-type"}, "simple", extras)
        self.assertEqual(rows[0].seed_values()["icbuCatProp"]["p-type"], "1")

    def test_simple_template_is_only_what_the_seller_must_fill(self) -> None:
        payload = build_template("simple")
        result = preview(payload, "simple")
        self.assertEqual(set(result["mapping"].values()), {"sku", "name", "price", "moq", "images", "note", "brand"})
        self.assertNotIn("英文标题", result["headers"])
        self.assertNotIn("叶子类目 ID", result["headers"])
        rows = apply_preview(payload, result["mapping"], "simple")
        self.assertEqual(rows[0].sku, "SKU-1001")
        self.assertEqual(rows[0].price, "1.80")
        self.assertEqual(rows[0].moq, "500")
        self.assertEqual(rows[0].brand, "")
        self.assertEqual(rows[0].extra_defaults(), {})

    def test_brand_is_a_redline_default_not_an_ai_seed(self) -> None:
        row = ExcelRow(brand="Acme", price="1.80")
        self.assertEqual(row.extra_defaults(), {"brand": "Acme"})
        self.assertNotIn("brand", row.seed_values())

    def test_official_alibaba_template_only_asks_for_what_ai_cannot_know(self) -> None:
        payload = build_template(
            "alibaba",
            {"name": "油漆刷", "category_id": "21111112"},
            [{"id": "productTitle", "name": "Product name", "who": "AI 生成"}],
        )
        result = preview(payload, "alibaba")
        self.assertEqual(set(result["mapping"].values()), {"sku", "price", "moq", "images", "note"})
        self.assertNotIn("英文标题", result["headers"])

    def test_dianxiaomi_template_stamps_the_listing_category(self) -> None:
        payload = build_template("dianxiaomi", {"name": "油漆刷", "category_id": "21111112"})
        result = preview(payload, "dianxiaomi")
        self.assertIn("英文标题", result["mapping"])
        self.assertNotIn("叶子类目 ID", result["headers"])


if __name__ == "__main__":
    unittest.main()
