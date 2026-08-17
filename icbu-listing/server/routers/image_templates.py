"""Category image stacks: plan prompts, then generate the 6 ICBU slots."""

from __future__ import annotations

import threading
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..deps import current_user
from ..models import User
from ..services import image_jobs, image_templates as stacks
from ..services.grsai_images import api_key

router = APIRouter(prefix="/api/v1/image-templates", tags=["image-templates"])


class PlanIn(BaseModel):
    family_id: str = ""
    product_name: str = ""
    category_id: str = ""
    category_hint: str = ""
    material: str = ""
    colors: list[str] = []
    usage: str = ""
    audience: str = ""
    features: list[str] = []
    specs: dict[str, Any] = {}
    note: str = ""
    reference_urls: list[str] = []
    size: str = ""
    pack_count: str = ""


def _plan(payload: PlanIn) -> dict[str, Any]:
    if not (payload.product_name or payload.category_hint or payload.note or payload.family_id):
        raise HTTPException(status_code=400, detail="先写品名、类目或选一个类目模板")
    specs = dict(payload.specs or {})
    if payload.size.strip():
        specs["size"] = payload.size.strip()
    if payload.pack_count.strip():
        specs["pack_count"] = payload.pack_count.strip()
    return stacks.plan_stack(
        family_id=payload.family_id,
        product_name=payload.product_name,
        category_hint=payload.category_hint,
        material=payload.material,
        colors=payload.colors,
        usage=payload.usage,
        audience=payload.audience,
        features=payload.features,
        specs=specs,
        note=payload.note,
        reference_urls=payload.reference_urls,
    )


@router.get("")
def list_templates(_: User = Depends(current_user)) -> dict[str, Any]:
    return stacks.catalog()


@router.post("/plan")
def plan(payload: PlanIn, _: User = Depends(current_user)) -> dict[str, Any]:
    return _plan(payload)


@router.post("/generate")
def generate(payload: PlanIn, user: User = Depends(current_user)) -> dict[str, Any]:
    if not api_key():
        raise HTTPException(status_code=400, detail="平台还没接上出图服务")
    planned = _plan(payload)
    planned["product_name"] = payload.product_name or planned.get("family", {}).get("name") or ""
    planned["category_id"] = payload.category_id
    planned["category_hint"] = payload.category_hint or planned.get("category_hint") or ""
    job = image_jobs.create_job(user.id, planned)
    thread = threading.Thread(target=image_jobs.run_job, args=(job["id"],), daemon=True)
    thread.start()
    latest = image_jobs.get_job(job["id"], user.id) or job
    return image_jobs.public_view(latest)


@router.get("/jobs/{job_id}")
def job_status(job_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
    job = image_jobs.get_job(job_id, user.id)
    if job is None:
        raise HTTPException(status_code=404, detail="这批图不存在")
    return image_jobs.public_view(job)


@router.get("/jobs/{job_id}/files/{filename}")
def job_file(job_id: str, filename: str, user: User = Depends(current_user)) -> FileResponse:
    job = image_jobs.get_job(job_id, user.id)
    if job is None:
        raise HTTPException(status_code=404, detail="这批图不存在")
    path = image_jobs.file_path(job, filename)
    if path is None:
        raise HTTPException(status_code=404, detail="这张图还没画好")
    media = "image/jpeg" if filename.lower().endswith((".jpg", ".jpeg")) else "image/png"
    return FileResponse(path, media_type=media, filename=filename)
