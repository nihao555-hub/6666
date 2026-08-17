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
            "title": "先登录你自己的店铺",
            "why": "用你的国际站卖家账号登录并授权。之后发品、改品、传图都进你自己的店。",
            "action": {"label": "去登录店铺", "to": "/shops"},
            "ai_does": ["登录之后才会按你店里的类目规则和运费模板成稿"],
        }
    if snap.red > 0:
        return {
            "id": "review_reds",
            "title": f"先改完 {snap.red} 条要处理的商品",
            "why": "红项多半是类目或属性对不上。点进商品改一下就能发。",
            "action": {"label": "去商品里改", "to": "/drafts"},
            "ai_does": ["标题、关键词、物流已经填好", "你只处理对不上的选项和价格"],
        }
    if snap.ready > 0:
        return {
            "id": "publish_ready",
            "title": f"{snap.ready} 条可以发到店里",
            "why": "绿的和黄的已经过校验。勾上就能进发布队列。",
            "action": {"label": "去商品里发布", "to": "/drafts"},
            "ai_does": ["失败原因会翻成中文，改完可重发"],
        }
    if snap.defaults_untouched:
        return {
            "id": "no_defaults",
            "title": "填一次店铺默认，后面不用再问",
            "why": "产地、单位、运费、包装填一次，之后每条商品自动套。",
            "action": {"label": "填店铺默认", "to": "/shops"},
            "ai_does": ["这些字段 AI 不猜"],
        }
    if snap.products > 0 and snap.drafts == 0:
        return {
            "id": "has_catalogue",
            "title": "货已经识别过，直接铺到店铺",
            "why": "图和识别做过了。勾店铺就能成稿，不用再填一张表。",
            "action": {"label": "去铺货", "to": "/products"},
            "ai_does": ["每家店各自传图、各自成稿"],
        }
    if snap.online_count and snap.online_count >= 20:
        return {
            "id": "established",
            "title": f"店里已有 {snap.online_count} 条在售，复制再改最快",
            "why": "从店里已有的品拉回来，保留类目和属性，只换文案再发。",
            "action": {"label": "去商品里看在售", "to": "/drafts?tab=live"},
            "ai_does": ["保留已过审的类目和属性", "换一套英文标题，避免被打成重铺"],
        }
    return {
        "id": "new_shop_photos",
        "title": "丢图加价格就能成稿",
        "why": "去投料上品。你只出图、价、起订量。标题和属性系统补。",
        "action": {"label": "去投料上品", "to": "/feed"},
        "ai_does": ["看图定类目", "对齐官方属性选项", "写英文标题和关键词"],
    }


def _alternatives(snap: Snapshot, current: str) -> list[dict[str, str]]:
    options = [
        {"id": "photos", "label": "只有实拍图", "to": "/feed", "hint": "进投料先选「有实拍」。按文件名前缀批量归货。"},
        {"id": "ai_images", "label": "没实拍：平台生成套图", "to": "/feed", "hint": "进投料先选「平台画图」。写出品名，平台画 6 张再填价。"},
        {"id": "excel", "label": "下载表格批量上品", "to": "/feed", "hint": "进投料先选「填表批量」。一行一个商品，做到一半也能回来接着做。"},
        {"id": "clone", "label": "店里已有同类目在售", "to": "/drafts?tab=live", "hint": "从在售拉回来改，保留类目和属性。"},
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
