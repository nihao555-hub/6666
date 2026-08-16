"""Category image stacks: prompts only. The seller's own image model renders them."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..deps import current_user
from ..models import User
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


@router.get("")
def list_templates(_: User = Depends(current_user)) -> dict[str, Any]:
    return stacks.catalog()


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
