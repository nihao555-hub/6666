"""Listing templates: fill empty fields, never overwrite what a person wrote.

Lingxing's documented rule, and the one we follow:

    template empty + draft filled  → keep the draft
    template filled + draft filled → keep the draft
    template filled + draft empty  → take the template
    both empty                     → leave empty

A template is scoped to one shop and one leaf category. Trade terms that do
not change between products (origin, logistics, sample policy, freight) live
here; titles, images and prices do not.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from sqlalchemy.orm import Session

from ..models import Template

PROTECTED = {
    "productTitle",
    "productKeywords",
    "scImages",
    "detailImage",
    "textDesc",
    "ladderPrice",
    "fob",
    "scPrice",
    "minOrderQuantity",
    "catId",
}


def fill_blank(template: Mapping[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    """Return a new values dict: template fills holes, never overwrites."""
    merged = dict(draft)
    for key, value in template.items():
        if key in PROTECTED or key.startswith("_"):
            continue
        current = merged.get(key)
        if _empty(current):
            merged[key] = value
        elif isinstance(value, dict) and isinstance(current, dict):
            merged[key] = fill_blank(value, current)
    return merged


def _empty(value: Any) -> bool:
    return value in (None, "", [], {})


def find_for(db: Session, shop_id: str, category_id: str) -> Template | None:
    if not shop_id or not category_id:
        return None
    return (
        db.query(Template)
        .filter(Template.shop_id == shop_id, Template.category_id == category_id)
        .order_by(Template.created_at.desc())
        .first()
    )


def values_of(template: Template) -> dict[str, Any]:
    try:
        payload = json.loads(template.values_json or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def apply_to_values(db: Session, shop_id: str, category_id: str, values: Mapping[str, Any]) -> dict[str, Any]:
    template = find_for(db, shop_id, category_id)
    if template is None:
        return dict(values)
    return fill_blank(values_of(template), dict(values))


def as_dict(template: Template) -> dict[str, Any]:
    return {
        "id": template.id,
        "shop_id": template.shop_id,
        "name": template.name,
        "category_id": template.category_id,
        "values": values_of(template),
        "is_auto": template.is_auto,
        "created_at": template.created_at.isoformat(),
    }
