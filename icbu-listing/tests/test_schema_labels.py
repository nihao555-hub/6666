import unittest

from server.services import schema_labels


class SchemaLabelTests(unittest.TestCase):
    def test_group_and_field_names_translate_to_chinese(self) -> None:
        self.assertEqual(schema_labels.group_label("icbuCatProp", "Product feature"), "类目属性")
        self.assertEqual(schema_labels.field_label("p-type", "Type"), "类型")
        self.assertEqual(
            schema_labels.header_label("icbuCatProp", "Product feature", "p-type", "Lead Color"),
            "类目属性 / 铅芯颜色",
        )

    def test_field_ids_with_suffixes(self) -> None:
        self.assertEqual(schema_labels.field_label("ladderPrice_0", "ladderPrice_0"), "阶梯价第 1 档")
        self.assertEqual(schema_labels.field_label("customMoreProperty_3", "x"), "自定义属性 4")

    def test_field_type_labels(self) -> None:
        self.assertEqual(schema_labels.field_type_label("multiCheck"), "多选")
        self.assertEqual(schema_labels.field_type_label("singleCheck"), "单选")


if __name__ == "__main__":
    unittest.main()
