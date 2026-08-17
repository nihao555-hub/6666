"""Assemble listing prompts from buluslan/gpt-image2-ecommerce (312★).

The skill's rule: keep the prompt short. Take prompt_template + defaults +
one category tip, then add only the ICBU red lines (no fake marks, square,
wholesale carton instead of luxury gift wrap).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

SKILL = {
    "repo": "buluslan/gpt-image2-ecommerce",
    "url": "https://github.com/buluslan/gpt-image2-ecommerce",
    "stars": 312,
    "took": "6 个国际站坑位对应它的主图/尺寸/细节/场景/包装/卖点模板，灯光构图写短，按类目加一条材质",
}

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "vendor" / "ecom-image-skill" / "templates"

SLOT_FILE = {
    "main": "01-hero-image.json",
    "range": "03-flat-lay.json",
    "scale": "13-size-spec.json",
    "detail": "04-detail-macro.json",
    "use": "02-lifestyle-scene.json",
    "pack": "10-packaging.json",
    "custom": "11-infographic.json",
}

FAMILY_TIP_KEY = {
    "stationery": "home",
    "tools": "electronics",
    "electronics": "electronics",
    "apparel": "fashion",
    "beauty": "beauty",
    "home": "home",
    "toys": "home",
    "jewelry": "jewelry",
    "industrial": "electronics",
    "food": "food",
    "sports": "home",
    "general": "home",
}

ICBU_GUARD = (
    "Alibaba.com wholesale listing, square 1:1. "
    "No Amazon or Prime badges, no star ratings, no prices, no watermarks, "
    "no fake CE/ISO/FDA marks, no invented accessories."
)


@lru_cache(maxsize=16)
def load_template(filename: str) -> dict[str, Any]:
    path = TEMPLATES_DIR / filename
    return json.loads(path.read_text(encoding="utf-8"))


def _fill(text: Any, values: Mapping[str, str]) -> str:
    if text is None:
        return ""
    out = str(text)
    for key, value in values.items():
        out = out.replace("{" + key + "}", value)
    if "{" in out and "}" in out:
        return ""
    return " ".join(out.split())


def assemble_prompt(
    slot_id: str,
    *,
    product: str,
    family_id: str = "",
    material: str = "",
    colors: Sequence[str] | None = None,
    features: Sequence[str] | None = None,
    usage: str = "",
    note: str = "",
    text_policy: str = "none",
) -> str:
    filename = SLOT_FILE.get(slot_id) or SLOT_FILE["main"]
    template = load_template(filename)
    values = {
        "product_description": product,
        "product": product,
        "material_description": material or "the real material",
        "scene_description": usage or "typical wholesale use",
        "composition_style": "product as the focal point",
        "mood_description": "honest catalog, not luxury advertising",
        "focus_area": material or "texture and material quality",
        "texture_description": material or "true surface finish",
        "lighting_style": "soft directional lighting highlighting texture",
        "camera_setup": "studio macro setup",
        "size_annotations": "only real measurements if known, otherwise omit numbers",
        "usage_steps": "do not invent steps",
        "additional_info": note or "",
        "packaging_components": "export carton and inner box",
        "feature_list": ", ".join(str(item) for item in (features or [])[:4]) or "only verified selling points",
        "data_elements": "none",
        "brand_colors": "neutral studio",
        "prop_list": "none unless they ship in the box",
        "background_material": "clean white",
        "color_scheme": ", ".join(str(item) for item in (colors or [])[:4]) or "true product colors",
    }
    fields = dict(template.get("defaults") or {})
    fields.update(template.get("prompt_template") or {})
    if slot_id == "main":
        fields["background"] = "pure white seamless background"
        fields["composition"] = "centered, front view, product fills most of the frame"
        fields["lighting"] = "soft diffused studio lighting, even illumination"
    elif slot_id == "range":
        fields["background"] = "clean white surface"
        fields["props"] = "the full color or size range only"
    elif slot_id == "pack":
        fields["display"] = "export carton and inner box, honest factory packing"
        fields["surface"] = "clean warehouse floor or white studio"
        fields["decorative"] = "none"
        fields["lighting"] = "even warehouse or studio light"
    elif slot_id == "custom":
        fields["features"] = values["feature_list"]
        fields["data_vis"] = "no charts, no certification badges"
        fields["layout"] = "product centered, short English feature labels only"

    bits: list[str] = []
    for key in (
        "type",
        "subject",
        "background",
        "setting",
        "display",
        "surface",
        "detail",
        "dimensions",
        "style",
        "features",
        "lighting",
        "composition",
        "camera",
        "quality",
    ):
        filled = _fill(fields.get(key), values)
        if filled:
            bits.append(filled)
    tip_key = FAMILY_TIP_KEY.get(family_id, "")
    tip = _fill((template.get("category_tips") or {}).get(tip_key), values)
    if tip:
        bits.append(tip)
    if material:
        bits.append(f"Material stays {material}.")
    if colors:
        bits.append("Colors stay " + ", ".join(str(item) for item in colors[:6]) + ".")
    if note:
        bits.append(f"Seller note: {note}.")
    bits.append(f"The product is {product}. Do not redesign the SKU.")
    bits.append(ICBU_GUARD)
    if text_policy == "none":
        bits.append("No overlay text.")
    elif text_policy == "short_en":
        bits.append("At most 6 short English words. No Chinese. No prices.")
    else:
        bits.append("Short English labels only. No Chinese. No prices. No fake certificates.")
    return " ".join(bits)
