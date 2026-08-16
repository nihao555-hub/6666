"""The schema layer is what keeps us from posting rubbish to Alibaba.

The fixtures below mirror the real shape returned by
`/alibaba/icbu/product/schema/get` for category 21110712: composites carry their
children under `<fields>`, and the values we submit go into `<complex-value>`.
"""

import sys
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from schema import (  # noqa: E402
    build_item_param,
    extract_values,
    index_fields,
    parse_schema,
    validate_values,
)

SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<itemSchema>
  <field id="productTitle" name="Product name" type="input">
    <rules>
      <rule name="requiredRule" value="true"/>
      <rule name="maxLengthRule" value="40" exProperty="include" unit="byte"/>
      <rule name="regexRule" value="[^\\x04-\\x80]+|[@!?]" exProperty="not include"/>
    </rules>
  </field>
  <field id="priceUnit" name="Unit" type="singleCheck">
    <rules><rule name="requiredRule" value="true"/></rules>
    <options>
      <option displayName="Piece/Pieces" value="17"/>
      <option displayName="Set/Sets" value="4"/>
    </options>
  </field>
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
        <options>
          <option displayName="colored" value="12970290"/>
          <option displayName="other" value="-1"/>
        </options>
      </field>
    </fields>
  </field>
  <field id="ladderPrice" name="Quantity price" type="complex">
    <fields>
      <field id="ladderPrice_0" type="complex">
        <fields>
          <field id="quantity" name="MOQ" type="input">
            <rules><rule name="valueTypeRule" value="long"/><rule name="requiredRule" value="true"/></rules>
          </field>
          <field id="price" name="Price" type="input">
            <rules><rule name="valueTypeRule" value="double"/><rule name="requiredRule" value="true"/></rules>
          </field>
        </fields>
      </field>
    </fields>
  </field>
  <field id="detailImage" name="Details" type="multiComplex">
    <rules><rule name="requiredRule" value="true"/></rules>
    <fields>
      <field id="gallery" name="gallery" type="singleCheck">
        <rules><rule name="requiredRule" value="true"/></rules>
        <options><option displayName="Detail shot" value="300"/></options>
      </field>
    </fields>
  </field>
</itemSchema>
"""

FIELDS = parse_schema(SAMPLE)
SPECS = index_fields(FIELDS)


class ParseTests(unittest.TestCase):
    def test_children_come_from_the_rule_block(self) -> None:
        group = SPECS["icbuCatProp"]
        self.assertEqual([child.id for child in group.children], ["p-1", "p-9"])
        self.assertTrue(group.child("p-1").required)

    def test_byte_limit_and_unit_are_kept(self) -> None:
        title = SPECS["productTitle"]
        self.assertEqual(title.max_length, 40)
        self.assertEqual(title.length_unit, "byte")

    def test_option_lookup_is_case_and_space_insensitive(self) -> None:
        self.assertEqual(SPECS["priceUnit"].option_by_label("piece / pieces").value, "17")

    def test_other_is_never_a_fuzzy_match(self) -> None:
        # Silently choosing "other" ships a wrong attribute instead of asking.
        self.assertIsNone(SPECS["icbuCatProp"].child("p-9").option_by_label("matte black"))


class BuildTests(unittest.TestCase):
    def _build(self) -> ET.Element:
        xml = build_item_param(
            FIELDS,
            {
                "productTitle": "Colored Pencil Set",
                "priceUnit": "17",
                "icbuCatProp": {"p-1": "100000458", "p-9": ["12970290"]},
                "ladderPrice": {"ladderPrice_0": {"quantity": "500", "price": "1.80"}},
                "detailImage": [{"gallery": "300"}],
            },
        )
        return ET.fromstring(xml)

    def test_root_is_item_param(self) -> None:
        self.assertEqual(self._build().tag, "itemParam")

    def test_composite_values_go_into_complex_value(self) -> None:
        root = self._build()
        group = root.find("./field[@id='icbuCatProp']")
        origin = group.find("./complex-value/field[@id='p-1']/value")
        self.assertEqual(origin.text, "100000458")
        # and not into the rule block
        self.assertIsNone(group.find("./fields"))

    def test_multi_check_uses_a_values_wrapper(self) -> None:
        colors = self._build().find("./field[@id='icbuCatProp']/complex-value/field[@id='p-9']")
        self.assertEqual([node.text for node in colors.findall("./values/value")], ["12970290"])

    def test_nested_composites_survive(self) -> None:
        quantity = self._build().find(
            "./field[@id='ladderPrice']/complex-value/field[@id='ladderPrice_0']/complex-value/field[@id='quantity']/value"
        )
        self.assertEqual(quantity.text, "500")

    def test_multi_complex_uses_complex_values(self) -> None:
        rows = self._build().findall("./field[@id='detailImage']/complex-values/complex-value")
        self.assertEqual(len(rows), 1)

    def test_rendered_values_round_trip(self) -> None:
        xml = build_item_param(
            FIELDS,
            {
                "productTitle": "Colored Pencil Set",
                "priceUnit": "17",
                "icbuCatProp": {"p-1": "100000458", "p-9": ["12970290"]},
                "ladderPrice": {"ladderPrice_0": {"quantity": "500", "price": "1.80"}},
            },
        )
        values = extract_values(xml)
        self.assertEqual(values["productTitle"], "Colored Pencil Set")
        self.assertEqual(values["icbuCatProp"]["p-1"], "100000458")
        self.assertEqual(values["icbuCatProp"]["p-9"], ["12970290"])
        self.assertEqual(values["ladderPrice"]["ladderPrice_0"]["price"], "1.80")

    def test_image_file_id_is_carried_as_an_attribute(self) -> None:
        xml = build_item_param(
            parse_schema('<itemSchema><field id="scImages" type="complex"><fields>'
                         '<field id="scImages_0" type="input"/></fields></field></itemSchema>'),
            {"scImages": {"scImages_0": {"$value": "//sc04.alicdn.com/a.png", "$attrs": {"fileId": "123"}}}},
        )
        node = ET.fromstring(xml).find("./field[@id='scImages']/complex-value/field[@id='scImages_0']/value")
        self.assertEqual(node.get("fileId"), "123")
        self.assertEqual(node.text, "//sc04.alicdn.com/a.png")


class ValidationTests(unittest.TestCase):
    def _messages(self, values: dict) -> list[str]:
        return [f"{issue.path}:{issue.message}" for issue in validate_values(FIELDS, values)]

    def test_missing_required_fields_are_reported(self) -> None:
        issues = validate_values(FIELDS, {})
        self.assertEqual(
            {issue.field_id for issue in issues if issue.level == "red"},
            {"productTitle", "priceUnit", "detailImage"},
        )

    def test_byte_limit_counts_bytes_not_characters(self) -> None:
        long_title = "A" * 41
        self.assertTrue(any("超过 40 byte" in message for message in self._messages({"productTitle": long_title})))

    def test_chinese_in_the_title_is_blocked(self) -> None:
        messages = self._messages({"productTitle": "彩色铅笔"})
        self.assertTrue(any("平台禁止的字符" in message for message in messages))

    def test_value_outside_the_option_list_is_blocked(self) -> None:
        messages = self._messages({"priceUnit": "9999"})
        self.assertTrue(any("不在平台可选值里" in message for message in messages))

    def test_required_child_of_a_present_composite_is_checked(self) -> None:
        messages = self._messages({"icbuCatProp": {"p-9": ["12970290"]}})
        self.assertTrue(any("icbuCatProp.p-1" in message for message in messages))

    def test_a_complete_draft_is_clean(self) -> None:
        issues = validate_values(
            FIELDS,
            {
                "productTitle": "Colored Pencil Set for Students",
                "priceUnit": "17",
                "icbuCatProp": {"p-1": "100000458"},
                "detailImage": [{"gallery": "300"}],
            },
        )
        self.assertEqual([issue.as_dict() for issue in issues], [])


if __name__ == "__main__":
    unittest.main()
