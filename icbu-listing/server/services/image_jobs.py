"""Background jobs that turn a 6-slot plan into generated listing photos."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from ..models import new_id
from . import grsai_images
from .grsai_images import GrsaiError, generated_dir

_LOCK = threading.Lock()
_JOBS: dict[str, dict[str, Any]] = {}


def _job_dir(job_id: str) -> Path:
    path = generated_dir() / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _persist(job: dict[str, Any]) -> None:
    path = _job_dir(str(job["id"])) / "job.json"
    path.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")


def _load_from_disk(job_id: str) -> dict[str, Any] | None:
    path = generated_dir() / job_id / "job.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("id") != job_id:
        return None
    return payload


def get_job(job_id: str, user_id: str | None = None) -> dict[str, Any] | None:
    with _LOCK:
        job = _JOBS.get(job_id)
    if job is None:
        job = _load_from_disk(job_id)
        if job is None:
            return None
        with _LOCK:
            _JOBS[job_id] = job
    if user_id is not None and job.get("user_id") != user_id:
        return None
    return job


def _update(job_id: str, **changes: Any) -> dict[str, Any]:
    with _LOCK:
        job = dict(_JOBS[job_id])
        job.update(changes)
        _JOBS[job_id] = job
        _persist(job)
    return job


def create_job(user_id: str, plan: dict[str, Any]) -> dict[str, Any]:
    job_id = new_id()
    slots = []
    for item in plan.get("slots") or []:
        slots.append(
            {
                "id": item.get("id"),
                "index": item.get("index"),
                "name": item.get("name"),
                "buyer_job": item.get("buyer_job"),
                "prompt": item.get("prompt"),
                "status": "queued",
                "filename": "",
                "url": "",
                "remote_url": "",
            }
        )
    family = plan.get("family") or {}
    job = {
        "id": job_id,
        "user_id": user_id,
        "status": "queued",
        "progress": "排队出图",
        "done": 0,
        "total": len(slots),
        "error": "",
        "product_name": plan.get("product_name") or family.get("name") or "",
        "family": family,
        "slots": slots,
    }
    with _LOCK:
        _JOBS[job_id] = job
        _persist(job)
    return job


def public_view(job: dict[str, Any]) -> dict[str, Any]:
    slots = []
    for item in job.get("slots") or []:
        filename = item.get("filename") or ""
        slots.append(
            {
                "id": item.get("id"),
                "index": item.get("index"),
                "name": item.get("name"),
                "buyer_job": item.get("buyer_job"),
                "prompt": item.get("prompt"),
                "status": item.get("status") or "queued",
                "url": f"/api/v1/image-templates/jobs/{job['id']}/files/{filename}" if filename else "",
            }
        )
    return {
        "id": job["id"],
        "status": job.get("status") or "queued",
        "progress": job.get("progress") or "",
        "done": job.get("done") or 0,
        "total": job.get("total") or len(slots),
        "error": job.get("error") or "",
        "product_name": job.get("product_name") or "",
        "family": job.get("family") or {},
        "slots": slots,
    }


def file_path(job: dict[str, Any], filename: str) -> Path | None:
    if not filename or "/" in filename or "\\" in filename or filename.startswith("."):
        return None
    known = {item.get("filename") for item in job.get("slots") or []}
    if filename not in known:
        return None
    path = _job_dir(str(job["id"])) / filename
    return path if path.is_file() else None


def uploads_for(job: dict[str, Any]) -> list[tuple[str, bytes]]:
    uploads: list[tuple[str, bytes]] = []
    for item in job.get("slots") or []:
        filename = item.get("filename") or ""
        path = file_path(job, filename)
        if path is None:
            continue
        uploads.append((filename, path.read_bytes()))
    return uploads


def run_job(job_id: str) -> None:
    job = get_job(job_id)
    if job is None:
        return
    _update(job_id, status="running", progress="开始出图", error="")
    reference: list[str] = []
    slots = list(job.get("slots") or [])
    try:
        for index, slot in enumerate(slots):
            name = slot.get("name") or f"第 {index + 1} 张"
            _update(job_id, progress=f"正在画第 {index + 1}/{len(slots)} 张：{name}")
            slots[index] = {**slot, "status": "running"}
            _update(job_id, slots=list(slots))
            content, remote_url = grsai_images.generate_one(
                str(slot.get("prompt") or ""),
                urls=reference,
            )
            ext = "png"
            if remote_url.lower().endswith(".jpg") or remote_url.lower().endswith(".jpeg"):
                ext = "jpg"
            filename = f"{int(slot.get('index') or index + 1):02d}-{slot.get('id') or 'slot'}.{ext}"
            dest = _job_dir(job_id) / filename
            dest.write_bytes(content)
            slots[index] = {
                **slot,
                "status": "done",
                "filename": filename,
                "remote_url": remote_url,
            }
            if remote_url and not reference:
                reference = [remote_url]
            _update(job_id, slots=list(slots), done=index + 1)
        _update(job_id, status="succeeded", progress="6 张套图已画好", error="")
    except GrsaiError as exc:
        _update(job_id, status="failed", error=exc.message, progress=exc.message)
    except Exception:
        _update(job_id, status="failed", error="出图失败，请再试一次", progress="出图失败，请再试一次")
