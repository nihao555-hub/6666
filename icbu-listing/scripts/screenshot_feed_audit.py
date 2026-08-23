#!/usr/bin/env python3
"""Capture Feed post-parse audit UI screenshot."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

os.environ.setdefault("DATABASE_PATH", str(ROOT / "data" / "auto-shoper.db"))
os.environ.pop("BLOB_READ_WRITE_TOKEN", None)
os.environ.pop("VERCEL", None)

from playwright.sync_api import sync_playwright  # noqa: E402

from server.config import settings  # noqa: E402
from server.crypto import sign_session  # noqa: E402
from server.db import SessionLocal  # noqa: E402
from server.models import User  # noqa: E402

API_BASE = "http://127.0.0.1:8010/api/v1"
BASE_URL = "http://127.0.0.1:5180"
OUT_DIR = Path("/opt/cursor/artifacts/screenshots")
OUT_PATH = OUT_DIR / "feed-audit-simple.png"
SHOP_ID = "63e040211b7c42c6a52386b4e6a3c4ea"
CATEGORY_ID = "21110712"


def _img(seed: str) -> str:
    return f"https://picsum.photos/seed/{seed}/96/96"


def _sample_rows() -> list[dict]:
    return [
        {
            "line": 2,
            "sku": "PEN-CP-12",
            "name": "12色木杆彩色铅笔",
            "title": "Wholesale 12-color wood pencil set OEM",
            "keywords": "colored pencil; wholesale; OEM",
            "price": "1.80",
            "moq": "500",
            "images": ";".join([_img("pen12a"), _img("pen12b"), _img("pen12c")]),
            "_audit_status": "approved",
            "_selected": False,
        },
        {
            "line": 3,
            "sku": "PEN-CP-24",
            "name": "24色彩色铅笔套装",
            "title": "24-color pencil set for school supply",
            "keywords": "24 color; pencil set",
            "price": "2.40",
            "moq": "300",
            "images": ";".join([_img("pen24a"), _img("pen24b")]),
            "_audit_status": "pending",
            "_selected": False,
        },
        {
            "line": 4,
            "sku": "PEN-CP-36",
            "name": "36色专业彩铅",
            "title": "Professional 36-color art pencils",
            "keywords": "art pencil; professional",
            "price": "",
            "moq": "200",
            "images": _img("pen36a"),
            "_audit_status": "pending",
            "_selected": False,
        },
        {
            "line": 5,
            "sku": "PEN-CP-48",
            "name": "48色铁盒彩铅",
            "title": "",
            "keywords": "tin box; 48 colors",
            "price": "4.50",
            "moq": "100",
            "images": _img("pen48a"),
            "_audit_status": "pending",
            "_selected": False,
        },
        {
            "line": 6,
            "sku": "PEN-CP-72",
            "name": "72色大师级彩铅",
            "title": "72-color master artist pencil set",
            "keywords": "artist; master grade",
            "price": "8.90",
            "moq": "50",
            "images": "",
            "_audit_status": "pending",
            "_selected": False,
        },
        {
            "line": 7,
            "sku": "PEN-CP-96",
            "name": "96色水溶彩铅",
            "title": "96-color water soluble pencil set",
            "keywords": "water soluble; 96 color",
            "price": "12.00",
            "moq": "30",
            "images": ";".join([_img("pen96a"), _img("pen96b"), _img("pen96c"), _img("pen96d")]),
            "_audit_status": "pending",
            "_selected": True,
        },
        {
            "line": 8,
            "sku": "PEN-CP-OEM",
            "name": "OEM定制彩铅",
            "title": "Custom logo colored pencil bulk order",
            "keywords": "OEM; custom logo",
            "price": "1.20",
            "moq": "",
            "images": _img("penoem"),
            "_audit_status": "pending",
            "_selected": False,
        },
        {
            "line": 9,
            "sku": "PEN-CP-GIFT",
            "name": "礼品装彩铅",
            "title": "Gift box colored pencil for promotion",
            "keywords": "gift box; promotion",
            "price": "3.20",
            "moq": "500",
            "images": ";".join([_img("gift1"), _img("gift2")]),
            "_audit_status": "approved",
            "_selected": False,
        },
    ]


def _sample_payload() -> dict:
    rows = _sample_rows()
    columns = [
        {"id": "sku", "label": "货号", "required": True, "source": "user"},
        {"id": "name", "label": "品名", "required": False, "source": "user"},
        {"id": "title", "label": "标题", "required": False, "source": "ai"},
        {"id": "keywords", "label": "关键词", "required": False, "source": "ai"},
        {"id": "price", "label": "单价", "required": True, "source": "user"},
        {"id": "moq", "label": "起订量", "required": True, "source": "user"},
        {"id": "brand", "label": "品牌", "required": False, "source": "user"},
        {"id": "note", "label": "备注", "required": False, "source": "user"},
        {"id": "attr.icbuCatProp.p-2", "label": "品牌属性", "required": True, "source": "schema"},
        {"id": "attr.icbuCatProp.p-1", "label": "材质", "required": True, "source": "schema"},
        {"id": "images", "label": "图片", "required": False, "source": "user"},
    ]
    return {
        "doc": {
            "categoryId": CATEGORY_ID,
            "categoryName": "Colored Pencils / 彩色铅笔",
            "columns": columns,
            "rows": rows,
            "row_issues": [
                {"line": 4, "sku": "PEN-CP-36", "level": "red", "message": "缺单价。价格是红线，AI 不代填。"},
                {"line": 8, "sku": "PEN-CP-OEM", "level": "red", "message": "缺起订量。AI 不代填。"},
            ],
            "warnings": [],
            "row_count": len(rows),
            "ready_count": 6,
            "source": "screenshot-demo",
            "reviewAiDone": True,
            "smartPlan": {
                "columns": columns,
                "column_count": len(columns),
                "category_name": "Colored Pencils / 彩色铅笔",
                "category_id": CATEGORY_ID,
            },
        },
        "rowCount": len(rows),
    }


def auth_context() -> tuple[str, str]:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "check@x.com").first()
        if user is None:
            user = db.query(User).first()
        if user is None:
            raise SystemExit("No users in database")
        return user.id, sign_session(user.id, settings.session_days * 86400, user.email)
    finally:
        db.close()


def seed_session_via_api(token: str) -> tuple[str, dict]:
    headers = {"Cookie": f"{settings.session_cookie}={token}"}
    with httpx.Client(base_url=API_BASE, headers=headers, timeout=30.0) as client:
        created = client.post("/feed-sessions", json={"path": "doc", "shop_id": SHOP_ID}).json()
        session_id = created["id"]
        payload = _sample_payload()
        saved = client.patch(
            f"/feed-sessions/{session_id}",
            json={
                "shop_id": SHOP_ID,
                "step": 1,
                "reached": 1,
                "payload": payload,
            },
        )
        saved.raise_for_status()
        return session_id, payload


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    user_id, token = auth_context()
    session_id, payload = seed_session_via_api(token)
    draft_key = f"icbu-feed-draft:{user_id}:{SHOP_ID}"
    draft = {
        "sessionId": session_id,
        "step": 1,
        "reached": 1,
        "payload": payload,
        "updatedAt": int(__import__("time").time() * 1000),
    }
    url = f"{BASE_URL}/#/feed?shop={SHOP_ID}"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 960})
        context.add_cookies(
            [
                {
                    "name": settings.session_cookie,
                    "value": token,
                    "domain": "127.0.0.1",
                    "path": "/",
                }
            ]
        )
        page = context.new_page()

        def _block_session_patch(route) -> None:
            if route.request.method == "PATCH" and "/feed-sessions/" in route.request.url:
                route.abort()
                return
            route.continue_()

        page.route("**/*", _block_session_patch)
        page.add_init_script(
            f"""
            try {{
              localStorage.clear();
              localStorage.setItem({json.dumps(draft_key)}, {json.dumps(json.dumps(draft, ensure_ascii=False))});
            }} catch {{}}
            """
        )
        page.goto(url, wait_until="networkidle", timeout=90000)
        page.wait_for_selector("text=内容审核", timeout=45000)
        page.wait_for_selector("text=批量成稿", timeout=30000)
        page.wait_for_timeout(1500)
        page.screenshot(path=str(OUT_PATH), full_page=True)
        browser.close()

    print(OUT_PATH)


if __name__ == "__main__":
    main()
