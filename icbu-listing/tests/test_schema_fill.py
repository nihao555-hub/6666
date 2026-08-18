"""Evidence-gated schema fill — deterministic path without live AI."""

import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from ai import Understanding  # noqa: E402
from schema import parse_schema  # noqa: E402

from server.services.fact_bundle import FactBundle, from_excel_row  # noqa: E402
from server.services.schema_fill import (  # noqa: E402
    FillResult,
    align_attributes,
    fill_category_draft,
    sample_fill_report,
)

SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<itemSchema>
  <field id="productTitle" name="Product name" type="input">
    <rules><rule name="requiredRule" value="true"/></rules>
  </field>
  <field id="priceUnit" name="Unit" type="singleCheck">
    <rules><rule name="requiredRule" value="true"/></rules>
    <options>
      <option displayName="Piece/Pieces" value="17"/>
    </options>
  </field>
  <field id="scPrice" name="Price setting" type="singleCheck">
    <options><option displayName="Tiered pricing by quantity" value="1"/></options>
  </field>
  <field id="ladderPrice" name="Quantity price" type="complex">
    <fields>
      <field id="ladderPrice_0" type="complex">
        <fields>
          <field id="quantity" name="MOQ" type="input">
            <rules><rule name="requiredRule" value="true"/></rules>
          </field>
          <field id="price" name="Price" type="input">
            <rules><rule name="requiredRule" value="true"/></rules>
          </field>
        </fields>
      </field>
    </fields>
  </field>
  <field id="minOrderQuantity" name="MOQ" type="input"/>
  <field id="icbuCatProp" name="Product feature" type="complex">
    <fields>
      <field id="p-1" name="Place of Origin" type="singleCheck">
        <rules><rule name="requiredRule" value="true"/></rules>
        <options>
          <option displayName="China" value="100000458"/>
          <option displayName="Vietnam" value="100000630"/>
        </options>
      </field>
      <field id="p-9" name="Lead Color" type="multiCheck">
        <rules><rule name="requiredRule" value="true"/></rules>
        <options>
          <option displayName="colored" value="12970290"/>
          <option displayName="other" value="-1"/>
        </options>
      </field>
    </fields>
  </field>
</itemSchema>
"""


class MockAi:
    def chat_json(self, messages: list[dict[str, Any]], temperature: float = 0.0) -> dict[str, Any]:
        return {"p-77": "matte", "p-9": "colored"}


class SchemaFillTests(unittest.TestCase):
    def test_local_origin_from_bundle_without_ai(self) -> None:
        fields = parse_schema(SAMPLE)
        group = next(field for field in fields if field.id == "icbuCatProp")
        bundle = FactBundle(origin="China")
        u = Understanding(product_name="Pencil set")
        result = FillResult()
        values = align_attributes(group, u, {"origin": "China"}, None, bundle, result)
        self.assertEqual(values["p-1"], "100000458")
        self.assertIn("icbuCatProp.p-1", result.evidence)

    def test_color_count_alone_does_not_infer_colored(self) -> None:
        fields = parse_schema(SAMPLE)
        group = next(field for field in fields if field.id == "icbuCatProp")
        bundle = FactBundle(name="12色木杆彩色铅笔", specs={"color_count": "12", "hardness": "HB"})
        u = bundle.enrich(Understanding(product_name="学生绘画铅笔套装"))
        result = FillResult()
        values = align_attributes(group, u, {"origin": "China"}, None, bundle, result)
        self.assertNotIn("p-9", values)

    def test_vision_color_fills_lead_color(self) -> None:
        fields = parse_schema(SAMPLE)
        group = next(field for field in fields if field.id == "icbuCatProp")
        bundle = FactBundle(name="Colored pencil set")
        u = bundle.enrich(Understanding(product_name="Colored pencil set", colors=["colored"]))
        result = FillResult()
        values = align_attributes(group, u, {"origin": "China"}, None, bundle, result)
        self.assertEqual(values.get("p-9"), ["12970290"])

    def test_color_spec_maps_to_option_without_ai(self) -> None:
        fields = parse_schema(SAMPLE)
        group = next(field for field in fields if field.id == "icbuCatProp")
        bundle = FactBundle(specs={"color": "colored"})
        u = bundle.enrich(Understanding(product_name="Colored pencil set", colors=["colored"]))
        result = FillResult()
        values = align_attributes(group, u, {"origin": "China"}, None, bundle, result)
        self.assertEqual(values.get("p-9"), ["12970290"])
        self.assertEqual(result.stats.ai_calls, 0)

    def test_ai_fills_unresolved_required_when_supported(self) -> None:
        xml = SAMPLE.replace(
            '      <field id="p-9" name="Lead Color" type="multiCheck">',
            '      <field id="p-77" name="Special finish" type="singleCheck">\n'
            '        <rules><rule name="requiredRule" value="true"/></rules>\n'
            '        <options><option displayName="matte" value="1"/></options>\n'
            "      </field>\n"
            '      <field id="p-9" name="Lead Color" type="multiCheck">',
        )
        fields = parse_schema(xml)
        group = next(field for field in fields if field.id == "icbuCatProp")
        bundle = FactBundle(note="Special finish matte for retail packs")
        u = Understanding(product_name="Pencil set")
        result = FillResult()
        values = align_attributes(group, u, {"origin": "China"}, MockAi(), bundle, result)
        self.assertEqual(values.get("p-77"), "1")
        self.assertEqual(result.stats.ai_calls, 1)

    def test_sample_fill_report_sets_trade_terms(self) -> None:
        bundle = FactBundle(
            name="Colored pencils",
            price="1.80",
            moq="500",
            origin="China",
            specs={"material": "Wood", "color": "12 colors"},
        )
        report = sample_fill_report(SAMPLE, bundle)
        self.assertEqual(report.values["ladderPrice"]["ladderPrice_0"]["quantity"], "500")
        self.assertEqual(report.values["icbuCatProp"]["p-1"], "100000458")
        self.assertTrue(report.stats.filled >= 1)

    def test_blocked_required_without_evidence(self) -> None:
        bundle = FactBundle(price="1.00", moq="100")
        report = fill_category_draft(
            SAMPLE,
            understanding=Understanding(product_name="Mystery item"),
            bundle=bundle,
            defaults={"origin": "China", "priceUnit": "Piece/Pieces", "saleType": "Unit"},
            category_values={},
            price="1.00",
            moq="100",
            ai=None,
            images_applied=True,
            title="Wholesale product",
        )
        self.assertTrue(any("仍缺事实依据" in issue["message"] for issue in report.issues))


if __name__ == "__main__":
    unittest.main()
