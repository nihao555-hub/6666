"""Templates fill empty fields and never overwrite what a person already wrote."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.services.templates import PROTECTED, fill_blank  # noqa: E402


class FillBlankTests(unittest.TestCase):
    def test_empty_draft_takes_template(self) -> None:
        merged = fill_blank({"origin": "Vietnam", "priceUnit": "Set/Sets"}, {})
        self.assertEqual(merged["origin"], "Vietnam")
        self.assertEqual(merged["priceUnit"], "Set/Sets")

    def test_filled_draft_keeps_its_own_value(self) -> None:
        merged = fill_blank(
            {"origin": "Vietnam", "priceUnit": "Set/Sets"},
            {"origin": "China", "priceUnit": ""},
        )
        self.assertEqual(merged["origin"], "China")
        self.assertEqual(merged["priceUnit"], "Set/Sets")

    def test_title_price_and_images_are_never_taken_from_template(self) -> None:
        template = {key: f"template-{key}" for key in PROTECTED}
        template["origin"] = "Vietnam"
        draft = {
            "productTitle": "Hand filled title",
            "ladderPrice": {"ladderPrice_0": {"quantity": "100", "price": "1.80"}},
            "minOrderQuantity": "100",
            "scImages": [{"fileId": "keep-me"}],
        }
        merged = fill_blank(template, draft)
        self.assertEqual(merged["productTitle"], "Hand filled title")
        self.assertEqual(merged["ladderPrice"]["ladderPrice_0"]["price"], "1.80")
        self.assertEqual(merged["minOrderQuantity"], "100")
        self.assertEqual(merged["scImages"][0]["fileId"], "keep-me")
        self.assertEqual(merged["origin"], "Vietnam")
        self.assertNotIn("catId", merged)  # protected and absent from draft stays absent

    def test_nested_dicts_fill_blank_recursively(self) -> None:
        merged = fill_blank(
            {"pkgMeasure": {"length": "10", "width": "8", "height": "4"}},
            {"pkgMeasure": {"length": "12", "width": ""}},
        )
        self.assertEqual(merged["pkgMeasure"]["length"], "12")
        self.assertEqual(merged["pkgMeasure"]["width"], "8")
        self.assertEqual(merged["pkgMeasure"]["height"], "4")

    def test_both_empty_stays_empty(self) -> None:
        self.assertEqual(fill_blank({}, {}), {})


if __name__ == "__main__":
    unittest.main()
