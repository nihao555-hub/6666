"""Shop-used leaves come from product.list + local drafts, not a history API."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

os.environ["DATABASE_PATH"] = str(Path(tempfile.mkdtemp()) / "shop-cats.db")
os.environ["UPLOAD_DIR"] = str(Path(tempfile.mkdtemp()) / "uploads")
os.environ["TOKEN_ENCRYPTION_KEY"] = "Frqkv73e3W19RfKb5WSgTueumPWcBSmpbM4wDyqu52o="
os.environ["REGISTRATION_CODES"] = "TEST-CODE"
os.environ["ALIBABA_APP_KEY"] = "test-key"
os.environ["ALIBABA_APP_SECRET"] = "test-secret"

from server.db import SessionLocal, init_db  # noqa: E402
from server.models import CategoryMemory, CategoryRecentPick, Draft, Shop, Template, User  # noqa: E402
from server.services import shop_categories  # noqa: E402
from server.services.shop_categories import _ONLINE_CACHE, _SIDEBAR_CACHE  # noqa: E402


class FakeApi:
    def __init__(self, pages: list[list[dict]] | None = None) -> None:
        self.pages = pages or [[{"category_id": "21111112"}, {"category_id": "21111112"}, {"category_id": "99"}]]
        self.calls = 0

    def list_products(self, current_page=1, page_size=20, filter_type="onSelling"):
        self.calls += 1
        rows = self.pages[current_page - 1] if current_page <= len(self.pages) else []
        return {"result": {"products": rows, "total_item": sum(len(page) for page in self.pages)}}

    def get_category(self, cat_id):
        names = {"21111112": ("Paint Brushes", "画笔"), "99": ("Other", "其他")}
        name, cn = names.get(str(cat_id), (f"Cat {cat_id}", ""))
        return {
            "result": {
                "category_id": str(cat_id),
                "name": name,
                "cn_name": cn,
                "leaf_category": True,
                "child_ids": [],
                "parent_ids": [],
            }
        }


class UsedLeafTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()

    def setUp(self) -> None:
        _ONLINE_CACHE.clear()
        self.db = SessionLocal()
        self.user = User(email=f"cat-{id(self)}@example.com", password_hash="x")
        self.db.add(self.user)
        self.db.commit()
        self.shop = Shop(user_id=self.user.id, name="刷子店", platform="alibaba_icbu")
        self.db.add(self.shop)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def test_online_products_rank_the_shops_usual_leaves(self) -> None:
        api = FakeApi()
        used = shop_categories.used_leaves(self.db, api, self.shop)
        ids = [item["category_id"] for item in used]
        self.assertEqual(ids[0], "21111112")
        self.assertEqual(used[0]["count"], 2)
        self.assertEqual(used[0]["source"], "online")
        self.assertIn("画笔", used[0]["label"])

    def test_local_drafts_and_memory_still_show_when_list_is_empty(self) -> None:
        self.db.add(Draft(user_id=self.user.id, shop_id=self.shop.id, category_id="21111112", title="x"))
        self.db.add(CategoryMemory(shop_id=self.shop.id, signature="brush", category_id="21111112", hits=4))
        self.db.add(Template(user_id=self.user.id, shop_id=self.shop.id, name="笔", category_id="99"))
        self.db.commit()
        api = FakeApi(pages=[[]])
        used = shop_categories.used_leaves(self.db, api, self.shop)
        by_id = {item["category_id"]: item for item in used}
        self.assertGreaterEqual(by_id["21111112"]["count"], 5)
        self.assertIn("99", by_id)

    def test_online_counts_are_cached_across_opens(self) -> None:
        api = FakeApi()
        shop_categories.used_leaves(self.db, api, self.shop)
        first = api.calls
        shop_categories.used_leaves(self.db, api, self.shop)
        self.assertEqual(api.calls, first)

    def test_recent_picks_track_explicit_selections(self) -> None:
        api = FakeApi(pages=[[]])
        shop_categories.record_recent_pick(self.db, self.shop, self.user, "21111112", "Paint Brushes / 画笔")
        shop_categories.record_recent_pick(self.db, self.shop, self.user, "99", "Other / 其他")
        shop_categories.record_recent_pick(self.db, self.shop, self.user, "21111112", "Paint Brushes / 画笔")
        recent = shop_categories.recent_picks(self.db, api, self.shop, self.user)
        self.assertEqual([item["category_id"] for item in recent], ["21111112", "99"])
        self.assertEqual(recent[0]["source"], "recent")
        self.assertIn("画笔", recent[0]["path_label"])

    def test_sidebar_caches_and_skips_extra_fetches(self) -> None:
        _SIDEBAR_CACHE.clear()
        self.db.add(CategoryMemory(shop_id=self.shop.id, signature="brush", category_id="21111112", category_name="Paint Brushes / 画笔", hits=2))
        self.db.commit()
        api = FakeApi()
        first = shop_categories.sidebar(self.db, api, self.shop, self.user)
        calls_after_first = api.calls
        second = shop_categories.sidebar(self.db, api, self.shop, self.user)
        self.assertEqual(calls_after_first, api.calls)
        self.assertEqual(first["used"][0]["category_id"], second["used"][0]["category_id"])
        self.assertIn("画笔", first["used"][0]["path_label"])

    def test_record_recent_pick_invalidates_sidebar_cache(self) -> None:
        _SIDEBAR_CACHE.clear()
        api = FakeApi(pages=[[]])
        shop_categories.sidebar(self.db, api, self.shop, self.user)
        shop_categories.record_recent_pick(self.db, self.shop, self.user, "99", "Other / 其他")
        recent = shop_categories.sidebar(self.db, api, self.shop, self.user)["recent"]
        self.assertEqual(recent[0]["category_id"], "99")


if __name__ == "__main__":
    unittest.main()
