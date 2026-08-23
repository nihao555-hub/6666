"""Issue list filtering for bulk-friendly audit."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.services.issue_filter import for_user, is_actionable  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
