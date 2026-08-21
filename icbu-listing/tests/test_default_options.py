"""Shop defaults come from the official rules, not from the seller's memory."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from schema import parse_schema  # noqa: E402
from server.services import defaults  # noqa: E402

SCHEMA = """<?xml version="1.0"?><itemSchema>
  <field id="icbuCatProp" type="complex"><fields>
    <field id="p-1" name="Place of Origin" type="singleCheck">
      <rules><rule name="requiredRule" value="true"/></rules>
      <options><option displayName="China" value="100000458"/><option displayName="Viet Nam" value="100000123"/></options>
    </field>
  </fields></field>
  <field id="priceUnit" name="Unit" type="singleCheck">
    <rules><rule name="requiredRule" value="true"/></rules>
    <options><option displayName="Bag/Bags" value="1"/><option displayName="Piece/Pieces" value="4"/></options>
  </field>
  <field id="shippingTemplate" name="Logistics supply mode" type="complex"><fields>
    <field id="templateType" type="singleCheck">
      <options><option displayName="FREIGHT_NEGOTIATION" value="0"/></options>
    </field>
    <field id="shippingTemplateId" type="singleCheck">
      <options><option displayName="画笔运费" value="2041723009"/><option displayName="retails" value="2003860290"/></options>
    </field>
  </fields></field>
  <field id="logisticsProperty" name="Logistics attribute" type="multiCheck">
    <options><option displayName="Ordinary goods" value="general_cargo_0"/></options>
  </field>
</itemSchema>"""


class FakeApi:
    def schema_xml(self, cat_id, language="en_US"):
        return SCHEMA

    def get_category(self, cat_id):
        return {"result": {"category_id": str(cat_id), "name": "Paint Brushes", "leaf_category": True}}

    def list_products(self, current_page=1, page_size=20, filter_type="onSelling"):
        return {"result": {"product_list": {"products": [{"category_id": 21111112}]}}}


class DefaultOptionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.specs = {item.id: item for item in parse_schema(SCHEMA)}

    def test_freight_templates_are_the_shops_own(self) -> None:
        """The one field nobody can type: it is a shop-specific numeric id."""
        found = defaults._find(self.specs, ("shippingTemplate", "shippingTemplateId"))
        self.assertIsNotNone(found)
        self.assertEqual(
            {option.display_name: option.value for option in found.options},
            {"画笔运费": "2041723009", "retails": "2003860290"},
        )

    def test_origin_is_located_by_name_not_by_a_hardcoded_id(self) -> None:
        found = defaults._find(self.specs, ("icbuCatProp", "@origin"))
        self.assertIsNotNone(found)
        self.assertTrue(found.has_option("100000458"))

    def test_saved_label_is_shown_as_the_official_value(self) -> None:
        """Defaults saved as «Piece/Pieces» must still select the right option."""
        found = self.specs["priceUnit"]
        self.assertEqual(defaults._stored_value(found, "Piece/Pieces"), "4")
        self.assertEqual(defaults._stored_value(found, "4"), "4")
        self.assertEqual(defaults._stored_value(found, "unknown"), "unknown")

    def test_fields_the_category_lacks_are_reported_not_hidden(self) -> None:
        import types

        shop = types.SimpleNamespace(id="shop-1")
        db = types.SimpleNamespace()
        view = _options_view(db, shop)
        by_key = {item["key"]: item for item in view["fields"]}
        self.assertEqual(by_key["priceUnit"]["kind"], "select")
        self.assertEqual(by_key["priceUnit"]["scope"], "product")
        self.assertEqual(by_key["origin"]["scope"], "shop")
        self.assertEqual(by_key["shippingTemplateId"]["kind"], "select")
        self.assertTrue(by_key["logisticsProperty"]["multiple"])
        # Plenty of leaves have no payment or port field at all. Asking for
        # them anyway is how a seller ends up filling in dead values.
        self.assertEqual(by_key["paymentMethod"]["kind"], "unsupported")
        self.assertEqual(by_key["port"]["kind"], "unsupported")


class PullDefaultsTests(unittest.TestCase):
    def test_extract_reads_nested_render_shape(self) -> None:
        extracted = defaults.extract_listing_defaults(
            {
                "icbuCatProp": {"p-1": "100000458"},
                "priceUnit": "4",
                "saleType": {"$value": "1"},
                "shippingTemplate": {"shippingTemplateId": "2041723009"},
                "logisticsProperty": ["general_cargo_0", "battery_1"],
                "pkgWeight": "0.35",
                "pkgMeasure": {"length": "20", "width": "10", "height": "8"},
                "brand": "Giorgione",
                "ladderPeriod": {"ladderPeriod_0": {"period": "7"}},
                "paymentMethod": "1",
                "port": "SNH",
                "market": "inquiry",
            }
        )
        self.assertEqual(extracted["origin"], "100000458")
        self.assertEqual(extracted["priceUnit"], "4")
        self.assertEqual(extracted["saleType"], "1")
        self.assertEqual(extracted["shippingTemplateId"], "2041723009")
        self.assertEqual(extracted["logisticsProperty"], "general_cargo_0,battery_1")
        self.assertEqual(extracted["pkgWeight"], "0.35")
        self.assertEqual(extracted["pkgLength"], "20")
        self.assertEqual(extracted["pkgWidth"], "10")
        self.assertEqual(extracted["pkgHeight"], "8")
        self.assertEqual(extracted["brand"], "Giorgione")
        self.assertEqual(extracted["ladderPeriod"], "7")
        self.assertEqual(extracted["paymentMethod"], "1")
        self.assertEqual(extracted["port"], "SNH")
        self.assertEqual(extracted["market"], "inquiry")

    def test_placeholders_are_replaced_until_the_seller_saves(self) -> None:
        current = {
            "origin": "China",
            "priceUnit": "Piece/Pieces",
            "shippingTemplateId": "",
            "brand": "",
            "ladderPeriod": "15",
        }
        extracted = {
            "origin": "100000123",
            "priceUnit": "4",
            "shippingTemplateId": "2041723009",
            "brand": "Giorgione",
            "ladderPeriod": "7",
        }
        merged, filled = defaults.apply_extracted(current, extracted)
        self.assertEqual(merged["origin"], "100000123")
        self.assertEqual(merged["priceUnit"], "4")
        self.assertEqual(merged["shippingTemplateId"], "2041723009")
        self.assertEqual(merged["brand"], "Giorgione")
        self.assertEqual(merged["ladderPeriod"], "7")
        self.assertEqual(set(filled), {"origin", "priceUnit", "shippingTemplateId", "brand", "ladderPeriod"})

    def test_seller_saved_keys_are_not_overwritten(self) -> None:
        current = {
            "origin": "China",
            "priceUnit": "Piece/Pieces",
            "shippingTemplateId": "",
            "_meta": {"user_keys": ["origin"]},
        }
        extracted = {"origin": "100000123", "priceUnit": "4", "shippingTemplateId": "2041723009"}
        merged, filled = defaults.apply_extracted(current, extracted, refresh=True)
        self.assertEqual(merged["origin"], "China")
        self.assertEqual(merged["priceUnit"], "4")
        self.assertEqual(merged["shippingTemplateId"], "2041723009")
        self.assertNotIn("origin", filled)
        self.assertIn("priceUnit", filled)

    def test_empty_listing_values_do_not_wipe_placeholders(self) -> None:
        current = {"origin": "China", "brand": ""}
        merged, filled = defaults.apply_extracted(current, {"origin": "", "brand": ""})
        self.assertEqual(merged["origin"], "China")
        self.assertEqual(merged["brand"], "")
        self.assertEqual(filled, [])

    def test_already_set_shop_skips_another_pull(self) -> None:
        import types

        shop = types.SimpleNamespace(
            defaults_json='{"origin":"100000458","priceUnit":"4","saleType":"1",'
            '"logisticsProperty":"battery_1","marketSample":"yes",'
            '"shippingTemplateId":"2041723009","paymentMethod":"1","port":"SNH",'
            '"market":"inquiry","ladderPeriod":"7","pkgWeight":"0.3",'
            '"pkgLength":"20","pkgWidth":"10","pkgHeight":"8","brand":"Giorgione"}'
        )

        class BoomApi:
            def list_products(self, *args, **kwargs):
                raise AssertionError("should not list when defaults are already filled")

            def schema_render(self, *args, **kwargs):
                raise AssertionError("should not render when defaults are already filled")

        result = defaults.pull_from_shop(types.SimpleNamespace(), BoomApi(), shop)
        self.assertEqual(result["reason"], "already_set")
        self.assertEqual(result["filled"], [])

    def test_leaf_habit_beats_shop_fallback_but_row_wins(self) -> None:
        shop = {
            "origin": "100000458",
            "priceUnit": "4",
            "pkgLength": "20",
            "pkgWidth": "10",
            "pkgHeight": "8",
            "shippingTemplateId": "2041723009",
        }
        category = {"pkgLength": "40", "pkgWidth": "30", "pkgHeight": "20", "priceUnit": "1"}
        extra = {"pkgLength": "12", "brand": "Giorgione"}
        layered = defaults.layer_defaults(shop, category, extra)
        self.assertEqual(layered["origin"], "100000458")
        self.assertEqual(layered["priceUnit"], "1")
        self.assertEqual(layered["pkgLength"], "12")
        self.assertEqual(layered["pkgWidth"], "30")
        self.assertEqual(layered["pkgHeight"], "20")
        self.assertEqual(layered["shippingTemplateId"], "2041723009")
        self.assertEqual(layered["brand"], "Giorgione")

    def test_option_labels_are_remembered_for_the_shop_list(self) -> None:
        labels = defaults.remember_option_labels(
            {},
            [
                {
                    "key": "shippingTemplateId",
                    "kind": "select",
                    "value": "2041723009",
                    "options": [{"value": "2041723009", "label": "画笔运费"}],
                }
            ],
        )
        self.assertEqual(labels["shippingTemplateId"], "画笔运费")


def _options_view(db, shop):
    """Run options_view with the schema and category caches stubbed out."""
    from server.services import catalog

    original_schema, original_node = catalog.get_schema_xml, catalog.get_node
    catalog.get_schema_xml = lambda *args, **kwargs: SCHEMA
    catalog.get_node = lambda *args, **kwargs: None
    try:
        return defaults.options_view(db, FakeApi(), shop, {"priceUnit": "Piece/Pieces"}, category_id="21111112")
    finally:
        catalog.get_schema_xml, catalog.get_node = original_schema, original_node


if __name__ == "__main__":
    unittest.main()
