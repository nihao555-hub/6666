"""Smart batch plan: sufficient evidence columns; AI infers remaining required + score."""

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
from server.services import review_enrich, smart_plan  # noqa: E402


def signup(tag: str = "user") -> TestClient:
    client = TestClient(app)
    email = f"{tag}-{uuid.uuid4().hex[:10]}@example.com"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "supersecret", "code": "TEST-CODE"},
    )
    assert response.status_code == 200, response.text
    return client


def _pencil_candidates() -> list[dict]:
    return [
        smart_plan._core_column("sku"),
        smart_plan._core_column("price"),
        smart_plan._core_column("moq"),
        smart_plan._core_column("name"),
        smart_plan._core_column("note"),
        smart_plan._core_column("images"),
        {
            "id": "attr.icbuCatProp.p-15",
            "label": "材质",
            "required": True,
            "source": "schema_required",
        },
        {
            "id": "attr.icbuCatProp.p-2",
            "label": "铅芯硬度",
            "required": True,
            "source": "schema_required",
        },
        {
            "id": "attr.icbuCatProp.p-9",
            "label": "铅芯颜色",
            "required": True,
            "source": "schema_required",
        },
        {
            "id": "attr.saleProp.s-1",
            "label": "色数",
            "required": True,
            "source": "schema_required",
        },
        {
            "id": "schema.paymentMethod",
            "label": "付款方式",
            "required": False,
            "source": "schema_score",
        },
    ]


class SmartPlanUnitTests(unittest.TestCase):
    def test_rule_based_includes_sufficient_evidence_attrs(self) -> None:
        candidates = _pencil_candidates()
        chosen = smart_plan._rule_based_user_columns(candidates)
        self.assertIn("sku", chosen)
        self.assertIn("attr.icbuCatProp.p-15", chosen)
        self.assertIn("attr.saleProp.s-1", chosen)
        self.assertNotIn("schema.paymentMethod", chosen)
        attr_cols = [fid for fid in chosen if fid.startswith("attr.")]
        self.assertGreaterEqual(len(attr_cols), 2)
        self.assertLessEqual(len(attr_cols), smart_plan.MAX_USER_MUST_PROVIDE_ATTRS)

    def test_sanitize_strips_score_columns_from_llm(self) -> None:
        candidates = _pencil_candidates()
        sanitized = smart_plan._sanitize_user_column_ids(
            candidates,
            ["sku", "price", "moq", "schema.paymentMethod", "attr.icbuCatProp.p-15"],
        )
        self.assertIn("attr.icbuCatProp.p-15", sanitized)
        self.assertNotIn("schema.paymentMethod", sanitized)

    def test_ai_target_includes_off_sheet_required_and_score(self) -> None:
        candidates = _pencil_candidates()
        user_ids = set(smart_plan._rule_based_user_columns(candidates))
        targets = review_enrich.ai_target_columns(candidates, user_ids)
        ids = {item["id"] for item in targets}
        # Required attrs on the download sheet are excluded from AI infer targets.
        for fid in user_ids:
            if fid.startswith("attr."):
                self.assertNotIn(fid, ids)
        self.assertIn("schema.paymentMethod", ids)

    def test_is_core_only_plan_detects_stale_cache(self) -> None:
        core_plan = {
            "columns": [smart_plan._core_column(fid) for fid in ("sku", "price", "moq", "images", "brand", "name", "note")],
        }
        self.assertTrue(smart_plan._is_core_only_plan(core_plan))
        core_plan["columns"].append({"id": "attr.icbuCatProp.p-15", "label": "材质"})
        self.assertFalse(smart_plan._is_core_only_plan(core_plan))

    def test_llm_memory_columns_include_all_required_off_sheet(self) -> None:
        from schema import parse_schema  # noqa: E402

        fields = parse_schema(
            """<?xml version="1.0"?><itemSchema>
              <field id="icbuCatProp" type="complex"><fields>
                <field id="p-15" name="Material" type="singleCheck"><rules><rule name="requiredRule" value="true"/></rules></field>
                <field id="p-2" name="Hardness" type="singleCheck"><rules><rule name="requiredRule" value="true"/></rules></field>
              </fields></field>
              <field id="saleProp" type="complex"><fields>
                <field id="s-1" name="Colors" type="singleCheck"><rules><rule name="requiredRule" value="true"/></rules>
                  <options><option displayName="12" value="12"/></options>
                </field>
              </fields></field>
              <field id="paymentMethod" type="multiCheck">
                <options><option displayName="T/T" value="T/T"/></options>
              </field>
            </itemSchema>"""
        )
        user_ids = {"sku", "price", "moq", "attr.icbuCatProp.p-15"}
        targets = smart_plan.llm_memory_columns(fields, user_ids)
        ids = {item["id"] for item in targets}
        self.assertIn("attr.icbuCatProp.p-2", ids)
        self.assertIn("attr.saleProp.s-1", ids)
        self.assertIn("schema.paymentMethod", ids)
        self.assertNotIn("attr.icbuCatProp.p-15", ids)
        self.assertTrue(all(item.get("llm_memory") for item in targets))

    def test_finalize_restores_anchors_when_llm_omits(self) -> None:
        candidates = _pencil_candidates()
        finalized = smart_plan._finalize_user_columns(candidates, ["sku", "price", "moq"])
        self.assertIn("name", finalized)
        self.assertIn("note", finalized)
        self.assertTrue(any(fid.startswith("attr.") for fid in finalized))

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

    def test_template_covered_required_attrs_stay_in_candidates(self) -> None:
        from schema import parse_schema  # noqa: E402

        fields = parse_schema(
            """<?xml version="1.0"?><itemSchema>
              <field id="icbuCatProp" type="complex"><fields>
                <field id="p-15" name="Material" type="singleCheck"><rules><rule name="requiredRule" value="true"/></rules></field>
              </fields></field>
            </itemSchema>"""
        )
        template = {"icbuCatProp": {"p-15": "Wood"}}
        candidates, _covered_shop, covered_template = smart_plan.candidate_columns(
            fields,
            shop_defaults={},
            template_values=template,
        )
        ids = [col["id"] for col in candidates]
        self.assertIn("attr.icbuCatProp.p-15", ids)
        self.assertTrue(any("Material" in item for item in covered_template))
        chosen = smart_plan._rule_based_user_columns(candidates)
        self.assertIn("attr.icbuCatProp.p-15", chosen)
        self.assertFalse(smart_plan._is_core_only_plan({"columns": smart_plan.columns_for_ids(candidates, chosen)}))


if __name__ == "__main__":
    unittest.main()
