"""Sanitized ICBU copy must stay factual and platform-safe."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from ai import Copy, sanitize_copy  # noqa: E402


class AiCopyTests(unittest.TestCase):
    def test_sanitize_strips_spam_and_forbidden_chars(self) -> None:
        raw = Copy(
            title="Hot Sale!!! 24色 Colored Pencil Set @factory",
            keywords=[
                "colored pencil set",
                "colored pencil set",
                "school art supply",
                "wholesale bulk order",
            ],
            highlights="<b>Nice</b> pencils for students",
            selling_points=["Smooth core", "Bright pigments", "Compact tin"],
            faqs=[{"question": "MOQ?", "answer": "500 sets per order."}],
            confidence=0.9,
        )
        cleaned = sanitize_copy(raw, title_limit=80, keyword_count=3)
        self.assertNotIn("Hot Sale", cleaned.title)
        self.assertNotIn("@", cleaned.title)
        self.assertNotIn("色", cleaned.title)
        self.assertLessEqual(len(cleaned.title.encode("utf-8")), 80)
        self.assertGreaterEqual(len(cleaned.keywords), 2)
        self.assertIn("school art supply", cleaned.keywords)
        self.assertNotIn("<b>", cleaned.highlights)

    def test_keywords_skip_title_duplicates(self) -> None:
        raw = Copy(
            title="Watercolor Paint Set for Students",
            keywords=["watercolor paint set", "student classroom supply", "bulk art material"],
            highlights="Student watercolor set.",
            selling_points=["Portable", "Vivid colors", "Easy wash"],
            faqs=[],
            confidence=0.8,
        )
        cleaned = sanitize_copy(raw, keyword_count=3)
        self.assertEqual(cleaned.keywords[0], "student classroom supply")
        self.assertEqual(len(cleaned.keywords), 2)


if __name__ == "__main__":
    unittest.main()
