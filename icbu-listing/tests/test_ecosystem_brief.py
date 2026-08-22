"""Alibaba ecosystem brief for business-assistant-style AI fill."""

import sys
import unittest
from pathlib import Path

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

    def test_build_brief_without_api(self) -> None:
        shop = Shop(name="测试店", platform="alibaba_icbu")
        brief = ecosystem_brief.build_brief(object(), shop, category_id="123", category_name="画笔")
        self.assertEqual(brief["category_id"], "123")
        self.assertIn("assistant_steps", brief)
        self.assertIn("keyword_strategy", brief)
