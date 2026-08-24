"""Category tree browse and root fetch resilience."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

os.environ["DATABASE_PATH"] = str(Path(tempfile.mkdtemp()) / "catalog-browse.db")
os.environ["UPLOAD_DIR"] = str(Path(tempfile.mkdtemp()) / "uploads")
os.environ["TOKEN_ENCRYPTION_KEY"] = "Frqkv73e3W19RfKb5WSgTueumPWcBSmpbM4wDyqu52o="
os.environ["REGISTRATION_CODES"] = "TEST-CODE"
os.environ["ALIBABA_APP_KEY"] = "test-key"
os.environ["ALIBABA_APP_SECRET"] = "test-secret"

from server.db import SessionLocal, init_db  # noqa: E402
from server.models import CategoryNode  # noqa: E402
from server.services import catalog  # noqa: E402
from server.services.shop_categories import _ONLINE_CACHE  # noqa: E402


class FakeCategoryApi:
    def __init__(self, *, fail: bool = False, empty_root: bool = False) -> None:
        self.fail = fail
        self.empty_root = empty_root
        self.calls = 0

    def get_category(self, cat_id):
        self.calls += 1
        if self.fail:
            raise RuntimeError("gateway down")
        cid = str(cat_id)
        if cid == "0":
            if self.empty_root:
                return {"result": {"category_id": "0", "name": "All", "leaf_category": False, "child_ids": []}}
            return {
                "result": {
                    "category_id": "0",
                    "name": "All Categories",
                    "cn_name": "全部类目",
                    "leaf_category": False,
                    "child_ids": ["100", "200"],
                }
            }
        names = {"100": ("Tools", "工具"), "200": ("Apparel", "服装")}
        name, cn = names.get(cid, (f"Cat {cid}", ""))
        return {
            "result": {
                "category_id": cid,
                "name": name,
                "cn_name": cn,
                "leaf_category": cid not in {"100", "200"},
                "child_ids": [],
                "parent_ids": ["0"],
            }
        }


class CatalogBrowseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()

    def setUp(self) -> None:
        self.db = SessionLocal()
        self.db.query(CategoryNode).delete()
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def test_get_node_root_returns_none_when_api_fails(self) -> None:
        api = FakeCategoryApi(fail=True)
        node = catalog.get_node(self.db, api, "0")
        self.assertIsNone(node)

    def test_get_node_root_fetches_children(self) -> None:
        api = FakeCategoryApi()
        root = catalog.get_node(self.db, api, "0")
        self.assertIsNotNone(root)
        children = catalog.get_children(self.db, api, root)
        self.assertEqual(len(children), 2)
        self.assertEqual(children[0].category_id, "100")

    def test_children_from_db_serves_cached_root_without_api(self) -> None:
        api = FakeCategoryApi()
        root = catalog.get_node(self.db, api, "0")
        catalog.get_children(self.db, api, root)
        cached = catalog.children_from_db(self.db, "0")
        self.assertEqual(len(cached), 2)

    def test_online_counts_do_not_cache_failed_empty(self) -> None:
        from server.models import Shop  # noqa: E402
        from server.services import shop_categories  # noqa: E402

        _ONLINE_CACHE.clear()
        shop = Shop(name="x", platform="alibaba_icbu")
        api = MagicMock()
        api.list_products.side_effect = RuntimeError("list failed")
        counts = shop_categories._online_counts(api, shop.id, max_pages=1)
        self.assertEqual(len(counts), 0)
        self.assertNotIn(shop.id, _ONLINE_CACHE)


if __name__ == "__main__":
    unittest.main()
