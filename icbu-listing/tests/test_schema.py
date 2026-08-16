import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from schema import fill_schema, parse_schema, required_fields

SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<itemSchema>
  <field id="productTitle" name="Product name" type="input">
    <rules>
      <rule name="requiredRule" value="true"/>
      <rule name="maxLengthRule" value="128" exProperty="include" unit="byte"/>
    </rules>
  </field>
  <field id="priceUnit" name="Unit" type="singleCheck">
    <rules>
      <rule name="requiredRule" value="true"/>
    </rules>
    <options>
      <option displayName="Piece/Pieces" value="17"/>
      <option displayName="Bag/Bags" value="1"/>
    </options>
  </field>
  <field id="predefined_method" type="multiCheck">
    <options>
      <option displayName="T/T." value="T/T"/>
      <option displayName="L/C." value="L/C"/>
    </options>
  </field>
</itemSchema>
"""


class SchemaTests(unittest.TestCase):
    def test_parse_required_and_options(self) -> None:
        fields = parse_schema(SAMPLE)
        by_id = {item.id: item for item in fields}
        self.assertTrue(by_id["productTitle"].required)
        self.assertEqual(by_id["productTitle"].max_length, 128)
        self.assertEqual(by_id["priceUnit"].option_by_label("Piece/Pieces").value, "17")
        self.assertEqual([item.id for item in required_fields(fields)], ["productTitle", "priceUnit"])

    def test_fill_input_and_multicheck(self) -> None:
        xml = fill_schema(
            SAMPLE,
            {
                "productTitle": "Stainless Steel Water Bottle Wholesale",
                "priceUnit": "17",
                "predefined_method": ["T/T", "L/C"],
            },
        )
        self.assertIn("<itemParam>", xml)
        self.assertIn("Stainless Steel Water Bottle Wholesale", xml)
        self.assertIn("<value>17</value>", xml)
        self.assertIn("<value>T/T</value>", xml)
        self.assertIn("<value>L/C</value>", xml)


if __name__ == "__main__":
    unittest.main()
