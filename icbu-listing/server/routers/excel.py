"""Excel template download, header preview, and import."""

from __future__ import annotations

import json
import threading
from typing import Any
from urllib.parse import urlparse

import requests
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ai import AiClient, ImageInput  # noqa: E402

from ..db import SessionLocal
from ..deps import current_user, get_db, shop_for
from ..models import Product, Shop, Template, User, new_id
from ..services import catalog, distribution, excel_import, pipeline, products as catalogue, templates
from ..services.shop_client import ShopNotConnected, shop_api, shop_defaults

router = APIRouter(prefix="/api/v1/excel", tags=["excel"])

MAX_IMAGE_BYTES = 8 * 1024 * 1024
FETCH_TIMEOUT = 15


def _attr_columns(db: Session, user: User, shop_id: str, category_id: str) -> list[dict[str, Any]]:
    if not shop_id or not category_id:
        return []
    from schema import parse_schema  # noqa: E402

    shop = shop_for(db, user, shop_id)
    xml = catalog.get_schema_xml(db, shop_api(shop), category_id, str(shop_defaults(shop).get("language") or "en_US"))
    return excel_import.category_attr_columns(parse_schema(xml))


@router.get("/styles")
def list_styles() -> list[dict[str, Any]]:
    return excel_import.styles_view()


@router.get("/sheet-plan")
def sheet_plan(
    shop_id: str,
    category_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    extras = _attr_columns(db, user, shop_id, category_id)
    node = None
    if shop_id and category_id:
        shop = shop_for(db, user, shop_id)
        node = catalog.get_node(db, shop_api(shop), category_id)
    return {
        "category_id": category_id,
        "category_name": catalog.label(node) if node is not None else category_id,
        "base": [excel_import.FIELDS[key] for key in excel_import.STYLES["simple"]["columns"]],
        "extra": extras,
    }


@router.get("/template")
def download_template(
    style: str = "simple",
    listing_template_id: str = "",
    category_id: str = "",
    shop_id: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    if style not in excel_import.STYLES:
        raise HTTPException(status_code=400, detail="不支持的导入方式")
    listing = None
    official_required: list[dict[str, str]] = []
    if listing_template_id:
        row = db.get(Template, listing_template_id)
        if row is None or row.user_id != user.id:
            raise HTTPException(status_code=404, detail="刊登模板不存在")
        listing = templates.as_dict(row)
        category_id = category_id or row.category_id
    extra_columns: list[dict[str, Any]] = []
    if style == "alibaba" and category_id:
        listing = listing or {"name": f"官方类目 {category_id}", "category_id": category_id}
        if shop_id:
            from schema import parse_schema  # noqa: E402

            shop = shop_for(db, user, shop_id)
            xml = catalog.get_schema_xml(db, shop_api(shop), category_id, str(shop_defaults(shop).get("language") or "en_US"))
            official_required = [
                {"id": item.id, "name": item.name, "who": excel_import.who_fills(item.id)}
                for item in parse_schema(xml)
                if item.required and item.type != "label"
            ]
    if style == "simple" and category_id and shop_id:
        listing = listing or {"name": category_id, "category_id": category_id}
        extra_columns = _attr_columns(db, user, shop_id, category_id)
    payload = excel_import.build_template(style, listing, official_required, extra_columns)
    filename = f"auto-shoper-{style}-{category_id or 'generic'}.xlsx"
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/preview")
async def preview_excel(
    style: str = Form("detect"),
    shop_id: str = Form(""),
    category_id: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件是空的")
    extras = _attr_columns(db, user, shop_id, category_id) if style == "simple" else []
    try:
        return excel_import.preview(content, style, extras)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"读不了这个表格：{exc}") from exc


@router.post("/import")
async def import_excel(
    style: str = Form("detect"),
    shop_id: str = Form(""),
    mapping: str = Form("{}"),
    create_drafts: bool = Form(False),
    listing_template_id: str = Form(""),
    category_id: str = Form(""),
    file: UploadFile = File(...),
    images: list[UploadFile] = File(default_factory=list),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    if style not in excel_import.STYLES:
        raise HTTPException(status_code=400, detail="不支持的导入方式")
    spec = excel_import.STYLES[style]
    shop = shop_for(db, user, shop_id) if shop_id else None
    wants_drafts = bool(create_drafts or spec.get("create_drafts_default"))
    if (wants_drafts or spec.get("needs_listing_template")) and shop is None:
        raise HTTPException(status_code=400, detail="这种导入方式要先选一个店铺")

    listing_id = ""
    if listing_template_id:
        row = db.get(Template, listing_template_id)
        if row is None or row.user_id != user.id:
            raise HTTPException(status_code=404, detail="刊登模板不存在")
        listing_id = row.id

    content = await file.read()
    try:
        mapping_payload = json.loads(mapping or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="列映射不是合法 JSON") from exc
    extras = _attr_columns(db, user, shop_id, category_id) if style == "simple" else []
    if not isinstance(mapping_payload, dict) or not mapping_payload:
        preview = excel_import.preview(content, style, extras)
        mapping_payload = preview.get("mapping") or {}

    try:
        rows = excel_import.apply_preview(content, mapping_payload, style, extras)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"读不了这个表格：{exc}") from exc
    if not rows:
        raise HTTPException(status_code=400, detail="表格里没有有效行")
    if category_id:
        for row in rows:
            if not row.category_id:
                row.category_id = category_id

    uploads: dict[str, bytes] = {}
    for item in images:
        raw = await item.read()
        if raw:
            uploads[(item.filename or "image.jpg").rsplit("/", 1)[-1].lower()] = raw

    batch_id = new_id()
    payload = [
        {
            "sku": row.sku,
            "name": row.name,
            "title": row.title,
            "keywords": row.keywords,
            "price": row.price,
            "moq": row.moq,
            "images": row.images,
            "note": row.note,
            "category_id": row.category_id,
            "origin": row.origin,
            "line": row.line,
            "attributes": row.attributes,
        }
        for row in rows
    ]
    thread = threading.Thread(
        target=_run_import,
        args=(user.id, shop.id if shop else "", batch_id, payload, uploads, wants_drafts, listing_id, style),
        daemon=True,
    )
    thread.start()
    return {"batch_id": batch_id, "count": len(rows), "style": style, "create_drafts": wants_drafts}


def _run_import(
    user_id: str,
    shop_id: str,
    batch_id: str,
    payload: list[dict[str, Any]],
    uploads: dict[str, bytes],
    create_drafts: bool,
    listing_template_id: str,
    style: str,
) -> None:
    del style  # reserved so a later importer can branch on the chosen style
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if user is None:
            return
        shop = db.get(Shop, shop_id) if shop_id else None
        listing = db.get(Template, listing_template_id) if listing_template_id else None
        ai = AiClient.from_env_or_none()
        for raw in payload:
            row = excel_import.ExcelRow(
                sku=raw.get("sku") or "",
                name=raw.get("name") or "",
                title=raw.get("title") or "",
                keywords=raw.get("keywords") or "",
                price=raw.get("price") or "",
                moq=raw.get("moq") or "",
                images=list(raw.get("images") or []),
                note=raw.get("note") or "",
                category_id=raw.get("category_id") or "",
                origin=raw.get("origin") or "",
                line=int(raw.get("line") or 0),
                attributes=dict(raw.get("attributes") or {}),
            )
            try:
                _import_one(db, user, shop, row, uploads, ai, create_drafts, listing, batch_id)
            except Exception as exc:
                if shop is not None and create_drafts:
                    distribution.failed_draft(db, user.id, shop.id, None, batch_id, f"第 {row.line} 行：{exc}")
    finally:
        db.close()


def _import_one(
    db: Session,
    user: User,
    shop: Shop | None,
    row: excel_import.ExcelRow,
    uploads: dict[str, bytes],
    ai: AiClient | None,
    create_drafts: bool,
    listing: Template | None,
    batch_id: str,
) -> None:
    files = _resolve_images(row, uploads)
    sku = row.sku or (files[0][0].rsplit(".", 1)[0][:60] if files else f"row-{row.line}")
    product = Product(
        user_id=user.id,
        sku=sku,
        name=row.name or row.title,
        price=row.price,
        moq=row.moq,
        note=row.note,
        batch_id=batch_id,
    )
    db.add(product)
    db.commit()
    if files:
        catalogue.save_images(db, user, product, files[:6])

    understanding, error = pipeline.understand(
        ai, [ImageInput(filename=name, content=content) for name, content in files[:6]], row.note or row.name or row.title
    )
    product.understanding_json = json.dumps(understanding.raw, ensure_ascii=False)
    if not product.name:
        product.name = understanding.product_name
    db.commit()

    if not create_drafts or shop is None:
        return

    forced = row.category_id or (listing.category_id if listing is not None else "")
    try:
        draft = distribution.build_draft_for_shop(
            db,
            user,
            shop,
            product,
            price=row.price,
            moq=row.moq,
            ai=ai,
            batch_id=batch_id,
            forced_category_id=forced,
            seed_values=row.seed_values(),
            provided_sources=row.provided_sources(),
        )
    except ShopNotConnected as exc:
        distribution.failed_draft(db, user.id, shop.id, product, batch_id, str(exc))
        return
    if error:
        issues = json.loads(draft.issues_json or "[]")
        issues.append({"field_id": "ai", "field_name": "AI 成稿", "level": "yellow", "message": error, "path": "ai"})
        draft.issues_json = json.dumps(issues, ensure_ascii=False)
        db.commit()


def _resolve_images(row: excel_import.ExcelRow, uploads: dict[str, bytes]) -> list[tuple[str, bytes]]:
    urls, names = excel_import.split_images(row.images)
    files = excel_import.match_uploads(row.sku, names, uploads)
    for url in urls[:6]:
        fetched = _fetch_image(url)
        if fetched:
            files.append(fetched)
    return files


def _fetch_image(url: str) -> tuple[str, bytes] | None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    try:
        response = requests.get(url, timeout=FETCH_TIMEOUT, stream=True)
        response.raise_for_status()
        data = response.content[: MAX_IMAGE_BYTES + 1]
        if len(data) > MAX_IMAGE_BYTES:
            return None
        name = parsed.path.rsplit("/", 1)[-1] or "image.jpg"
        return name, data
    except requests.RequestException:
        return None
