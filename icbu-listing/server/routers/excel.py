"""Excel template download, header preview, and import."""

from __future__ import annotations

import json
import threading
from typing import Any, Mapping
from urllib.parse import quote, urlparse

import requests

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ai import AiClient, AiUnavailable, ImageInput  # noqa: E402
from gop_client import GopError  # noqa: E402

from ..db import SessionLocal, reload_db_from_blob, reload_db_from_blob_throttled
from ..deps import current_user, get_db, shop_for
from ..models import Product, Shop, Template, User, new_id
from ..services import catalog, distribution, document_parse, ecosystem_brief, excel_import, excel_images, feed_sessions, grid_images, pipeline, products as catalogue, public_refs, review_enrich, smart_plan, template_suggest, templates
from ..services.fact_bundle import from_excel_row
from ..services.shop_client import ShopNotConnected, shop_api, shop_defaults

router = APIRouter(prefix="/api/v1/excel", tags=["excel"])

MAX_IMAGE_BYTES = 8 * 1024 * 1024
FETCH_TIMEOUT = 15


def _attr_columns(
    db: Session,
    user: User,
    shop_id: str,
    category_id: str,
    *,
    fetch: bool = True,
) -> list[dict[str, Any]]:
    if not shop_id or not category_id:
        return []
    from schema import parse_schema  # noqa: E402

    shop = shop_for(db, user, shop_id)
    try:
        xml = catalog.get_schema_xml(
            db,
            shop_api(shop),
            category_id,
            str(shop_defaults(shop).get("language") or "en_US"),
            fetch=fetch,
        )
    except RuntimeError:
        return []
    return excel_import.category_attr_columns(parse_schema(xml))


def _schema_columns(
    db: Session,
    user: User,
    shop_id: str,
    category_id: str,
    *,
    fetch: bool = True,
) -> list[dict[str, Any]]:
    if not shop_id or not category_id:
        return []
    from schema import parse_schema  # noqa: E402

    shop = shop_for(db, user, shop_id)
    try:
        xml = catalog.get_schema_xml(
            db,
            shop_api(shop),
            category_id,
            "zh",
            fetch=fetch,
        )
    except RuntimeError:
        return []
    return excel_import.schema_field_columns(parse_schema(xml))


def _columns_for_style(
    db: Session,
    user: User,
    shop_id: str,
    category_id: str,
    style: str,
    *,
    fetch: bool = True,
) -> list[dict[str, Any]]:
    if style == "full_schema":
        return _attr_columns(db, user, shop_id, category_id, fetch=fetch)
    if style == "simple":
        return _attr_columns(db, user, shop_id, category_id, fetch=fetch)
    return []


def _category_hint(db: Session, user: User, shop_id: str, category_id: str, category_name: str) -> str:
    bits = [str(category_name or "").strip()]
    if shop_id and category_id:
        try:
            shop = shop_for(db, user, shop_id)
            api = shop_api(shop)
            node = catalog.get_node(db, api, category_id, fetch=False)
            if node is not None:
                bits.append(catalog.label(node))
            for item in catalog.path_of(db, api, category_id, fetch=False):
                bits.append(catalog.label(item))
        except Exception:
            pass
    seen: set[str] = set()
    ordered: list[str] = []
    for part in bits:
        key = part.strip()
        if key and key not in seen:
            seen.add(key)
            ordered.append(key)
    return " / ".join(ordered)


def _parse_plan_columns(raw: str) -> list[dict[str, Any]] | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="智能表列配置不是合法 JSON") from exc
    if not isinstance(payload, list):
        raise HTTPException(status_code=400, detail="智能表列配置格式不对")
    return [dict(item) for item in payload if isinstance(item, dict)]


def _resolve_grid_columns(
    db: Session,
    user: User,
    shop_id: str,
    category_id: str,
    *,
    plan_columns: list[dict[str, Any]] | None = None,
    fetch: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, list[dict[str, Any]]]:
    if plan_columns:
        hint = _category_hint(db, user, shop_id, category_id, "")
        profile = excel_import.sheet_profile(hint, category_id=category_id, attr_columns=plan_columns)
        return document_parse.grid_columns(profile, plan_columns, plan_columns=plan_columns), profile, plan_columns
    hint = _category_hint(db, user, shop_id, category_id, "")
    extras = _columns_for_style(db, user, shop_id, category_id, "simple", fetch=fetch)
    profile = excel_import.sheet_profile(hint, category_id=category_id, attr_columns=extras)
    return document_parse.grid_columns(profile, extras), profile, extras


@router.get("/styles")
def list_styles() -> list[dict[str, Any]]:
    return excel_import.styles_view()


@router.get("/sheet-plan")
def sheet_plan(
    shop_id: str = "",
    category_id: str = "",
    category_name: str = "",
    style: str = "simple",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    hint = _category_hint(db, user, shop_id, category_id, category_name)
    extras = _columns_for_style(db, user, shop_id, category_id, style, fetch=bool(category_id and shop_id))
    if category_id:
        profile = excel_import.sheet_profile(hint, category_id=category_id, attr_columns=extras)
    elif hint:
        profile = excel_import.sheet_profile(hint)
    else:
        profile = excel_import.sheet_profile("")
    policy = excel_import.fill_policy(extras if not category_id else [], profile)
    preview = excel_import.sheet_preview(style if style in excel_import.STYLES else "simple", profile)
    origin_kind = "leaf_schema"
    if profile.get("family_id") == "full_schema":
        origin_kind = "full_schema"
    elif not category_id:
        origin_kind = "platform_short"
    return {
        "category_id": category_id,
        "category_name": hint or category_name,
        "style": style,
        "user_fills": policy["user_fills"],
        "shop_fills": policy["shop_fills"],
        "ai_fills": policy["ai_fills"],
        "redline": policy["redline"],
        "guarantee": policy["guarantee"],
        "ai_attrs": extras,
        "preview": preview,
        "sheet": profile,
        "from_official_form": False,
        "sheet_origin": {
            "kind": origin_kind,
            "from_official_form": False,
            "columns_from": (
                f"叶子类目 {category_id} 的 schema.get 全部字段（必填+选填）"
                if origin_kind == "full_schema"
                else (
                    f"叶子类目 {category_id} 的 schema.get 必填属性"
                    if category_id
                    else "平台短表：先选叶子类目"
                )
            ),
            "official_attrs": (
                "填写页含该类目 schema 返回的全部必填与选填列；7521 类各不同。"
                if origin_kind == "full_schema"
                else (
                    "填写页已含该类目官方必填列；7540 个叶子类目各有一套，不是 12 张家族表。"
                    if category_id
                    else "选了叶子类目后，按 schema 生成填写列。"
                )
            ),
        },
    }


@router.get("/ecosystem-brief")
def ecosystem_brief_endpoint(
    shop_id: str = "",
    category_id: str = "",
    category_name: str = "",
    include_shop_examples: str = "false",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    if not shop_id or not category_id:
        raise HTTPException(status_code=400, detail="先选店铺和叶子类目")
    shop = shop_for(db, user, shop_id)
    hint = _category_hint(db, user, shop_id, category_id, category_name)
    use_shop = str(include_shop_examples or "").strip().lower() in {"1", "true", "yes", "on"}
    try:
        brief = ecosystem_brief.build_brief(
            db,
            shop,
            category_id=category_id,
            category_name=hint or category_name,
            api=shop_api(shop) if use_shop else None,
            include_shop_examples=use_shop,
        )
    except Exception as exc:
        brief = ecosystem_brief.build_brief(
            db,
            shop,
            category_id=category_id,
            category_name=hint or category_name,
            api=None,
            include_shop_examples=False,
        )
        brief["warning"] = str(exc)
    return brief


@router.get("/smart-plan")
def smart_plan_endpoint(
    shop_id: str = "",
    category_id: str = "",
    category_name: str = "",
    refresh: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    reload_db_from_blob_throttled(min_interval_seconds=3.0)
    if not shop_id:
        raise HTTPException(status_code=400, detail="先选一个店铺")
    if not category_id:
        raise HTTPException(status_code=400, detail="先选叶子类目")
    shop = shop_for(db, user, shop_id)
    hint = _category_hint(db, user, shop_id, category_id, category_name)
    ai = AiClient.from_env_or_none()
    try:
        return smart_plan.build_plan(
            db,
            shop_api(shop),
            shop,
            category_id=category_id,
            category_name=hint or category_name,
            ai=ai,
            refresh=refresh,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/smart-template")
def download_smart_template(
    shop_id: str = "",
    category_id: str = "",
    category_name: str = "",
    refresh: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    reload_db_from_blob_throttled(min_interval_seconds=3.0)
    if not shop_id or not category_id:
        raise HTTPException(status_code=400, detail="先选店铺和叶子类目")
    shop = shop_for(db, user, shop_id)
    hint = _category_hint(db, user, shop_id, category_id, category_name)
    ai = AiClient.from_env_or_none()
    plan = smart_plan.build_plan(
        db,
        shop_api(shop),
        shop,
        category_id=category_id,
        category_name=hint or category_name,
        ai=ai,
        refresh=refresh,
    )
    return _smart_template_response(plan, hint or category_name)


@router.post("/smart-template-from-plan")
def download_smart_template_from_plan(
    body: dict[str, Any],
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    """Build XLSX from an already-loaded smart plan (skips schema fetch + LLM)."""
    reload_db_from_blob()
    shop_id = str(body.get("shop_id") or "").strip()
    category_id = str(body.get("category_id") or "").strip()
    if not shop_id or not category_id:
        raise HTTPException(status_code=400, detail="先选店铺和叶子类目")
    shop_for(db, user, shop_id)
    columns = body.get("columns") or []
    if not isinstance(columns, list) or not columns:
        raise HTTPException(status_code=400, detail="缺少填写列，请先选类目并等待规划完成")
    plan = {
        "category_id": category_id,
        "category_name": str(body.get("category_name") or ""),
        "columns": columns,
        "reasoning": body.get("reasoning") or "",
        "tips": body.get("tips") or "",
        "covered_by_shop": body.get("covered_by_shop") or [],
        "covered_by_template": body.get("covered_by_template") or [],
        "ai_fills": body.get("ai_fills") or [],
    }
    return _smart_template_response(plan, plan["category_name"] or category_id)


def _smart_template_response(plan: Mapping[str, Any], name_hint: str) -> Response:
    payload = smart_plan.build_smart_template_bytes(plan)
    category_id = str(plan.get("category_id") or "")
    ascii_name = f"auto-shoper-smart-{category_id}.xlsx"
    utf_name = f"智能批量上品-{name_hint or category_id}.xlsx"
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(utf_name)}"
        },
    )


@router.get("/official-attrs")
def official_attrs(
    shop_id: str = "",
    category_id: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    extras: list[dict[str, Any]] = []
    try:
        extras = _attr_columns(db, user, shop_id, category_id, fetch=True)
    except Exception:
        extras = []
    policy = excel_import.fill_policy(extras)
    return {
        "category_id": category_id,
        "ai_attrs": extras,
        "ai_fills": policy["ai_fills"],
    }


@router.get("/template")
def download_template(
    style: str = "simple",
    listing_template_id: str = "",
    category_id: str = "",
    shop_id: str = "",
    category_name: str = "",
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
    ai_attrs: list[dict[str, Any]] = []
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
    hint = _category_hint(db, user, shop_id, category_id, category_name)
    if style == "simple" and category_id:
        listing = listing or {"name": hint or category_id, "category_id": category_id}
        ai_attrs = _columns_for_style(db, user, shop_id, category_id, style, fetch=True)
    elif style == "full_schema" and category_id:
        listing = listing or {"name": hint or category_id, "category_id": category_id}
        ai_attrs = _columns_for_style(db, user, shop_id, category_id, style, fetch=True)
    elif style == "simple" and (hint or category_id):
        listing = listing or {"name": hint or category_id, "category_id": category_id}
        ai_attrs = _attr_columns(db, user, shop_id, category_id, fetch=False)
    else:
        ai_attrs = []
    payload = excel_import.build_template(
        style,
        listing,
        official_required,
        ai_attrs,
        category_name=hint,
        category_id=category_id or str((listing or {}).get("category_id") or ""),
    )
    profile = (
        excel_import.sheet_profile(hint, category_id=category_id, attr_columns=ai_attrs)
        if category_id
        else (excel_import.sheet_profile(hint) if hint else None)
    )
    ascii_name = f"auto-shoper-{(profile or {}).get('filename_id') or style}-{category_id or 'generic'}.xlsx"
    utf_name = f"{(profile or {}).get('filename') or ascii_name}.xlsx" if profile and profile.get("filename") else ascii_name
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(utf_name)}"
        },
    )


@router.post("/preview")
async def preview_excel(
    style: str = Form("detect"),
    shop_id: str = Form(""),
    category_id: str = Form(""),
    image_mode: str = Form("keep_draw"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件是空的")
    extras = _columns_for_style(db, user, shop_id, category_id, style) if style in {"simple", "full_schema"} else []
    try:
        return excel_import.preview(content, style, extras, image_mode)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"读不了这个表格：{exc}") from exc


def _rows_payload(rows: list[excel_import.ExcelRow]) -> list[dict[str, Any]]:
    return [
        {
            "sku": row.sku,
            "name": row.name,
            "title": row.title,
            "keywords": row.keywords,
            "price": row.price,
            "moq": row.moq,
            "images": row.images,
            "note": row.note,
            "brand": row.brand,
            "category_id": row.category_id,
            "origin": row.origin,
            "spec": row.spec,
            "specs": row.specs,
            "line": row.line,
            "attributes": row.attributes,
            "listing_template_id": row.listing_template_id,
        }
        for row in rows
    ]


def _launch_import(
    *,
    user: User,
    shop: Shop | None,
    rows: list[excel_import.ExcelRow],
    uploads: dict[str, bytes],
    wants_drafts: bool,
    listing_id: str,
    style: str,
    image_mode: str,
    public_base: str,
    session: Any | None = None,
    db: Session | None = None,
) -> dict[str, Any]:
    if not rows:
        raise HTTPException(
            status_code=400,
            detail="没有可导入的商品行。请检查资料或在前台表格里补货号、价、起订量。",
        )
    batch_id = new_id()
    thread = threading.Thread(
        target=_run_import,
        args=(
            user.id,
            shop.id if shop else "",
            batch_id,
            _rows_payload(rows),
            uploads,
            wants_drafts,
            listing_id,
            style,
            excel_import.normalize_image_mode(image_mode),
            public_base,
        ),
        daemon=True,
    )
    thread.start()
    if session is not None and db is not None:
        feed_sessions.save(
            db,
            session,
            status="done",
            shop_id=shop.id if shop else session.shop_id,
            payload={"batchId": batch_id, "rowCount": len(rows)},
        )
    return {
        "batch_id": batch_id,
        "count": len(rows),
        "style": style,
        "create_drafts": wants_drafts,
        "image_mode": excel_import.normalize_image_mode(image_mode),
    }


@router.post("/doc-parse")
async def parse_documents(
    shop_id: str = Form(""),
    category_id: str = Form(""),
    category_name: str = Form(""),
    image_mode: str = Form("keep_draw"),
    columns: str = Form(""),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    if not category_id:
        raise HTTPException(status_code=400, detail="先选叶子类目")
    if shop_id:
        shop_for(db, user, shop_id)
    uploads: list[tuple[str, bytes]] = []
    for item in files:
        raw = await item.read()
        if raw:
            uploads.append((item.filename or "document.bin", raw))
    if not uploads:
        raise HTTPException(status_code=400, detail="资料文件是空的")
    hint = _category_hint(db, user, shop_id, category_id, category_name)
    plan_columns = _parse_plan_columns(columns)
    grid_columns, profile, extras = _resolve_grid_columns(
        db,
        user,
        shop_id,
        category_id,
        plan_columns=plan_columns,
        fetch=bool(category_id and shop_id and not plan_columns),
    )
    ai = AiClient.from_env_or_none()
    try:
        result = document_parse.parse_documents(
            uploads,
            profile=profile,
            extra_columns=extras,
            category_id=category_id,
            category_name=hint or category_name,
            image_mode=image_mode,
            ai=ai,
            plan_columns=plan_columns,
        )
        result["planner"] = "smart" if plan_columns else "simple"
        download_columns = plan_columns or result.get("columns") or []
        review_columns = download_columns
        if category_id and shop_id and download_columns:
            shop = shop_for(db, user, shop_id)
            review_columns = smart_plan.expand_audit_columns(
                db,
                shop_api(shop),
                shop,
                category_id,
                download_columns,
            )
        else:
            review_columns = review_enrich.order_review_columns(download_columns)
        enriched_rows = []
        for row in result.get("rows") or []:
            item = dict(row)
            item.setdefault("title", str(item.get("title") or ""))
            item.setdefault("keywords", str(item.get("keywords") or ""))
            item.setdefault("highlights", str(item.get("highlights") or ""))
            enriched_rows.append(item)
        enrich_warnings = ["进入审核后会自动生成英文标题和关键词；单价/起订量/官方属性列需你填写。"]
        result["download_columns"] = download_columns
        result["columns"] = review_columns
        result["rows"] = enriched_rows
        result["warnings"] = list(result.get("warnings") or []) + enrich_warnings
        return result
    except AiUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"解析失败：{exc}") from exc


@router.post("/grid-check")
async def check_grid_rows(
    shop_id: str = Form(""),
    category_id: str = Form(""),
    image_mode: str = Form("keep_draw"),
    rows: str = Form("[]"),
    columns: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    if shop_id:
        shop_for(db, user, shop_id)
    try:
        payload = json.loads(rows or "[]")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="表格数据不是合法 JSON") from exc
    if not isinstance(payload, list):
        raise HTTPException(status_code=400, detail="表格数据格式不对")
    plan_columns = _parse_plan_columns(columns)
    grid_columns, _profile, _extras = _resolve_grid_columns(
        db,
        user,
        shop_id,
        category_id,
        plan_columns=plan_columns,
    )
    return document_parse.check_grid(payload, grid_columns, category_id=category_id, image_mode=image_mode)


@router.post("/grid-regen-copy")
async def grid_regen_copy(
    shop_id: str = Form(""),
    category_id: str = Form(""),
    category_name: str = Form(""),
    rows: str = Form("[]"),
    lines: str = Form("[]"),
    use_ecosystem: str = Form("false"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    if shop_id:
        shop_for(db, user, shop_id)
    try:
        payload = json.loads(rows or "[]")
        selected = json.loads(lines or "[]")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="表格数据不是合法 JSON") from exc
    if not isinstance(payload, list):
        raise HTTPException(status_code=400, detail="表格数据格式不对")
    hint = _category_hint(db, user, shop_id, category_id, category_name)
    targets = {int(item) for item in selected if str(item).strip()} if isinstance(selected, list) and selected else set()
    ai = AiClient.from_env_or_none()
    if ai is None:
        raise HTTPException(status_code=503, detail="重写文案需要配置 AI")
    eco: dict[str, Any] | None = None
    use_eco = str(use_ecosystem or "").strip().lower() in {"1", "true", "yes", "on"}
    if use_eco and shop_id and category_id:
        shop = shop_for(db, user, shop_id)
        try:
            eco = ecosystem_brief.build_brief(
                db,
                shop,
                category_id=category_id,
                category_name=hint or category_name,
                api=shop_api(shop),
                include_shop_examples=False,
            )
        except Exception:
            eco = ecosystem_brief.build_brief(
                db,
                shop,
                category_id=category_id,
                category_name=hint or category_name,
                api=None,
                include_shop_examples=False,
            )
    updated: list[dict[str, Any]] = []
    errors: list[str] = []
    for row in payload:
        if not isinstance(row, Mapping):
            continue
        item = dict(row)
        line = int(item.get("line") or 0)
        if targets and line not in targets:
            updated.append(item)
            continue
        try:
            suggested = review_enrich.suggest_copy_for_row(
                ai,
                item,
                category_name=hint or category_name,
                ecosystem_brief=eco,
            )
            item.update(suggested)
            item["_copy_source"] = "ai"
        except Exception as exc:
            errors.append(f"第 {line or '?'} 行：{exc}")
        updated.append(item)
    return {"rows": updated, "errors": errors}


@router.post("/grid-infer-fields")
async def grid_infer_fields(
    shop_id: str = Form(""),
    category_id: str = Form(""),
    category_name: str = Form(""),
    rows: str = Form("[]"),
    lines: str = Form("[]"),
    columns: str = Form(""),
    plan_columns: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    if shop_id:
        shop_for(db, user, shop_id)
    try:
        payload = json.loads(rows or "[]")
        selected = json.loads(lines or "[]")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="表格数据不是合法 JSON") from exc
    if not isinstance(payload, list):
        raise HTTPException(status_code=400, detail="表格数据格式不对")
    download_columns = _parse_plan_columns(plan_columns or columns)
    expanded_columns = _parse_plan_columns(columns)
    grid_columns, _profile, _extras = _resolve_grid_columns(
        db,
        user,
        shop_id,
        category_id,
        plan_columns=download_columns,
    )
    if category_id and shop_id and download_columns:
        shop = shop_for(db, user, shop_id)
        grid_columns = smart_plan.expand_audit_columns(db, shop_api(shop), shop, category_id, download_columns)
    if expanded_columns and len(expanded_columns) >= len(grid_columns or []):
        grid_columns = expanded_columns
    user_column_ids = {str(col.get("id") or "") for col in (download_columns or []) if col.get("id")}
    targets = {int(item) for item in selected if str(item).strip()} if isinstance(selected, list) and selected else set()
    ai = AiClient.from_env_or_none()
    shop_defaults_payload: dict[str, Any] = {}
    if shop_id:
        try:
            shop = shop_for(db, user, shop_id)
            shop_defaults_payload = smart_plan._shop_defaults(shop)
        except Exception:
            shop_defaults_payload = {}
    updated, errors, filled_count, meta = review_enrich.infer_fields_for_rows(
        payload,
        grid_columns,
        lines=targets or None,
        ai=ai,
        shop_defaults=shop_defaults_payload,
        user_column_ids=user_column_ids,
        category_name=category_name,
    )
    return {
        "rows": updated,
        "errors": errors,
        "filled_count": filled_count,
        "fillable_columns": meta.get("fillable_columns", 0),
        "missing_required_cells": meta.get("missing_required_cells", 0),
        "columns": grid_columns,
    }


@router.post("/grid-generate-images")
async def grid_generate_images(
    shop_id: str = Form(""),
    category_id: str = Form(""),
    category_name: str = Form(""),
    rows: str = Form("[]"),
    lines: str = Form("[]"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    if shop_id:
        shop_for(db, user, shop_id)
    try:
        payload = json.loads(rows or "[]")
        selected = json.loads(lines or "[]")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="表格数据不是合法 JSON") from exc
    if not isinstance(payload, list):
        raise HTTPException(status_code=400, detail="表格数据格式不对")
    if not category_id:
        raise HTTPException(status_code=400, detail="先选叶子类目")
    hint = _category_hint(db, user, shop_id, category_id, category_name)
    targets = {int(item) for item in selected if str(item).strip()} if isinstance(selected, list) and selected else set()
    updated: list[dict[str, Any]] = []
    errors: list[str] = []
    for row in payload:
        if not isinstance(row, Mapping):
            continue
        line = int(row.get("line") or 0)
        if targets and line not in targets:
            updated.append(grid_images.refresh_row_job(row, user.id))
            continue
        item = grid_images.refresh_row_job(dict(row), user.id)
        status = str(item.get("image_job_status") or "")
        if item.get("image_job_id") and status in {"queued", "running"}:
            updated.append(item)
            continue
        try:
            job_id = grid_images.start_row_job(
                user.id,
                item,
                category_id=category_id,
                category_name=hint or category_name,
            )
            item["image_job_id"] = job_id
            item = grid_images.refresh_row_job(item, user.id)
        except ValueError as exc:
            errors.append(f"第 {line or '?'} 行：{exc}")
        updated.append(item)
    return {"rows": updated, "errors": errors}


@router.post("/grid-poll-images")
async def grid_poll_images(
    rows: str = Form("[]"),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    try:
        payload = json.loads(rows or "[]")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="表格数据不是合法 JSON") from exc
    if not isinstance(payload, list):
        raise HTTPException(status_code=400, detail="表格数据格式不对")
    refreshed = [grid_images.refresh_row_job(item, user.id) for item in payload if isinstance(item, dict)]
    pending = sum(
        1
        for item in refreshed
        if str(item.get("image_job_status") or "") in {"queued", "running"}
    )
    return {"rows": refreshed, "pending": pending}


@router.post("/grid-suggest-template")
async def grid_suggest_template(
    shop_id: str = Form(""),
    category_id: str = Form(""),
    category_name: str = Form(""),
    rows: str = Form("[]"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    if not shop_id or not category_id:
        raise HTTPException(status_code=400, detail="先选店铺和叶子类目")
    shop = shop_for(db, user, shop_id)
    try:
        payload = json.loads(rows or "[]")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="表格数据不是合法 JSON") from exc
    if not isinstance(payload, list):
        raise HTTPException(status_code=400, detail="表格数据格式不对")
    ai = AiClient.from_env_or_none()
    result = template_suggest.suggest(
        db,
        shop,
        category_id,
        [item for item in payload if isinstance(item, dict)],
        category_name=category_name,
        ai=ai,
    )
    if payload:
        result["rows"] = template_suggest.apply_row_suggestions(
            [dict(item) for item in payload if isinstance(item, dict)],
            result.get("suggestion") or {},
            result.get("row_suggestions") or [],
        )
    return result


@router.post("/import-rows")
async def import_rows(
    request: Request,
    shop_id: str = Form(""),
    category_id: str = Form(""),
    session_id: str = Form(""),
    image_mode: str = Form("keep_draw"),
    listing_template_id: str = Form(""),
    rows: str = Form("[]"),
    columns: str = Form(""),
    images: list[UploadFile] = File(default_factory=list),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    shop = shop_for(db, user, shop_id) if shop_id else None
    if shop is None:
        raise HTTPException(status_code=400, detail="批量成稿要先选一个店铺")
    try:
        payload = json.loads(rows or "[]")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="表格数据不是合法 JSON") from exc
    if not isinstance(payload, list):
        raise HTTPException(status_code=400, detail="表格数据格式不对")
    default_template_id = ""
    if listing_template_id:
        row = db.get(Template, listing_template_id)
        if row is None or row.user_id != user.id or row.shop_id != shop.id:
            raise HTTPException(status_code=404, detail="刊登模板不存在")
        default_template_id = row.id
    for item in payload:
        if not isinstance(item, dict):
            continue
        if not str(item.get("_template_id") or "").strip() and default_template_id:
            item["_template_id"] = default_template_id
    plan_columns = _parse_plan_columns(columns)
    grid_columns, _profile, _extras = _resolve_grid_columns(
        db,
        user,
        shop_id,
        category_id,
        plan_columns=plan_columns,
    )
    parsed = document_parse.grid_to_excel_rows(payload, grid_columns, category_id=category_id)
    if category_id:
        for row in parsed:
            if not row.category_id:
                row.category_id = category_id

    uploads: dict[str, bytes] = {}
    for item in images:
        raw = await item.read()
        if raw:
            uploads[(item.filename or "image.jpg").rsplit("/", 1)[-1].lower()] = raw
    session = feed_sessions.get_owned(db, user.id, session_id) if session_id else None
    if not uploads and session is not None:
        for name, raw in feed_sessions.file_bytes(session, "excel_images"):
            uploads[name.rsplit("/", 1)[-1].lower()] = raw

    return _launch_import(
        user=user,
        shop=shop,
        rows=parsed,
        uploads=uploads,
        wants_drafts=True,
        listing_id=default_template_id,
        style="simple",
        image_mode=image_mode,
        public_base=public_refs.request_base(request),
        session=session,
        db=db,
    )


@router.post("/import")
async def import_excel(
    request: Request,
    style: str = Form("detect"),
    shop_id: str = Form(""),
    mapping: str = Form("{}"),
    create_drafts: bool = Form(False),
    listing_template_id: str = Form(""),
    category_id: str = Form(""),
    session_id: str = Form(""),
    image_mode: str = Form("keep_draw"),
    file: UploadFile | None = File(None),
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

    content = await file.read() if file is not None else b""
    session = feed_sessions.get_owned(db, user.id, session_id) if session_id else None
    if not content and session is not None:
        stored = feed_sessions.file_bytes(session, "excel")
        content = stored[0][1] if stored else b""
    if not content:
        raise HTTPException(status_code=400, detail="先选一个表格")
    try:
        mapping_payload = json.loads(mapping or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="列映射不是合法 JSON") from exc
    extras = _columns_for_style(db, user, shop_id, category_id, style) if style in {"simple", "full_schema"} else []
    if not isinstance(mapping_payload, dict) or not mapping_payload:
        preview = excel_import.preview(content, style, extras)
        mapping_payload = preview.get("mapping") or {}

    try:
        rows = excel_import.apply_preview(content, mapping_payload, style, extras)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"读不了这个表格：{exc}") from exc
    if not rows:
        raise HTTPException(
            status_code=400,
            detail="表格里只有示例行。示例行导入时会自动跳过，请把你的货写在它下面，一行一个商品。",
        )
    if category_id:
        for row in rows:
            if not row.category_id:
                row.category_id = category_id

    uploads: dict[str, bytes] = {}
    for item in images:
        raw = await item.read()
        if raw:
            uploads[(item.filename or "image.jpg").rsplit("/", 1)[-1].lower()] = raw
    if not uploads and session is not None:
        for name, raw in feed_sessions.file_bytes(session, "excel_images"):
            uploads[name.rsplit("/", 1)[-1].lower()] = raw

    return _launch_import(
        user=user,
        shop=shop,
        rows=rows,
        uploads=uploads,
        wants_drafts=wants_drafts,
        listing_id=listing_id,
        style=style,
        image_mode=image_mode,
        public_base=public_refs.request_base(request),
        session=session,
        db=db,
    )


def _run_import(
    user_id: str,
    shop_id: str,
    batch_id: str,
    payload: list[dict[str, Any]],
    uploads: dict[str, bytes],
    create_drafts: bool,
    listing_template_id: str,
    style: str,
    image_mode: str = "keep_draw",
    public_base: str = "",
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
        if shop is not None:
            try:
                from . import defaults as defaults_service

                defaults_service.pull_from_shop(db, shop_api(shop), shop)
            except (GopError, ShopNotConnected, RuntimeError, TypeError, ValueError):
                pass
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
                brand=raw.get("brand") or "",
                category_id=raw.get("category_id") or "",
                origin=raw.get("origin") or "",
                spec=raw.get("spec") or "",
                specs=dict(raw.get("specs") or {}),
                line=int(raw.get("line") or 0),
                attributes=dict(raw.get("attributes") or {}),
                listing_template_id=str(raw.get("listing_template_id") or raw.get("_template_id") or "").strip(),
            )
            row_template_id = row.listing_template_id
            row_listing = listing
            if row_template_id:
                picked = db.get(Template, row_template_id)
                if picked is not None and picked.shop_id == shop.id:
                    row_listing = picked
            try:
                _import_one(
                    db, user, shop, row, uploads, ai, create_drafts, row_listing, batch_id, image_mode, public_base
                )
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
    image_mode: str = "keep_draw",
    public_base: str = "",
) -> None:
    forced = row.category_id or (listing.category_id if listing is not None else "")
    category_hint = ""
    if shop is not None and forced:
        node = catalog.get_node(db, shop_api(shop), forced)
        category_hint = catalog.label(node) if node is not None else ""
    fact_note = row.fact_text() or row.note
    files: list[tuple[str, bytes]] = []
    source = ""
    prebuilt, prebuilt_source = grid_images.apply_job_to_excel_row(row, user.id)
    if prebuilt:
        files, source = prebuilt, prebuilt_source
    if not files:
        try:
            files, source = excel_images.prepare_row_images(
                row,
                uploads,
                image_mode,
                user_id=user.id,
                category_id=forced,
                fetch_url=_fetch_image,
                category_hint=category_hint,
                public_base=public_base,
            )
        except excel_images.ExcelImageError as exc:
            if shop is not None and create_drafts:
                distribution.failed_draft(db, user.id, shop.id, None, batch_id, f"第 {row.line} 行：{exc.message}")
            elif shop is None:
                product = Product(
                    user_id=user.id,
                    sku=row.sku or f"row-{row.line}",
                    name=row.name or row.title,
                    price=row.price,
                    moq=row.moq,
                    note=exc.message,
                    batch_id=batch_id,
                )
                db.add(product)
                db.commit()
            return

    if source == "skip":
        if shop is not None and create_drafts:
            distribution.failed_draft(db, user.id, shop.id, None, batch_id, f"第 {row.line} 行没图，已按「只导入有图的行」跳过")
            return
        product = Product(
            user_id=user.id,
            sku=row.sku or f"row-{row.line}",
            name=row.name or row.title,
            price=row.price,
            moq=row.moq,
            note="没图，已按「只导入有图的行」跳过",
            batch_id=batch_id,
        )
        db.add(product)
        db.commit()
        return

    sku = row.sku or (files[0][0].rsplit(".", 1)[0][:60] if files else f"row-{row.line}")
    note = fact_note
    if source == "generated":
        extra = "平台按品名和规格画了套图，不是实拍。买家要实拍时再补。"
        note = "\n".join(part for part in (fact_note.strip(), extra) if part)
    elif source == "completed":
        extra = "原图留下了，缺的转化位是平台补的，不是实拍。"
        note = "\n".join(part for part in (fact_note.strip(), extra) if part)
    product = Product(
        user_id=user.id,
        sku=sku,
        name=row.name or row.title,
        price=row.price,
        moq=row.moq,
        note=note,
        batch_id=batch_id,
    )
    db.add(product)
    db.commit()
    if files:
        catalogue.save_images(db, user, product, files[:6])

    understanding, error = pipeline.understand(
        ai, [ImageInput(filename=name, content=content) for name, content in files[:6]], note or row.name or row.title
    )
    product.understanding_json = json.dumps(understanding.raw, ensure_ascii=False)
    if not product.name:
        product.name = understanding.product_name
    db.commit()

    if not create_drafts or shop is None:
        return

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
            extra_defaults=row.extra_defaults(),
            fact_bundle=from_excel_row(row),
            template_id=row.listing_template_id or (listing.id if listing is not None else ""),
        )
    except ShopNotConnected as exc:
        distribution.failed_draft(db, user.id, shop.id, product, batch_id, str(exc))
        return
    if error:
        issues = json.loads(draft.issues_json or "[]")
        issues.append({"field_id": "ai", "field_name": "AI 成稿", "level": "yellow", "message": error, "path": "ai"})
        draft.issues_json = json.dumps(issues, ensure_ascii=False)
        db.commit()
    if source in {"generated", "completed"}:
        excel_images.mark_generated_images(db, draft, source)


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
