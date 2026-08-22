"""Review enrich: copy columns and schema inventory."""

import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

os.environ.setdefault("TOKEN_ENCRYPTION_KEY", "Frqkv73e3W19RfKb5WSgTueumPWcBSmpbM4wDyqu52o=")

from server.services import review_enrich  # noqa: E402


class ReviewEnrichTests(unittest.TestCase):
    def test_order_review_columns_puts_copy_first(self) -> None:
        plan = [
            {"id": "sku", "label": "货号"},
            {"id": "price", "label": "单价"},
            {"id": "attr.icbuCatProp.p-1", "label": "材质"},
        ]
        ordered = review_enrich.order_review_columns(plan)
        ids = [col["id"] for col in ordered]
        self.assertEqual(ids[:3], ["title", "keywords", "highlights"])
        self.assertIn("sku", ids)
        self.assertLess(ids.index("title"), ids.index("sku"))

    def test_enrich_rows_without_ai(self) -> None:
        cols, rows, warnings = review_enrich.enrich_rows(
            [{"line": 2, "sku": "A", "name": "测试", "price": "1", "moq": "100"}],
            [{"id": "sku", "label": "货号"}, {"id": "price", "label": "单价"}],
            category_name="彩铅",
            ai=None,
        )
        self.assertTrue(any(col["id"] == "title" for col in cols))
        self.assertTrue(warnings)
        self.assertIn("title", rows[0])

    def test_enrich_rows_with_mock_ai(self) -> None:
        ai = MagicMock()
        ai.write_copy.return_value = MagicMock(
            title="Wholesale Cosmetic Puff Set OEM",
            keywords=["cosmetic puff", "makeup sponge", "beauty blender"],
            highlights="Soft latex-free puff",
            selling_points=["OEM welcome"],
        )
        cols, rows, _warnings = review_enrich.enrich_rows(
            [{"line": 2, "sku": "PUFF-1", "name": "化妆粉扑", "price": "2", "moq": "500"}],
            [{"id": "sku", "label": "货号"}],
            category_name="化妆棉扑",
            ai=ai,
        )
        self.assertEqual(rows[0]["title"], "Wholesale Cosmetic Puff Set OEM")
        self.assertIn("cosmetic puff", rows[0]["keywords"])
        self.assertEqual(cols[0]["id"], "title")

    def test_infer_fields_from_note(self) -> None:
        columns = [
            {
                "id": "attr.icbuCatProp.p-hard",
                "label": "硬度",
                "required": True,
                "options": [{"label": "HB", "value": "HB"}, {"label": "2B", "value": "2B"}],
            }
        ]
        patch, hints = review_enrich.infer_fields_for_row(
            {"name": "铅笔", "note": "HB 硬度，适合素描", "sku": "P-1"},
            columns,
        )
        self.assertEqual(patch.get("attr.icbuCatProp.p-hard"), "HB")
        self.assertTrue(hints)

    def test_ai_target_columns_excludes_user_sheet(self) -> None:
        candidates = [
            {"id": "sku", "label": "货号", "required": True},
            {"id": "attr.icbuCatProp.p-hard", "label": "硬度", "required": True, "source": "schema_required"},
            {"id": "schema.paymentMethod", "label": "付款", "source": "schema_score"},
        ]
        targets = review_enrich.ai_target_columns(candidates, {"sku", "price", "moq"})
        ids = {item["id"] for item in targets}
        self.assertIn("attr.icbuCatProp.p-hard", ids)
        self.assertIn("schema.paymentMethod", ids)
        self.assertNotIn("sku", ids)

    def test_infer_fields_with_mock_ai(self) -> None:
        ai = MagicMock()
        ai.chat_json.return_value = {"attr.icbuCatProp.p-hard": "HB"}
        columns = [
            {
                "id": "attr.icbuCatProp.p-hard",
                "label": "硬度",
                "required": True,
                "source": "schema_required",
                "options": [{"label": "HB", "value": "HB"}, {"label": "2B", "value": "2B"}],
            }
        ]
        rows, _errors, filled, meta = review_enrich.infer_fields_for_rows(
            [{"line": 2, "sku": "P-1", "name": "铅笔", "note": "素描铅笔"}],
            columns,
            ai=ai,
        )
        self.assertEqual(filled, 1)
        self.assertEqual(rows[0].get("attr.icbuCatProp.p-hard"), "HB")
        self.assertGreaterEqual(meta.get("fillable_columns", 0), 1)

    def test_infer_fields_skips_ambiguous(self) -> None:
        columns = [
            {
                "id": "attr.icbuCatProp.p-hard",
                "label": "硬度",
                "options": [{"label": "HB", "value": "HB"}, {"label": "2B", "value": "2B"}],
            }
        ]
        patch, _hints = review_enrich.infer_fields_for_row(
            {"name": "铅笔", "note": "HB 和 2B 混装", "sku": "P-2"},
            columns,
        )
        self.assertEqual(patch, {})

    def test_infer_facts_include_ai_copy(self) -> None:
        ai = MagicMock()
        ai.chat_json.return_value = {"attr.icbuCatProp.p-hard": "HB"}
        columns = [
            {
                "id": "attr.icbuCatProp.p-hard",
                "label": "硬度",
                "required": True,
                "source": "schema_required",
                "options": [{"label": "HB", "value": "HB"}],
            }
        ]
        review_enrich.infer_fields_for_row(
            {
                "sku": "P-1",
                "name": "铅笔",
                "note": "素描",
                "title": "HB Graphite Pencil Wholesale",
                "keywords": "graphite pencil, hb pencil",
            },
            columns,
            ai=ai,
            user_column_ids={"sku", "name", "note"},
        )
        prompt = ai.chat_json.call_args[0][0][0]["content"]
        self.assertIn("HB Graphite Pencil Wholesale", prompt)
        self.assertIn("graphite pencil", prompt)


if __name__ == "__main__":
    unittest.main()
