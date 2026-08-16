"""One tenant must never see or touch another tenant's shops and drafts."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

os.environ["DATABASE_PATH"] = str(Path(tempfile.mkdtemp()) / "tenancy.db")
os.environ["TOKEN_ENCRYPTION_KEY"] = "Frqkv73e3W19RfKb5WSgTueumPWcBSmpbM4wDyqu52o="
os.environ["REGISTRATION_CODES"] = "TEST-CODE"
os.environ["ALIBABA_APP_KEY"] = "test-key"
os.environ["ALIBABA_APP_SECRET"] = "test-secret"
os.environ["ALIBABA_ACCESS_TOKEN"] = "test-token"
os.environ.pop("OPENAI_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

from server.db import init_db  # noqa: E402
from server.main import app  # noqa: E402


def signup(email: str) -> TestClient:
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "supersecret", "code": "TEST-CODE"},
    )
    assert response.status_code == 200, response.text
    return client


class TenancyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()

    def test_registration_code_is_enforced(self) -> None:
        client = TestClient(app)
        response = client.post(
            "/api/v1/auth/register",
            json={"email": "nope@example.com", "password": "supersecret", "code": "WRONG"},
        )
        self.assertEqual(response.status_code, 400)

    def test_anonymous_cannot_reach_the_api(self) -> None:
        client = TestClient(app)
        self.assertEqual(client.get("/api/v1/shops").status_code, 401)
        self.assertEqual(client.get("/api/v1/alibaba/oauth/start").status_code, 401)
        self.assertEqual(client.get("/api/v1/drafts").status_code, 401)

    def test_one_tenant_can_bind_several_shops(self) -> None:
        alice = signup("alice@example.com")
        first = alice.post("/api/v1/shops/bind-env", json={"name": "工厂店"})
        second = alice.post("/api/v1/shops/bind-env", json={"name": "贸易店"})
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)

        shops = alice.get("/api/v1/shops").json()
        self.assertEqual([shop["name"] for shop in shops], ["工厂店", "贸易店"])
        self.assertTrue(all(shop["connected"] for shop in shops))
        # the raw token is never handed back to the browser
        self.assertNotIn("access_token", first.text)

    def test_shops_are_invisible_across_tenants(self) -> None:
        bob = signup("bob@example.com")
        carol = signup("carol@example.com")
        shop_id = bob.post("/api/v1/shops/bind-env", json={"name": "Bob 的店"}).json()["id"]

        self.assertEqual(carol.get("/api/v1/shops").json(), [])
        self.assertEqual(carol.get(f"/api/v1/shops/{shop_id}/online").status_code, 404)
        self.assertEqual(carol.get(f"/api/v1/shops/{shop_id}/photobank").status_code, 404)
        self.assertEqual(carol.delete(f"/api/v1/shops/{shop_id}").status_code, 404)
        self.assertEqual(
            carol.post(f"/api/v1/shops/{shop_id}/defaults", json={"defaults": {"origin": "Vietnam"}}).status_code,
            404,
        )
        # bob still has his shop
        self.assertEqual(len(bob.get("/api/v1/shops").json()), 1)

    def test_defaults_round_trip(self) -> None:
        dave = signup("dave@example.com")
        shop_id = dave.post("/api/v1/shops/bind-env", json={"name": "Dave"}).json()["id"]
        saved = dave.post(
            f"/api/v1/shops/{shop_id}/defaults",
            json={"defaults": {"origin": "Vietnam", "priceUnit": "Set/Sets"}, "publish_mode": "online"},
        ).json()
        self.assertEqual(saved["defaults"]["origin"], "Vietnam")
        self.assertEqual(saved["defaults"]["marketSample"], "Unavailable")  # untouched default survives
        self.assertEqual(saved["publish_mode"], "online")

    def test_feed_requires_an_image(self) -> None:
        erin = signup("erin@example.com")
        shop_id = erin.post("/api/v1/shops/bind-env", json={"name": "Erin"}).json()["id"]
        response = erin.post("/api/v1/listings/feed", data={"shop_id": shop_id, "price": "1", "moq": "10"})
        self.assertEqual(response.status_code, 400)

    def test_feed_rejects_a_foreign_shop(self) -> None:
        frank = signup("frank@example.com")
        grace = signup("grace@example.com")
        shop_id = frank.post("/api/v1/shops/bind-env", json={"name": "Frank"}).json()["id"]
        response = grace.post(
            "/api/v1/listings/feed",
            data={"shop_id": shop_id},
            files={"files": ("a.png", b"not-a-real-image", "image/png")},
        )
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
