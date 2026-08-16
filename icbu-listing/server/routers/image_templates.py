"""Category image stacks: plan prompts, then generate one ICBU slot at a time."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ai import AiClient, AiUnavailable, ImageInput  # noqa: E402

from ..config import settings
from ..deps import current_user
from ..models import User, new_id
from ..services import image_templates as stacks

router = APIRouter(prefix="/api/v1/image-templates", tags=["image-templates"])


class PlanIn(BaseModel):
    family_id: str = ""
    product_name: str = ""
    category_hint: str = ""
    material: str = ""
    colors: list[str] = []
    usage: str = ""
    audience: str = ""
    features: list[str] = []
    specs: dict[str, Any] = {}
    note: str = ""


def _generated_dir(user: User) -> Path:
    folder = Path(settings.upload_dir) / user.id / "generated"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


@router.get("")
def list_templates(_: User = Depends(current_user)) -> dict[str, Any]:
    catalog = stacks.catalog()
    catalog["image_enabled"] = settings.image_enabled
    catalog["image_model"] = settings.image_model
    return catalog


@router.post("/plan")
def plan(payload: PlanIn, _: User = Depends(current_user)) -> dict[str, Any]:
    if not (payload.product_name or payload.category_hint or payload.note or payload.family_id):
        raise HTTPException(status_code=400, detail="先写品名、类目或选一个类目模板")
    return stacks.plan_stack(
        family_id=payload.family_id,
        product_name=payload.product_name,
        category_hint=payload.category_hint,
        material=payload.material,
        colors=payload.colors,
        usage=payload.usage,
        audience=payload.audience,
        features=payload.features,
        specs=payload.specs,
        note=payload.note,
    )


@router.post("/generate")
async def generate_slot(
    slot_id: str = Form(""),
    prompt: str = Form(""),
    product_name: str = Form(""),
    family_id: str = Form(""),
    references: list[UploadFile] = File(default=[]),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    if not prompt.strip():
        raise HTTPException(status_code=400, detail="没有生图提示词")
    ai = AiClient.from_env_or_none()
    if ai is None:
        raise HTTPException(status_code=400, detail="没有配置 OPENAI_API_KEY，无法生图")
    if not ai.image_model():
        raise HTTPException(status_code=400, detail="没有配置 IMAGE_MODEL，无法生图")

    refs: list[ImageInput] = []
    for item in references[:4]:
        content = await item.read()
        if content:
            refs.append(ImageInput(filename=item.filename or "ref.jpg", content=content))
    try:
        png = ai.generate_image(prompt, references=refs)
    except AiUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    file_id = new_id()
    safe_slot = "".join(ch for ch in (slot_id or "slot") if ch.isalnum() or ch in "-_")[:24] or "slot"
    filename = f"{safe_slot}-{file_id}.png"
    path = _generated_dir(user) / filename
    path.write_bytes(png)
    return {
        "id": file_id,
        "slot_id": slot_id,
        "family_id": family_id,
        "product_name": product_name,
        "filename": filename,
        "url": f"/api/v1/image-templates/files/{filename}",
        "bytes": len(png),
    }


@router.get("/files/{filename}")
def generated_file(filename: str, user: User = Depends(current_user)) -> FileResponse:
    safe = Path(filename).name
    path = _generated_dir(user) / safe
    if not path.is_file():
        raise HTTPException(status_code=404, detail="图片不存在")
    return FileResponse(path, media_type="image/png", filename=safe)
