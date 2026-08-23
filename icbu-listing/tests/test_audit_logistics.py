"""Logistics audit panel and 4.8 quality gate."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from schema import SchemaField, SchemaOption  # noqa: E402
from server.services.audit_logistics import (  # noqa: E402
    apply_packaging,
    apply_shipping,
    panel_for_draft,
    shipping_ok,
)
from server.services.quality import MIN_QUALITY_SCORE, score_listing  # noqa: E402


def _shipping_field() -> SchemaField:
    return SchemaField(
        id="shippingTemplate",
        name="运费",
        type="complex",
        children=[
            SchemaField(
                id="shippingTemplateId",
                name="模板",
                type="singleCheck",
                options=[SchemaOption(value="123", display_name="智能运费")],
            )
        ],
    )


class AuditLogisticsTests(unittest.TestCase):
    def test_shipping_ok_with_negotiated_type(self) -> None:
        values = {"shippingTemplate": {"templateType": "FREIGHT_NEGOTIATION"}}
        self.assertTrue(shipping_ok(values, has_field=True))

    def test_shipping_missing(self) -> None:
        self.assertFalse(shipping_ok({}, has_field=True))

    def test_apply_shipping_and_packaging(self) -> None:
        values: dict = {}
        apply_shipping(values, "123")
        apply_packaging(values, pkg_weight="0.3", pkg_length="20", pkg_width="15", pkg_height="2")
        self.assertEqual(values["shippingTemplate"]["shippingTemplateId"], "123")
        self.assertEqual(values["pkgWeight"], "0.3")
        self.assertEqual(values["pkgMeasure"]["length"], "20")

    def test_panel_marks_missing_packaging(self) -> None:
        xml = """<itemSchema><field id="shippingTemplate" type="complex"><fields>
        <field id="shippingTemplateId" type="singleCheck"><options>
        <option displayName="智能运费" value="123"/></options></field></fields></field>
        <field id="pkgWeight" type="input"/><field id="pkgMeasure" type="complex"/></itemSchema>"""
        draft = SimpleNamespace(
            category_id="21110712",
            values_json='{"shippingTemplate":{"templateType":"FREIGHT_NEGOTIATION"}}',
        )
        shop = SimpleNamespace(id="shop-1")
        panel = panel_for_draft(None, shop, draft, xml=xml)
        packaging = next(item for item in panel["items"] if item["id"] == "packaging")
        self.assertFalse(packaging["ok"])
        shipping = next(item for item in panel["items"] if item["id"] == "shippingTemplate")
        self.assertTrue(shipping["ok"])


class QualityThresholdTests(unittest.TestCase):
    def test_min_score_is_48(self) -> None:
        self.assertEqual(MIN_QUALITY_SCORE, 4.8)

    def test_complete_listing_meets_threshold(self) -> None:
        fields = [
            SchemaField(id="priceUnit", name="单位", type="singleCheck"),
            SchemaField(id="saleType", name="售卖", type="singleCheck"),
            SchemaField(id="scPrice", name="价格设置", type="singleCheck"),
            SchemaField(id="shippingTemplate", name="运费", type="complex"),
            SchemaField(id="logisticsProperty", name="物流", type="singleCheck"),
            SchemaField(id="pkgWeight", name="重量", type="input"),
            SchemaField(id="pkgMeasure", name="尺寸", type="complex"),
            SchemaField(id="marketSample", name="样品", type="singleCheck"),
            SchemaField(id="productTitle", name="标题", type="input"),
            SchemaField(id="productKeywords", name="词", type="complex"),
            SchemaField(id="textDesc", name="描述", type="input"),
            SchemaField(id="icbuCatProp", name="属性", type="complex"),
        ]
        values = {
            "catId": "21110712",
            "productTitle": "Colored Pencil Set",
            "productKeywords": {"a": "colored pencil", "b": "school pencil", "c": "drawing set"},
            "icbuCatProp": {"p-1": "1"},
            "priceUnit": "1",
            "saleType": "1",
            "scPrice": "1",
            "ladderPrice": {"ladderPrice_0": {"quantity": "500", "price": "1.80"}},
            "shippingTemplate": {"templateType": "FREIGHT_NEGOTIATION"},
            "logisticsProperty": ["1"],
            "pkgWeight": "0.5",
            "pkgMeasure": {"length": "20", "width": "10", "height": "5"},
            "marketSample": "1",
            "textDesc": "Student colored pencil set.",
        }
        report = score_listing(
            values=values,
            fields=fields,
            image_count=4,
            price="1.80",
            moq="500",
            category_id="21110712",
        )
        self.assertGreaterEqual(report["score"], MIN_QUALITY_SCORE)
        self.assertTrue(report["ready"])


if __name__ == "__main__":
    unittest.main()
