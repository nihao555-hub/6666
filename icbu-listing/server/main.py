from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import ROOT, settings
from .db import init_db
from .routers import auth, excel, image_templates, listings, overview, products, shops, templates

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
    }


DIST = ROOT / "webapp" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(DIST / "index.html")

    @app.get("/{path:path}")
    def spa(path: str) -> FileResponse:
        candidate = DIST / path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(DIST / "index.html")
