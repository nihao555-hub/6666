"""Excel rows can arrive with no photo, one photo, or a full set."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

os.environ["DATABASE_PATH"] = str(Path(tempfile.mkdtemp()) / "excel-images.db")
os.environ["UPLOAD_DIR"] = str(Path(tempfile.mkdtemp()) / "uploads")
os.environ["TOKEN_ENCRYPTION_KEY"] = "Frqkv73e3W19RfKb5WSgTueumPWcBSmpbM4wDyqu52o="
os.environ["REGISTRATION_CODES"] = "TEST-CODE"
os.environ["ALIBABA_APP_KEY"] = "test-key"
os.environ["ALIBABA_APP_SECRET"] = "test-secret"

from server.services.excel_images import ExcelImageError, prepare_row_images  # noqa: E402
from server.services.excel_import import ExcelRow  # noqa: E402


class ExcelImageModeTests(unittest.TestCase):
    def test_one_photo_is_used_as_is(self) -> None:
        row = ExcelRow(sku="A-01", name="油漆刷", images=["a.jpg"])
        files, source = prepare_row_images(
            row,
            {"a.jpg": b"shot"},
            "mixed",
            user_id="u1",
            generate=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should use the photo")),
        )
        self.assertEqual(source, "photos")
        self.assertEqual(files, [("a.jpg", b"shot")])

    def test_missing_photo_draws_a_set(self) -> None:
        row = ExcelRow(sku="A-02", name="陶瓷杯")
        drawn, source = prepare_row_images(
            row,
            {},
            "mixed",
            user_id="u1",
            generate=lambda *args, **kwargs: [("01-main.png", b"gen")],
        )
        self.assertEqual(source, "generated")
        self.assertEqual(drawn, [("01-main.png", b"gen")])

    def test_photos_only_skips_empty_rows(self) -> None:
        skipped, source = prepare_row_images(ExcelRow(sku="A-02", name="陶瓷杯"), {}, "photos_only", user_id="u1")
        self.assertEqual(source, "skip")
        self.assertEqual(skipped, [])

    def test_generate_all_ignores_existing_photos(self) -> None:
        row = ExcelRow(sku="A-01", name="油漆刷", images=["a.jpg"])
        drawn, source = prepare_row_images(
            row,
            {"a.jpg": b"shot"},
            "generate_all",
            user_id="u1",
            generate=lambda *args, **kwargs: [("01-main.png", b"gen")],
        )
        self.assertEqual(source, "generated")
        self.assertEqual(drawn, [("01-main.png", b"gen")])

    def test_cannot_draw_without_a_name(self) -> None:
        with self.assertRaises(ExcelImageError):
            prepare_row_images(ExcelRow(sku="A-03"), {}, "mixed", user_id="u1")


if __name__ == "__main__":
    unittest.main()
