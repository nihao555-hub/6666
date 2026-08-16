import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

import os  # noqa: E402

os.environ.setdefault("TOKEN_ENCRYPTION_KEY", "Frqkv73e3W19RfKb5WSgTueumPWcBSmpbM4wDyqu52o=")

from server.services.dedup import compare  # noqa: E402
from server.services.publisher import (  # noqa: E402
    guess_fields,
    humanise,
    is_auto_fixable,
    parse_publish_response,
)

ATTRS = {"icbuCatProp": {"p-1": "100000458", "p-9": ["12970290"]}}


class DedupTests(unittest.TestCase):
    def test_same_attributes_and_reworded_title_is_high_risk(self) -> None:
        score, reason = compare(
            "Colored Pencil Set for Students Drawing",
            "21110712",
            ATTRS,
            "Drawing Colored Pencil Set for Students",
            "21110712",
            ATTRS,
        )
        self.assertGreaterEqual(score, 0.82)
        self.assertIn("属性都一样", reason)

    def test_different_products_in_the_same_category_are_fine(self) -> None:
        score, reason = compare(
            "Colored Pencil Set for Students",
            "21110712",
            ATTRS,
            "Watercolor Brush Pen Kit for Calligraphy",
            "21110712",
            {"icbuCatProp": {"p-1": "100000458", "p-9": ["999"]}},
        )
        self.assertEqual(reason, "")
        self.assertLess(score, 0.62)

    def test_different_categories_never_collide(self) -> None:
        score, reason = compare("Same Title Here", "1", ATTRS, "Same Title Here", "2", ATTRS)
        self.assertEqual((score, reason), (0.0, ""))

    def test_marketing_filler_does_not_create_similarity(self) -> None:
        # "wholesale high quality hot sale" is on every listing in the shop.
        score, _ = compare(
            "Wholesale High Quality Hot Sale Ceramic Mug",
            "1",
            {},
            "Wholesale High Quality Hot Sale Steel Bottle",
            "1",
            {},
        )
        self.assertLess(score, 0.62)


class ErrorTranslationTests(unittest.TestCase):
    def test_documented_code_becomes_chinese_with_a_next_step(self) -> None:
        message = humanise("PUB_BIZCHECK_CAT_PUB_RESTRICT: category not allowed")
        self.assertIn("经营范围", message)
        self.assertIn("需要先去卖家后台处理", message)

    def test_fixable_and_unfixable_are_distinguished(self) -> None:
        self.assertTrue(is_auto_fixable("CHK_IMAGE_FILE_COUNT_EXCEED"))
        self.assertFalse(is_auto_fixable("PUB_BIZCHECK_SUSPICIOUS"))

    def test_unknown_errors_fall_back_to_keywords(self) -> None:
        self.assertIn("标题", humanise("The product title is too long"))

    def test_field_ids_are_pulled_out_of_the_message(self) -> None:
        self.assertIn("p-191288433", guess_fields("attribute [p-191288433] is required"))

    def test_success_response_yields_the_product_id(self) -> None:
        outcome = parse_publish_response({"result": {"product_id": 10000046695776}})
        self.assertTrue(outcome.ok)
        self.assertEqual(outcome.product_id, "10000046695776")

    def test_error_response_is_not_mistaken_for_success(self) -> None:
        outcome = parse_publish_response({"result": {"error_message": "PUB_BIZCHECK_SKU_PRICE"}})
        self.assertFalse(outcome.ok)
        self.assertIn("价格", outcome.error)

    def test_empty_response_is_reported_rather_than_assumed_ok(self) -> None:
        outcome = parse_publish_response({"result": {}})
        self.assertFalse(outcome.ok)


if __name__ == "__main__":
    unittest.main()
