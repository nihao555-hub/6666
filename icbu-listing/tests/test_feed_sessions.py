"""Unfinished listing paths persist per tenant and can be resumed."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

os.environ["DATABASE_PATH"] = str(Path(tempfile.mkdtemp()) / "feed-sessions.db")
os.environ["UPLOAD_DIR"] = str(Path(tempfile.mkdtemp()) / "uploads")
os.environ["TOKEN_ENCRYPTION_KEY"] = "Frqkv73e3W19RfKb5WSgTueumPWcBSmpbM4wDyqu52o="
os.environ["REGISTRATION_CODES"] = "TEST-CODE"
os.environ["ALIBABA_APP_KEY"] = "test-key"
os.environ["ALIBABA_APP_SECRET"] = "test-secret"
os.environ.pop("OPENAI_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

from server.db import init_db  # noqa: E402
from server.main import app  # noqa: E402
from server.models import Draft  # noqa: E402

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc``\x00\x00\x00\x02\x00\x01"
    b"\xe5'\xde\xfc\x00\x00\x00\x00IEND\xaeB`\x82"
)


def signup(email: str) -> TestClient:
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "supersecret", "code": "TEST-CODE"},
    )
    assert response.status_code == 200, response.text
    return client


class FeedSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()

    def test_seller_can_keep_several_unfinished_paths(self) -> None:
        owner = signup("feed-keep@example.com")
        other = signup("feed-other@example.com")
        first = owner.post("/api/v1/feed-sessions", json={"path": "photo"}).json()
        second = owner.post("/api/v1/feed-sessions", json={"path": "ai"}).json()
        self.assertEqual(first["path_label"], "有实拍")
        self.assertEqual(second["path_label"], "平台画图")

        owner.patch(
            f"/api/v1/feed-sessions/{second['id']}",
            json={"step": 1, "reached": 1, "payload": {"aiForm": {"productName": "油漆刷"}}},
        )
        listed = owner.get("/api/v1/feed-sessions").json()["sessions"]
        self.assertEqual(len(listed), 2)
        titles = {item["title"] for item in listed}
        self.assertIn("油漆刷", titles)

        self.assertEqual(other.get(f"/api/v1/feed-sessions/{first['id']}").status_code, 404)
        self.assertEqual(other.get("/api/v1/feed-sessions").json()["sessions"], [])

    def test_staged_photos_can_finish_a_listing_after_reopen(self) -> None:
        client = signup("feed-resume@example.com")
        shop_id = client.post("/api/v1/shops/bind-env", json={"name": "半成品店"}).json()["id"]
        session = client.post("/api/v1/feed-sessions", json={"path": "photo", "shop_id": shop_id}).json()
        uploaded = client.post(
            f"/api/v1/feed-sessions/{session['id']}/files",
            data={"kind": "photos", "keep": ""},
            files=[("files", ("brush.jpg", PNG, "image/png"))],
        )
        self.assertEqual(uploaded.status_code, 200, uploaded.text)
        self.assertEqual(len(uploaded.json()["files"]), 1)
        stored = uploaded.json()["files"][0]["stored"]
        image = client.get(f"/api/v1/feed-sessions/{session['id']}/files/{stored}")
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image.content, PNG)

        def fake_build(db, user, shop, **kwargs):
            self.assertEqual(len(kwargs["uploads"]), 1)
            self.assertEqual(kwargs["uploads"][0][1], PNG)
            draft = Draft(
                user_id=user.id,
                shop_id=shop.id,
                sku=kwargs["sku"],
                title="Paint brush",
                price=kwargs["price"],
                moq=kwargs["moq"],
                status="green",
                issues_json="[]",
            )
            db.add(draft)
            db.commit()
            return draft

        with patch("server.routers.listings._generate", side_effect=fake_build):
            created = client.post(
                "/api/v1/listings/feed",
                data={
                    "shop_id": shop_id,
                    "session_id": session["id"],
                    "price": "1.2",
                    "moq": "100",
                },
            )
        self.assertEqual(created.status_code, 200, created.text)
        leftover = client.get("/api/v1/feed-sessions").json()["sessions"]
        self.assertEqual(leftover, [])

    def test_doc_files_can_be_staged(self) -> None:
        client = signup("feed-doc@example.com")
        session = client.post("/api/v1/feed-sessions", json={"path": "doc"}).json()
        uploaded = client.post(
            f"/api/v1/feed-sessions/{session['id']}/files",
            data={"kind": "doc", "keep": ""},
            files=[("files", ("batch.xlsx", b"fake-xlsx", "application/vnd.ms-excel"))],
        )
        self.assertEqual(uploaded.status_code, 200, uploaded.text)
        self.assertEqual(uploaded.json()["files"][0]["kind"], "doc")

    def test_patch_recreates_missing_session(self) -> None:
        import uuid

        client = signup("feed-upsert@example.com")
        ghost_id = uuid.uuid4().hex
        resp = client.patch(
            f"/api/v1/feed-sessions/{ghost_id}",
            json={"step": 1, "reached": 1, "payload": {"doc": {"categoryName": "测试类目", "rowCount": 2}}},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["id"], ghost_id)
        self.assertIn("测试类目", resp.json()["title"])

    def test_drop_hides_the_unfinished_path(self) -> None:
        client = signup("feed-drop@example.com")
        session = client.post("/api/v1/feed-sessions", json={"path": "excel"}).json()
        self.assertEqual(session["path_label"], "批量上品")
        moved = client.patch(f"/api/v1/feed-sessions/{session['id']}", json={"step": 3, "reached": 3}).json()
        self.assertEqual(moved["step_label"], "商品表")
        self.assertEqual(client.delete(f"/api/v1/feed-sessions/{session['id']}").status_code, 200)
        self.assertEqual(client.get("/api/v1/feed-sessions").json()["sessions"], [])
