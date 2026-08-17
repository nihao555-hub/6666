"""Platform-generated listing photos go through Grsai, never a live draw in tests."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

os.environ["DATABASE_PATH"] = str(Path(tempfile.mkdtemp()) / "grsai.db")
os.environ["UPLOAD_DIR"] = str(Path(tempfile.mkdtemp()) / "uploads")
os.environ["GENERATED_DIR"] = str(Path(tempfile.mkdtemp()) / "generated")
os.environ["TOKEN_ENCRYPTION_KEY"] = "Frqkv73e3W19RfKb5WSgTueumPWcBSmpbM4wDyqu52o="
os.environ["REGISTRATION_CODES"] = "TEST-CODE"
os.environ["ALIBABA_APP_KEY"] = "test-key"
os.environ["ALIBABA_APP_SECRET"] = "test-secret"
os.environ["ALIBABA_ACCESS_TOKEN"] = "test-token"
os.environ["GRSAI_API_KEY"] = "test-grsai-key"
os.environ["GRSAI_BASE_URL"] = "https://api.grsai.example"
os.environ.pop("OPENAI_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

from server.db import init_db  # noqa: E402
from server.main import app  # noqa: E402
from server.models import Draft  # noqa: E402
from server.services.grsai_images import GrsaiError, parse_response  # noqa: E402

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc``\x00\x00\x00\x02\x00\x01"
    b"\xe5'\xde\xfc\x00\x00\x00\x00IEND\xaeB`\x82"
)


class ImmediateThread:
    def __init__(self, target, args=(), kwargs=None, daemon=None):
        self.target = target
        self.args = args
        self.kwargs = kwargs or {}

    def start(self) -> None:
        self.target(*self.args, **self.kwargs)


def signup(email: str) -> TestClient:
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "supersecret", "code": "TEST-CODE"},
    )
    assert response.status_code == 200, response.text
    return client


class GrsaiParseTests(unittest.TestCase):
    def test_plain_json(self) -> None:
        payload = parse_response('{"status":"succeeded","results":[{"url":"https://cdn.example/a.png"}]}')
        self.assertEqual(payload["status"], "succeeded")
        self.assertEqual(payload["results"][0]["url"], "https://cdn.example/a.png")

    def test_sse_uses_last_data_line(self) -> None:
        text = (
            "data: {\"status\":\"processing\"}\n"
            "data: {\"status\":\"succeeded\",\"results\":[{\"url\":\"https://cdn.example/b.png\"}]}\n"
            "data: [DONE]\n"
        )
        payload = parse_response(text)
        self.assertEqual(payload["status"], "succeeded")
        self.assertEqual(payload["results"][0]["url"], "https://cdn.example/b.png")

    def test_empty_is_an_error(self) -> None:
        with self.assertRaises(GrsaiError):
            parse_response("   ")


class ImageGenerateApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()

    def test_generate_needs_a_name(self) -> None:
        client = signup("img-empty@example.com")
        response = client.post("/api/v1/image-templates/generate", json={})
        self.assertEqual(response.status_code, 400)

    def test_generate_without_key_is_blocked(self) -> None:
        client = signup("img-nokey@example.com")
        with patch("server.routers.image_templates.api_key", return_value=""):
            response = client.post(
                "/api/v1/image-templates/generate",
                json={"product_name": "paint brush"},
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("出图服务", response.json()["detail"])

    def test_generate_job_is_tenant_scoped_and_serves_files(self) -> None:
        owner = signup("img-owner@example.com")
        other = signup("img-other@example.com")
        calls: list[tuple[str, tuple[str, ...]]] = []

        def fake_generate(prompt: str, *, urls=None, aspect_ratio="1:1"):
            calls.append((prompt[:40], tuple(urls or [])))
            return PNG, f"https://cdn.example/{len(calls)}.png"

        with (
            patch("server.services.grsai_images.generate_one", side_effect=fake_generate),
            patch("server.routers.image_templates.threading.Thread", ImmediateThread),
        ):
            started = owner.post(
                "/api/v1/image-templates/generate",
                json={
                    "product_name": "paint brush",
                    "category_id": "21111112",
                    "category_hint": "Tools & Hardware / 五金工具",
                },
            )
        self.assertEqual(started.status_code, 200, started.text)
        job = started.json()
        self.assertEqual(job["status"], "succeeded")
        self.assertEqual(job["category_id"], "21111112")
        self.assertEqual(job["done"], 6)
        self.assertEqual(len(job["slots"]), 6)
        self.assertTrue(all(slot["url"] for slot in job["slots"]))
        self.assertEqual(len(calls), 6)
        self.assertEqual(calls[0][1], ())
        self.assertEqual(calls[1][1], ("https://cdn.example/1.png",))

    def test_seller_reference_photo_is_sent_from_the_first_slot(self) -> None:
        owner = signup("img-ref@example.com")
        calls: list[tuple[str, ...]] = []

        def fake_generate(prompt: str, *, urls=None, aspect_ratio="1:1"):
            calls.append(tuple(urls or []))
            return PNG, f"https://cdn.example/{len(calls)}.png"

        with (
            patch("server.services.grsai_images.generate_one", side_effect=fake_generate),
            patch("server.routers.image_templates.threading.Thread", ImmediateThread),
        ):
            started = owner.post(
                "/api/v1/image-templates/generate",
                json={
                    "product_name": "油漆刷",
                    "reference_urls": ["https://cdn.example/brush.jpg", "not-a-url"],
                },
            )
        self.assertEqual(started.status_code, 200, started.text)
        self.assertEqual(started.json()["product_brief"], "wall paint brush")
        self.assertEqual(calls[0], ("https://cdn.example/brush.jpg",))
        self.assertEqual(calls[1], ("https://cdn.example/brush.jpg", "https://cdn.example/1.png"))

    def test_feed_from_generated_waits_until_done_and_marks_yellow(self) -> None:
        client = signup("img-feed@example.com")
        shop_id = client.post("/api/v1/shops/bind-env", json={"name": "生成图店"}).json()["id"]

        def fake_generate(prompt: str, *, urls=None, aspect_ratio="1:1"):
            return PNG, "https://cdn.example/main.png"

        with (
            patch("server.services.grsai_images.generate_one", side_effect=fake_generate),
            patch("server.routers.image_templates.threading.Thread", ImmediateThread),
        ):
            job = client.post(
                "/api/v1/image-templates/generate",
                json={"product_name": "paint brush"},
            ).json()

        too_soon = client.post(
            "/api/v1/listings/feed-from-generated",
            json={"shop_id": shop_id, "job_id": "missing", "price": "1.2", "moq": "100"},
        )
        self.assertEqual(too_soon.status_code, 404)

        def fake_build(db, user, shop, **kwargs):
            self.assertEqual(len(kwargs["uploads"]), 6)
            self.assertTrue(all(content == PNG for _, content in kwargs["uploads"]))
            self.assertIn("不是实拍", kwargs["note"])
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
                "/api/v1/listings/feed-from-generated",
                json={
                    "shop_id": shop_id,
                    "job_id": job["id"],
                    "price": "1.2",
                    "moq": "100",
                    "sku": "BR-1",
                },
            )
        self.assertEqual(created.status_code, 200, created.text)
        body = created.json()
        self.assertEqual(body["status"], "yellow")
        self.assertEqual(body["price"], "1.2")
        self.assertTrue(any("不是实拍" in item.get("message", "") for item in body["issues"]))

    def test_foreign_shop_cannot_eat_generated_images(self) -> None:
        owner = signup("img-shop-a@example.com")
        other = signup("img-shop-b@example.com")
        shop_id = owner.post("/api/v1/shops/bind-env", json={"name": "A"}).json()["id"]

        def fake_generate(prompt: str, *, urls=None, aspect_ratio="1:1"):
            return PNG, "https://cdn.example/main.png"

        with (
            patch("server.services.grsai_images.generate_one", side_effect=fake_generate),
            patch("server.routers.image_templates.threading.Thread", ImmediateThread),
        ):
            job_id = owner.post(
                "/api/v1/image-templates/generate",
                json={"product_name": "paint brush"},
            ).json()["id"]

        stolen = other.post(
            "/api/v1/listings/feed-from-generated",
            json={"shop_id": shop_id, "job_id": job_id, "price": "1", "moq": "10"},
        )
        self.assertEqual(stolen.status_code, 404)


class GrsaiClientTests(unittest.TestCase):
    def test_generate_one_downloads_the_result_url(self) -> None:
        from server.services import grsai_images

        class FakeResponse:
            def __init__(self, status_code: int, text: str = "", content: bytes = b""):
                self.status_code = status_code
                self.text = text
                self.content = content

        def fake_post(url, json=None, headers=None, timeout=None):
            self.assertIn("/v1/draw/completions", url)
            self.assertEqual(json["model"], "gpt-image-2")
            self.assertEqual(json["aspectRatio"], "1:1")
            self.assertTrue(json["shutProgress"])
            self.assertTrue(headers["Authorization"].startswith("Bearer "))
            return FakeResponse(
                200,
                '{"status":"succeeded","results":[{"url":"https://cdn.example/out.png"}]}',
            )

        def fake_get(url, timeout=None):
            self.assertEqual(url, "https://cdn.example/out.png")
            return FakeResponse(200, content=PNG)

        with (
            patch.object(grsai_images.requests, "post", side_effect=fake_post),
            patch.object(grsai_images.requests, "get", side_effect=fake_get),
        ):
            content, remote = grsai_images.generate_one("a white brush")
        self.assertEqual(content, PNG)
        self.assertEqual(remote, "https://cdn.example/out.png")

    def test_failed_status_becomes_chinese_error(self) -> None:
        from server.services import grsai_images

        class FakeResponse:
            status_code = 200
            text = '{"status":"failed","error":"quota exceeded"}'

        with patch.object(grsai_images.requests, "post", return_value=FakeResponse()):
            with self.assertRaises(GrsaiError) as ctx:
                grsai_images.generate_one("x")
        self.assertIn("额度", ctx.exception.message)

    def test_code_minus_one_insufficient_credits(self) -> None:
        from server.services import grsai_images

        class FakeResponse:
            status_code = 200
            text = '{"code":-1,"data":null,"msg":"insufficient credits"}'

        with patch.object(grsai_images.requests, "post", return_value=FakeResponse()):
            with self.assertRaises(GrsaiError) as ctx:
                grsai_images.generate_one("x")
        self.assertIn("额度", ctx.exception.message)
