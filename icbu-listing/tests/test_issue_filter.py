"""Issue list filtering for bulk-friendly audit."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.services.issue_filter import for_user, is_actionable, row_issues_for_user  # noqa: E402


class IssueFilterTests(unittest.TestCase):
    def test_orphan_schema_field_is_hidden(self) -> None:
        issue = {
            "field_id": "p-1-1",
            "level": "yellow",
            "message": "该类目没有这个字段，提交时会被忽略",
            "path": "icbuCatProp.p-1-1",
        }
        self.assertFalse(is_actionable(issue))
        self.assertEqual(for_user([issue]), [])

    def test_real_required_attr_stays(self) -> None:
        issue = {
            "field_id": "p-color",
            "level": "red",
            "message": "必填项还没有值",
            "path": "icbuCatProp.p-color",
        }
        self.assertTrue(is_actionable(issue))
        self.assertEqual(len(for_user([issue])), 1)

    def test_logistics_and_quality_hidden(self) -> None:
        issues = [
            {"field_id": "productQuality", "level": "red", "message": "4.2", "path": "productQuality"},
            {"field_id": "shippingTemplate", "level": "red", "message": "缺运费", "path": "logistics.shippingTemplate"},
        ]
        self.assertEqual(for_user(issues), [])

    def test_yellow_issues_hidden(self) -> None:
        issues = [
            {"field_id": "images", "level": "yellow", "message": "没有图片", "path": "scImages"},
            {"field_id": "p-1-1", "level": "yellow", "message": "置信度偏低", "path": "icbuCatProp.p-1-1"},
        ]
        self.assertEqual(for_user(issues), [])

    def test_row_issues_only_price_moq(self) -> None:
        issues = [
            {"line": 2, "level": "red", "message": "缺单价。价格是红线，AI 不代填。"},
            {"line": 3, "level": "yellow", "message": "没有图片"},
            {"line": 4, "level": "red", "message": "必填项还没有值", "path": "icbuCatProp.p-color"},
        ]
        filtered = row_issues_for_user(issues)
        self.assertEqual(len(filtered), 1)
        self.assertIn("单价", filtered[0]["message"])


if __name__ == "__main__":
    unittest.main()
