from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings
from ..deps import current_user, get_db
from ..models import Draft, Job, Product, Shop, User
from ..services.situation import Snapshot, recommend

router = APIRouter(prefix="/api/v1", tags=["overview"])


@router.get("/overview")
def overview(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict[str, Any]:
    shops = db.query(Shop).filter(Shop.user_id == user.id).count()
    products = db.query(Product).filter(Product.user_id == user.id).count()
    by_status = dict(
        db.query(Draft.status, func.count(Draft.id)).filter(Draft.user_id == user.id).group_by(Draft.status).all()
    )
    jobs = dict(
        db.query(Job.status, func.count(Job.id)).filter(Job.user_id == user.id).group_by(Job.status).all()
    )
    red_issues = 0
    for (raw,) in db.query(Draft.issues_json).filter(Draft.user_id == user.id, Draft.status == "red").all():
        try:
            red_issues += sum(1 for item in json.loads(raw or "[]") if item.get("level") == "red")
        except json.JSONDecodeError:
            continue

    shop_row = db.query(Shop).filter(Shop.user_id == user.id).order_by(Shop.created_at).first()
    defaults_untouched = True
    online_count = None
    if shop_row is not None:
        raw = (shop_row.defaults_json or "").strip()
        defaults_untouched = raw in {"", "{}"}
        if shop_row.online_count >= 0:
            online_count = shop_row.online_count

    situation = recommend(
        Snapshot(
            shops=shops,
            defaults_untouched=defaults_untouched,
            products=products,
            red=by_status.get("red", 0),
            ready=by_status.get("green", 0) + by_status.get("yellow", 0),
            drafts=sum(by_status.values()),
            online_count=online_count,
            ai_enabled=settings.ai_enabled,
        )
    )

    return {
        "shops": shops,
        "products": products,
        "drafts": sum(by_status.values()),
        "drafts_by_status": by_status,
        "red": by_status.get("red", 0),
        "red_issues": red_issues,
        "ready": by_status.get("green", 0) + by_status.get("yellow", 0),
        "success": jobs.get("success", 0),
        "failed": jobs.get("failed", 0),
        "ai_enabled": settings.ai_enabled,
        "image_enabled": settings.image_enabled,
        "platform_ready": settings.has_platform_app,
        "situation": situation,
    }
