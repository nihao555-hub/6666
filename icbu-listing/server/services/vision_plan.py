"""Analyze uploaded product photos to inform smart-plan column selection."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any, Mapping, Sequence

from ai import AiClient, AiUnavailable, ImageInput, Understanding  # noqa: E402

MAX_GROUPS = 5
MAX_IMAGES_PER_GROUP = 6

_VISION_ATTR_HINTS: list[tuple[re.Pattern[str], tuple[str, ...]]] = [
    (re.compile(r"材质|材料|material", re.I), ("material", "材质", "材料")),
    (re.compile(r"类型|type|款式|style", re.I), ("type", "类型", "款式")),
    (re.compile(r"色数|color count|pieces|支数|count", re.I), ("color count", "色数", "支数")),
    (re.compile(r"颜色|color", re.I), ("color", "颜色", "色彩")),
    (re.compile(r"硬度|hardness", re.I), ("hardness", "硬度")),
    (re.compile(r"规格|尺寸|size", re.I), ("size", "规格", "尺寸")),
]


def _group_key(filename: str) -> str:
    name = (filename or "product").replace("\\", "/")
    parts = [part for part in name.split("/") if part and part != "."]
    if len(parts) >= 2:
        return parts[-2]
    stem = parts[-1].rsplit(".", 1)[0] if parts else "product"
    return stem or "product"


def understanding_to_dict(u: Understanding, *, group: str = "", image_count: int = 0) -> dict[str, Any]:
    return {
        "group": group,
        "image_count": image_count,
        "product_name": u.product_name,
        "category_hint": u.category_hint,
        "material": u.material,
        "colors": list(u.colors or []),
        "style": u.style,
        "usage": u.usage,
        "features": list(u.features or []),
        "specs": dict(u.specs or {}),
        "confidence": u.confidence,
    }


def analyze_images_for_plan(
    ai: AiClient | None,
    uploads: Sequence[tuple[str, bytes]],
    bank_images: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Run vision on grouped uploads + photobank URLs. Returns sample dicts per SKU group."""
    if ai is None:
        return []
    groups: dict[str, list[tuple[str, bytes]]] = defaultdict(list)
    for name, content in uploads:
        if not content:
            continue
        key = _group_key(name)
        groups[key].append((name, content))
    samples: list[dict[str, Any]] = []
    for group_key, files in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))[:MAX_GROUPS]:
        inputs = [ImageInput(filename=name, content=content) for name, content in files[:MAX_IMAGES_PER_GROUP]]
        try:
            understanding = ai.understand(inputs, hint=f"Batch SKU group: {group_key}")
        except (AiUnavailable, ValueError, TypeError):
            continue
        samples.append(understanding_to_dict(understanding, group=group_key, image_count=len(files)))
    bank = [item for item in (bank_images or []) if str(item.get("url") or "").strip()]
    if bank:
        inputs = [
            ImageInput(
                filename=str(item.get("file_name") or "bank.jpg"),
                url=str(item.get("url") or ""),
            )
            for item in bank[:MAX_IMAGES_PER_GROUP]
        ]
        try:
            understanding = ai.understand(inputs, hint="Selected from shop photobank")
            samples.append(
                understanding_to_dict(
                    understanding,
                    group="photobank",
                    image_count=len(bank),
                )
            )
        except (AiUnavailable, ValueError, TypeError):
            pass
    return samples


def vision_summary_text(samples: Sequence[Mapping[str, Any]]) -> str:
    if not samples:
        return ""
    compact = []
    for item in samples:
        bit = {
            "group": item.get("group"),
            "product_name": item.get("product_name"),
            "category_hint": item.get("category_hint"),
            "material": item.get("material"),
            "colors": item.get("colors"),
            "features": item.get("features"),
            "specs": item.get("specs"),
            "confidence": item.get("confidence"),
        }
        compact.append({key: value for key, value in bit.items() if value})
    return json.dumps(compact, ensure_ascii=False)


def attr_ids_covered_by_vision(
    candidates: Sequence[Mapping[str, Any]],
    samples: Sequence[Mapping[str, Any]],
) -> set[str]:
    """Required attr columns vision already resolved — skip on download sheet."""
    if not samples:
        return set()
    blob = vision_summary_text(samples).lower()
    covered: set[str] = set()
    for col in candidates:
        col_id = str(col.get("id") or "")
        if not col_id.startswith("attr."):
            continue
        label = str(col.get("label") or col.get("header") or "")
        for pattern, tokens in _VISION_ATTR_HINTS:
            if not pattern.search(label):
                continue
            for token in tokens:
                if token.lower() in blob:
                    covered.add(col_id)
                    break
    return covered
