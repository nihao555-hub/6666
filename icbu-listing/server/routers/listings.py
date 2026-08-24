from __future__ import annotations

import json
import re
import threading
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ai import AiClient, ImageInput, Understanding  # noqa: E402
from gop_client import GopError  # noqa: E402

from ..db import SessionLocal
from ..deps import current_user, get_db, owned_draft, shop_for
from ..models import CategoryNode, Draft, Job, Product, Shop, User, new_id
from ..services import (
    audit,
    audit_logistics,
    catalog,
    dedup,
    distribution,
    images as image_service,
    issue_filter,
    pipeline,
    products as catalogue,
    publisher,
    sources,
)
from ..services import feed_sessions, image_jobs, shop_categories, excel_import
from ..services.shop_client import ShopNotConnected, shop_api, shop_defaults

router = APIRouter(prefix="/api/v1", tags=["listings"])

MAX_IMAGES = 6
SKU_SPLIT = re.compile(r"[_\-.]")


class DraftPatch(BaseModel):
    values: dict[str, Any] | None = None
    price: str | None = None
    moq: str | None = None
    sku: str | None = None
    category_id: str | None = None
    regenerate: bool = False
    reviewed: bool | None = None
    audit_note: str = ""


class PublishBatchIn(BaseModel):
    draft_ids: list[str]


class BulkReviewIn(BaseModel):
    draft_ids: list[str] = []
    batch_id: str = ""
    note: str = ""


class GeneratedFeedIn(BaseModel):
    shop_id: str
    job_id: str
    sku: str = ""
    price: str = ""
    moq: str = ""
    note: str = ""
    category_id: str = ""
    session_id: str = ""


def draft_view(draft: Draft, detailed: bool = False, shop_name: str = "") -> dict[str, Any]:
    view: dict[str, Any] = {
        "id": draft.id,
        "shop_id": draft.shop_id,
        "shop_name": shop_name,
        "batch_id": draft.batch_id,
        "sku": draft.sku,
        "title": draft.title,
        "price": draft.price,
        "moq": draft.moq,
        "status": draft.status,
        "category_id": draft.category_id,
        "category_name": draft.category_name,
        "category_confidence": draft.category_confidence,
        "issues": issue_filter.for_user(_json(draft.issues_json, [])),
        "images": _json(draft.images_json, []),
        "product_id": draft.product_id,
        "product_online_id": draft.product_online_id,
        "updated_at": draft.updated_at.isoformat(),
        "quality": _json(draft.ai_json, {}).get("quality"),
        "reviewed": audit.is_reviewed(draft),
        "audit": audit.view(draft),
    }
    if detailed:
        view["values"] = _json(draft.values_json, {})
        view["ai"] = _json(draft.ai_json, {})
        view["category_candidates"] = _json(draft.category_candidates_json, [])
        view["sources"] = sources.view(sources.parse(getattr(draft, "sources_json", None)))
        view["audit_fields"] = []
    return view


def _detailed_draft(db: Session, user: User, draft: Draft) -> dict[str, Any]:
    view = draft_view(draft, detailed=True)
    view["audit_fields"] = _audit_fields_for(db, user, draft)
    try:
        shop = shop_for(db, user, draft.shop_id)
        xml = catalog.get_schema_xml(db, shop_api(shop), draft.category_id) if draft.category_id else ""
        view["logistics"] = audit_logistics.panel_for_draft(db, shop, draft, xml=xml)
    except (ShopNotConnected, GopError, HTTPException, RuntimeError):
        view["logistics"] = {"ready": True, "items": [], "shipping_options": [], "template_hint": {}}
    return view


def _audit_fields_for(db: Session, user: User, draft: Draft) -> list[dict[str, Any]]:
    if not draft.category_id:
        return []
    try:
        shop = shop_for(db, user, draft.shop_id)
        xml = catalog.get_schema_xml(db, shop_api(shop), draft.category_id)
    except (ShopNotConnected, GopError, HTTPException, RuntimeError):
        return []
    return audit.form_fields(xml, _json(draft.values_json, {}), sources.parse(getattr(draft, "sources_json", None)))


def job_view(job: Job, shop_name: str = "") -> dict[str, Any]:
    return {
        "id": job.id,
        "draft_id": job.draft_id,
        "shop_id": job.shop_id,
        "shop_name": shop_name,
        "batch_id": job.batch_id,
        "status": job.status,
        "mode": job.mode,
        "attempts": job.attempts,
        "sku": job.sku,
        "title": job.title,
        "product_id": job.product_online_id,
        "error": job.error,
        "error_fields": _json(job.error_fields_json, []),
        "created_at": job.created_at.isoformat(),
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


def _shop_names(db: Session, user: User, shop_ids: list[str]) -> dict[str, str]:
    ids = [item for item in set(shop_ids) if item]
    if not ids:
        return {}
    rows = db.query(Shop).filter(Shop.user_id == user.id, Shop.id.in_(ids)).all()
    return {shop.id: shop.name or shop.account or "未命名店铺" for shop in rows}


def _json(raw: str, fallback: Any) -> Any:
    try:
        return json.loads(raw or "")
    except (json.JSONDecodeError, TypeError):
        return fallback


def _sku_from_filename(filename: str) -> str:
    stem = filename.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    parts = SKU_SPLIT.split(stem)
    return parts[0] if parts and parts[0] else stem


def _store_draft(
    db: Session,
    user: User,
    shop: Shop,
    result: pipeline.DraftResult,
    *,
    sku: str,
    price: str,
    moq: str,
    bank_images: list[image_service.BankImage],
    batch_id: str = "",
    draft: Draft | None = None,
    field_sources: dict[str, str] | None = None,
) -> Draft:
    if draft is None:
        draft = Draft(user_id=user.id, shop_id=shop.id, batch_id=batch_id)
        db.add(draft)
    draft.sku = sku
    draft.price = price
    draft.moq = moq
    draft.title = result.title or draft.title
    draft.category_id = result.category_id
    draft.category_name = result.category_name
    draft.category_confidence = result.category_confidence
    draft.category_candidates_json = json.dumps(result.category_candidates, ensure_ascii=False)
    draft.values_json = json.dumps(result.values, ensure_ascii=False)
    draft.issues_json = json.dumps(result.issues, ensure_ascii=False)
    draft.images_json = json.dumps([item.as_dict() for item in bank_images], ensure_ascii=False)
    draft.ai_json = json.dumps(result.ai, ensure_ascii=False)
    draft.sources_json = sources.dump(field_sources or sources.infer_initial(result.values))
    draft.status = result.status
    draft.updated_at = datetime.utcnow()
    db.commit()

    # Needs the row committed so it can be compared against its siblings.
    risk = dedup.check(db, draft)
    if risk is not None:
        issues = list(result.issues) + [risk.as_issue()]
        draft.issues_json = json.dumps(issues, ensure_ascii=False)
        draft.status = pipeline.status_of(issues)
        db.commit()
    return draft


def _parse_photobank_images(raw: str) -> list[image_service.BankImage]:
    if not raw or not raw.strip():
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="图片银行选择不是合法 JSON") from exc
    if not isinstance(payload, list):
        raise HTTPException(status_code=400, detail="图片银行选择必须是数组")
    bank: list[image_service.BankImage] = []
    for item in payload[:MAX_IMAGES]:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        file_id = str(item.get("file_id") or item.get("id") or "").strip()
        file_name = str(item.get("file_name") or "product.jpg").strip() or "product.jpg"
        bank.append(image_service.BankImage(file_name=file_name, file_id=file_id, url=url))
    return bank


def _generate(
    db: Session,
    user: User,
    shop: Shop,
    *,
    uploads: list[tuple[str, bytes]],
    sku: str,
    price: str,
    moq: str,
    note: str,
    category_id: str = "",
    batch_id: str = "",
    bank_images: list[image_service.BankImage] | None = None,
) -> Draft:
    """Feeding always lands a catalogue product first.

    The draft is then produced from that product, so the same photos and the
    same recognition can be reused when the seller sends it to another shop.
    """
    ai = AiClient.from_env_or_none()
    if bank_images:
        understanding, ai_error = pipeline.understand(
            ai,
            [ImageInput(filename=item.file_name, url=item.absolute_url) for item in bank_images[:MAX_IMAGES]],
            note,
        )
        uploads: list[tuple[str, bytes]] = []
    else:
        understanding, ai_error = pipeline.understand(
            ai, [ImageInput(filename=name, content=content) for name, content in uploads], note
        )

    product = Product(
        user_id=user.id,
        sku=sku,
        name=understanding.product_name,
        price=price,
        moq=moq,
        note=note,
        understanding_json=json.dumps(understanding.raw, ensure_ascii=False),
    )
    db.add(product)
    db.commit()
    if uploads:
        catalogue.save_images(db, user, product, uploads[:MAX_IMAGES])

    draft = distribution.build_draft_for_shop(
        db,
        user,
        shop,
        product,
        price=price,
        moq=moq,
        ai=ai,
        batch_id=batch_id,
        forced_category_id=category_id,
        bank_images=bank_images,
    )

    if ai_error:
        issues = _json(draft.issues_json, [])
        issues.append({"field_id": "ai", "field_name": "AI 成稿", "level": "red", "message": ai_error, "path": "ai"})
        draft.issues_json = json.dumps(issues, ensure_ascii=False)
        draft.status = "red"
        db.commit()
    return draft


@router.post("/listings/feed")
async def feed(
    shop_id: str = Form(...),
    sku: str = Form(""),
    price: str = Form(""),
    moq: str = Form(""),
    note: str = Form(""),
    category_id: str = Form(""),
    session_id: str = Form(""),
    photobank_images: str = Form(""),
    files: list[UploadFile] = File(default_factory=list),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    shop = shop_for(db, user, shop_id)
    uploads = [(item.filename or "image.jpg", await item.read()) for item in files[:MAX_IMAGES]]
    uploads = [(name, content) for name, content in uploads if content]
    session = feed_sessions.get_owned(db, user.id, session_id) if session_id else None
    if not uploads and session is not None:
        uploads = feed_sessions.file_bytes(session, "photos")[:MAX_IMAGES]
    bank_images = _parse_photobank_images(photobank_images)
    if not uploads and not bank_images:
        raise HTTPException(status_code=400, detail="至少要传一张图，或从图片银行选图")

    try:
        draft = _generate(
            db,
            user,
            shop,
            uploads=uploads,
            sku=sku or (_sku_from_filename(uploads[0][0]) if uploads else sku or "PHOTO"),
            price=price,
            moq=moq,
            note=note,
            category_id=category_id,
            bank_images=bank_images or None,
        )
    except ShopNotConnected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if session is not None:
        feed_sessions.save(db, session, status="done", shop_id=shop.id)
    return draft_view(draft, detailed=True)


@router.post("/listings/feed-from-generated")
def feed_from_generated(
    payload: GeneratedFeedIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    shop = shop_for(db, user, payload.shop_id)
    job = image_jobs.get_job(payload.job_id, user.id)
    if job is None:
        raise HTTPException(status_code=404, detail="这批图不存在")
    if job.get("status") != "succeeded":
        raise HTTPException(status_code=400, detail="图片还没画完")
    uploads = image_jobs.uploads_for(job)
    if not uploads:
        raise HTTPException(status_code=400, detail="这批图还不能用")

    product_name = str(job.get("product_name") or "").strip()
    sku = (payload.sku or "").strip() or re.sub(r"[^A-Za-z0-9]+", "-", product_name).strip("-")[:40] or "GEN"
    category_id = (payload.category_id or job.get("category_id") or "").strip()
    extra = "平台按类目生成了 6 张套图，不是实拍。买家要实拍时再补。"
    note = "\n".join(part for part in (payload.note.strip(), extra) if part)
    session = feed_sessions.get_owned(db, user.id, payload.session_id) if payload.session_id else None

    try:
        draft = _generate(
            db,
            user,
            shop,
            uploads=uploads[:MAX_IMAGES],
            sku=sku,
            price=payload.price,
            moq=payload.moq,
            note=note,
            category_id=category_id,
        )
    except ShopNotConnected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    issues = _json(draft.issues_json, [])
    issues.append(
        {
            "field_id": "scImages",
            "field_name": "商品图片",
            "level": "yellow",
            "message": "这 6 张是平台生成图，不是实拍。买家问实拍时要自己补。",
            "path": "scImages",
        }
    )
    draft.issues_json = json.dumps(issues, ensure_ascii=False)
    if draft.status == "green":
        draft.status = "yellow"
    db.commit()
    if session is not None:
        feed_sessions.save(db, session, status="done", shop_id=shop.id)
    return draft_view(draft, detailed=True)


@router.post("/listings/batch")
async def feed_batch(
    shop_id: str = Form(...),
    price: str = Form(""),
    moq: str = Form(""),
    note: str = Form(""),
    session_id: str = Form(""),
    files: list[UploadFile] = File(default_factory=list),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Drop a folder: images are grouped into products by filename prefix.

    `SKU-1001_1.jpg`, `SKU-1001_2.jpg` become one draft; the work runs in the
    background so the seller can close the tab.
    """
    shop = shop_for(db, user, shop_id)

    grouped: dict[str, list[tuple[str, bytes]]] = {}
    for item in files:
        content = await item.read()
        if not content:
            continue
        grouped.setdefault(_sku_from_filename(item.filename or "image.jpg"), []).append(
            (item.filename or "image.jpg", content)
        )
    session = feed_sessions.get_owned(db, user.id, session_id) if session_id else None
    if not grouped and session is not None:
        for name, content in feed_sessions.file_bytes(session, "batch"):
            grouped.setdefault(_sku_from_filename(name), []).append((name, content))
    if not grouped:
        raise HTTPException(status_code=400, detail="没有可用的图片")

    batch_id = new_id()
    payload = {sku: items[:MAX_IMAGES] for sku, items in grouped.items()}

    thread = threading.Thread(
        target=_run_batch,
        args=(user.id, shop.id, batch_id, payload, price, moq, note),
        daemon=True,
    )
    thread.start()
    if session is not None:
        feed_sessions.save(
            db,
            session,
            status="done",
            shop_id=shop.id,
            payload={"batchId": batch_id, "rowCount": len(payload)},
        )
    return {"batch_id": batch_id, "count": len(payload), "skus": list(payload)}


def _run_batch(
    user_id: str,
    shop_id: str,
    batch_id: str,
    payload: dict[str, list[tuple[str, bytes]]],
    price: str,
    moq: str,
    note: str,
) -> None:
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        shop = db.get(Shop, shop_id)
        if user is None or shop is None:
            return
        for sku, uploads in payload.items():
            try:
                _generate(
                    db,
                    user,
                    shop,
                    uploads=uploads,
                    sku=sku,
                    price=price,
                    moq=moq,
                    note=note,
                    batch_id=batch_id,
                )
            except Exception as exc:  # one bad product must not kill the batch
                draft = Draft(
                    user_id=user_id,
                    shop_id=shop_id,
                    batch_id=batch_id,
                    sku=sku,
                    status="red",
                    issues_json=json.dumps(
                        [{"field_id": "ai", "field_name": "成稿", "level": "red", "message": str(exc)[:300]}],
                        ensure_ascii=False,
                    ),
                )
                db.add(draft)
                db.commit()
    finally:
        db.close()


@router.get("/batches/{batch_id}")
def batch_progress(
    batch_id: str,
    total: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    drafts = db.query(Draft).filter(Draft.user_id == user.id, Draft.batch_id == batch_id).all()
    products = db.query(Product).filter(Product.user_id == user.id, Product.batch_id == batch_id).count()
    counts = {"red": 0, "yellow": 0, "green": 0, "published": 0, "failed": 0, "publishing": 0}
    reviewed = 0
    ready = 0
    for draft in drafts:
        counts[draft.status] = counts.get(draft.status, 0) + 1
        if draft.reviewed_at:
            reviewed += 1
        if audit.can_publish(draft)[0]:
            ready += 1
    done = max(len(drafts), products)
    expected = total if total > 0 else done
    return {
        "batch_id": batch_id,
        "total": expected,
        "done": done,
        "complete": done >= expected if expected else bool(drafts),
        "products": products,
        "drafts": len(drafts),
        "reviewed": reviewed,
        "ready": ready,
        "pending": len(drafts) - reviewed,
        "counts": counts,
    }


@router.get("/drafts")
def list_drafts(
    shop_id: str = "",
    status: str = "",
    batch_id: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[dict[str, Any]]:
    query = db.query(Draft).filter(Draft.user_id == user.id)
    if shop_id:
        query = query.filter(Draft.shop_id == shop_id)
    if status:
        query = query.filter(Draft.status == status)
    if batch_id:
        query = query.filter(Draft.batch_id == batch_id)
    drafts = query.order_by(Draft.updated_at.desc()).limit(500).all()
    names = _shop_names(db, user, [draft.shop_id for draft in drafts])
    return [draft_view(draft, shop_name=names.get(draft.shop_id, "")) for draft in drafts]


@router.get("/drafts/{draft_id}")
def get_draft(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    draft: Draft = Depends(owned_draft),
) -> dict[str, Any]:
    return _detailed_draft(db, user, draft)


@router.patch("/drafts/{draft_id}")
def patch_draft(
    payload: DraftPatch,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    draft: Draft = Depends(owned_draft),
) -> dict[str, Any]:
    shop = shop_for(db, user, draft.shop_id)

    if payload.category_id and payload.category_id != draft.category_id or payload.regenerate:
        stored = _json(draft.ai_json, {}).get("understanding") or {}
        understanding = Understanding.from_payload(stored)
        bank_images = [image_service.from_dict(item) for item in _json(draft.images_json, [])]
        old_values = _json(draft.values_json, {})
        field_sources = sources.parse(getattr(draft, "sources_json", None))
        category_changed = bool(payload.category_id and payload.category_id != draft.category_id)
        if category_changed:
            field_sources = sources.unlock_for_category_change(field_sources)
        from ..services.fact_bundle import FactBundle

        ai_data = _json(draft.ai_json, {})
        fb_raw = ai_data.get("fact_bundle")
        fact_bundle = FactBundle.from_dict(fb_raw) if isinstance(fb_raw, dict) else None
        result = pipeline.build_draft(
            db,
            shop_api(shop),
            shop,
            understanding=understanding,
            images=bank_images,
            price=payload.price if payload.price is not None else draft.price,
            moq=payload.moq if payload.moq is not None else draft.moq,
            defaults=shop_defaults(shop),
            ai=AiClient.from_env_or_none(),
            forced_category_id=payload.category_id or draft.category_id,
            language=str(shop_defaults(shop).get("language") or "en_US"),
            fact_bundle=fact_bundle,
        )
        result.values = sources.keep_locked(old_values, result.values, field_sources)
        if field_sources.get("productTitle") in sources.LOCKED and old_values.get("productTitle"):
            result.title = str(old_values["productTitle"])
        _store_draft(
            db,
            user,
            shop,
            result,
            sku=payload.sku or draft.sku,
            price=payload.price if payload.price is not None else draft.price,
            moq=payload.moq if payload.moq is not None else draft.moq,
            bank_images=bank_images,
            draft=draft,
            field_sources=field_sources,
        )
        audit.clear_review(draft, "regenerate" if payload.regenerate else "category")
        if payload.reviewed:
            audit.mark_reviewed(draft, payload.audit_note)
        db.commit()
        return _detailed_draft(db, user, draft)

    values = _json(draft.values_json, {})
    field_sources = sources.parse(getattr(draft, "sources_json", None))
    if payload.values:
        field_sources = sources.mark_user_edits(values, payload.values, field_sources)
        values.update(payload.values)
    if payload.price is not None:
        draft.price = payload.price
        field_sources["ladderPrice"] = "user"
    if payload.moq is not None:
        draft.moq = payload.moq
        field_sources["minOrderQuantity"] = "user"
    if payload.sku is not None:
        draft.sku = payload.sku
    if payload.price is not None or payload.moq is not None:
        if draft.price and draft.moq:
            values["ladderPrice"] = {"ladderPrice_0": {"quantity": draft.moq, "price": draft.price}}
        if draft.moq:
            values["minOrderQuantity"] = draft.moq

    draft.values_json = json.dumps(values, ensure_ascii=False)
    draft.sources_json = sources.dump(field_sources)
    draft.title = str(values.get("productTitle") or draft.title)

    if draft.category_id:
        xml = catalog.get_schema_xml(db, shop_api(shop), draft.category_id)
        pipeline.rescore_draft(draft, xml, db=db, shop=shop)

    draft.updated_at = datetime.utcnow()
    if payload.reviewed:
        audit.mark_reviewed(draft, payload.audit_note)
    elif payload.audit_note:
        payload_audit = audit.parse(getattr(draft, "audit_json", None))
        payload_audit["note"] = payload.audit_note.strip()
        draft.audit_json = audit.dump(payload_audit)
    db.commit()
    return _detailed_draft(db, user, draft)


@router.post("/drafts/bulk-review")
def bulk_review_drafts(
    payload: BulkReviewIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Mark many drafts reviewed at once — for batches of hundreds/thousands."""
    query = db.query(Draft).filter(Draft.user_id == user.id)
    if payload.batch_id:
        query = query.filter(Draft.batch_id == payload.batch_id)
    if payload.draft_ids:
        query = query.filter(Draft.id.in_(payload.draft_ids))
    rows = query.all()
    reviewed = 0
    skipped = 0
    for draft in rows:
        issues = issue_filter.for_user(_json(draft.issues_json, []))
        if draft.status == "red" or any(item.get("level") == "red" for item in issues):
            skipped += 1
            continue
        audit.mark_reviewed(draft, payload.note)
        reviewed += 1
    db.commit()
    return {"ok": True, "reviewed": reviewed, "skipped": skipped, "total": len(rows)}


@router.delete("/drafts/{draft_id}")
def delete_draft(db: Session = Depends(get_db), draft: Draft = Depends(owned_draft)) -> dict[str, bool]:
    db.delete(draft)
    db.commit()
    return {"ok": True}


def _publish_one(db: Session, user: User, shop: Shop, draft: Draft, *, job: Job | None = None) -> Job:
    allowed, reason = audit.can_publish(draft)
    if not allowed:
        if job is None:
            job = Job(
                user_id=user.id,
                shop_id=shop.id,
                draft_id=draft.id,
                batch_id=draft.batch_id,
                mode=shop.publish_mode,
                status="failed",
                attempts=1,
                sku=draft.sku,
                title=draft.title,
                error=reason,
                finished_at=datetime.utcnow(),
            )
            db.add(job)
        else:
            job.mode = shop.publish_mode
            job.status = "failed"
            job.error = reason
            job.attempts = (job.attempts or 0) + 1
            job.finished_at = datetime.utcnow()
        db.commit()
        return job

    if job is None:
        job = Job(
            user_id=user.id,
            shop_id=shop.id,
            draft_id=draft.id,
            batch_id=draft.batch_id,
            mode=shop.publish_mode,
            status="running",
            attempts=1,
            sku=draft.sku,
            title=draft.title,
        )
        db.add(job)
    else:
        job.mode = shop.publish_mode
        job.status = "running"
        job.attempts = (job.attempts or 0) + 1
        job.error = ""
        job.error_fields_json = ""
        job.finished_at = None
        job.product_online_id = ""
    draft.status = "publishing"
    db.commit()

    try:
        api = shop_api(shop)
        xml = catalog.get_schema_xml(db, api, draft.category_id)
        outcome = publisher.publish(
            api,
            draft.category_id,
            xml,
            _json(draft.values_json, {}),
            mode=shop.publish_mode,
        )
    except (GopError, ShopNotConnected, RuntimeError) as exc:
        outcome = publisher.PublishOutcome(ok=False, error=str(exc))

    job.finished_at = datetime.utcnow()
    if outcome.ok:
        job.status = "success"
        job.product_online_id = outcome.product_id
        draft.status = "published"
        draft.product_online_id = outcome.product_id
    else:
        job.status = "failed"
        job.error = outcome.error
        job.error_fields_json = json.dumps(outcome.error_fields, ensure_ascii=False)
        draft.status = "failed"
    db.commit()
    return job


@router.post("/drafts/{draft_id}/publish")
def publish_draft(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    draft: Draft = Depends(owned_draft),
) -> dict[str, Any]:
    shop = shop_for(db, user, draft.shop_id)
    allowed, reason = audit.can_publish(draft)
    if not allowed:
        raise HTTPException(status_code=400, detail=reason)
    return job_view(_publish_one(db, user, shop, draft))


@router.post("/drafts/publish")
def publish_many(
    payload: PublishBatchIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    drafts = (
        db.query(Draft)
        .filter(Draft.user_id == user.id, Draft.id.in_(payload.draft_ids))
        .all()
    )
    if not drafts:
        raise HTTPException(status_code=404, detail="没有找到可发布的草稿")

    skipped = []
    eligible = []
    for draft in drafts:
        allowed, reason = audit.can_publish(draft)
        if allowed:
            eligible.append(draft)
        else:
            skipped.append({"id": draft.id, "sku": draft.sku, "reason": reason})
    if not eligible:
        raise HTTPException(status_code=400, detail=skipped[0]["reason"] if skipped else "没有可发布的草稿")

    shops = {shop.id: shop for shop in db.query(Shop).filter(Shop.user_id == user.id).all()}
    queued = []
    for draft in eligible:
        shop = shops.get(draft.shop_id)
        job = Job(
            user_id=user.id,
            shop_id=draft.shop_id,
            draft_id=draft.id,
            batch_id=draft.batch_id,
            mode=(shop.publish_mode if shop is not None else "draft"),
            status="queued",
            sku=draft.sku,
            title=draft.title,
        )
        db.add(job)
        queued.append(job.id)
    db.commit()

    threading.Thread(target=_run_publish_queue, args=(user.id, queued), daemon=True).start()
    return {"queued": len(queued), "job_ids": queued, "skipped": skipped}


def _run_publish_queue(user_id: str, job_ids: list[str]) -> None:
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if user is None:
            return
        for job_id in job_ids:
            job = db.get(Job, job_id)
            if job is None or job.status != "queued":
                continue
            draft = db.get(Draft, job.draft_id)
            shop = db.get(Shop, job.shop_id)
            if draft is None or shop is None:
                job.status = "failed"
                job.error = "草稿或店铺已经不存在"
                job.finished_at = datetime.utcnow()
                db.commit()
                continue
            _publish_one(db, user, shop, draft, job=job)
    finally:
        db.close()


@router.get("/jobs")
def list_jobs(
    shop_id: str = "",
    status: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[dict[str, Any]]:
    query = db.query(Job).filter(Job.user_id == user.id)
    if shop_id:
        query = query.filter(Job.shop_id == shop_id)
    if status:
        query = query.filter(Job.status == status)
    jobs = query.order_by(Job.created_at.desc()).limit(300).all()
    names = _shop_names(db, user, [job.shop_id for job in jobs])
    return [job_view(job, shop_name=names.get(job.shop_id, "")) for job in jobs]


@router.post("/jobs/{job_id}/retry")
def retry_job(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    job = db.get(Job, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="任务不存在")
    draft = db.get(Draft, job.draft_id)
    shop = db.get(Shop, job.shop_id)
    if draft is None or shop is None:
        raise HTTPException(status_code=400, detail="草稿或店铺已经不存在")
    allowed, reason = audit.can_publish(draft)
    if not allowed:
        raise HTTPException(status_code=400, detail=reason)
    return job_view(_publish_one(db, user, shop, draft))


@router.get("/shops/{shop_id}/categories")
def browse_categories(
    shop_id: str,
    parent: str = "0",
    sidebar: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    shop = shop_for(db, user, shop_id)
    try:
        api = shop_api(shop)
    except ShopNotConnected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    parent = str(parent or "0")
    db_children = catalog.children_from_db(db, parent)
    if db_children:
        node = catalog.get_node(db, api, parent, fetch=False) or db.get(CategoryNode, parent)
        if node is None and parent == "0":
            node = CategoryNode(
                category_id="0",
                name="All Categories",
                cn_name="全部类目",
                level=0,
                is_leaf=False,
                parent_id="",
            )
        if node is None:
            node = CategoryNode(
                category_id=parent,
                name=parent,
                cn_name="",
                level=0,
                is_leaf=False,
                parent_id="",
            )
        recent: list[dict[str, Any]] = []
        used: list[dict[str, Any]] = []
        if parent == "0" and sidebar:
            recent = shop_categories.recent_picks(db, shop, user)
            used = shop_categories.used_leaves(db, shop, api=api, include_online=True, cache_only=True)
        return {
            "origin": "official_icbu_tree",
            "note": "这是国际站官方类目树，和后台选类目是同一棵。上面「最近选过」是你在这家店点过的叶子；「已经上过的」来自在线商品和本地草稿。",
            "node": catalog.as_dict(node),
            "path": catalog.summarise(catalog.path_from_db(db, parent)) if parent != "0" else [],
            "children": catalog.summarise(db_children),
            "recent": recent,
            "used": used,
            "cached": True,
        }

    node = catalog.get_node(db, api, parent)
    if node is None:
        if parent == "0":
            raise HTTPException(status_code=503, detail="类目树暂时拉不到，请确认店铺已授权后重试")
        stale = db.get(CategoryNode, parent)
        return {
            "origin": "official_icbu_tree",
            "note": "这个类目节点暂时拉不到。请返回上一层，或从右侧「最近选过 / 店里上过」直接选叶子。",
            "node": catalog.as_dict(stale) if stale is not None else {
                "category_id": parent,
                "name": parent,
                "cn_name": "",
                "level": 0,
                "is_leaf": False,
                "label": parent,
            },
            "path": catalog.summarise(catalog.path_from_db(db, parent)) if stale is not None else [],
            "children": [],
            "recent": [],
            "used": [],
            "cached": False,
        }
    recent: list[dict[str, Any]] = []
    used: list[dict[str, Any]] = []
    if parent == "0" and sidebar:
        recent = shop_categories.recent_picks(db, shop, user)
        used = shop_categories.used_leaves(db, shop, api=api, include_online=True, online_pages=1)
    children = catalog.summarise(catalog.get_children(db, api, node))
    if parent == "0" and not children:
        raise HTTPException(status_code=503, detail="类目树暂时拉不到，请确认店铺已授权后重试")
    return {
        "origin": "official_icbu_tree",
        "note": "这是国际站官方类目树，和后台选类目是同一棵。上面「最近选过」是你在这家店点过的叶子；「已经上过的」来自在线商品和本地草稿。",
        "node": catalog.as_dict(node),
        "path": catalog.summarise(catalog.path_of(db, api, parent)) if parent != "0" else [],
        "children": children,
        "recent": recent,
        "used": used,
        "cached": False,
    }


@router.get("/shops/{shop_id}/categories/sidebar")
def category_sidebar(
    shop_id: str,
    refresh: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    shop = shop_for(db, user, shop_id)
    try:
        api = shop_api(shop)
    except ShopNotConnected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return shop_categories.sidebar(db, api, shop, user, refresh_online=refresh)


class CategoryPickIn(BaseModel):
    category_id: str
    category_name: str = ""


@router.post("/shops/{shop_id}/categories/recent")
def remember_category_pick(
    shop_id: str,
    body: CategoryPickIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    shop = shop_for(db, user, shop_id)
    cid = str(body.category_id or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="缺少类目 ID")
    shop_categories.record_recent_pick(db, shop, user, cid, body.category_name)
    return {"ok": True, "category_id": cid}


@router.get("/shops/{shop_id}/categories/{category_id}/schema")
def category_schema(
    category_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    shop_id: str = "",
) -> dict[str, Any]:
    from schema import parse_schema  # noqa: E402

    shop = shop_for(db, user, shop_id)
    api = shop_api(shop)
    xml = catalog.get_schema_xml(db, api, category_id, "zh")
    fields = parse_schema(xml)
    flat = excel_import.flatten_schema_fields(fields)
    required = [item for item in flat if item["required"]]
    optional = [item for item in flat if not item["required"]]
    return {
        "category_id": category_id,
        "fields": [
            {
                "id": item.id,
                "name": item.name,
                "type": item.type,
                "required": item.required,
                "max_length": item.max_length,
                "options": [{"value": o.value, "label": o.display_name} for o in item.options[:200]],
                "children": [
                    {
                        "id": child.id,
                        "name": child.name,
                        "type": child.type,
                        "required": child.required,
                        "options": [{"value": o.value, "label": o.display_name} for o in child.options[:200]],
                    }
                    for child in item.children
                ],
            }
            for item in fields
            if item.type != "label"
        ],
        "fields_flat": flat,
        "required_fields": required,
        "optional_fields": optional,
        "required_count": len(required),
        "optional_count": len(optional),
        "total_count": len(flat),
    }
