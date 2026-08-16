"""Pick the fastest listing path from what this seller already has.

Official Alibaba bulk upload is one path: pick a leaf category, download
that category's Excel, put photobank URLs in the sheet, detect, then
import. That is the right path when the seller already has a spreadsheet
and a freight template. It is the wrong first screen for a factory that
only has a folder of photos, or for a shop that already has a thousand
live listings they could copy.

This module only looks at the seller's current state and names the path
that wastes the least of their time. AI does the official 40-column work
on every path; the seller still only supplies what a machine cannot know.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Snapshot:
    shops: int = 0
    defaults_untouched: bool = True
    products: int = 0
    red: int = 0
    ready: int = 0
    drafts: int = 0
    online_count: int | None = None
    ai_enabled: bool = True


def recommend(snap: Snapshot) -> dict[str, Any]:
    primary = _primary(snap)
    return {
        "id": primary["id"],
        "title": primary["title"],
        "why": primary["why"],
        "action": primary["action"],
        "ai_does": primary["ai_does"],
        "official_note": primary.get("official_note", ""),
        "alternatives": _alternatives(snap, primary["id"]),
        "snapshot": {
            "shops": snap.shops,
            "products": snap.products,
            "red": snap.red,
            "ready": snap.ready,
            "drafts": snap.drafts,
            "online_count": snap.online_count,
            "defaults_untouched": snap.defaults_untouched,
            "ai_enabled": snap.ai_enabled,
        },
    }


def _primary(snap: Snapshot) -> dict[str, Any]:
    if snap.shops == 0:
        return {
            "id": "no_shop",
            "title": "先授权自己的店铺",
            "why": "国际站上品必须用你自己店的 token。官方批量上传也是进你的店，不是公共库。",
            "action": {"label": "去授权店铺", "to": "/shops"},
            "ai_does": ["授权之后才会拉你的类目规则、运费模板和图片银行"],
            "official_note": "官方入口在 My Alibaba → 产品管理 → 批量上传，同样要先登录自己的店。",
        }
    if snap.red > 0:
        return {
            "id": "review_reds",
            "title": f"先审完 {snap.red} 条红项",
            "why": "再投新料只会把队列拉长。红项多半是类目或官方属性对不上，点一下就能发。",
            "action": {"label": "去草稿箱审红项", "to": "/drafts"},
            "ai_does": ["标题、关键词、物流已经按官方 schema 填好", "你只处理对不上的选项和价格"],
        }
    if snap.ready > 0:
        return {
            "id": "publish_ready",
            "title": f"{snap.ready} 条可以入队发布",
            "why": "绿项和黄项已经过本地校验。官方也是先检测再导入，通过的直接提交。",
            "action": {"label": "去草稿箱发布", "to": "/drafts"},
            "ai_does": ["发布失败会把官方错误码翻成中文，改完可重发"],
            "official_note": "官方建议先用不超过 15 条测试，再大批量。我们默认发到官方草稿箱。",
        }
    if snap.defaults_untouched:
        return {
            "id": "no_defaults",
            "title": "填一次店铺默认，后面不用再问",
            "why": "官方批量上传要求运费模板、计量单位、包装提前设好。你填一次，之后每条商品自动套。",
            "action": {"label": "填店铺默认", "to": "/shops"},
            "ai_does": ["老店可以从一条在线商品反推这些默认值，不用手抄"],
            "official_note": "官方 Excel 里这些是红星必填。我们改成店铺默认 + 刊登模板，表格里不再出现。",
        }
    if snap.products > 0 and snap.drafts == 0:
        return {
            "id": "has_catalogue",
            "title": "商品库里已有货，直接铺到店铺",
            "why": "图和识别已经做过。官方还要你按类目再填一张表；这里勾店铺就能成稿。",
            "action": {"label": "去商品库铺货", "to": "/products"},
            "ai_does": ["每家店各自上传图片银行", "第二家店起换标题角度，降低重铺折叠"],
        }
    if snap.online_count and snap.online_count >= 20:
        return {
            "id": "established",
            "title": f"店里已有 {snap.online_count} 条在线品，复制再差异化最快",
            "why": "官方后台也支持从已有商品复制。我们回读 schema.render，保留类目和属性，AI 重写标题和关键词，避免被打成重铺。",
            "action": {"label": "从在线商品复制", "to": "/online"},
            "ai_does": ["回读官方字段，不用手填 40 列", "换一套英文标题和关键词", "属性、物流、运费模板沿用已过审的值"],
            "official_note": "官方复制会连标题和图片一起拷，容易进重铺组。我们强制换文案，并提醒换图。",
        }
    return {
        "id": "new_shop_photos",
        "title": "新店：丢图 + 价格就能成稿",
        "why": "还没有在线品可复制。官方要你先选类目再下 Excel；我们看图定类目，你只出图、价、起订量。",
        "action": {"label": "去投料上品", "to": "/feed"},
        "ai_does": ["看图理解", "beam search 定叶子类目", "属性对齐官方选项", "写英文标题和关键词", "图进图片银行"],
        "official_note": "有现成表格就改走 Excel。官方类目表也可以下，但只需填货号价格起订量和图。",
    }


def _alternatives(snap: Snapshot, current: str) -> list[dict[str, str]]:
    options = [
        {"id": "photos", "label": "只有实拍图", "to": "/feed", "hint": "工厂最常见。按文件名前缀批量归货。"},
        {"id": "ai_images", "label": "没实拍：先出套图提示词", "to": "/feed?tab=ai", "hint": "按类目复制 6 条提示词，自己生图后再投料。"},
        {"id": "excel", "label": "已有 Excel / 别的 ERP 表", "to": "/feed?tab=excel", "hint": "领星资料库、店小秘模板、马帮导出、官方类目表、智能探测。"},
        {"id": "clone", "label": "店里已有同类目在线品", "to": "/online", "hint": "复制已过审的类目和属性，AI 只改文案。"},
        {"id": "catalogue", "label": "货已在商品库", "to": "/products", "hint": "勾商品 × 勾店铺，一键铺多店。"},
        {"id": "official", "label": "按官方：先选类目再填表", "to": "/feed?tab=excel&style=alibaba", "hint": "和 My Alibaba 批量上传同一思路，但 40 个红星字段由 AI 填。"},
    ]
    skip = {
        "no_shop": {"photos", "excel", "clone", "catalogue", "official", "ai_images"},
        "review_reds": set(),
        "publish_ready": set(),
        "no_defaults": set(),
        "has_catalogue": {"catalogue"},
        "established": {"clone"},
        "new_shop_photos": {"photos"},
    }.get(current, set())
    if not snap.products:
        skip.add("catalogue")
    if snap.online_count == 0:
        skip.add("clone")
    return [item for item in options if item["id"] not in skip]
