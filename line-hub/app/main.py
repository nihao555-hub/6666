"""5 账号 LINE webhook 入口。

每个账号一条独立路径：
    POST /webhook/acc1 … /webhook/acc5

LINE 会带 X-Line-Signature；服务端用该账号自己的 channel secret 验签。
验签通过后立刻回 200，业务（回消息）放到后台任务，避免超时重投。
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from .config import Account, load_accounts
from .line_api import reply_text
from .signature import verify_signature

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
log = logging.getLogger("line-hub")

accounts: dict[str, Account] = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    global accounts
    accounts = load_accounts()
    log.info("loaded accounts: %s", ", ".join(sorted(accounts)))
    yield


app = FastAPI(title="line-hub", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict:
    return {"ok": True, "accounts": sorted(accounts)}


@app.get("/")
async def root() -> PlainTextResponse:
    return PlainTextResponse("line-hub ready\n")


@app.post("/webhook/{slug}")
async def webhook(
    slug: str,
    request: Request,
    background: BackgroundTasks,
    x_line_signature: str | None = Header(default=None),
) -> JSONResponse:
    acc = accounts.get(slug)
    if acc is None:
        raise HTTPException(status_code=404, detail=f"unknown account: {slug}")

    body = await request.body()
    if not verify_signature(acc.channel_secret, body, x_line_signature or ""):
        log.warning("bad signature slug=%s", slug)
        raise HTTPException(status_code=403, detail="invalid signature")

    payload = await request.json() if body else {}
    events = payload.get("events") or []
    log.info("ok slug=%s events=%d", slug, len(events))
    background.add_task(handle_events, acc, events)
    return JSONResponse({"ok": True})


async def handle_events(acc: Account, events: list[dict]) -> None:
    for event in events:
        etype = event.get("type")
        source = (event.get("source") or {}).get("userId", "-")
        log.info("event slug=%s type=%s user=%s", acc.slug, etype, source)

        if etype == "follow":
            reply_token = event.get("replyToken")
            if reply_token:
                await reply_text(
                    acc.channel_token,
                    reply_token,
                    f"你好，这里是 {acc.display_name}。发任意文字即可回声。",
                )
            continue

        if etype != "message":
            continue
        msg = event.get("message") or {}
        if msg.get("type") != "text":
            continue
        reply_token = event.get("replyToken")
        if not reply_token:
            continue
        text = (msg.get("text") or "").strip() or "(空消息)"
        await reply_text(acc.channel_token, reply_token, f"[{acc.display_name}] {text}")
