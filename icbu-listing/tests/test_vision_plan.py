"""Vision-assisted smart plan helpers."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.services import smart_plan, vision_plan  # noqa: E402


def _pencil_candidates() -> list[dict]:
    return [
        smart_plan._core_column("sku"),
        {
            "id": "attr.icbuCatProp.p-15",
            "label": "材质",
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
            "id": "attr.icbuCatProp.p-2",
            "label": "铅芯硬度",
            "required": True,
            "source": "schema_required",
        },
    ]


class VisionPlanTests(unittest.TestCase):
    def test_group_key_uses_parent_folder(self) -> None:
        self.assertEqual(vision_plan._group_key("batch/sku-001/main.jpg"), "sku-001")

    def test_attr_ids_covered_by_material_in_vision(self) -> None:
        samples = [{"group": "sku1", "material": "wood", "colors": ["red", "blue"]}]
        covered = vision_plan.attr_ids_covered_by_vision(_pencil_candidates(), samples)
        self.assertIn("attr.icbuCatProp.p-15", covered)

    def test_rule_based_skips_vision_covered_attrs(self) -> None:
        candidates = _pencil_candidates()
        samples = [{"group": "sku1", "material": "wood", "specs": {"color count": "24"}}]
        chosen = smart_plan._rule_based_user_columns(candidates, vision_samples=samples)
        self.assertNotIn("attr.icbuCatProp.p-15", chosen)

    def test_analyze_without_ai_returns_empty(self) -> None:
        uploads = [("folder/a.jpg", b"\xff\xd8\xff")]
        self.assertEqual(vision_plan.analyze_images_for_plan(None, uploads), [])


if __name__ == "__main__":
    unittest.main()
