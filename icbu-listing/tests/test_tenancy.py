"""One tenant must never see or touch another tenant's shops and drafts."""

import os
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

os.environ["DATABASE_PATH"] = str(Path(tempfile.mkdtemp()) / "tenancy.db")
os.environ["UPLOAD_DIR"] = str(Path(tempfile.mkdtemp()) / "uploads")
os.environ["TOKEN_ENCRYPTION_KEY"] = "Frqkv73e3W19RfKb5WSgTueumPWcBSmpbM4wDyqu52o="
os.environ["REGISTRATION_CODES"] = "TEST-CODE"
os.environ["ALIBABA_APP_KEY"] = "test-key"
os.environ["ALIBABA_APP_SECRET"] = "test-secret"
os.environ["ALIBABA_ACCESS_TOKEN"] = "test-token"
os.environ.pop("OPENAI_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

from server.db import init_db  # noqa: E402
from server.main import app  # noqa: E402


def _fill_sheet(template: bytes, rows: list[list[str]]) -> bytes:
    """Append real goods under the worked example, the way a seller does."""
    import io

    from openpyxl import load_workbook

    book = load_workbook(io.BytesIO(template))
    sheet = book["填写"]
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


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
        self.assertTrue(all(shop["bound_by"] == "debug" for shop in shops))
        # the raw token is never handed back to the browser
        self.assertNotIn("access_token", first.text)

    def test_oauth_start_uses_the_public_host_not_localhost(self) -> None:
        owner = signup("oauth-host@example.com")
        started = owner.get(
            "/api/v1/alibaba/oauth/start",
            headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "demo.trycloudflare.com"},
        )
        self.assertEqual(started.status_code, 200, started.text)
        body = started.json()
        self.assertEqual(body["redirect_uri"], "https://demo.trycloudflare.com/api/v1/alibaba/oauth/callback")
        self.assertIn("redirect_uri=https%3A%2F%2Fdemo.trycloudflare.com", body["url"])

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

    def test_catalogue_is_invisible_across_tenants(self) -> None:
        ivy = signup("ivy@example.com")
        jane = signup("jane@example.com")
        created = ivy.post(
            "/api/v1/products",
            data={"sku": "BRUSH-01", "price": "1.80", "moq": "500"},
            files={"files": ("brush.png", TINY_PNG, "image/png")},
        )
        self.assertEqual(created.status_code, 200, created.text)
        product_id = created.json()["id"]
        self.assertEqual(created.json()["sku"], "BRUSH-01")
        self.assertEqual(ivy.get("/api/v1/overview").json()["products"], 1)

        self.assertEqual(jane.get("/api/v1/products").json(), [])
        self.assertEqual(jane.get(f"/api/v1/products/{product_id}").status_code, 404)
        self.assertEqual(jane.delete(f"/api/v1/products/{product_id}").status_code, 404)
        self.assertEqual(len(ivy.get("/api/v1/products").json()), 1)

    def test_deleting_a_product_does_not_remove_its_drafts(self) -> None:
        kate = signup("kate@example.com")
        shop_id = kate.post("/api/v1/shops/bind-env", json={"name": "Kate"}).json()["id"]
        product_id = kate.post(
            "/api/v1/products",
            data={"sku": "KEEP-ME", "price": "2", "moq": "50"},
            files={"files": ("a.png", TINY_PNG, "image/png")},
        ).json()["id"]

        from server.db import SessionLocal
        from server.models import Draft, User

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.email == "kate@example.com").one()
            draft = Draft(
                user_id=user.id,
                shop_id=shop_id,
                product_id=product_id,
                sku="KEEP-ME",
                title="Existing draft",
                status="yellow",
            )
            db.add(draft)
            db.commit()
            draft_id = draft.id
        finally:
            db.close()

        self.assertEqual(kate.delete(f"/api/v1/products/{product_id}").status_code, 200)
        self.assertEqual(kate.get(f"/api/v1/products/{product_id}").status_code, 404)
        leftover = kate.get(f"/api/v1/drafts/{draft_id}")
        self.assertEqual(leftover.status_code, 200, leftover.text)
        self.assertEqual(leftover.json()["sku"], "KEEP-ME")

    def test_distribute_is_a_cartesian_product(self) -> None:
        leo = signup("leo@example.com")
        shop_a = leo.post("/api/v1/shops/bind-env", json={"name": "A 店"}).json()["id"]
        shop_b = leo.post("/api/v1/shops/bind-env", json={"name": "B 店"}).json()["id"]
        first = leo.post(
            "/api/v1/products",
            data={"sku": "P1", "price": "1", "moq": "10"},
            files={"files": ("p1.png", TINY_PNG, "image/png")},
        ).json()["id"]
        second = leo.post(
            "/api/v1/products",
            data={"sku": "P2", "price": "2", "moq": "20"},
            files={"files": ("p2.png", TINY_PNG, "image/png")},
        ).json()["id"]

        from server.models import Draft
        from server.routers import products as products_router
        from server.services import distribution

        created: list[tuple[str, str, str]] = []

        def fake_build(db, user, shop, product, **kwargs):
            draft = Draft(
                user_id=user.id,
                shop_id=shop.id,
                product_id=product.id,
                sku=product.sku,
                title=f"{product.sku} for {shop.name}",
                status="yellow",
                batch_id=kwargs.get("batch_id") or "",
            )
            db.add(draft)
            db.commit()
            created.append((product.id, shop.id, kwargs.get("angle") or ""))
            return draft

        with unittest.mock.patch("server.routers.products.threading.Thread"):
            queued = leo.post(
                "/api/v1/products/distribute",
                json={"product_ids": [first, second], "shop_ids": [shop_a, shop_b], "differentiate": True},
            )
        self.assertEqual(queued.status_code, 200, queued.text)
        self.assertEqual(queued.json()["count"], 4)
        self.assertEqual(queued.json()["products"], 2)
        self.assertEqual(queued.json()["shops"], 2)

        with unittest.mock.patch.object(distribution, "build_draft_for_shop", side_effect=fake_build):
            products_router._run_distribute(
                _user_id("leo@example.com"),
                queued.json()["batch_id"],
                [(first, shop_a), (first, shop_b), (second, shop_a), (second, shop_b)],
                None,
                None,
                True,
            )

        self.assertEqual(len(created), 4)
        first_angles = [angle for product_id, _shop, angle in created if product_id == first]
        self.assertEqual(first_angles[0], "")
        self.assertTrue(first_angles[1])
        self.assertNotEqual(first_angles[0], first_angles[1])

        drafts = leo.get("/api/v1/drafts").json()
        self.assertEqual(len(drafts), 4)
        self.assertEqual({item["shop_name"] for item in drafts}, {"A 店", "B 店"})
        only_a = leo.get("/api/v1/drafts", params={"shop_id": shop_a}).json()
        self.assertEqual(len(only_a), 2)
        self.assertTrue(all(item["shop_id"] == shop_a for item in only_a))

    def test_excel_endpoints_are_tenant_scoped(self) -> None:
        pat = signup("pat@example.com")
        quin = signup("quin@example.com")
        self.assertEqual(pat.get("/api/v1/excel/styles").status_code, 200)
        template = pat.get("/api/v1/excel/template", params={"style": "lingxing"})
        self.assertEqual(template.status_code, 200, template.text)
        self.assertIn("spreadsheet", template.headers.get("content-type", ""))

        filled = _fill_sheet(template.content, [["A-01", "毛笔", "2.30", "300", "A-01_1.jpg"]])
        preview = pat.post(
            "/api/v1/excel/preview",
            data={"style": "lingxing"},
            files={"file": ("goods.xlsx", filled, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual(preview.json()["row_count"], 1)

        untouched = pat.post(
            "/api/v1/excel/import",
            data={"style": "lingxing", "mapping": "{}", "create_drafts": "false"},
            files={"file": ("goods.xlsx", template.content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        self.assertEqual(untouched.status_code, 400)
        self.assertIn("示例", untouched.json()["detail"])

        with unittest.mock.patch("server.routers.excel.threading.Thread"):
            imported = pat.post(
                "/api/v1/excel/import",
                data={"style": "lingxing", "mapping": "{}", "create_drafts": "false"},
                files={"file": ("goods.xlsx", filled, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        self.assertEqual(imported.status_code, 200, imported.text)
        self.assertEqual(imported.json()["count"], preview.json()["row_count"])

        foreign = quin.get(
            "/api/v1/excel/template",
            params={"style": "dianxiaomi", "listing_template_id": "not-yours"},
        )
        self.assertEqual(foreign.status_code, 404)

    def test_template_is_shop_scoped_and_isolated(self) -> None:
        mia = signup("mia@example.com")
        ned = signup("ned@example.com")
        shop_id = mia.post("/api/v1/shops/bind-env", json={"name": "Mia"}).json()["id"]
        created = mia.post(
            "/api/v1/templates",
            json={
                "shop_id": shop_id,
                "name": "油漆刷默认",
                "category_id": "21111112",
                "values": {"origin": "Vietnam", "productTitle": "should-be-ignored"},
            },
        )
        self.assertEqual(created.status_code, 200, created.text)
        template_id = created.json()["id"]
        self.assertEqual(ned.get("/api/v1/templates").json(), [])
        self.assertEqual(ned.delete(f"/api/v1/templates/{template_id}").status_code, 404)
        self.assertEqual(len(mia.get("/api/v1/templates", params={"shop_id": shop_id}).json()), 1)


def _user_id(email: str) -> str:
    from server.db import SessionLocal
    from server.models import User

    db = SessionLocal()
    try:
        return db.query(User).filter(User.email == email).one().id
    finally:
        db.close()


TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05"
    b"\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


if __name__ == "__main__":
    unittest.main()
