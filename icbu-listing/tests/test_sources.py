"""Hand edits and Excel values survive regenerate and templates."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.services.sources import (  # noqa: E402
    apply_incoming,
    infer_initial,
    keep_locked,
    mark_template_fills,
    mark_user_edits,
    unlock_for_category_change,
)


class SourceLockTests(unittest.TestCase):
    def test_regenerate_keeps_hand_edited_title_and_excel_price(self) -> None:
        old = {
            "productTitle": "Seller Fixed Title",
            "ladderPrice": {"ladderPrice_0": {"quantity": "500", "price": "1.80"}},
            "origin": "China",
        }
        new = {
            "productTitle": "AI just rewrote this",
            "ladderPrice": {"ladderPrice_0": {"quantity": "10", "price": "9.99"}},
            "origin": "Vietnam",
            "productKeywords": {"productKeywords_0": "brush"},
        }
        sources = {
            "productTitle": "user",
            "ladderPrice": "excel",
            "origin": "shop",
        }
        merged = keep_locked(old, new, sources)
        self.assertEqual(merged["productTitle"], "Seller Fixed Title")
        self.assertEqual(merged["ladderPrice"]["ladderPrice_0"]["price"], "1.80")
        self.assertEqual(merged["origin"], "Vietnam")
        self.assertEqual(merged["productKeywords"]["productKeywords_0"], "brush")

    def test_user_edit_is_the_only_thing_that_overwrites_a_lock(self) -> None:
        base = {"productTitle": "From Excel"}
        sources = {"productTitle": "excel"}
        after_ai, sources_ai = apply_incoming(base, {"productTitle": "AI title"}, sources, "ai")
        self.assertEqual(after_ai["productTitle"], "From Excel")
        after_user, sources_user = apply_incoming(base, {"productTitle": "I typed this"}, sources_ai, "user")
        self.assertEqual(after_user["productTitle"], "I typed this")
        self.assertEqual(sources_user["productTitle"], "user")

    def test_template_only_marks_fields_it_actually_filled(self) -> None:
        before = {"origin": "", "priceUnit": "Piece/Pieces"}
        after = {"origin": "Vietnam", "priceUnit": "Piece/Pieces"}
        sources = mark_template_fills(before, after, {"priceUnit": "shop"})
        self.assertEqual(sources["origin"], "template")
        self.assertEqual(sources["priceUnit"], "shop")

    def test_changing_category_unlocks_attributes(self) -> None:
        sources = unlock_for_category_change(
            {"productTitle": "user", "icbuCatProp": "user", "catId": "excel", "origin": "shop"}
        )
        self.assertEqual(sources["productTitle"], "user")
        self.assertEqual(sources["origin"], "shop")
        self.assertNotIn("icbuCatProp", sources)
        self.assertNotIn("catId", sources)

    def test_saving_a_field_marks_it_user(self) -> None:
        sources = mark_user_edits(
            {"productTitle": "old"},
            {"productTitle": "new", "textDesc": "same as missing"},
            {},
        )
        self.assertEqual(sources["productTitle"], "user")
        self.assertEqual(sources["textDesc"], "user")

    def test_initial_inference_splits_trade_copy_and_shop(self) -> None:
        sources = infer_initial(
            {
                "productTitle": "t",
                "ladderPrice": {},
                "origin": "China",
                "scImages": [],
                "icbuCatProp": {},
            },
            {"productTitle": "excel"},
        )
        self.assertEqual(sources["productTitle"], "excel")
        self.assertEqual(sources["ladderPrice"], "user")
        self.assertEqual(sources["origin"], "shop")
        self.assertEqual(sources["scImages"], "system")
        self.assertEqual(sources["icbuCatProp"], "ai")


if __name__ == "__main__":
    unittest.main()
