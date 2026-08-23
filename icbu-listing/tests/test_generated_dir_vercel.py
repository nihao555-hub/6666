"""Generated image dir must stay writable on Vercel (/tmp)."""

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class GeneratedDirVercelTests(unittest.TestCase):
    def test_vercel_uses_tmp_not_repo_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["VERCEL"] = "1"
            os.environ["DATA_ROOT"] = tmp
            os.environ.pop("GENERATED_DIR", None)
            os.environ.pop("UPLOAD_DIR", None)
            import server.config as config

            importlib.reload(config)
            import server.services.grsai_images as grsai_images

            importlib.reload(grsai_images)
            path = grsai_images.generated_dir()
            self.assertTrue(str(path).startswith("/tmp/"))
            probe = path / ".write-probe"
            probe.write_text("ok", encoding="utf-8")
            self.assertEqual(probe.read_text(encoding="utf-8"), "ok")


if __name__ == "__main__":
    unittest.main()
