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
from ..models import Draft, Job, Product, Shop, User, new_id
from ..services import (
    catalog,
    dedup,
    distribution,
    images as image_service,
    pipeline,
    products as catalogue,
    publisher,
    sources,
)
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


class PublishBatchIn(BaseModel):
    draft_ids: list[str]


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
        "issues": _json(draft.issues_json, []),
        "images": _json(draft.images_json, []),
        "product_id": draft.product_id,
        "product_online_id": draft.product_online_id,
        "updated_at": draft.updated_at.isoformat(),
        "quality": _json(draft.ai_json, {}).get("quality"),
    }
    if detailed:
        view["values"] = _json(draft.values_json, {})
        view["ai"] = _json(draft.ai_json, {})
        view["category_candidates"] = _json(draft.category_candidates_json, [])
        view["sources"] = sources.view(sources.parse(getattr(draft, "sources_json", None)))
    return view


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
) -> Draft:
    """Feeding always lands a catalogue product first.

    The draft is then produced from that product, so the same photos and the
    same recognition can be reused when the seller sends it to another shop.
    """
    ai = AiClient.from_env_or_none()
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
    files: list[UploadFile] = File(default_factory=list),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    shop = shop_for(db, user, shop_id)
    uploads = [(item.filename or "image.jpg", await item.read()) for item in files[:MAX_IMAGES]]
    uploads = [(name, content) for name, content in uploads if content]
    if not uploads:
        raise HTTPException(status_code=400, detail="至少要传一张图")

    try:
        draft = _generate(
            db,
            user,
            shop,
            uploads=uploads,
            sku=sku or _sku_from_filename(uploads[0][0]),
            price=price,
            moq=moq,
            note=note,
            category_id=category_id,
        )
    except ShopNotConnected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return draft_view(draft, detailed=True)


@router.post("/listings/batch")
async def feed_batch(
    shop_id: str = Form(...),
    price: str = Form(""),
    moq: str = Form(""),
    note: str = Form(""),
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
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    drafts = db.query(Draft).filter(Draft.user_id == user.id, Draft.batch_id == batch_id).all()
    products = db.query(Product).filter(Product.user_id == user.id, Product.batch_id == batch_id).count()
    counts = {"red": 0, "yellow": 0, "green": 0, "published": 0, "failed": 0}
    for draft in drafts:
        counts[draft.status] = counts.get(draft.status, 0) + 1
    return {"batch_id": batch_id, "done": max(len(drafts), products), "products": products, "drafts": len(drafts), "counts": counts}


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
def get_draft(draft: Draft = Depends(owned_draft)) -> dict[str, Any]:
    return draft_view(draft, detailed=True)


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
        return draft_view(draft, detailed=True)

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
        issues = [issue.as_dict() for issue in pipeline.revalidate(xml, values)]
        if not draft.price:
            issues.append({"field_id": "price", "field_name": "价格", "level": "red", "message": "价格要你来定"})
        if not draft.moq:
            issues.append({"field_id": "minOrderQuantity", "field_name": "起订量", "level": "red", "message": "起订量要你来定"})
        draft.issues_json = json.dumps(issues, ensure_ascii=False)
        draft.status = pipeline.status_of(issues)

    draft.updated_at = datetime.utcnow()
    db.commit()
    return draft_view(draft, detailed=True)


@router.delete("/drafts/{draft_id}")
def delete_draft(db: Session = Depends(get_db), draft: Draft = Depends(owned_draft)) -> dict[str, bool]:
    db.delete(draft)
    db.commit()
    return {"ok": True}


def _publish_one(db: Session, user: User, shop: Shop, draft: Draft) -> Job:
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

    queued = []
    for draft in drafts:
        job = Job(
            user_id=user.id,
            shop_id=draft.shop_id,
            draft_id=draft.id,
            batch_id=draft.batch_id,
            mode="draft",
            status="queued",
            sku=draft.sku,
            title=draft.title,
        )
        db.add(job)
        queued.append(job.id)
    db.commit()

    threading.Thread(target=_run_publish_queue, args=(user.id, queued), daemon=True).start()
    return {"queued": len(queued), "job_ids": queued}


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
                db.commit()
                continue
            db.delete(job)
            db.commit()
            _publish_one(db, user, shop, draft)
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
    return job_view(_publish_one(db, user, shop, draft))


@router.get("/shops/{shop_id}/categories")
def browse_categories(
    parent: str = "0",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    shop_id: str = "",
) -> dict[str, Any]:
    shop = shop_for(db, user, shop_id)
    api = shop_api(shop)
    node = catalog.get_node(db, api, parent)
    if node is None:
        raise HTTPException(status_code=404, detail="类目不存在")
    return {
        "node": catalog.as_dict(node),
        "path": catalog.summarise(catalog.path_of(db, api, parent)) if parent != "0" else [],
        "children": catalog.summarise(catalog.get_children(db, api, node)),
    }


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
    xml = catalog.get_schema_xml(db, api, category_id, str(shop_defaults(shop).get("language") or "en_US"))
    fields = parse_schema(xml)
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
    }
