"""Alibaba ecosystem brief for business-assistant-style AI fill."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from server.models import Shop  # noqa: E402
from server.services import ecosystem_brief  # noqa: E402


class EcosystemBriefTests(unittest.TestCase):
    def test_score_copy_row_flags_missing_title(self) -> None:
        scored = ecosystem_brief.score_copy_row({"title": "", "keywords": "wholesale brush"})
        self.assertLess(scored["score"], 70)
        self.assertIn("缺英文标题", scored["issues"])

    def test_score_copy_row_rewards_inquiry_keywords(self) -> None:
        scored = ecosystem_brief.score_copy_row(
            {
                "title": "Industrial Paint Brush Set for Wholesale OEM Orders",
                "keywords": "paint brush wholesale, oem brush set, bulk art supplies",
            }
        )
        self.assertGreaterEqual(scored["score"], 80)
        self.assertIn(scored["tier"], {"S", "A"})

    def test_prompt_block_includes_golden_titles(self) -> None:
        brief = {
            "category_name": "Paint Brushes",
            "golden_titles": ["Wholesale Flat Paint Brush 2 Inch"],
            "keyword_strategy": [{"tier": "S", "hint": "core product term"}],
            "assistant_steps": ["compliance"],
            "tips": "test",
        }
        block = ecosystem_brief.prompt_block(brief)
        self.assertIn("Wholesale Flat Paint Brush", block)
        self.assertIn("Paint Brushes", block)

    def test_prompt_block_includes_golden_listings(self) -> None:
        brief = {
            "category_name": "Paint Brushes",
            "golden_listings": [
                {
                    "title": "Wholesale Flat Paint Brush 2 Inch for OEM Bulk Orders",
                    "keywords": ["paint brush wholesale", "flat brush bulk", "oem art brush"],
                    "key_attrs": {"Material": "Bristle", "Handle": "Wood"},
                    "highlights": "Factory direct paint brush for wholesale buyers.",
                    "moq": "500",
                    "price": "1.80",
                    "image_count": 6,
                }
            ],
        }
        block = ecosystem_brief.prompt_block(brief)
        self.assertIn("Example 1", block)
        self.assertIn("paint brush wholesale", block)
        self.assertIn("Material=Bristle", block)

    def test_prompt_block_includes_platform_rules(self) -> None:
        brief = {
            "category_name": "Paint Brushes",
            "platform_search_rules": ["compliance → matching → inquiry ranking"],
            "keyword_strategy": [{"tier": "S", "hint": "core product term"}],
            "assistant_steps": ["compliance"],
        }
        block = ecosystem_brief.prompt_block(brief)
        self.assertIn("Alibaba International platform brief", block)
        self.assertIn("compliance → matching → inquiry ranking", block)

    def test_build_brief_without_api(self) -> None:
        shop = Shop(name="测试店", platform="alibaba_icbu")
        brief = ecosystem_brief.build_brief(object(), shop, category_id="123", category_name="画笔")
        self.assertEqual(brief["category_id"], "123")
        self.assertEqual(brief["scope"], "platform")
        self.assertIn("assistant_steps", brief)
        self.assertIn("keyword_strategy", brief)
        self.assertIn("platform_search_rules", brief)
        self.assertEqual(brief["golden_listings"], [])

    def test_sample_golden_listings_from_rendered_shop_listing(self) -> None:
        shop = Shop(name="测试店", platform="alibaba_icbu", defaults_json='{"language":"en_US"}')
        api = MagicMock()
        api.list_products.return_value = {
            "result": {
                "total_item": 1,
                "products": [
                    {
                        "product_id": "9001",
                        "category_id": "123",
                        "subject": "Wholesale Flat Paint Brush 2 Inch OEM Bulk Supply",
                    }
                ],
            }
        }
        api.schema_render.return_value = {
            "result": {
                "data": """
                <itemSchema>
                  <field id="productTitle" type="input"><value>Wholesale Flat Paint Brush 2 Inch OEM Bulk Supply</value></field>
                  <field id="productKeywords" type="complex">
                    <complex-value>
                      <field id="productKeywords_0" type="input"><value>paint brush wholesale</value></field>
                      <field id="productKeywords_1" type="input"><value>flat brush bulk</value></field>
                    </complex-value>
                  </field>
                  <field id="textDesc" type="input"><value>Factory direct brush for wholesale buyers.</value></field>
                </itemSchema>
                """
            }
        }

        listings = ecosystem_brief._sample_golden_listings(api, shop, category_id="123", limit=2)
        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0]["title"], "Wholesale Flat Paint Brush 2 Inch OEM Bulk Supply")
        self.assertGreaterEqual(listings[0]["quality_score"], 35)


if __name__ == "__main__":
    unittest.main()
