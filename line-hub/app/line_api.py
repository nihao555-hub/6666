"""最小 LINE Messaging API 客户端：reply / push。"""
from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger("line-hub")
API = "https://api.line.me/v2/bot"


async def reply_text(token: str, reply_token: str, text: str) -> None:
    await _post(token, "/message/reply", {"replyToken": reply_token, "messages": [{"type": "text", "text": text}]})


async def push_text(token: str, to: str, text: str) -> None:
    await _post(token, "/message/push", {"to": to, "messages": [{"type": "text", "text": text}]})


async def _post(token: str, path: str, payload: dict[str, Any]) -> None:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(API + path, json=payload, headers=headers)
        if resp.status_code >= 300:
            log.warning("LINE API %s -> %s %s", path, resp.status_code, resp.text[:300])
            resp.raise_for_status()
