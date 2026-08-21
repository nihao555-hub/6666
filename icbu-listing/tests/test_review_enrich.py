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


if __name__ == "__main__":
    unittest.main()
