from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import ROOT, settings
from .db import init_db, persist_database
from .routers import auth, excel, feed_sessions, image_templates, listings, overview, products, shops, templates

app = FastAPI(title="Auto Shoper · 国际站批量上品", version="0.2.0")

if settings.cors_origin_regex:
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(auth.router)
app.include_router(shops.router)
app.include_router(products.router)
app.include_router(templates.router)
app.include_router(excel.router)
app.include_router(listings.router)
app.include_router(overview.router)
app.include_router(image_templates.router)
app.include_router(image_templates.public_router)
app.include_router(feed_sessions.router)


@app.middleware("http")
async def persist_sqlite_snapshot(request: Request, call_next):
    response = await call_next(request)
    if request.method != "GET" or request.url.path.startswith("/api/v1/auth"):
        persist_database()
    return response


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/api/v1/health")
def health() -> dict[str, object]:
    return {
        "ok": True,
        "platform_ready": settings.has_platform_app,
        "ai_enabled": settings.ai_enabled,
        "image_enabled": settings.image_enabled,
        "text_model": settings.text_model,
        "image_model": settings.image_model,
        "db_persist": "blob" if settings.blob_read_write_token else "local",
        "git_sha": os.environ.get("VERCEL_GIT_COMMIT_SHA") or os.environ.get("GIT_SHA") or "",
        "production_url": "https://icbu-listing.vercel.app",
        "config": {
            "alibaba_app": settings.has_platform_app,
            "alibaba_dev_token": bool(settings.dev_access_token),
            "token_encryption": bool(settings.token_encryption_key),
            "openai": settings.ai_enabled,
            "grsai": settings.image_enabled,
            "blob": bool(settings.blob_read_write_token),
            "registration_codes": bool(settings.registration_codes),
            "cookie_secure": settings.cookie_secure,
            "oauth_redirect": bool(settings.oauth_redirect_uri),
        },
    }


DIST = ROOT / "webapp" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(DIST / "index.html")

    @app.get("/{path:path}")
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail="接口不存在")
        candidate = DIST / path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(DIST / "index.html")
