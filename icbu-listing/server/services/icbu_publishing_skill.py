"""Load aidi1723/alibaba-icbu-publishing-skill rules vendored under vendor/.

Upstream: https://github.com/aidi1723/alibaba-icbu-publishing-skill (MIT)
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

VENDOR_ROOT = Path(__file__).resolve().parents[2] / "vendor" / "alibaba-icbu-publishing"

TITLE_RULES = """
Title formula (ICBU publishing skill):
Core Product + Structure/Type + 1-2 Performance Words + Scene + Custom/OEM support word

Rules:
- Put the core product word early.
- Use concrete buyer search language, not adjective stuffing.
- Keep OEM/custom/export packing as support words, not leading every title.
- Avoid unverifiable claims (CE, FDA, Hurricane Impact) unless proof exists.
- Do not create variation by changing only one adjective — vary type, scene, spec, buyer role.
"""

KEYWORD_RULES = """
Keyword rules (ICBU publishing skill):
- 1-3 inquiry-qualified buyer search terms, not generic traffic bait.
- Mix product word, type, application, material, or spec when relevant.
- Keywords must match the title story and category attributes.
- Never keyword-stuff; each term should stand alone as a search query.
"""

BULK_RULES = """
Bulk upload checklist (ICBU publishing skill):
- Category, title, attributes, and images must tell the same product story.
- Required official attrs must use valid option values, never free-text "Other" guesses.
- Price and MOQ are business decisions — never invent them.
- Separate published SKU coverage from core-ranking SKU focus.
"""


@lru_cache(maxsize=1)
def skill_prompt_block() -> str:
    """Compact rules block for LLM planners and copy writers."""
    chunks = [TITLE_RULES.strip(), KEYWORD_RULES.strip(), BULK_RULES.strip()]
    skill_path = VENDOR_ROOT / "SKILL.md"
    if skill_path.is_file():
        text = skill_path.read_text(encoding="utf-8")
        # Pull title section if present
        if "Title formula" in text or "Title And Keyword Rules" in text:
            chunks.append(f"Reference skill excerpt available at {skill_path.name}")
    return "\n\n".join(chunks)


def checklist_for_review() -> list[dict[str, str]]:
    """Human-facing review checklist shown in the UI."""
    return [
        {"id": "category", "label": "类目一致", "hint": "整批共用所选叶子类目，行内属性选项合法"},
        {"id": "copy", "label": "标题关键词", "hint": "英文标题靠前放核心词；1～3 个询盘向关键词"},
        {"id": "trade", "label": "价量红线", "hint": "单价、起订量由你定，AI 不会改"},
        {"id": "attrs", "label": "必填属性", "hint": "下拉必须来自官方选项，不能手打 Other"},
        {"id": "images", "label": "六张图", "hint": "实拍可上传；缺图可并发出图，生成图成稿后标黄"},
        {"id": "quality", "label": "信息分 5.0", "hint": "成稿后本地预估六桶，人审过才能发"},
    ]
