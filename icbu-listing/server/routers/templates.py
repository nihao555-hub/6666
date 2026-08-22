from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..deps import current_user, get_db, shop_for
from ..models import CategoryNode, Draft, Template, User
from ..services import catalog, sources, templates as service
from ..services.pipeline import status_of

router = APIRouter(prefix="/api/v1", tags=["templates"])


class TemplateIn(BaseModel):
    shop_id: str
    name: str
    category_id: str
    values: dict[str, Any] = {}


class ApplyIn(BaseModel):
    draft_ids: list[str]


@router.get("/templates")
def list_templates(
    shop_id: str = "",
    category_id: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[dict[str, Any]]:
    query = db.query(Template).filter(Template.user_id == user.id)
    if shop_id:
        query = query.filter(Template.shop_id == shop_id)
    if category_id:
        query = query.filter(Template.category_id == category_id)
    return [service.as_dict(item) for item in query.order_by(Template.created_at.desc()).all()]


@router.post("/templates")
def create_template(
    payload: TemplateIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    shop_for(db, user, payload.shop_id)
    if not payload.category_id:
        raise HTTPException(status_code=400, detail="模板必须绑一个叶子类目")
    node = db.get(CategoryNode, payload.category_id)
    category_label = catalog.label(node) if node is not None else ""
    row = Template(
        user_id=user.id,
        shop_id=payload.shop_id,
        name=payload.name or category_label or "未命名模板",
        category_id=payload.category_id,
        values_json=json.dumps(payload.values, ensure_ascii=False),
    )
    db.add(row)
    db.commit()
    return service.as_dict(row)


@router.patch("/templates/{template_id}")
def update_template(
    template_id: str,
    payload: TemplateIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    row = db.get(Template, template_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="模板不存在")
    shop_for(db, user, payload.shop_id)
    row.shop_id = payload.shop_id
    row.name = payload.name or row.name
    row.category_id = payload.category_id or row.category_id
    row.values_json = json.dumps(payload.values, ensure_ascii=False)
    db.commit()
    return service.as_dict(row)


@router.delete("/templates/{template_id}")
def delete_template(
    template_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, bool]:
    row = db.get(Template, template_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="模板不存在")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/templates/{template_id}/apply")
def apply_template(
    template_id: str,
    payload: ApplyIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Fill empty fields on existing drafts. Hand-filled values stay put."""
    row = db.get(Template, template_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="模板不存在")

    applied = 0
    for draft in db.query(Draft).filter(Draft.user_id == user.id, Draft.id.in_(payload.draft_ids)).all():
        try:
            values = json.loads(draft.values_json or "{}")
        except json.JSONDecodeError:
            values = {}
        merged = service.fill_blank(service.values_of(row), values)
        if merged == values:
            continue
        field_sources = sources.parse(getattr(draft, "sources_json", None))
        draft.sources_json = sources.dump(sources.mark_template_fills(values, merged, field_sources))
        draft.values_json = json.dumps(merged, ensure_ascii=False)
        try:
            issues = json.loads(draft.issues_json or "[]")
        except json.JSONDecodeError:
            issues = []
        draft.status = status_of(issues)
        applied += 1
    db.commit()
    return {"applied": applied}
