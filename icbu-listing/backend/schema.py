"""Parse, fill and validate the ICBU product schema.

The schema returned by `/alibaba/icbu/product/schema/get` is a rule document:
every field carries `<rules>`, `<options>` and, for composites, a nested
`<fields>` block describing its children.

Values do **not** go into that `<fields>` block. A live product rendered by
`/icbu/product/schema/render` puts them in `<complex-value>` (for `complex`)
and `<complex-values>` (for `multiComplex`), so the document we submit back is
built the same way.

Value conventions used across the app (JSON-serialisable, so drafts can live in
the database):

    input / singleCheck      "USD"  or  {"$value": "//img", "$attrs": {...}}
    multiCheck / multiInput  ["a", "b"]
    complex                  {"child_id": <value>}
    multiComplex             [{"child_id": <value>}, ...]
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator, Mapping
from xml.etree import ElementTree as ET

GENERIC_OPTIONS = {"other", "others", "customized", "custom", "其他", "其它"}
MULTI_VALUE_TYPES = {"multiCheck", "multiInput"}
COMPLEX_TYPES = {"complex", "multiComplex"}
VALUE_KEY = "$value"
ATTRS_KEY = "$attrs"


@dataclass
class SchemaRule:
    name: str
    value: str
    extra: dict[str, str] = field(default_factory=dict)


@dataclass
class SchemaOption:
    value: str
    display_name: str
    extra: dict[str, str] = field(default_factory=dict)


@dataclass
class SchemaField:
    id: str
    name: str
    type: str
    rules: list[SchemaRule] = field(default_factory=list)
    options: list[SchemaOption] = field(default_factory=list)
    children: list["SchemaField"] = field(default_factory=list)

    def rule(self, name: str) -> SchemaRule | None:
        for item in self.rules:
            if item.name == name:
                return item
        return None

    def rules_named(self, name: str) -> list[SchemaRule]:
        return [item for item in self.rules if item.name == name]

    @property
    def required(self) -> bool:
        rule = self.rule("requiredRule")
        return bool(rule and rule.value.lower() == "true")

    @property
    def value_type(self) -> str:
        rule = self.rule("valueTypeRule")
        return rule.value if rule else "text"

    @property
    def max_length(self) -> int | None:
        return _int_rule(self.rule("maxLengthRule"))

    @property
    def length_unit(self) -> str:
        rule = self.rule("maxLengthRule")
        return (rule.extra.get("unit") if rule else None) or "character"

    @property
    def min_items(self) -> int | None:
        return _int_rule(self.rule("minInputNumRule"))

    @property
    def max_items(self) -> int | None:
        return _int_rule(self.rule("maxInputNumRule"))

    @property
    def forbidden_patterns(self) -> list[str]:
        return [
            item.value
            for item in self.rules_named("regexRule")
            if item.extra.get("exProperty") == "not include" and item.value
        ]

    @property
    def supports_custom_value(self) -> bool:
        """Attributes whose tip says a negative `inputValue` is accepted."""
        rule = self.rule("valueAttributeRule")
        return bool(rule and rule.value == "inputValue")

    def child(self, child_id: str) -> "SchemaField | None":
        for item in self.children:
            if item.id == child_id:
                return item
        return None

    def option_by_label(self, label: str) -> SchemaOption | None:
        needle = _normalise(label)
        if not needle:
            return None
        for option in self.options:
            if _normalise(option.display_name) == needle or _normalise(option.value) == needle:
                return option
        # Loose pass. "Other" is never a good guess: picking it silently ships a
        # wrong attribute instead of asking the seller, so it stays opt-in.
        for option in self.options:
            display = _normalise(option.display_name)
            if len(display) < 3 or display in GENERIC_OPTIONS or option.value == "-1":
                continue
            if needle in display or display in needle:
                return option
        return None

    def has_option(self, value: str) -> bool:
        target = str(value)
        return any(option.value == target for option in self.options)


@dataclass
class ValidationIssue:
    field_id: str
    field_name: str
    level: str  # red | yellow
    message: str
    path: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "field_id": self.field_id,
            "field_name": self.field_name,
            "level": self.level,
            "message": self.message,
            "path": self.path or self.field_id,
        }


def _int_rule(rule: SchemaRule | None) -> int | None:
    if rule is None:
        return None
    try:
        return int(rule.value)
    except ValueError:
        return None


def _normalise(text: str) -> str:
    return re.sub(r"[\s/_-]+", "", (text or "").strip().lower())


def _parse_field(node: ET.Element) -> SchemaField:
    rules = [
        SchemaRule(
            name=item.get("name", ""),
            value=item.get("value", ""),
            extra={k: v for k, v in item.attrib.items() if k not in {"name", "value"}},
        )
        for item in node.findall("./rules/rule")
    ]
    options = [
        SchemaOption(
            value=item.get("value", ""),
            display_name=item.get("displayName", ""),
            extra={k: v for k, v in item.attrib.items() if k not in {"value", "displayName"}},
        )
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
    fields = [_parse_field(child) for child in root.findall("./field")]
    if fields:
        return fields
    return [_parse_field(child) for child in root.findall(".//field") if child.get("id")]


def walk_fields(fields: Iterable[SchemaField]) -> Iterator[SchemaField]:
    for item in fields:
        yield item
        yield from walk_fields(item.children)


def index_fields(fields: Iterable[SchemaField]) -> dict[str, SchemaField]:
    """Top-level index. Children are reachable through `SchemaField.child`."""
    return {item.id: item for item in fields}


def required_fields(fields: Iterable[SchemaField]) -> list[SchemaField]:
    return [item for item in walk_fields(fields) if item.required and item.type != "label"]


# --------------------------------------------------------------------------
# building the submitted document
# --------------------------------------------------------------------------


def _leaf(value: Any) -> tuple[str, dict[str, str]]:
    if isinstance(value, Mapping) and VALUE_KEY in value:
        attrs = {str(k): str(v) for k, v in (value.get(ATTRS_KEY) or {}).items()}
        return str(value[VALUE_KEY]), attrs
    if isinstance(value, bool):
        return ("true" if value else "false"), {}
    return str(value), {}


def _write_leaf(parent: ET.Element, value: Any) -> None:
    text, attrs = _leaf(value)
    node = ET.SubElement(parent, "value", attrs)
    node.text = text


def _write_field(parent: ET.Element, spec: SchemaField | None, field_id: str, value: Any) -> None:
    field_type = spec.type if spec else _guess_type(value)
    node = ET.SubElement(parent, "field", {"id": field_id, "type": field_type})

    if field_type == "multiComplex":
        holder = ET.SubElement(node, "complex-values")
        rows = value if isinstance(value, list) else [value]
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            entry = ET.SubElement(holder, "complex-value")
            _write_children(entry, spec, row)
        return

    if field_type == "complex":
        entry = ET.SubElement(node, "complex-value")
        if isinstance(value, Mapping):
            _write_children(entry, spec, value)
        return

    if field_type in MULTI_VALUE_TYPES:
        holder = ET.SubElement(node, "values")
        items = value if isinstance(value, list) else [value]
        for item in items:
            _write_leaf(holder, item)
        return

    _write_leaf(node, value)


def _write_children(parent: ET.Element, spec: SchemaField | None, values: Mapping[str, Any]) -> None:
    for child_id, child_value in values.items():
        if child_value is None:
            continue
        _write_field(parent, spec.child(child_id) if spec else None, child_id, child_value)


def _guess_type(value: Any) -> str:
    if isinstance(value, list):
        if value and isinstance(value[0], Mapping) and VALUE_KEY not in value[0]:
            return "multiComplex"
        return "multiCheck"
    if isinstance(value, Mapping) and VALUE_KEY not in value:
        return "complex"
    return "input"


def build_item_param(fields: Iterable[SchemaField], values: Mapping[str, Any]) -> str:
    """Build the `itemParam` document submitted to schema.add / schema.update."""
    specs = index_fields(fields)
    root = ET.Element("itemParam")
    for field_id, value in values.items():
        if value is None or value == "" or value == [] or value == {}:
            continue
        _write_field(root, specs.get(field_id), field_id, value)
    return '<?xml version="1.0" encoding="UTF-8"?>' + ET.tostring(root, encoding="unicode")


def fill_schema(rule_xml: str, values: Mapping[str, Any]) -> str:
    return build_item_param(parse_schema(rule_xml), values)


# --------------------------------------------------------------------------
# validation — run this before spending an API call
# --------------------------------------------------------------------------


def _length(text: str, unit: str) -> int:
    return len(text.encode("utf-8")) if unit == "byte" else len(text)


def _check_leaf(spec: SchemaField, value: Any, path: str, issues: list[ValidationIssue]) -> None:
    text, _ = _leaf(value)
    limit = spec.max_length
    if limit is not None and _length(text, spec.length_unit) > limit:
        issues.append(
            ValidationIssue(spec.id, spec.name, "red", f"超过 {limit} {spec.length_unit}，当前 {_length(text, spec.length_unit)}", path)
        )
    for pattern in spec.forbidden_patterns:
        try:
            if re.search(pattern, text):
                issues.append(ValidationIssue(spec.id, spec.name, "red", "含平台禁止的字符（中文、@、问号、邮箱或 HTML 标签）", path))
                break
        except re.error:
            continue
    if spec.options and spec.type in {"singleCheck", "multiCheck"}:
        if not spec.has_option(text) and not (spec.supports_custom_value and text.lstrip("-").isdigit() and text.startswith("-")):
            issues.append(ValidationIssue(spec.id, spec.name, "red", f"「{text}」不在平台可选值里", path))
    if spec.value_type in {"double", "long", "integer"} and text:
        try:
            float(text)
        except ValueError:
            issues.append(ValidationIssue(spec.id, spec.name, "red", "必须是数字", path))


def _check_field(spec: SchemaField, value: Any, path: str, issues: list[ValidationIssue]) -> None:
    if spec.type == "label":
        return

    empty = value is None or value == "" or value == [] or value == {}
    if empty:
        if spec.required:
            issues.append(ValidationIssue(spec.id, spec.name or spec.id, "red", "必填项还没有值", path))
        return

    if spec.type == "multiComplex":
        rows = value if isinstance(value, list) else [value]
        limit = spec.max_items
        if limit is not None and len(rows) > limit:
            issues.append(ValidationIssue(spec.id, spec.name, "red", f"最多 {limit} 组，当前 {len(rows)} 组", path))
        for index, row in enumerate(rows):
            if isinstance(row, Mapping):
                _check_children(spec, row, f"{path}[{index}]", issues)
        return

    if spec.type == "complex":
        if isinstance(value, Mapping):
            filled = [k for k, v in value.items() if v not in (None, "", [], {})]
            low = spec.min_items
            high = spec.max_items
            if low is not None and len(filled) < low:
                issues.append(ValidationIssue(spec.id, spec.name, "red", f"至少要 {low} 项，当前 {len(filled)} 项", path))
            if high is not None and len(filled) > high:
                issues.append(ValidationIssue(spec.id, spec.name, "red", f"最多 {high} 项，当前 {len(filled)} 项", path))
            _check_children(spec, value, path, issues)
        return

    if spec.type in MULTI_VALUE_TYPES:
        items = value if isinstance(value, list) else [value]
        for index, item in enumerate(items):
            _check_leaf(spec, item, f"{path}[{index}]", issues)
        return

    _check_leaf(spec, value, path, issues)


def _check_children(spec: SchemaField, values: Mapping[str, Any], path: str, issues: list[ValidationIssue]) -> None:
    for child in spec.children:
        _check_field(child, values.get(child.id), f"{path}.{child.id}", issues)
    for child_id, child_value in values.items():
        child = spec.child(child_id)
        if child is None and child_value not in (None, "", [], {}):
            issues.append(ValidationIssue(child_id, child_id, "yellow", "该类目没有这个字段，提交时会被忽略", f"{path}.{child_id}"))


def _read_leaf(node: ET.Element) -> Any:
    value_node = node.find("./value")
    if value_node is None:
        return None
    text = (value_node.text or "").strip()
    attrs = {key: val for key, val in value_node.attrib.items() if val}
    if attrs:
        return {VALUE_KEY: text, ATTRS_KEY: attrs}
    return text


def _read_field(node: ET.Element) -> Any:
    field_type = node.get("type") or ""
    if field_type == "multiComplex":
        rows = []
        for entry in node.findall("./complex-values/complex-value"):
            row = {child.get("id", ""): _read_field(child) for child in entry.findall("./field") if child.get("id")}
            rows.append({key: val for key, val in row.items() if val not in (None, "", [], {})})
        return rows
    if field_type == "complex":
        entry = node.find("./complex-value")
        if entry is None:
            return {}
        return {
            child.get("id", ""): _read_field(child)
            for child in entry.findall("./field")
            if child.get("id") and _read_field(child) not in (None, "", [], {})
        }
    if field_type in MULTI_VALUE_TYPES:
        items = []
        for value_node in node.findall("./values/value"):
            text = (value_node.text or "").strip()
            if text:
                items.append(text)
        return items
    return _read_leaf(node)


def extract_values(xml_text: str) -> dict[str, Any]:
    """Read a rendered schema (with values) back into the draft JSON shape."""
    if not (xml_text or "").strip():
        return {}
    root = ET.fromstring(xml_text)
    values: dict[str, Any] = {}
    for node in root.findall("./field"):
        field_id = node.get("id") or ""
        if not field_id or node.get("type") == "label":
            continue
        extracted = _read_field(node)
        if extracted not in (None, "", [], {}):
            values[field_id] = extracted
    return values


def validate_values(fields: Iterable[SchemaField], values: Mapping[str, Any]) -> list[ValidationIssue]:
    """Check a draft against the category rules before calling schema.add."""
    issues: list[ValidationIssue] = []
    for spec in fields:
        _check_field(spec, values.get(spec.id), spec.id, issues)
    return issues
