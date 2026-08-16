"""Category image stacks must be deterministic and ICBU-shaped."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

os.environ["DATABASE_PATH"] = str(Path(tempfile.mkdtemp()) / "images.db")
os.environ["UPLOAD_DIR"] = str(Path(tempfile.mkdtemp()) / "uploads")
os.environ["TOKEN_ENCRYPTION_KEY"] = "Frqkv73e3W19RfKb5WSgTueumPWcBSmpbM4wDyqu52o="
os.environ["REGISTRATION_CODES"] = "TEST-CODE"
os.environ["ALIBABA_APP_KEY"] = "test-key"
os.environ["ALIBABA_APP_SECRET"] = "test-secret"
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("IMAGE_MODEL", None)

from fastapi.testclient import TestClient  # noqa: E402

from server.db import init_db  # noqa: E402
from server.main import app  # noqa: E402
from server.services.image_templates import (  # noqa: E402
    ICBU_MAX_IMAGES,
    pick_family,
    plan_stack,
)


def signup(email: str) -> TestClient:
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "supersecret", "code": "TEST-CODE"},
    )
    assert response.status_code == 200, response.text
    return client


class ImageTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()

    def test_colored_pencils_use_stationery_stack(self) -> None:
        family = pick_family("colored pencil set", "Colored Pencils")
        self.assertEqual(family.id, "stationery")
        self.assertEqual(len(family.slots), ICBU_MAX_IMAGES)
        self.assertEqual(family.slots[0].id, "main")
        self.assertEqual(family.slots[0].text_policy, "none")
        self.assertTrue(any(slot.id == "pack" for slot in family.slots))
        self.assertTrue(any(slot.id == "custom" for slot in family.slots))

    def test_paint_brush_is_tools_not_beauty(self) -> None:
        self.assertEqual(pick_family("paint brush set for wall").id, "tools")
        self.assertEqual(pick_family("wireless earbuds").id, "electronics")
        self.assertEqual(pick_family("women floral midi dress").id, "apparel")
        self.assertEqual(pick_family("unknown widget").id, "general")

    def test_plan_locks_identity_and_forbids_fake_marks(self) -> None:
        plan = plan_stack(
            product_name="colored pencil set",
            category_hint="Colored Pencils",
            material="basswood",
            colors=["red", "blue"],
            features=["24 colors"],
        )
        self.assertEqual(plan["family"]["id"], "stationery")
        self.assertEqual(len(plan["slots"]), 6)
        main = plan["slots"][0]
        self.assertIn("No overlay text", main["prompt"])
        self.assertIn("pure white", main["prompt"].lower())
        for slot in plan["slots"]:
            self.assertIn("PRODUCT IDENTITY LOCK", slot["prompt"])
            self.assertIn("basswood", slot["prompt"])
            self.assertIn("no fake CE/ISO/FDA marks", slot["prompt"])
            self.assertIn("No Amazon or Prime badges", slot["prompt"])

    def test_explicit_family_wins_over_keywords(self) -> None:
        plan = plan_stack(product_name="pencil", family_id="industrial")
        self.assertEqual(plan["family"]["id"], "industrial")

    def test_catalog_and_plan_need_login(self) -> None:
        anon = TestClient(app)
        self.assertEqual(anon.get("/api/v1/image-templates").status_code, 401)
        client = signup("img-catalog@example.com")
        catalog = client.get("/api/v1/image-templates")
        self.assertEqual(catalog.status_code, 200, catalog.text)
        self.assertGreaterEqual(len(catalog.json()["families"]), 8)
        self.assertIn("image_enabled", catalog.json())
        planned = client.post("/api/v1/image-templates/plan", json={"product_name": "paint brush"})
        self.assertEqual(planned.status_code, 200, planned.text)
        self.assertEqual(planned.json()["family"]["id"], "tools")
        self.assertEqual(len(planned.json()["slots"]), 6)

    def test_generate_without_image_model_is_rejected(self) -> None:
        client = signup("img-generate@example.com")
        response = client.post(
            "/api/v1/image-templates/generate",
            data={"slot_id": "main", "prompt": "white background product"},
        )
        self.assertEqual(response.status_code, 400)
