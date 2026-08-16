import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from flow import FLOW, first_release_steps, user_must_do


class FlowTests(unittest.TestCase):
    def test_user_only_touches_four_moments(self) -> None:
        ids = [step.id for step in user_must_do()]
        self.assertEqual(ids, ["authorize", "drop_assets", "review", "online"])

    def test_first_release_ends_at_publish(self) -> None:
        ids = [step.id for step in first_release_steps()]
        self.assertIn("publish", ids)
        self.assertNotIn("online", ids)

    def test_schema_add_is_the_only_publish_api(self) -> None:
        publish = next(step for step in FLOW if step.id == "publish")
        self.assertEqual(publish.apis, ("/icbu/product/schema/add",))


if __name__ == "__main__":
    unittest.main()
