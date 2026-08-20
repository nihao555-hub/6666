"""Human audit gate for AI-filled drafts.

AI will mis-pick a leaf, map the wrong official option, or write a title
that does not match the photo. Red/yellow issues only catch schema holes.
This layer makes a person open the draft, edit what is wrong, and mark it
reviewed before anything can enter the publish queue.

Review is orthogonal to red/yellow/green:

    red      still blocks publish, even if reviewed
    yellow   publishable only after review and local quality 5.0
    green    publishable only after review and local quality 5.0

Regenerate and category change wipe the review, because AI rewrote fields.
A hand edit after review keeps the stamp: the person just corrected it.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Mapping

from . import quality, sources

COPY_FIELDS = (
    ("productTitle", "英文标题", "textarea"),
    ("productKeywords", "关键词", "keywords"),
    ("textDesc", "卖点描述", "textarea"),
)

ATTR_GROUPS = (
    ("icbuCatProp", "类目属性"),
    ("saleProp", "规格"),
)

UNPUBLISHABLE = {"red", "publishing"}


def parse(raw: str | None) -> dict[str, Any]:
    try:
        payload = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def dump(payload: Mapping[str, Any]) -> str:
    return json.dumps(dict(payload), ensure_ascii=False)


def is_reviewed(draft: Any) -> bool:
    return bool(getattr(draft, "reviewed_at", None))


def view(draft: Any) -> dict[str, Any]:
    payload = parse(getattr(draft, "audit_json", None))
    reviewed_at = getattr(draft, "reviewed_at", None)
    return {
        "reviewed": bool(reviewed_at),
        "reviewed_at": reviewed_at.isoformat() if reviewed_at else None,
        "note": str(payload.get("note") or ""),
        "cleared_reason": str(payload.get("cleared_reason") or ""),
    }


def mark_reviewed(draft: Any, note: str = "") -> None:
    draft.reviewed_at = datetime.utcnow()
    payload = parse(getattr(draft, "audit_json", None))
    payload["reviewed"] = True
    payload["note"] = (note or "").strip()
    payload.pop("cleared_reason", None)
    draft.audit_json = dump(payload)


def clear_review(draft: Any, reason: str = "regenerate") -> None:
    draft.reviewed_at = None
    payload = parse(getattr(draft, "audit_json", None))
    payload["reviewed"] = False
    payload["cleared_reason"] = reason
    draft.audit_json = dump(payload)


def has_red(issues: Any) -> bool:
    if not isinstance(issues, list):
        return False
    return any(str(item.get("level")) == "red" for item in issues if isinstance(item, Mapping))


def can_publish(draft: Any, issues: list[Mapping[str, Any]] | None = None) -> tuple[bool, str]:
    status = str(getattr(draft, "status", "") or "")
    if issues is None:
        issues = parse_issues(getattr(draft, "issues_json", None))
    if status == "red" or has_red(issues):
        return False, "还有红项没改完，先打开商品改掉再发"
    if status == "publishing":
        return False, "这条正在发布"
    if not is_reviewed(draft):
        return False, "AI 填的还没人核对。打开商品看一眼，改完点「审过了」再发"
    ok, reason = quality.quality_ready(draft)
    if not ok:
        return False, reason
    return True, ""


def parse_issues(raw: str | None) -> list[Mapping[str, Any]]:
    try:
        payload = json.loads(raw or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    return payload if isinstance(payload, list) else []


def form_fields(
    xml: str,
    values: Mapping[str, Any],
    field_sources: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Editable AI / attribute fields a person must be able to correct."""
    from schema import parse_schema  # noqa: E402

    specs = {item.id: item for item in parse_schema(xml)}
    origins = dict(field_sources or {})
    fields: list[dict[str, Any]] = []

    for field_id, name, kind in COPY_FIELDS:
        fields.append(
            _field(
                field_id=field_id,
                name=name,
                kind=kind,
                required=field_id == "productTitle",
                value=_copy_value(values.get(field_id), kind),
                origin=origins.get(field_id, "ai"),
                options=[],
            )
        )

    for group_id, group_name in ATTR_GROUPS:
        group = specs.get(group_id)
        if group is None:
            continue
        group_values = values.get(group_id) if isinstance(values.get(group_id), Mapping) else {}
        origin = origins.get(group_id, "ai")
        for child in group.children:
            if child.type == "label":
                continue
            kind = "select" if child.options else "input"
            if child.type in {"multiCheck", "multiInput"}:
                kind = "multiselect" if child.options else "input"
            fields.append(
                _field(
                    field_id=child.id,
                    name=child.name,
                    kind=kind,
                    required=child.required,
                    value=group_values.get(child.id, ""),
                    origin=origin,
                    options=[{"value": option.value, "label": option.display_name} for option in child.options[:200]],
                    group=group_id,
                    group_name=group_name,
                )
            )

    brand = specs.get("brand")
    if brand is not None:
        fields.append(
            _field(
                field_id="brand",
                name=brand.name or "品牌",
                kind="select" if brand.options else "input",
                required=brand.required,
                value=values.get("brand", ""),
                origin=origins.get("brand", "shop"),
                options=[{"value": option.value, "label": option.display_name} for option in brand.options[:200]],
                group="",
                group_name="品牌",
            )
        )
    return fields


def _copy_value(value: Any, kind: str) -> Any:
    if kind == "keywords" and isinstance(value, Mapping):
        return ", ".join(str(item) for item in value.values() if item)
    return value if value is not None else ""


def _field(
    *,
    field_id: str,
    name: str,
    kind: str,
    required: bool,
    value: Any,
    origin: str,
    options: list[dict[str, str]],
    group: str = "",
    group_name: str = "",
) -> dict[str, Any]:
    return {
        "id": field_id,
        "group": group,
        "group_name": group_name,
        "name": name,
        "kind": kind,
        "required": required,
        "value": value,
        "source": {
            "origin": origin,
            "label": sources.LABELS.get(origin, origin),
            "locked": origin in sources.LOCKED,
        },
        "options": options,
    }
