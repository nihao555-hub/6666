"""Resolve photos for one Excel row: use what exists, or draw a 6-slot set."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from sqlalchemy.orm import Session

from ..models import Draft
from . import image_jobs, image_templates, public_refs
from .ecom_skill import parse_seller_facts
from .excel_import import ExcelRow, decide_image_action, resolve_row_files, split_images
from .grsai_images import GrsaiError, api_key

GENERATED_IMAGE_ISSUE = {
    "field_id": "scImages",
    "field_name": "商品图片",
    "level": "yellow",
    "message": "这几张是平台生成图，不是实拍。买家问实拍时要自己补。",
    "path": "scImages",
}
COMPLETED_IMAGE_ISSUE = {
    "field_id": "scImages",
    "field_name": "商品图片",
    "level": "yellow",
    "message": "原图留下了，缺的转化位是平台补的生成图，不是实拍。买家问实拍时要自己补。",
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
    category_hint: str = "",
    note: str = "",
    specs: dict | None = None,
    reference_urls: Sequence[str] | None = None,
    slot_start: int = 0,
) -> list[tuple[str, bytes]]:
    if not api_key():
        raise ExcelImageError("平台还没接上出图服务，没图的行画不了套图")
    name = (product_name or note or "").strip()
    if not name:
        raise ExcelImageError("这行没图也没品名，没法画套图。写上品名，或配至少一张图。")
    facts = {key: str(value).strip() for key, value in (specs or {}).items() if str(value).strip()}
    for key, value in parse_seller_facts(name, note, *facts.values()).items():
        facts.setdefault(key, value)
    planned = image_templates.plan_stack(
        product_name=name,
        category_hint=category_hint,
        note=note,
        specs=facts,
        reference_urls=list(reference_urls or []),
    )
    slots = list(planned.get("slots") or [])[max(0, int(slot_start or 0)) :]
    if not slots:
        return []
    planned["slots"] = slots
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


def _host_reference(
    files: Sequence[tuple[str, bytes]],
    public_base: str,
    existing: Sequence[str],
) -> list[str]:
    urls = [str(item) for item in existing if str(item).strip()]
    if public_base and files:
        try:
            name, content = files[0]
            ref_id = public_refs.store(content, name)
            urls.insert(0, public_refs.public_url(public_base, ref_id))
        except Exception:
            pass
    return urls[:4]


def _draw(
    painter: Callable[..., list[tuple[str, bytes]]],
    user_id: str,
    name: str,
    *,
    category_id: str,
    category_hint: str = "",
    note: str,
    specs: dict | None = None,
    reference_urls: Sequence[str],
    slot_start: int = 0,
) -> list[tuple[str, bytes]]:
    kwargs = {
        "category_id": category_id,
        "category_hint": category_hint,
        "note": note,
        "specs": dict(specs or {}),
        "reference_urls": list(reference_urls),
        "slot_start": slot_start,
    }
    try:
        try:
            drawn = painter(user_id, name, **kwargs)
        except TypeError:
            drawn = painter(
                user_id,
                name,
                category_id=category_id,
                note=note,
                reference_urls=list(reference_urls),
            )
    except GrsaiError as exc:
        raise ExcelImageError(exc.message) from exc
    if not drawn and slot_start <= 0:
        raise ExcelImageError("出图失败，请再试一次")
    return list(drawn or [])


def prepare_row_images(
    row: ExcelRow,
    uploads: dict[str, bytes],
    mode: str,
    *,
    user_id: str,
    category_id: str = "",
    fetch_url: Callable[[str], tuple[str, bytes] | None] | None = None,
    generate: Callable[..., list[tuple[str, bytes]]] | None = None,
    category_hint: str = "",
    public_base: str = "",
) -> tuple[list[tuple[str, bytes]], str]:
    """Return (files, source) where source is photos | completed | generated | skip."""
    files = resolve_row_files(row, uploads, fetch_url)
    action = decide_image_action(bool(files), mode)
    if action == "skip":
        return [], "skip"
    if action == "use_photos":
        return files, "photos"
    urls, _ = split_images(row.images)
    refs = _host_reference(files, public_base, urls)
    painter = generate or generate_row_images
    note = row.fact_text() or row.note
    specs = row.image_specs()
    if action == "complete":
        if len(files) >= 6:
            return files[:6], "photos"
        name = row_caption(row)
        if not name:
            raise ExcelImageError("这行要补转化位，但没品名也没标题，没法画。写上品名。")
        extra = _draw(
            painter,
            user_id,
            name,
            category_id=category_id,
            category_hint=category_hint,
            note=note,
            specs=specs,
            reference_urls=refs,
            slot_start=len(files),
        )
        merged = (files + extra)[:6]
        return merged, "completed" if extra else "photos"
    name = row_caption(row)
    if not name:
        raise ExcelImageError("这行没图也没品名，没法画套图。写上品名，或配至少一张图。")
    drawn = _draw(
        painter,
        user_id,
        name,
        category_id=category_id,
        category_hint=category_hint,
        note=note,
        specs=specs,
        reference_urls=refs,
        slot_start=0,
    )
    return drawn, "generated"


def mark_generated_images(db: Session, draft: Draft, source: str = "generated") -> None:
    issue = dict(COMPLETED_IMAGE_ISSUE if source == "completed" else GENERATED_IMAGE_ISSUE)
    issues = json.loads(draft.issues_json or "[]")
    if not isinstance(issues, list):
        issues = []
    if not any(item.get("path") == "scImages" and "不是实拍" in str(item.get("message") or "") for item in issues):
        issues.append(issue)
    draft.issues_json = json.dumps(issues, ensure_ascii=False)
    if draft.status == "green":
        draft.status = "yellow"
    db.commit()
