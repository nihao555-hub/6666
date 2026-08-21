"""FactBundle parsing from Excel rows and ladder price tiers."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from ai import Understanding  # noqa: E402

from server.services.excel_import import ExcelRow  # noqa: E402
from server.services.fact_bundle import FactBundle, from_excel_row, parse_price_tiers  # noqa: E402


class FactBundleTests(unittest.TestCase):
    def test_parse_ladder_from_note(self) -> None:
        tiers = parse_price_tiers("500@1.50; 1000@1.20", fallback_moq="500", fallback_price="1.50")
        self.assertEqual(len(tiers), 2)
        self.assertEqual(tiers[0].quantity, "500")
        self.assertEqual(tiers[0].price, "1.50")

    def test_from_excel_row_records_evidence(self) -> None:
        row = ExcelRow(
            sku="PEN-01",
            name="彩色铅笔",
            price="1.80",
            moq="500",
            brand="Giorgione",
            origin="China",
            note="500@1.80",
            specs={"color": "12 colors", "material": "wood"},
        )
        bundle = from_excel_row(row)
        self.assertEqual(bundle.sku, "PEN-01")
        self.assertTrue(bundle.has("brand"))
        self.assertTrue(bundle.has("spec.color"))
        self.assertEqual(bundle.ladder_values()["ladderPrice_0"]["quantity"], "500")

    def test_enrich_merges_specs_into_understanding(self) -> None:
        bundle = FactBundle(name="Pencil set", specs={"color": "Red, Blue", "material": "Wood"})
        u = bundle.enrich(Understanding(product_name="Colored pencils", material=""))
        self.assertIn("Red", u.colors)
        self.assertEqual(u.material, "Wood")
        self.assertEqual(u.specs.get("color"), "Red, Blue")

    def test_from_dict_roundtrip(self) -> None:
        bundle = FactBundle(
            sku="MKR-01",
            name="Marker set",
            brand="Giorgione",
            note="dual tip",
            specs={"color_count": "24", "tip": "Dual tip"},
            moq="200",
            price="3.20",
            origin="China",
        )
        restored = FactBundle.from_dict(bundle.as_dict())
        self.assertEqual(restored.sku, "MKR-01")
        self.assertEqual(restored.specs["tip"], "Dual tip")
        self.assertEqual(restored.note, "dual tip")


if __name__ == "__main__":
    unittest.main()
