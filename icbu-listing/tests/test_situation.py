"""The start screen must change with what the seller already has."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.services.situation import Snapshot, recommend  # noqa: E402


class SituationTests(unittest.TestCase):
    def test_no_shop_blocks_everything_else(self) -> None:
        result = recommend(Snapshot())
        self.assertEqual(result["id"], "no_shop")
        self.assertEqual(result["action"]["to"], "/shops")
        self.assertEqual(result["alternatives"], [])

    def test_red_drafts_come_before_new_feed(self) -> None:
        result = recommend(Snapshot(shops=1, defaults_untouched=False, red=4, products=10))
        self.assertEqual(result["id"], "review_reds")
        self.assertIn("红项", result["title"])

    def test_ready_drafts_go_to_publish(self) -> None:
        result = recommend(Snapshot(shops=1, defaults_untouched=False, ready=8))
        self.assertEqual(result["id"], "publish_ready")

    def test_empty_defaults_match_official_pre_req(self) -> None:
        result = recommend(Snapshot(shops=1, defaults_untouched=True))
        self.assertEqual(result["id"], "no_defaults")

    def test_catalogue_without_drafts_is_distribute(self) -> None:
        result = recommend(Snapshot(shops=1, defaults_untouched=False, products=20, drafts=0))
        self.assertEqual(result["id"], "has_catalogue")
        self.assertEqual(result["action"]["to"], "/products")

    def test_established_shop_is_told_to_clone(self) -> None:
        result = recommend(Snapshot(shops=1, defaults_untouched=False, online_count=1227))
        self.assertEqual(result["id"], "established")
        self.assertEqual(result["action"]["to"], "/online")

    def test_new_shop_gets_photo_path_and_excel_alternative(self) -> None:
        result = recommend(Snapshot(shops=1, defaults_untouched=False, online_count=0))
        self.assertEqual(result["id"], "new_shop_photos")
        ids = [item["id"] for item in result["alternatives"]]
        self.assertIn("excel", ids)
        self.assertIn("official", ids)
        self.assertNotIn("clone", ids)
        self.assertNotIn("photos", ids)
