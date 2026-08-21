"""Assemble listing prompts from buluslan/gpt-image2-ecommerce (312★).

Follow the skill README, not a keyword dump:

- 简洁为王：只传核心信息，不过度约束
- 自然语言优先：描述性句子优于关键词堆砌
- 材质描述：明确写出纹理（磨砂玻璃、拉丝金属、哑光质感）
- 光照很重要：始终包含光照方向和质感
- 善用参考图：产品图走 urls，不写进 prompt

Alibaba.com is English. Seller names in Chinese / Arabic / etc. become a
short English noun phrase before they reach the image model. Printed text
already on the product stays; we do not add extra languages on top.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

SKILL = {
    "repo": "buluslan/gpt-image2-ecommerce",
    "url": "https://github.com/buluslan/gpt-image2-ecommerce",
    "stars": 312,
    "took": "6 个国际站坑位用它的主图/尺寸/细节/场景/包装/卖点模板；短句、材质、光照，产品图走参考图",
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
    "ports": "04-detail-macro.json",
    "explode": "03-flat-lay.json",
    "spec": "11-infographic.json",
    "wear": "02-lifestyle-scene.json",
    "fabric": "04-detail-macro.json",
    "size": "13-size-spec.json",
    "colors": "03-flat-lay.json",
    "texture": "04-detail-macro.json",
    "sizes": "03-flat-lay.json",
    "facts": "11-infographic.json",
    "room": "02-lifestyle-scene.json",
    "dimension": "13-size-spec.json",
    "material": "04-detail-macro.json",
    "set": "03-flat-lay.json",
    "play": "02-lifestyle-scene.json",
    "parts": "03-flat-lay.json",
    "craft": "04-detail-macro.json",
    "action": "02-lifestyle-scene.json",
    "contents": "04-detail-macro.json",
    "serve": "02-lifestyle-scene.json",
}

FAMILY_TIP_KEY = {
    "electronics": "electronics",
    "apparel": "fashion",
    "beauty": "beauty",
    "home": "home",
    "jewelry": "jewelry",
    "food": "food",
}

FAMILY_LOOK = {
    "stationery": "Show the real surface from the product or reference. Do not invent a wood, pigment, or barrel finish.",
    "tools": "Show the real working end from the product or reference. Do not invent bristles, metal, or extra parts.",
    "electronics": "Show the real housing from the product or reference. Do not invent ports, screens, or accessories.",
    "apparel": "Show the real fabric from the product or reference. Do not invent prints or extra garments.",
    "beauty": "Show the real pack from the product or reference. Do not invent a formula, glow, or open texture.",
    "home": "Show the real surface from the product or reference. Do not invent glaze, wood, or extra pieces.",
    "toys": "Show the real surface from the product or reference. Do not invent sparkle or extra parts.",
    "jewelry": "Show the real metal or stone from the product or reference. Do not invent a cut or hallmark.",
    "industrial": "Show the real machine from the product or reference. Do not invent internals, model numbers, or ports.",
    "food": "Show the real pack from the product or reference. Do not invent steam, seals, or nutrition marks.",
    "sports": "Show the real gear from the product or reference. Do not invent a size or extra accessory.",
    "general": "Show the real surface from the product or reference. Do not invent a material, finish, or extra part.",
}

# Seller names we see often. Image prompts stay English even when the seller types Chinese.
LOCAL_EN = {
    "油漆刷": "wall paint brush",
    "油漆刷套装": "wall paint brush set",
    "猪鬃油漆刷": "hog-bristle wall paint brush",
    "无线耳机": "wireless earbuds",
    "无线蓝牙耳机": "wireless bluetooth earbuds",
    "蓝牙耳机": "bluetooth earbuds",
    "陶瓷马克杯": "ceramic mug",
    "马克杯": "ceramic mug",
    "彩铅": "colored pencil set",
    "彩铅套装": "colored pencil set",
    "سماعات أذن لاسلكية": "wireless earbuds",
    "taza de cerámica": "ceramic mug",
    "taza de ceramica": "ceramic mug",
}

NON_LATIN = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\u4e00-\u9fff\u3400-\u4dbf"
    r"\u3040-\u30ff\uac00-\ud7af\u0400-\u04FF\u0590-\u05FF]"
)


@lru_cache(maxsize=16)
def load_template(filename: str) -> dict[str, Any]:
    path = TEMPLATES_DIR / filename
    return json.loads(path.read_text(encoding="utf-8"))


def looks_non_latin(text: str) -> bool:
    return bool(NON_LATIN.search(text or ""))


def _local_english(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    hit = LOCAL_EN.get(raw) or LOCAL_EN.get(raw.lower())
    if hit:
        return hit
    for key, value in LOCAL_EN.items():
        if key and key in raw:
            return value
    return ""


def english_brief(product_name: str, note: str = "") -> str:
    """Short English noun phrase for the image model. Family matching still uses the original name."""
    name = (product_name or "").strip()
    extra = (note or "").strip()
    if not name and not extra:
        return "wholesale product"
    mapped = _local_english(name) or _local_english(extra)
    if mapped:
        return mapped
    if not looks_non_latin(name) and not looks_non_latin(extra):
        return name or extra
    try:
        from ai import AiClient

        client = AiClient.from_env_or_none()
    except Exception:
        client = None
    if client is not None:
        try:
            data = client.chat_json(
                [
                    {
                        "role": "user",
                        "content": (
                            "Turn this seller product name into a short English noun phrase "
                            "for a product photograph. Include a visible material if it is obvious. "
                            "No marketing adjectives. JSON only: {\"english\": \"...\"}\n"
                            f"Name: {name}\nNote: {extra}"
                        ),
                    }
                ],
                temperature=0.0,
            )
            brief = str((data or {}).get("english") or "").strip()
            if brief and not looks_non_latin(brief):
                return brief
        except Exception:
            pass
    latin = re.sub(NON_LATIN, " ", name)
    latin = " ".join(latin.split())
    return latin or "wholesale product"


def english_note(note: str) -> str:
    text = (note or "").strip()
    if not text:
        return ""
    if not looks_non_latin(text):
        return text
    mapped = _local_english(text)
    if mapped:
        return mapped
    try:
        from ai import AiClient

        client = AiClient.from_env_or_none()
    except Exception:
        client = None
    if client is None:
        return ""
    try:
        data = client.chat_json(
            [
                {
                    "role": "user",
                    "content": (
                        "Rewrite this seller note as one short English clause for a photo prompt. "
                        "Keep only visible facts (material, color, pack count). JSON: {\"english\": \"...\"}\n"
                        f"Note: {text}"
                    ),
                }
            ],
            temperature=0.0,
        )
        brief = str((data or {}).get("english") or "").strip()
        return brief if brief and not looks_non_latin(brief) else ""
    except Exception:
        return ""


def _fill(text: Any, values: Mapping[str, str]) -> str:
    if text is None:
        return ""
    out = str(text)
    for key, value in values.items():
        out = out.replace("{" + key + "}", value)
    if "{" in out and "}" in out:
        return ""
    return " ".join(out.split())


def _lighting(slot_id: str, template: Mapping[str, Any], values: Mapping[str, str]) -> str:
    fields = dict(template.get("defaults") or {})
    fields.update(template.get("prompt_template") or {})
    if slot_id == "main":
        return "Soft diffused studio lighting from the upper left, even fill, faint contact shadow."
    if slot_id == "pack":
        return "Even warehouse or studio light from above-left, honest cardboard texture."
    filled = _fill(fields.get("lighting"), values)
    if filled:
        if "from" not in filled.lower() and "through" not in filled.lower():
            return f"{filled.rstrip('.')} from the upper left."
        return filled.rstrip(".") + "."
    return "Soft directional light from the upper left, gentle fill from the right."


def _scene(
    slot_id: str,
    brief: str,
    usage: str,
    template: Mapping[str, Any],
    values: Mapping[str, str],
    *,
    size: str = "",
    pack_count: str = "",
) -> str:
    if slot_id == "main":
        return f"Centered front view of the {brief} on a clean white background, product filling most of the frame."
    if slot_id in {"range", "colors", "set", "parts", "sizes", "explode"}:
        return f"Top-down flat lay of the real {brief} only, even spacing. Do not add pieces, colors, or accessories that were not given."
    if slot_id in {"scale", "size", "dimension"}:
        if size:
            return f"The {brief} on white. The only allowed size mark is: {size}. No other numbers."
        return (
            f"The {brief} next to a plain ruler or hand on white for scale. "
            "Do not print any numbers, mm, cm, inch, or made-up length."
        )
    if slot_id in {"detail", "ports", "fabric", "texture", "craft", "material", "contents"}:
        return f"Close photograph of the real working end or surface of the {brief}. Do not invent internals, extra ports, or a finish that was not given."
    if slot_id in {"use", "wear", "room", "play", "action", "serve"}:
        place = usage or "a believable workplace"
        return f"The same {brief} in {place}, product still easy to recognize. Do not add tools or accessories that were not given."
    if slot_id == "pack":
        if pack_count:
            return (
                f"Export carton and inner box of the {brief} on a clean warehouse floor. "
                f"The only allowed pack line is: {pack_count}."
            )
        return (
            f"Export carton and inner box of the {brief} on a clean warehouse floor. "
            "No pack count, barcode, or size on the box unless it was given."
        )
    if slot_id in {"custom", "spec", "facts"}:
        return f"The {brief} centered. Label only facts that were given. No charts, no invented numbers."
    subject = _fill((template.get("prompt_template") or {}).get("subject"), values)
    return subject or f"A clear commercial photograph of the {brief}."


def _marketplace_line(text_policy: str) -> str:
    if text_policy == "none":
        return (
            "Alibaba.com square listing photo. Keep any text already printed on the product. "
            "Add no overlay text, badges, prices, or watermarks."
        )
    if text_policy == "short_en":
        return (
            "Alibaba.com square listing photo. Short English labels only. "
            "Keep printed-on-product text. No extra languages, prices, or fake marks."
        )
    return (
        "Alibaba.com square listing photo. A few short English facts only if they were given. "
        "No fake CE, ISO, or FDA marks, and no extra languages."
    )


FACT_PATTERNS = (
    ("color_count", re.compile(r"(\d+)\s*色")),
    ("piece_count", re.compile(r"(\d+)\s*支")),
    ("size", re.compile(r"(\d+(?:\.\d+)?)\s*(mm|cm|inch|寸)", re.I)),
)


def parse_seller_facts(*texts: str) -> dict[str, str]:
    """Pull visible facts the seller typed. Guessing is allowed only from these."""
    blob = " ".join(str(item or "") for item in texts if item)
    facts: dict[str, str] = {}
    if not blob:
        return facts
    match = FACT_PATTERNS[0][1].search(blob)
    if match:
        facts["color_count"] = f"{match.group(1)} colors"
    match = FACT_PATTERNS[1][1].search(blob)
    if match:
        facts["piece_count"] = f"{match.group(1)} pcs"
    match = FACT_PATTERNS[2][1].search(blob)
    if match:
        facts["size"] = f"{match.group(1)}{match.group(2)}"
    match = re.search(r"(\d+)\s*colors?\b", blob, re.I)
    if match and "color_count" not in facts:
        facts["color_count"] = f"{match.group(1)} colors"
    match = re.search(r"(\d+)\s*(?:pcs|pieces)\b", blob, re.I)
    if match and "piece_count" not in facts:
        facts["piece_count"] = f"{match.group(1)} pcs"
    if "水溶" in blob or "watercolor" in blob.lower():
        facts["finish"] = "water-soluble"
    for grade in ("2H", "2B", "HB", "4B", "6B", "H", "B"):
        if re.search(rf"(?<![A-Za-z0-9]){grade}(?![A-Za-z0-9])", blob, re.I) or grade in blob:
            facts["hardness"] = grade
            break
    return facts


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
    product_brief: str = "",
    specs: Mapping[str, Any] | None = None,
    has_reference: bool = False,
) -> str:
    filename = SLOT_FILE.get(slot_id) or SLOT_FILE["main"]
    template = load_template(filename)
    brief = (product_brief or english_brief(product, note)).strip() or "wholesale product"
    facts = dict(specs or {})
    facts.update({key: value for key, value in parse_seller_facts(note, product).items() if key not in facts})
    size = str(facts.get("size") or facts.get("dimension") or "").strip()
    pack_count = str(facts.get("pack_count") or facts.get("carton") or facts.get("piece_count") or "").strip()
    if material:
        material_en = english_brief(material) if looks_non_latin(material) else material
        material_line = f"The surface is {material_en}."
    else:
        material_line = FAMILY_LOOK.get(family_id) or FAMILY_LOOK["general"]
    values = {
        "product_description": brief,
        "product": brief,
        "material_description": material or "the real material from the reference",
        "scene_description": usage or "typical wholesale use",
        "texture_description": material or "true surface finish from the reference",
        "focus_area": material or "texture and material quality",
        "size_annotations": size or "omit all numbers",
        "feature_list": ", ".join(str(item) for item in (features or [])[:4]) or "only verified selling points",
    }
    lighting = _lighting(slot_id, template, values)
    scene = _scene(slot_id, brief, usage, template, values, size=size, pack_count=pack_count)
    tip_key = FAMILY_TIP_KEY.get(family_id, "")
    tip = _fill((template.get("category_tips") or {}).get(tip_key), values)

    sentences = [
        f"A commercial photograph of {brief}. {material_line}",
        f"Lighting: {lighting}",
        scene,
    ]
    if tip and slot_id in {"detail", "use", "texture", "fabric"}:
        sentences.append(tip.rstrip(".") + ".")
    color_bits = [str(item) for item in (colors or []) if str(item).strip()]
    if color_bits:
        sentences.append("Keep only these colors: " + ", ".join(color_bits[:4]) + ".")
    note_en = english_note(note)
    if note_en:
        sentences.append(f"Seller fact: {note_en}.")
    given = [f"{key}={value}" for key, value in facts.items() if value]
    if given:
        sentences.append("Use only these seller specs: " + ", ".join(given[:8]) + ".")
    if has_reference:
        sentences.append("Match the reference photo: same silhouette, color, labels, and surface. Do not redesign the SKU.")
    feature_bits = [str(item) for item in (features or []) if str(item).strip()]
    if feature_bits and text_policy != "none":
        sentences.append("Only these facts: " + ", ".join(feature_bits[:4]) + ".")
    sentences.append(_marketplace_line(text_policy))
    sentences.append(
        "Guess only from the reference photo and seller specs. If a size, pack count, color, accessory, brand, or certificate was not given, omit it."
    )
    return " ".join(" ".join(part.split()) for part in sentences if part and part.strip())


def clean_reference_urls(urls: Sequence[str] | None) -> list[str]:
    out: list[str] = []
    for raw in urls or []:
        item = str(raw or "").strip()
        if item.startswith("https://") or item.startswith("http://"):
            out.append(item)
        if len(out) >= 4:
            break
    return out
