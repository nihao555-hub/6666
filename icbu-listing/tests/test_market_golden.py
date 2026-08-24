"""Platform category golden references for image generation."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from server.services import market_golden  # noqa: E402


class MarketGoldenTests(unittest.TestCase):
    def test_score_listing_summary_boosts_rating_and_sales(self) -> None:
        low = market_golden._score_listing_summary(
            {"subject": "Wholesale Paint Brush Set", "category_id": "123"},
            category_id="123",
        )
        high = market_golden._score_listing_summary(
            {
                "subject": "Wholesale Paint Brush Set",
                "category_id": "123",
                "review_score": 4.9,
                "sold_quantity": 1200,
            },
            category_id="123",
        )
        self.assertGreater(high, low)
        low = market_golden._score_listing_summary(
            {"subject": "Wholesale Paint Brush Set", "category_id": "123"},
            category_id="123",
        )
        high = market_golden._score_listing_summary(
            {
                "subject": "Wholesale Paint Brush Set",
                "category_id": "123",
                "group_name": "Best Seller",
                "display": "Y",
            },
            category_id="123",
        )
        self.assertGreater(high, low)

    def test_search_category_listings_ranks_by_score(self) -> None:
        api = MagicMock()
        api.search_products.return_value = {
            "result": {
                "products": [
                    {"product_id": "1", "subject": "Basic Brush", "category_id": "99"},
                    {
                        "product_id": "2",
                        "subject": "Wholesale OEM Paint Brush Bulk",
                        "category_id": "99",
                        "group_name": "Hot",
                        "display": "Y",
                    },
                ]
            }
        }
        rows = market_golden.search_category_listings(api, category_id="99", subject="brush")
        self.assertEqual(rows[0]["product_id"], "2")

    def test_fetch_category_golden_falls_back_to_conversion_dna(self) -> None:
        api = MagicMock()
        api.search_products.side_effect = RuntimeError("gateway blocked")
        payload = market_golden.fetch_category_golden(
            api,
            category_id="99",
            category_name="Paint Brushes",
            product_name="Flat Brush",
        )
        self.assertEqual(payload["source"], "category_conversion_dna")
        self.assertIn("slot_priorities", payload)
        self.assertIn("family", payload)

    def test_apply_to_plan_injects_style_refs_when_no_seller_photos(self) -> None:
        plan = {"reference_urls": [], "slots": [{"prompt": "white background main"}]}
        golden = {
            "source": "platform_category_search",
            "style_reference_urls": ["https://img.example.com/a.jpg"],
            "listings": [{"title": "Wholesale Brush", "quality_score": 80}],
            "slot_priorities": ["白底主图"],
        }
        out = market_golden.apply_to_plan(plan, golden)
        self.assertEqual(out["reference_urls"], ["https://img.example.com/a.jpg"])
        self.assertIn("market_golden", out)
        self.assertIn("MARKET GOLDEN", out["slots"][0]["prompt"])

    def test_apply_to_plan_keeps_seller_refs_when_present(self) -> None:
        plan = {"reference_urls": ["https://seller.example.com/my.jpg"], "slots": [{"prompt": "main"}]}
        golden = {
            "style_reference_urls": ["https://img.example.com/other.jpg"],
            "listings": [{"title": "Other SKU"}],
        }
        out = market_golden.apply_to_plan(plan, golden)
        self.assertEqual(out["reference_urls"], ["https://seller.example.com/my.jpg"])
        self.assertNotIn("style_reference_urls", out)


if __name__ == "__main__":
    unittest.main()
