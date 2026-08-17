"""Fill sheet is a family short form; official attrs come from schema.get later."""

import os
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

os.environ["DATABASE_PATH"] = str(Path(tempfile.mkdtemp()) / "sheet-plan.db")
os.environ["UPLOAD_DIR"] = str(Path(tempfile.mkdtemp()) / "uploads")
os.environ["TOKEN_ENCRYPTION_KEY"] = "Frqkv73e3W19RfKb5WSgTueumPWcBSmpbM4wDyqu52o="
os.environ["REGISTRATION_CODES"] = "TEST-CODE"
os.environ["ALIBABA_APP_KEY"] = "test-key"
os.environ["ALIBABA_APP_SECRET"] = "test-secret"
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


class SheetPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()

    def test_sheet_plan_follows_family_not_7521_official_forms(self) -> None:
        client = signup("sheet-plan@example.com")
        pencils = client.get(
            "/api/v1/excel/sheet-plan",
            params={"category_name": "Office & School Supplies / Colored Pencils"},
        )
        brushes = client.get(
            "/api/v1/excel/sheet-plan",
            params={"category_name": "Tools & Hardware / Paint Brushes"},
        )
        other = client.get(
            "/api/v1/excel/sheet-plan",
            params={"category_name": "Office & School Supplies / Other"},
        )
        self.assertEqual(pencils.status_code, 200, pencils.text)
        self.assertEqual(brushes.status_code, 200, brushes.text)
        self.assertEqual(other.status_code, 200, other.text)
        pencil_plan = pencils.json()
        brush_plan = brushes.json()
        other_plan = other.json()
        self.assertEqual(pencil_plan["sheet"]["family_id"], "stationery")
        self.assertEqual(brush_plan["sheet"]["family_id"], "tools")
        self.assertEqual(other_plan["sheet"]["family_id"], "stationery")
        self.assertFalse(pencil_plan["from_official_form"])
        pencil_cols = [item["label"] for item in pencil_plan["preview"]["columns"]]
        brush_cols = [item["label"] for item in brush_plan["preview"]["columns"]]
        self.assertIn("色数", pencil_cols)
        self.assertIn("硬度", pencil_cols)
        self.assertNotIn("色数", brush_cols)
        self.assertIn("尺寸", brush_cols)
        self.assertIn("材质", brush_cols)
        self.assertNotEqual(pencil_cols, brush_cols)
        self.assertLess(len(pencil_cols), 20)

    def test_official_attrs_are_a_separate_leaf_call(self) -> None:
        client = signup("official-attrs@example.com")
        shop_id = client.post("/api/v1/shops/bind-env", json={"name": "官方属性店"}).json()["id"]
        with unittest.mock.patch("server.routers.excel._attr_columns", return_value=[
            {"id": "leadHardness", "header": "Lead Hardness", "name": "Lead Hardness"}
        ]) as mocked:
            response = client.get(
                "/api/v1/excel/official-attrs",
                params={"shop_id": shop_id, "category_id": "123"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["category_id"], "123")
        self.assertEqual(payload["ai_attrs"][0]["header"], "Lead Hardness")
        self.assertTrue(any("Hardness" in item["label"] or "硬度" in item["label"] for item in payload["ai_fills"]))
        mocked.assert_called()
        _, kwargs = mocked.call_args
        self.assertTrue(kwargs.get("fetch"))

    def test_simple_template_uses_family_columns_from_category_name(self) -> None:
        client = signup("family-xlsx@example.com")
        response = client.get(
            "/api/v1/excel/template",
            params={"style": "simple", "category_name": "Office & School Supplies / Other"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        from io import BytesIO

        from openpyxl import load_workbook

        book = load_workbook(BytesIO(response.content))
        fill_sheet = next(name for name in book.sheetnames if name != "说明")
        headers = [cell.value for cell in next(book[fill_sheet].iter_rows(min_row=1, max_row=1))]
        self.assertIn("色数", headers)
        self.assertIn("硬度", headers)
        self.assertNotIn("Lead Color", headers)
        self.assertNotIn("Lead Hardness", headers)


if __name__ == "__main__":
    unittest.main()
