"""Parse and fill ICBU product schema XML.

Official schema types: input, multiInput, singleCheck, multiCheck,
complex, multiComplex, label.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping
from xml.etree import ElementTree as ET


@dataclass
class SchemaRule:
    name: str
    value: str
    extra: dict[str, str] = field(default_factory=dict)


@dataclass
class SchemaOption:
    value: str
    display_name: str


@dataclass
class SchemaField:
    id: str
    name: str
    type: str
    rules: list[SchemaRule] = field(default_factory=list)
    options: list[SchemaOption] = field(default_factory=list)
    children: list["SchemaField"] = field(default_factory=list)

    @property
    def required(self) -> bool:
        return any(rule.name == "requiredRule" and rule.value.lower() == "true" for rule in self.rules)

    @property
    def max_length(self) -> int | None:
        for rule in self.rules:
            if rule.name == "maxLengthRule":
                try:
                    return int(rule.value)
                except ValueError:
                    return None
        return None

    def option_by_label(self, label: str) -> SchemaOption | None:
        needle = label.strip().lower()
        for option in self.options:
            if option.display_name.lower() == needle or option.value.lower() == needle:
                return option
        return None


def _text(node: ET.Element | None, default: str = "") -> str:
    if node is None or node.text is None:
        return default
    return node.text


def _parse_field(node: ET.Element) -> SchemaField:
    rules = [
        SchemaRule(name=item.get("name", ""), value=item.get("value", ""), extra={k: v for k, v in item.attrib.items() if k not in {"name", "value"}})
        for item in node.findall("./rules/rule")
    ]
    options = [
        SchemaOption(value=item.get("value", ""), display_name=item.get("displayName", ""))
        for item in node.findall("./options/option")
    ]
    children = [_parse_field(child) for child in node.findall("./fields/field")]
    return SchemaField(
        id=node.get("id", ""),
        name=node.get("name", ""),
        type=node.get("type", "input"),
        rules=rules,
        options=options,
        children=children,
    )


def parse_schema(xml_text: str) -> list[SchemaField]:
    root = ET.fromstring(xml_text)
    if root.tag.endswith("itemSchema") or root.tag == "itemSchema":
        return [_parse_field(child) for child in root.findall("./field")]
    if root.tag.endswith("itemParam") or root.tag == "itemParam":
        return [_parse_field(child) for child in root.findall("./field")]
    return [_parse_field(child) for child in root.findall(".//field") if child.get("id")]


def flatten_fields(fields: Iterable[SchemaField]) -> list[SchemaField]:
    out: list[SchemaField] = []
    for item in fields:
        out.append(item)
        out.extend(flatten_fields(item.children))
    return out


def required_fields(fields: Iterable[SchemaField]) -> list[SchemaField]:
    return [item for item in flatten_fields(fields) if item.required and item.type != "label"]


def walk_set(parent: ET.Element, field_id: str, value: Any) -> bool:
    for node in parent.findall(".//field"):
        if node.get("id") != field_id:
            continue
        field_type = node.get("type", "input")
        if field_type in {"multiCheck", "multiInput"}:
            values = node.find("values")
            if values is None:
                values = ET.SubElement(node, "values")
            else:
                for child in list(values):
                    values.remove(child)
            items = value if isinstance(value, list) else [value]
            for item in items:
                leaf = ET.SubElement(values, "value")
                leaf.text = str(item)
        else:
            leaf = node.find("value")
            if leaf is None:
                leaf = ET.SubElement(node, "value")
            leaf.text = str(value)
        return True
    return False


def fill_schema(rule_xml: str, values: Mapping[str, Any]) -> str:
    root = ET.fromstring(rule_xml)
    container = root if root.tag in {"itemSchema", "itemParam"} or root.tag.endswith("itemSchema") else root
    for field_id, value in values.items():
        walk_set(container, field_id, value)
    if root.tag.endswith("itemSchema") or root.tag == "itemSchema":
        root.tag = "itemParam"
    return ET.tostring(root, encoding="unicode")
