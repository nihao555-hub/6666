"""Resolve photos for one Excel row: use what exists, or draw a 6-slot set."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from sqlalchemy.orm import Session

from ..models import Draft
from . import image_jobs, image_templates
from .excel_import import ExcelRow, decide_image_action, resolve_row_files, split_images
from .grsai_images import GrsaiError, api_key

GENERATED_IMAGE_ISSUE = {
    "field_id": "scImages",
    "field_name": "商品图片",
    "level": "yellow",
    "message": "这几张是平台生成图，不是实拍。买家问实拍时要自己补。",
    "path": "scImages",
}


class ExcelImageError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def row_caption(row: ExcelRow) -> str:
    return (row.name or row.title or row.sku or row.note or "").strip()


def generate_row_images(
    user_id: str,
    product_name: str,
    *,
    category_id: str = "",
    note: str = "",
    reference_urls: Sequence[str] | None = None,
) -> list[tuple[str, bytes]]:
    if not api_key():
        raise ExcelImageError("平台还没接上出图服务，没图的行画不了套图")
    name = (product_name or note or "").strip()
    if not name:
        raise ExcelImageError("这行没图也没品名，没法画套图。写上品名，或配至少一张图。")
    planned = image_templates.plan_stack(
        product_name=name,
        category_hint="",
        note=note,
        reference_urls=list(reference_urls or []),
    )
    planned["product_name"] = name
    planned["category_id"] = category_id
    job = image_jobs.create_job(user_id, planned)
    image_jobs.run_job(job["id"])
    latest = image_jobs.get_job(job["id"], user_id) or job
    if latest.get("status") != "succeeded":
        raise ExcelImageError(str(latest.get("error") or "出图失败，请再试一次"))
    uploads = image_jobs.uploads_for(latest)
    if not uploads:
        raise ExcelImageError("出图失败，请再试一次")
    return uploads


def prepare_row_images(
    row: ExcelRow,
    uploads: dict[str, bytes],
    mode: str,
    *,
    user_id: str,
    category_id: str = "",
    fetch_url: Callable[[str], tuple[str, bytes] | None] | None = None,
    generate: Callable[..., list[tuple[str, bytes]]] | None = None,
) -> tuple[list[tuple[str, bytes]], str]:
    """Return (files, source) where source is photos | generated | skip."""
    files = resolve_row_files(row, uploads, fetch_url)
    action = decide_image_action(bool(files), mode)
    if action == "skip":
        return [], "skip"
    if action == "use_photos":
        return files, "photos"
    name = row_caption(row)
    if not name:
        raise ExcelImageError("这行没图也没品名，没法画套图。写上品名，或配至少一张图。")
    urls, _ = split_images(row.images)
    painter = generate or generate_row_images
    try:
        drawn = painter(
            user_id,
            name,
            category_id=category_id,
            note=row.note,
            reference_urls=urls,
        )
    except GrsaiError as exc:
        raise ExcelImageError(exc.message) from exc
    if not drawn:
        raise ExcelImageError("出图失败，请再试一次")
    return drawn, "generated"


def mark_generated_images(db: Session, draft: Draft) -> None:
    issues = json.loads(draft.issues_json or "[]")
    if not isinstance(issues, list):
        issues = []
    if not any(item.get("path") == "scImages" and "不是实拍" in str(item.get("message") or "") for item in issues):
        issues.append(dict(GENERATED_IMAGE_ISSUE))
    draft.issues_json = json.dumps(issues, ensure_ascii=False)
    if draft.status == "green":
        draft.status = "yellow"
    db.commit()
