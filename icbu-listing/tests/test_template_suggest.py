"""Template suggestion during batch review."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

os.environ["DATABASE_PATH"] = str(Path(tempfile.mkdtemp()) / "template-suggest.db")
os.environ["UPLOAD_DIR"] = str(Path(tempfile.mkdtemp()) / "uploads")
os.environ["TOKEN_ENCRYPTION_KEY"] = "Frqkv73e3W19RfKb5WSgTueumPWcBSmpbM4wDyqu52o="
os.environ["REGISTRATION_CODES"] = "TEST-CODE"
os.environ["ALIBABA_APP_KEY"] = "test-key"
os.environ["ALIBABA_APP_SECRET"] = "test-secret"

from server.db import SessionLocal, init_db  # noqa: E402
from server.models import Shop, Template, User  # noqa: E402
from server.services import template_suggest, templates  # noqa: E402


class TemplateSuggestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()

    def setUp(self) -> None:
        self.db = SessionLocal()
        self.user = User(email=f"tpl-{id(self)}@example.com", password_hash="x")
        self.db.add(self.user)
        self.db.commit()
        self.shop = Shop(user_id=self.user.id, name="模板店", platform="alibaba_icbu")
        self.db.add(self.shop)
        self.db.commit()
        self.category_id = "21111112"

    def tearDown(self) -> None:
        self.db.close()

    def _add_template(self, name: str, values: dict, *, is_auto: bool = False) -> Template:
        row = Template(
            user_id=self.user.id,
            shop_id=self.shop.id,
            name=name,
            category_id=self.category_id,
            values_json=__import__("json").dumps(values, ensure_ascii=False),
            is_auto=is_auto,
        )
        self.db.add(row)
        self.db.commit()
        return row

    def test_single_template_is_auto_selected(self) -> None:
        only = self._add_template("画笔海运", {"priceUnit": "Piece/Pieces", "port": "Shanghai"})
        rows = [{"line": 2, "sku": "SKU-1", "name": "Paint brush", "note": "bulk sea freight"}]
        result = template_suggest.suggest(self.db, self.shop, self.category_id, rows)
        self.assertEqual(result["suggestion"]["template_id"], only.id)
        self.assertEqual(result["suggestion"]["source"], "single")
        self.assertEqual(len(result["templates"]), 1)

    def test_rule_pick_uses_newest_when_no_signal(self) -> None:
        older = self._add_template("旧模板", {"priceUnit": "Set/Sets"})
        newer = self._add_template("新模板", {"priceUnit": "Piece/Pieces"})
        rows = [{"line": 2, "sku": "SKU-1", "name": "Item", "note": ""}]
        result = template_suggest.suggest(self.db, self.shop, self.category_id, rows, ai=None)
        self.assertEqual(result["suggestion"]["template_id"], newer.id)
        self.assertNotEqual(result["suggestion"]["template_id"], older.id)

    def test_apply_row_suggestions_writes_template_fields(self) -> None:
        row = self._add_template("默认", {"origin": "China"})
        suggestion = {"template_id": row.id, "template_name": "默认", "reasoning": "只有一个"}
        updated = template_suggest.apply_row_suggestions(
            [{"line": 2, "sku": "A"}],
            suggestion,
            [{"line": 2, "sku": "A", "template_id": row.id, "template_name": "默认", "reasoning": "只有一个"}],
        )
        self.assertEqual(updated[0]["_template_id"], row.id)
        self.assertEqual(updated[0]["_template_name"], "默认")

    def test_apply_to_values_respects_template_id(self) -> None:
        first = self._add_template("A", {"origin": "China", "priceUnit": "Piece/Pieces"})
        second = self._add_template("B", {"origin": "Germany", "priceUnit": "Set/Sets"})
        merged = templates.apply_to_values(
            self.db,
            self.shop.id,
            self.category_id,
            {},
            template_id=second.id,
        )
        self.assertEqual(merged.get("origin"), "Germany")
        self.assertNotEqual(merged.get("origin"), templates.values_of(first).get("origin"))


if __name__ == "__main__":
    unittest.main()
