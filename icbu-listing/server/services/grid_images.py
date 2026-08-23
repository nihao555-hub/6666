"""Six-slot image placeholders and async generation for the batch grid."""

from __future__ import annotations

import threading
from typing import Any, Mapping, Sequence

from . import image_jobs, image_templates
from .ecom_skill import parse_seller_facts
from .excel_import import ExcelRow, split_images
from .grsai_images import api_key

DEFAULT_SLOT_NAMES = ("白底主图", "细节", "尺寸", "场景", "外箱", "OEM")


def empty_slots() -> list[dict[str, Any]]:
    return [
        {
            "index": index,
            "id": f"slot-{index}",
            "name": DEFAULT_SLOT_NAMES[index - 1] if index <= len(DEFAULT_SLOT_NAMES) else f"图{index}",
            "status": "empty",
            "url": "",
        }
        for index in range(1, 7)
    ]


def slots_from_urls(urls: Sequence[str]) -> list[dict[str, Any]]:
    slots = empty_slots()
    for index, url in enumerate(list(urls)[:6]):
        if not str(url or "").strip():
            continue
        slots[index] = {**slots[index], "status": "uploaded", "url": str(url).strip()}
    return slots


def attach_row_images(item: dict[str, Any]) -> dict[str, Any]:
    row = dict(item)
    if row.get("image_slots"):
        return row
    images = [part.strip() for part in str(row.get("images") or "").split(";") if part.strip()]
    urls, _ = split_images(images)
    row["image_slots"] = slots_from_urls(urls) if urls else empty_slots()
    row.setdefault("image_job_id", "")
    return row


def slots_from_job_view(view: Mapping[str, Any]) -> list[dict[str, Any]]:
    planned = empty_slots()
    by_index = {int(item.get("index") or 0): item for item in view.get("slots") or []}
    for index in range(1, 7):
        slot = by_index.get(index) or {}
        status = str(slot.get("status") or "empty")
        url = str(slot.get("url") or "")
        if status == "done" and url:
            status = "done"
        elif status in {"running", "queued"}:
            status = status
        elif url:
            status = "done"
        else:
            status = "empty" if view.get("status") not in {"running", "queued"} else status
        planned[index - 1] = {
            "index": index,
            "id": str(slot.get("id") or planned[index - 1]["id"]),
            "name": str(slot.get("name") or planned[index - 1]["name"]),
            "status": status,
            "url": url,
        }
    return planned


def refresh_row_job(row: Mapping[str, Any], user_id: str) -> dict[str, Any]:
    item = attach_row_images(dict(row))
    job_id = str(item.get("image_job_id") or "").strip()
    if not job_id:
        return item
    job = image_jobs.get_job(job_id, user_id)
    if job is None:
        item["image_job_id"] = ""
        return item
    view = image_jobs.public_view(job)
    item["image_slots"] = slots_from_job_view(view)
    item["image_job_status"] = view.get("status") or ""
    item["image_job_error"] = view.get("error") or ""
    return item


def _row_facts(row: Mapping[str, Any]) -> dict[str, str]:
    name = str(row.get("name") or row.get("sku") or "").strip()
    note = str(row.get("note") or "").strip()
    facts = parse_seller_facts(name, note)
    return {key: str(value).strip() for key, value in facts.items() if str(value).strip()}


def start_row_job(
    user_id: str,
    row: Mapping[str, Any],
    *,
    category_id: str = "",
    category_name: str = "",
    api: Any | None = None,
    market_golden: Mapping[str, Any] | None = None,
) -> str:
    if not api_key():
        raise ValueError("平台还没接上出图服务")
    name = str(row.get("name") or row.get("sku") or row.get("note") or "").strip()
    if not name:
        raise ValueError("这行没品名也没货号，没法画套图")
    note = str(row.get("note") or "").strip()
    images = [part.strip() for part in str(row.get("images") or "").split(";") if part.strip()]
    urls, _ = split_images(images)
    planned = image_templates.plan_stack(
        product_name=name,
        category_hint=category_name,
        note=note,
        specs=_row_facts(row),
        reference_urls=urls,
    )
    if category_id:
        from . import market_golden as mg

        golden = market_golden
        if golden is None and api is not None:
            try:
                golden = mg.fetch_category_golden(
                    api,
                    category_id=category_id,
                    category_name=category_name,
                    product_name=name,
                )
            except Exception:
                golden = None
        if golden:
            planned = mg.apply_to_plan(planned, golden)
    planned["product_name"] = name
    planned["category_id"] = category_id
    planned["category_hint"] = category_name
    job = image_jobs.create_job(user_id, planned)
    thread = threading.Thread(target=image_jobs.run_job, args=(job["id"],), daemon=True)
    thread.start()
    return str(job["id"])


def job_files_for_row(user_id: str, job_id: str) -> list[tuple[str, bytes]]:
    job = image_jobs.get_job(job_id, user_id)
    if job is None or job.get("status") != "succeeded":
        return []
    return image_jobs.uploads_for(job)


def row_has_ready_images(row: Mapping[str, Any], user_id: str) -> bool:
    slots = row.get("image_slots") or []
    done = sum(1 for item in slots if str(item.get("url") or "").strip())
    if done >= 6:
        return True
    job_id = str(row.get("image_job_id") or "").strip()
    if not job_id:
        return False
    job = image_jobs.get_job(job_id, user_id)
    return bool(job and job.get("status") == "succeeded" and len(image_jobs.uploads_for(job)) >= 1)


def apply_job_to_excel_row(row: ExcelRow, user_id: str) -> tuple[list[tuple[str, bytes]], str]:
    job_id = str(row.raw.get("image_job_id") or "").strip()
    if not job_id:
        return [], ""
    files = job_files_for_row(user_id, job_id)
    if not files:
        return [], ""
    return files[:6], "generated"
