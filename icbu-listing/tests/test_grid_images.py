"""Batch grid image slots and job refresh."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from server.services.grid_images import (  # noqa: E402
    attach_row_images,
    empty_slots,
    slots_from_urls,
)


class GridImageTests(unittest.TestCase):
    def test_empty_slots_has_six_placeholders(self) -> None:
        slots = empty_slots()
        self.assertEqual(len(slots), 6)
        self.assertEqual(slots[0]["status"], "empty")
        self.assertEqual(slots[0]["url"], "")

    def test_attach_row_images_from_urls(self) -> None:
        item = attach_row_images({"images": "https://img.example.com/a.jpg; b.jpg"})
        self.assertEqual(len(item["image_slots"]), 6)
        self.assertEqual(item["image_slots"][0]["status"], "uploaded")
        self.assertIn("example.com", item["image_slots"][0]["url"])

    def test_attach_row_images_defaults_when_blank(self) -> None:
        item = attach_row_images({"sku": "A-1"})
        self.assertEqual(len(item["image_slots"]), 6)
        self.assertTrue(all(slot["status"] == "empty" for slot in item["image_slots"]))

    def test_attach_row_images_replaces_empty_placeholder_slots(self) -> None:
        item = attach_row_images(
            {
                "images": "https://img.example.com/a.jpg",
                "image_slots": empty_slots(),
            }
        )
        self.assertIn("example.com", item["image_slots"][0]["url"])

    def test_attach_row_images_keeps_generated_slots(self) -> None:
        generated = empty_slots()
        generated[0] = {**generated[0], "status": "done", "url": "/api/v1/image-templates/jobs/j1/files/1.png"}
        item = attach_row_images({"images": "local.jpg", "image_slots": generated})
        self.assertEqual(item["image_slots"][0]["url"], "/api/v1/image-templates/jobs/j1/files/1.png")

    def test_start_row_job_requires_name(self) -> None:
        from server.services import grid_images

        with patch.object(grid_images, "api_key", return_value="test-key"):
            with self.assertRaises(ValueError):
                grid_images.start_row_job("user-1", {"sku": ""})


if __name__ == "__main__":
    unittest.main()
