"""Grid image kickoff skips browser blob placeholders but starts real jobs."""

import json
import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

os.environ["DATABASE_PATH"] = str(Path(tempfile.mkdtemp()) / f"grid-gen-{uuid.uuid4().hex}.db")
os.environ["UPLOAD_DIR"] = str(Path(tempfile.mkdtemp()) / "uploads")
os.environ["TOKEN_ENCRYPTION_KEY"] = "Frqkv73e3W19RfKb5WSgTueumPWcBSmpbM4wDyqu52o="
os.environ["REGISTRATION_CODES"] = "TEST-CODE"
os.environ["ALIBABA_APP_KEY"] = "test-key"
os.environ["ALIBABA_APP_SECRET"] = "test-secret"
os.environ.setdefault("GRSAI_API_KEY", "test-grsai-key")
os.environ.pop("OPENAI_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

from server.db import init_db  # noqa: E402
from server.main import app  # noqa: E402


def signup() -> TestClient:
    client = TestClient(app)
    email = f"grid-{uuid.uuid4().hex[:10]}@example.com"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "supersecret", "code": "TEST-CODE"},
    )
    assert response.status_code == 200, response.text
    return client


class GridGenerateImagesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()

    def test_blob_slots_do_not_block_job_start(self) -> None:
        client = signup()
        rows = [
            {
                "line": 2,
                "sku": "SKU-1",
                "name": "Colored Pencil Set",
                "image_slots": [
                    {"index": i, "url": f"blob:http://localhost/{i}", "status": "uploaded"}
                    for i in range(1, 7)
                ],
            }
        ]
        started: list[str] = []

        def fake_start(user_id, row, *, category_id="", category_name="", api=None, shop=None):
            started.append(str(row.get("sku")))
            return "job-test-1"

        with patch("server.routers.excel.grid_images.start_row_job", side_effect=fake_start), patch(
            "server.routers.excel.grid_images.refresh_row_job",
            side_effect=lambda row, user_id: {**row, "image_job_id": "job-test-1", "image_job_status": "queued"},
        ):
            response = client.post(
                "/api/v1/excel/grid-generate-images",
                data={
                    "category_id": "21110712",
                    "category_name": "彩铅",
                    "rows": json.dumps(rows, ensure_ascii=False),
                    "lines": "[]",
                },
            )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(len(started), 1)
        self.assertGreaterEqual(body.get("jobs_started", 0), 1)


if __name__ == "__main__":
    unittest.main()
