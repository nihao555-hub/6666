"""Habits readiness unit tests."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

os.environ.setdefault("TOKEN_ENCRYPTION_KEY", "Frqkv73e3W19RfKb5WSgTueumPWcBSmpbM4wDyqu52o=")

from server.services import habits_ready  # noqa: E402


class HabitsReadyTests(unittest.TestCase):
    def test_rule_pick_shipping_prefers_negotiated(self) -> None:
        options = [
            {"value": "1", "label": "智能运费模板"},
            {"value": "2", "label": "买卖双方协商物流"},
        ]
        picked = habits_ready._rule_pick_shipping(options, category_name="未知", context="")
        self.assertEqual(picked["shipping_template_id"], "2")

    def test_recommend_shipping_without_ai(self) -> None:
        options = [{"value": "2041723009", "label": "画笔运费"}]
        picked = habits_ready.recommend_shipping(
            None,
            options,
            category_id="21110712",
            category_name="彩色铅笔",
            context="colored pencil wooden",
        )
        self.assertEqual(picked["shipping_template_id"], "2041723009")

    def test_apply_habits_updates_shop_defaults(self) -> None:
        from server.models import Shop

        shop = Shop(user_id="u1", name="测试", platform="alibaba_icbu", defaults_json='{"origin":"China"}')
        result = habits_ready.apply_habits(
            MagicMock(),
            shop,
            category_id="21110712",
            shipping_template_id="2041723009",
            apply_shipping_to="shop",
        )
        self.assertTrue(result["ok"])
        import json

        merged = json.loads(shop.defaults_json)
        self.assertEqual(merged["shippingTemplateId"], "2041723009")


if __name__ == "__main__":
    unittest.main()
