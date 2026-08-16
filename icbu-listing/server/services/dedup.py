"""Repeat-listing risk check.

Alibaba groups listings it considers duplicates by title, attributes and images
together, then shows only one of them and can demote the whole shop. Every
batch listing tool still sells "publish more variations of the same thing", so
warning before submission is worth more than publishing faster.

This is intentionally a local heuristic on what we already stored: it flags the
pairs a seller should look at, it does not claim to reproduce the platform's
classifier.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from sqlalchemy.orm import Session

from ..models import Draft

STOPWORDS = {
    "for", "with", "and", "the", "of", "in", "on", "a", "an", "to",
    "wholesale", "high", "quality", "hot", "sale", "new", "custom", "professional",
}
RISK_HIGH = 0.82
RISK_MEDIUM = 0.62


@dataclass
class DuplicateRisk:
    level: str  # high | medium | low
    score: float
    against: str  # the other draft's sku or id
    reason: str

    def as_issue(self) -> dict[str, Any]:
        return {
            "field_id": "dedup",
            "field_name": "重复铺货风险",
            "level": "red" if self.level == "high" else "yellow",
            "message": f"和「{self.against}」{self.reason}（相似度 {self.score:.0%}）。"
            "平台会把重铺组折叠成一条，严重的会整店降权。",
            "path": "dedup",
        }


def tokenise(title: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (title or "").lower())
    return {word for word in words if word not in STOPWORDS and len(word) > 2}


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def attribute_fingerprint(values: Mapping[str, Any]) -> str:
    parts = []
    for group in ("icbuCatProp", "saleProp"):
        block = values.get(group)
        if isinstance(block, Mapping):
            for key in sorted(block):
                parts.append(f"{key}={json.dumps(block[key], sort_keys=True, ensure_ascii=False)}")
    return "|".join(parts)


def compare(
    title: str,
    category_id: str,
    values: Mapping[str, Any],
    other_title: str,
    other_category_id: str,
    other_values: Mapping[str, Any],
) -> tuple[float, str]:
    if category_id and other_category_id and category_id != other_category_id:
        return 0.0, ""

    title_score = jaccard(tokenise(title), tokenise(other_title))
    same_attributes = bool(attribute_fingerprint(values)) and attribute_fingerprint(values) == attribute_fingerprint(
        other_values
    )

    if same_attributes and title_score >= 0.4:
        # The platform's own guidance: identical attributes plus a reworded
        # title is still one product to them.
        return max(title_score, RISK_HIGH), "类目和全部属性都一样，只是标题措辞不同"
    if title_score >= RISK_HIGH:
        return title_score, "标题几乎重复"
    if title_score >= RISK_MEDIUM:
        return title_score, "标题高度相似"
    return title_score, ""


def check(db: Session, draft: Draft, limit: int = 300) -> DuplicateRisk | None:
    """Compare one draft against the rest of the same shop."""
    values = _load(draft.values_json, {})
    title = str(values.get("productTitle") or draft.title or "")
    if not title:
        return None

    siblings: Iterable[Draft] = (
        db.query(Draft)
        .filter(
            Draft.shop_id == draft.shop_id,
            Draft.id != draft.id,
            Draft.category_id == draft.category_id,
        )
        .order_by(Draft.updated_at.desc())
        .limit(limit)
        .all()
    )

    best: DuplicateRisk | None = None
    for other in siblings:
        other_values = _load(other.values_json, {})
        score, reason = compare(
            title,
            draft.category_id,
            values,
            str(other_values.get("productTitle") or other.title or ""),
            other.category_id,
            other_values,
        )
        if not reason:
            continue
        level = "high" if score >= RISK_HIGH else "medium"
        if best is None or score > best.score:
            best = DuplicateRisk(level=level, score=score, against=other.sku or other.id[:8], reason=reason)
    return best


def _load(raw: str, fallback: Any) -> Any:
    try:
        return json.loads(raw or "")
    except (json.JSONDecodeError, TypeError):
        return fallback
