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
        self.assertEqual(by_key["shippingTemplateId"]["kind"], "select")
        self.assertTrue(by_key["logisticsProperty"]["multiple"])
        # Plenty of leaves have no payment or port field at all. Asking for
        # them anyway is how a seller ends up filling in dead values.
        self.assertEqual(by_key["paymentMethod"]["kind"], "unsupported")
        self.assertEqual(by_key["port"]["kind"], "unsupported")


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
