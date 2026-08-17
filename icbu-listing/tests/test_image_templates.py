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

from fastapi.testclient import TestClient  # noqa: E402

from server.db import init_db  # noqa: E402
from server.main import app  # noqa: E402
from server.services.ecom_skill import assemble_prompt, english_brief  # noqa: E402
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
        self.assertEqual(pick_family("سماعات أذن لاسلكية").id, "electronics")
        self.assertEqual(pick_family("Taza de cerámica").id, "home")

    def test_official_alibaba_category_names_pick_a_stack(self) -> None:
        self.assertEqual(pick_family("", "Tools & Hardware / 五金工具").id, "tools")
        self.assertEqual(pick_family("", "Apparel & Accessories / 服装及配饰").id, "apparel")
        self.assertEqual(pick_family("", "Office & School Supplies").id, "stationery")
        self.assertEqual(pick_family("", "Consumer Electronics").id, "electronics")

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
        self.assertEqual(plan["skill"]["repo"], "buluslan/gpt-image2-ecommerce")
        self.assertEqual(plan["product_brief"], "colored pencil set")
        self.assertIn("no overlay text", main["prompt"].lower())
        self.assertIn("white", main["prompt"].lower())
        self.assertIn("soft diffused studio lighting", main["prompt"].lower())
        self.assertIn("upper left", main["prompt"].lower())
        self.assertIn("commercial photograph", main["prompt"].lower())
        self.assertLess(len(main["prompt"]), 900)
        for slot in plan["slots"]:
            self.assertIn("basswood", slot["prompt"])
            self.assertIn("lighting:", slot["prompt"].lower())
            self.assertIn("alibaba.com", slot["prompt"].lower())
            self.assertIn("colored pencil set", slot["prompt"])
            self.assertNotIn("No Amazon or Prime badges", slot["prompt"])
        self.assertTrue(any("fake" in item["prompt"].lower() for item in plan["slots"]))

    def test_skill_hero_prompt_stays_short_and_white(self) -> None:
        prompt = assemble_prompt("main", product="paint brush", family_id="tools", material="bristle")
        self.assertLess(len(prompt), 900)
        self.assertIn("soft diffused studio lighting", prompt.lower())
        self.assertIn("paint brush", prompt)
        self.assertIn("bristle", prompt)
        self.assertIn("upper left", prompt)
        detail = assemble_prompt("detail", product="paint brush", family_id="tools", material="bristle")
        self.assertNotIn("port precision", detail)

    def test_non_english_names_become_english_in_the_prompt(self) -> None:
        self.assertEqual(english_brief("油漆刷"), "wall paint brush")
        self.assertEqual(english_brief("سماعات أذن لاسلكية"), "wireless earbuds")
        self.assertEqual(english_brief("Taza de cerámica"), "ceramic mug")
        plan = plan_stack(product_name="油漆刷", note="猪鬃刷毛，铁皮箍")
        self.assertEqual(plan["family"]["id"], "tools")
        self.assertEqual(plan["product_name"], "油漆刷")
        self.assertEqual(plan["product_brief"], "wall paint brush")
        for slot in plan["slots"]:
            self.assertIn("wall paint brush", slot["prompt"])
            self.assertNotIn("油漆刷", slot["prompt"])
            self.assertNotIn("猪鬃", slot["prompt"])

    def test_prompts_do_not_invent_size_or_pack_count(self) -> None:
        bare = plan_stack(product_name="paint brush")
        scale = next(item for item in bare["slots"] if item["id"] in {"scale", "size", "dimension"})
        pack = next(item for item in bare["slots"] if item["id"] == "pack")
        self.assertIn("do not print any numbers", scale["prompt"].lower())
        self.assertNotIn("200mm", scale["prompt"])
        self.assertIn("no pack count", pack["prompt"].lower())
        self.assertIn("do not invent numbers", pack["prompt"].lower())
        given = plan_stack(
            product_name="paint brush",
            material="hog bristle",
            specs={"size": "25cm", "pack_count": "100 pcs / carton"},
        )
        scale_given = next(item for item in given["slots"] if item["id"] in {"scale", "size", "dimension"})
        pack_given = next(item for item in given["slots"] if item["id"] == "pack")
        self.assertIn("25cm", scale_given["prompt"])
        self.assertIn("100 pcs / carton", pack_given["prompt"])
        self.assertIn("hog bristle", given["slots"][0]["prompt"])

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
        planned = client.post("/api/v1/image-templates/plan", json={"product_name": "paint brush"})
        self.assertEqual(planned.status_code, 200, planned.text)
        self.assertEqual(planned.json()["family"]["id"], "tools")
        self.assertEqual(len(planned.json()["slots"]), 6)
        self.assertTrue(all(item.get("prompt") for item in planned.json()["slots"]))
