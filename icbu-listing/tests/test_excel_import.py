"""Excel styles, header detection, and official templates."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.services.excel_import import (  # noqa: E402
    ExcelRow,
    apply_preview,
    build_template,
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
