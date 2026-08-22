"""grid-regen-copy respects use_ecosystem opt-in."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

os.environ["DATABASE_PATH"] = str(Path(tempfile.mkdtemp()) / "grid-regen-copy.db")
os.environ["UPLOAD_DIR"] = str(Path(tempfile.mkdtemp()) / "uploads")
os.environ["TOKEN_ENCRYPTION_KEY"] = "Frqkv73e3W19RfKb5WSgTueumPWcBSmpbM4wDyqu52o="
os.environ["REGISTRATION_CODES"] = "TEST-CODE"
os.environ["ALIBABA_APP_KEY"] = "test-key"
os.environ["ALIBABA_APP_SECRET"] = "test-secret"
os.environ.pop("OPENAI_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

from server.db import init_db  # noqa: E402
from server.main import app  # noqa: E402


def signup(tag: str = "user") -> TestClient:
    client = TestClient(app)
    email = f"{tag}-{uuid.uuid4().hex[:10]}@example.com"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "supersecret", "code": "TEST-CODE"},
    )
    assert response.status_code == 200, response.text
    return client


class GridRegenCopyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()

    def test_skips_ecosystem_when_disabled(self) -> None:
        client = signup("eco-off")
        shop_id = client.post("/api/v1/shops/bind-env", json={"name": "测试店"}).json()["id"]
        row = {"line": 3, "sku": "SKU-1", "name": "Test pencil", "note": "wood barrel", "price": "9", "moq": "100"}

        mock_ai = MagicMock()
        mock_ai.write_copy.return_value = MagicMock(
            title="Test Title",
            keywords=["wholesale", "pencil"],
            highlights="Good quality",
            selling_points=["Good quality"],
        )
        with patch("server.routers.excel.AiClient.from_env_or_none", return_value=mock_ai):
            with patch("server.routers.excel.ecosystem_brief.build_brief") as build_brief:
                response = client.post(
                    "/api/v1/excel/grid-regen-copy",
                    data={
                        "shop_id": shop_id,
                        "category_id": "21110712",
                        "category_name": "Colored Pencils",
                        "rows": json.dumps([row]),
                        "lines": json.dumps([]),
                        "use_ecosystem": "false",
                    },
                )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertNotIn("ecosystem_brief", payload)
        self.assertEqual(payload["rows"][0]["title"], "Test Title")
        build_brief.assert_not_called()

    def test_builds_ecosystem_when_enabled(self) -> None:
        client = signup("eco-on")
        shop_id = client.post("/api/v1/shops/bind-env", json={"name": "测试店2"}).json()["id"]
        row = {"line": 3, "sku": "SKU-2", "name": "Test pencil", "note": "wood barrel", "price": "9", "moq": "100"}

        mock_ai = MagicMock()
        mock_ai.write_copy.return_value = MagicMock(
            title="Eco Title",
            keywords=["oem", "factory"],
            highlights="Eco copy",
            selling_points=["Eco copy"],
        )
        brief = {"tips": "use inquiry terms", "golden_titles": ["Sample title"], "schema_limits": {}}
        with patch("server.routers.excel.AiClient.from_env_or_none", return_value=mock_ai):
            with patch("server.routers.excel.ecosystem_brief.build_brief", return_value=brief) as build_brief:
                response = client.post(
                    "/api/v1/excel/grid-regen-copy",
                    data={
                        "shop_id": shop_id,
                        "category_id": "21110712",
                        "category_name": "Colored Pencils",
                        "rows": json.dumps([row]),
                        "lines": json.dumps([]),
                        "use_ecosystem": "true",
                    },
                )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertNotIn("ecosystem_brief", payload)
        self.assertEqual(payload["rows"][0]["title"], "Eco Title")
        build_brief.assert_called_once()
