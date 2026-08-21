"""AI-filled drafts cannot publish until a person reviews them."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

os.environ["DATABASE_PATH"] = str(Path(tempfile.mkdtemp()) / "audit.db")
os.environ["UPLOAD_DIR"] = str(Path(tempfile.mkdtemp()) / "uploads")
os.environ["TOKEN_ENCRYPTION_KEY"] = "Frqkv73e3W19RfKb5WSgTueumPWcBSmpbM4wDyqu52o="
os.environ["REGISTRATION_CODES"] = "TEST-CODE"
os.environ["ALIBABA_APP_KEY"] = "test-key"
os.environ["ALIBABA_APP_SECRET"] = "test-secret"
os.environ["ALIBABA_ACCESS_TOKEN"] = "test-token"
os.environ.pop("OPENAI_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

from server.db import SessionLocal, init_db  # noqa: E402
from server.main import app  # noqa: E402
from server.models import Draft, Shop  # noqa: E402
from server.services import audit  # noqa: E402


SCHEMA = """
<schema>
  <field id="productTitle" name="Title" type="input">
    <rules><rule name="requiredRule" value="true"/></rules>
  </field>
  <field id="icbuCatProp" name="Category properties" type="complex"><fields>
    <field id="p-color" name="铅芯颜色" type="singleCheck">
      <rules><rule name="requiredRule" value="true"/></rules>
      <options>
        <option displayName="Colored" value="colored"/>
        <option displayName="Other" value="other"/>
      </options>
    </field>
    <field id="@origin" name="原产地" type="singleCheck">
      <options><option displayName="China" value="CN"/></options>
    </field>
  </fields></field>
  <field id="saleProp" name="Sale properties" type="complex"><fields>
    <field id="p-hard" name="铅芯硬度" type="singleCheck">
      <rules><rule name="requiredRule" value="true"/></rules>
      <options>
        <option displayName="HB" value="hb"/>
        <option displayName="2B" value="2b"/>
      </options>
    </field>
  </fields></field>
  <field id="brand" name="品牌" type="input"/>
</schema>
"""


def signup(email: str) -> TestClient:
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "supersecret", "code": "TEST-CODE"},
    )
    assert response.status_code == 200, response.text
    return client


class AuditGateTests(unittest.TestCase):
    def test_unreviewed_green_cannot_publish(self) -> None:
        draft = SimpleNamespace(status="green", issues_json="[]", reviewed_at=None)
        ok, reason = audit.can_publish(draft)
        self.assertFalse(ok)
        self.assertIn("核对", reason)

    def test_red_still_blocks_after_review(self) -> None:
        draft = SimpleNamespace(
            status="red",
            issues_json='[{"level":"red","message":"缺属性"}]',
            reviewed_at=datetime.utcnow(),
        )
        ok, reason = audit.can_publish(draft)
        self.assertFalse(ok)
        self.assertIn("红项", reason)

    def test_reviewed_yellow_can_publish_when_quality_is_five(self) -> None:
        draft = SimpleNamespace(
            status="yellow",
            issues_json='[{"level":"yellow","message":"生成图"}]',
            reviewed_at=datetime.utcnow(),
            ai_json='{"quality": {"score": 5.0, "ready": true, "missing": []}}',
        )
        ok, reason = audit.can_publish(draft)
        self.assertTrue(ok)
        self.assertEqual(reason, "")

    def test_reviewed_yellow_blocked_when_quality_below_five(self) -> None:
        draft = SimpleNamespace(
            status="yellow",
            issues_json='[{"level":"yellow","message":"生成图"}]',
            reviewed_at=datetime.utcnow(),
            ai_json='{"quality": {"score": 4.2, "ready": false, "missing": ["实拍图至少 3 张"]}}',
        )
        ok, reason = audit.can_publish(draft)
        self.assertFalse(ok)
        self.assertIn("4.2", reason)

    def test_mark_and_clear_review(self) -> None:
        draft = SimpleNamespace(reviewed_at=None, audit_json="{}")
        audit.mark_reviewed(draft, "颜色改过")
        self.assertTrue(audit.is_reviewed(draft))
        self.assertEqual(audit.view(draft)["note"], "颜色改过")
        audit.clear_review(draft, "category")
        self.assertFalse(audit.is_reviewed(draft))
        self.assertEqual(audit.view(draft)["cleared_reason"], "category")

    def test_form_exposes_ai_copy_and_official_attrs(self) -> None:
        fields = audit.form_fields(
            SCHEMA,
            {
                "productTitle": "Colored Pencil",
                "productKeywords": {"productKeywords_0": "pencil"},
                "textDesc": "school set",
                "icbuCatProp": {"p-color": "colored", "@origin": "CN"},
                "saleProp": {"p-hard": "hb"},
                "brand": "",
            },
            {"productTitle": "ai", "icbuCatProp": "ai", "saleProp": "ai", "brand": "shop"},
        )
        by_id = {item["id"]: item for item in fields}
        self.assertEqual(by_id["productTitle"]["source"]["label"], "AI")
        self.assertEqual(by_id["p-color"]["name"], "铅芯颜色")
        self.assertTrue(by_id["p-color"]["required"])
        self.assertEqual(by_id["p-color"]["value"], "colored")
        self.assertEqual(by_id["p-hard"]["group"], "saleProp")
        self.assertEqual(by_id["brand"]["source"]["label"], "店铺默认")
        labels = {option["label"] for option in by_id["p-hard"]["options"]}
        self.assertIn("HB", labels)


class AuditApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()

    def test_publish_is_blocked_until_reviewed(self) -> None:
        client = signup("audit-seller@example.com")
        bound = client.post("/api/v1/shops/bind-env", json={"name": "审计店"})
        self.assertEqual(bound.status_code, 200, bound.text)
        shop_id = bound.json()["id"]

        db = SessionLocal()
        try:
            shop = db.get(Shop, shop_id)
            draft = Draft(
                user_id=shop.user_id,
                shop_id=shop.id,
                sku="AUDIT-1",
                title="AI Title",
                price="1.2",
                moq="100",
                status="green",
                values_json='{"productTitle":"AI Title"}',
                issues_json="[]",
            )
            db.add(draft)
            db.commit()
            draft_id = draft.id
        finally:
            db.close()

        listed = client.get("/api/v1/drafts").json()
        self.assertTrue(listed)
        self.assertFalse(listed[0]["reviewed"])

        blocked = client.post(f"/api/v1/drafts/{draft_id}/publish")
        self.assertEqual(blocked.status_code, 400)
        self.assertIn("核对", blocked.json()["detail"])

        batch = client.post("/api/v1/drafts/publish", json={"draft_ids": [draft_id]})
        self.assertEqual(batch.status_code, 400)

        saved = client.patch(
            f"/api/v1/drafts/{draft_id}",
            json={"values": {"productTitle": "Hand Fixed Title"}, "reviewed": True, "audit_note": "标题改过"},
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        body = saved.json()
        self.assertTrue(body["reviewed"])
        self.assertEqual(body["audit"]["note"], "标题改过")
        self.assertEqual(body["title"], "Hand Fixed Title")
        self.assertEqual(body["sources"]["productTitle"]["origin"], "user")

        overview = client.get("/api/v1/overview").json()
        self.assertGreaterEqual(overview["ready"], 1)
        self.assertEqual(overview["unaudited"], 0)


if __name__ == "__main__":
    unittest.main()
