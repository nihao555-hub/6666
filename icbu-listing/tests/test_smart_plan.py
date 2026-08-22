"""Smart batch plan: minimal user columns from schema + shop/template coverage."""

import json
import os
import sys
import tempfile
import unittest
import unittest.mock
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

os.environ["DATABASE_PATH"] = str(Path(tempfile.mkdtemp()) / "smart-plan.db")
os.environ["UPLOAD_DIR"] = str(Path(tempfile.mkdtemp()) / "uploads")
os.environ["TOKEN_ENCRYPTION_KEY"] = "Frqkv73e3W19RfKb5WSgTueumPWcBSmpbM4wDyqu52o="
os.environ["REGISTRATION_CODES"] = "TEST-CODE"
os.environ["ALIBABA_APP_KEY"] = "test-key"
os.environ["ALIBABA_APP_SECRET"] = "test-secret"
os.environ.pop("OPENAI_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

from server.db import init_db  # noqa: E402
from server.main import app  # noqa: E402
from server.services import smart_plan  # noqa: E402


def signup(tag: str = "user") -> TestClient:
    client = TestClient(app)
    email = f"{tag}-{uuid.uuid4().hex[:10]}@example.com"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "supersecret", "code": "TEST-CODE"},
    )
    assert response.status_code == 200, response.text
    return client


class SmartPlanUnitTests(unittest.TestCase):
    def test_rule_based_always_includes_core(self) -> None:
        candidates = [
            smart_plan._core_column("sku"),
            smart_plan._core_column("price"),
            smart_plan._core_column("moq"),
            smart_plan._core_column("name"),
            {
                "id": "attr.icbuCatProp.p-2",
                "label": "铅芯硬度",
                "required": True,
                "source": "schema_required",
            },
        ]
        chosen = smart_plan._rule_based_user_columns(candidates)
        self.assertEqual(chosen[:3], ["sku", "price", "moq"])
        self.assertIn("attr.icbuCatProp.p-2", chosen)

    def test_finalize_restores_required_when_llm_omits(self) -> None:
        candidates = [
            smart_plan._core_column("sku"),
            smart_plan._core_column("price"),
            smart_plan._core_column("moq"),
            smart_plan._core_column("name"),
            smart_plan._core_column("note"),
            {
                "id": "attr.icbuCatProp.p-2",
                "label": "铅芯硬度",
                "required": True,
                "source": "schema_required",
            },
        ]
        llm_minimal = ["sku", "price", "moq"]
        finalized = smart_plan._finalize_user_columns(candidates, llm_minimal)
        self.assertIn("name", finalized)
        self.assertIn("note", finalized)
        self.assertIn("attr.icbuCatProp.p-2", finalized)

    def test_build_smart_template_bytes(self) -> None:
        plan = {
            "category_id": "21110712",
            "category_name": "彩铅",
            "columns": [
                smart_plan._core_column("sku"),
                smart_plan._core_column("price"),
                smart_plan._core_column("moq"),
            ],
            "reasoning": "测试",
            "tips": "一行一个 SKU",
            "covered_by_shop": ["产地"],
            "covered_by_template": [],
            "ai_fills": [{"id": "productTitle", "label": "英文标题"}],
        }
        payload = smart_plan.build_smart_template_bytes(plan)
        self.assertTrue(payload.startswith(b"PK"))


class SmartPlanCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()

    def test_build_plan_uses_cache_without_second_llm_call(self) -> None:
        from server.db import SessionLocal  # noqa: E402
        from server.models import Shop, User  # noqa: E402

        db = SessionLocal()
        user = User(email=f"cache-{uuid.uuid4().hex[:8]}@example.com", password_hash="x")
        db.add(user)
        db.commit()
        shop = Shop(user_id=user.id, name="缓存店", platform="alibaba_icbu")
        db.add(shop)
        db.commit()
        calls = {"n": 0}

        def fake_llm(*_args, **_kwargs):
            calls["n"] += 1
            return (["sku", "price", "moq", "name"], "测试规划", "一行一个 SKU")

        with unittest.mock.patch(
            "server.services.smart_plan.catalog.get_schema_xml",
            return_value="<fields></fields>",
        ), unittest.mock.patch(
            "server.services.smart_plan.parse_schema",
            return_value=[],
        ), unittest.mock.patch.object(smart_plan, "_llm_user_columns", side_effect=fake_llm):
            first = smart_plan.build_plan(db, object(), shop, category_id="21110712", category_name="彩铅", ai=object())
            second = smart_plan.build_plan(db, object(), shop, category_id="21110712", category_name="彩铅", ai=object())
        self.assertFalse(first.get("cached"))
        self.assertTrue(second.get("cached"))
        self.assertEqual(calls["n"], 1)
        db.close()

    def test_build_plan_skips_schema_on_fast_cache_hit(self) -> None:
        from server.db import SessionLocal  # noqa: E402
        from server.models import Shop, User  # noqa: E402

        db = SessionLocal()
        user = User(email=f"fast-{uuid.uuid4().hex[:8]}@example.com", password_hash="x")
        db.add(user)
        db.commit()
        shop = Shop(user_id=user.id, name="极速店", platform="alibaba_icbu")
        db.add(shop)
        db.commit()
        schema_calls = {"n": 0}

        def counting_schema(*_args, **_kwargs):
            schema_calls["n"] += 1
            return "<fields></fields>"

        with unittest.mock.patch(
            "server.services.smart_plan.catalog.get_schema_xml",
            side_effect=counting_schema,
        ), unittest.mock.patch(
            "server.services.smart_plan.parse_schema",
            return_value=[],
        ), unittest.mock.patch.object(
            smart_plan,
            "_llm_user_columns",
            return_value=(["sku", "price", "moq", "name", "note"], "测试", "准备报价单"),
        ):
            smart_plan.build_plan(db, object(), shop, category_id="21110712", category_name="彩铅", ai=object())
            smart_plan.build_plan(db, object(), shop, category_id="21110712", category_name="彩铅", ai=object())
        self.assertEqual(schema_calls["n"], 1)
        db.close()

    def test_refresh_bypasses_cache(self) -> None:
        from server.db import SessionLocal  # noqa: E402
        from server.models import Shop, User  # noqa: E402

        db = SessionLocal()
        user = User(email=f"refresh-{uuid.uuid4().hex[:8]}@example.com", password_hash="x")
        db.add(user)
        db.commit()
        shop = Shop(user_id=user.id, name="刷新店", platform="alibaba_icbu")
        db.add(shop)
        db.commit()
        calls = {"n": 0}

        def fake_llm(*_args, **_kwargs):
            calls["n"] += 1
            return (["sku", "price", "moq"], "再次规划", "准备报价单")

        with unittest.mock.patch(
            "server.services.smart_plan.catalog.get_schema_xml",
            return_value="<fields></fields>",
        ), unittest.mock.patch(
            "server.services.smart_plan.parse_schema",
            return_value=[],
        ), unittest.mock.patch.object(smart_plan, "_llm_user_columns", side_effect=fake_llm):
            smart_plan.build_plan(db, object(), shop, category_id="21110712", ai=object())
            smart_plan.build_plan(db, object(), shop, category_id="21110712", ai=object(), refresh=True)
        self.assertEqual(calls["n"], 2)
        db.close()


class SmartPlanApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()

    def test_smart_plan_requires_category(self) -> None:
        client = signup("smart-req")
        shop_id = client.post("/api/v1/shops/bind-env", json={"name": "智能店"}).json()["id"]
        missing = client.get("/api/v1/excel/smart-plan", params={"shop_id": shop_id})
        self.assertEqual(missing.status_code, 400)

    def test_smart_plan_with_mock_schema(self) -> None:
        client = signup("smart-plan")
        shop_id = client.post("/api/v1/shops/bind-env", json={"name": "智能店2"}).json()["id"]
        with unittest.mock.patch(
            "server.services.smart_plan.catalog.get_schema_xml",
            return_value="<fields></fields>",
        ), unittest.mock.patch(
            "server.services.smart_plan.parse_schema",
            return_value=[],
        ):
            response = client.get(
                "/api/v1/excel/smart-plan",
                params={"shop_id": shop_id, "category_id": "21110712", "category_name": "彩铅"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        plan = response.json()
        self.assertEqual(plan["category_id"], "21110712")
        self.assertGreaterEqual(plan["column_count"], 3)
        ids = [col["id"] for col in plan["columns"]]
        self.assertIn("sku", ids)
        self.assertIn("price", ids)
        self.assertIn("moq", ids)
        self.assertGreaterEqual(len(plan.get("review_checklist") or []), 4)
        self.assertEqual(plan.get("publishing_skill"), "aidi1723/alibaba-icbu-publishing-skill")

    def test_smart_template_from_plan_download(self) -> None:
        client = signup("smart-plan-xlsx")
        shop_id = client.post("/api/v1/shops/bind-env", json={"name": "智能店4"}).json()["id"]
        response = client.post(
            "/api/v1/excel/smart-template-from-plan",
            json={
                "shop_id": shop_id,
                "category_id": "21110712",
                "category_name": "彩铅",
                "columns": [
                    smart_plan._core_column("sku"),
                    smart_plan._core_column("price"),
                    smart_plan._core_column("moq"),
                ],
                "reasoning": "测试",
                "tips": "一行一个 SKU",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("spreadsheetml", response.headers.get("content-type", ""))
        self.assertTrue(response.content.startswith(b"PK"))

    def test_smart_template_download(self) -> None:
        client = signup("smart-xlsx")
        shop_id = client.post("/api/v1/shops/bind-env", json={"name": "智能店3"}).json()["id"]
        with unittest.mock.patch(
            "server.services.smart_plan.catalog.get_schema_xml",
            return_value="<fields></fields>",
        ), unittest.mock.patch(
            "server.services.smart_plan.parse_schema",
            return_value=[],
        ):
            response = client.get(
                "/api/v1/excel/smart-template",
                params={"shop_id": shop_id, "category_id": "21110712", "category_name": "彩铅"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("spreadsheetml", response.headers.get("content-type", ""))
        self.assertTrue(response.content.startswith(b"PK"))


if __name__ == "__main__":
    unittest.main()
