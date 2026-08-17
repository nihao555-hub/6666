from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from gop_client import GopError  # noqa: E402

from ..config import settings
from ..crypto import encrypt_secret, read_state, sign_state
from ..deps import current_user, get_db, owned_shop
from ..models import Draft, Job, Shop, User
from ai import AiClient  # noqa: E402

from ..services import clone, defaults as defaults_service, templates as template_service
from ..services.shop_client import (
    ShopNotConnected,
    authorize_url,
    platform_client,
    refresh_if_needed,
    shop_api,
    shop_defaults,
    store_token,
)

router = APIRouter(prefix="/api/v1", tags=["shops"])

DEFAULT_TEMPLATE: dict[str, Any] = {
    "origin": "China",
    "priceUnit": "Piece/Pieces",
    "saleType": "Unit",
    # Official value, not «普货»: that label only comes back on zh calls, so a
    # label default silently dropped the field on every English publish.
    "logisticsProperty": "general_cargo_0",
    "marketSample": "Unavailable",
    "shippingTemplateId": "",
    "pkgWeight": "",
    "pkgLength": "",
    "pkgWidth": "",
    "pkgHeight": "",
    "brand": "",
    "language": "en_US",
    "paymentMethod": "T/T",
    "port": "",
    "ladderPeriod": "15",
    "market": "询盘",
}


class BindEnvIn(BaseModel):
    name: str = "环境店铺"


class DefaultsIn(BaseModel):
    defaults: dict[str, Any]
    # What the seller saw when they picked. Stored so shop lists stay readable
    # without re-fetching the schema just to turn «4» back into «Piece/Pieces».
    labels: dict[str, str] | None = None
    publish_mode: str | None = None
    name: str | None = None


class CloneIn(BaseModel):
    product_id: str
    category_id: str
    differentiate: bool = True
    name: str = ""


def oauth_callback_uri(request: Request) -> str:
    """Callback Alibaba will hit. Must match authorize + token exchange.

    Public tunnels send X-Forwarded-*. Using the env default (127.0.0.1)
    would send the seller back to their own laptop after they confirm.
    """
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "http").split(",")[0].strip()
    host = (
        request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    ).split(",")[0].strip()
    return f"{proto}://{host}/api/v1/alibaba/oauth/callback"


def _oauth_error(reason: str, message: str) -> RedirectResponse:
    """Stay on this host. The env success/error URLs still point at localhost."""
    query = urlencode({"alibaba": "error", "reason": reason, "message": message})
    return RedirectResponse(f"/#/shops?{query}", status_code=302)


def shop_view(shop: Shop) -> dict[str, Any]:
    return {
        "id": shop.id,
        "name": shop.name or shop.account or "未命名店铺",
        "account": shop.account,
        "seller_id": shop.seller_id,
        "platform": shop.platform,
        "status": shop.status,
        "publish_mode": shop.publish_mode,
        "connected": bool(shop.access_token),
        "bound_by": "oauth" if shop.refresh_token else "debug",
        "defaults": {**DEFAULT_TEMPLATE, **shop_defaults(shop)},
        "token_expires_at": shop.token_expires_at.isoformat() if shop.token_expires_at else None,
        "last_error": shop.last_error,
        "created_at": shop.created_at.isoformat(),
    }


@router.get("/shops")
def list_shops(db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[dict[str, Any]]:
    shops = db.query(Shop).filter(Shop.user_id == user.id).order_by(Shop.created_at).all()
    return [shop_view(shop) for shop in shops]


@router.get("/alibaba/oauth/start")
def oauth_start(request: Request, user: User = Depends(current_user)) -> dict[str, str]:
    if not settings.has_platform_app:
        raise HTTPException(status_code=400, detail="平台还没有接好国际站应用，暂时不能登录店铺")
    redirect_uri = oauth_callback_uri(request)
    state = sign_state({"user_id": user.id, "redirect_uri": redirect_uri})
    return {"url": authorize_url(state, redirect_uri), "redirect_uri": redirect_uri}


@router.get("/alibaba/oauth/callback")
def oauth_callback(
    request: Request,
    code: str = "",
    state: str = "",
    db: Session = Depends(get_db),
) -> RedirectResponse:
    payload = read_state(state)
    if not code or payload is None:
        return _oauth_error("state", "授权回跳的校验参数无效或已过期，请重新点一次登录")

    user_id = str(payload.get("user_id") or "")
    user = db.get(User, user_id)
    if user is None:
        return _oauth_error("user", "找不到发起授权的账号，请重新登录后再试")

    redirect_uri = str(payload.get("redirect_uri") or "") or oauth_callback_uri(request)
    try:
        raw = platform_client().execute(
            "/auth/token/create",
            {"code": code, "redirect_uri": redirect_uri},
            access_token=None,
        )
    except (GopError, ShopNotConnected) as exc:
        return _oauth_error("exchange", f"换取店铺 token 失败：{exc}")

    body = raw if isinstance(raw, dict) else {}
    seller_id = str(body.get("seller_id") or body.get("user_id") or body.get("userId") or "")

    shop = None
    if seller_id:
        shop = (
            db.query(Shop)
            .filter(Shop.user_id == user.id, Shop.seller_id == seller_id, Shop.platform == "alibaba_icbu")
            .one_or_none()
        )
    if shop is None:
        shop = Shop(user_id=user.id, platform="alibaba_icbu", defaults_json=json.dumps(DEFAULT_TEMPLATE))
        db.add(shop)

    store_token(shop, body)
    db.commit()
    return RedirectResponse("/#/shops?alibaba=connected", status_code=302)


@router.post("/shops/bind-env")
def bind_env_shop(
    payload: BindEnvIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Local convenience: adopt the token in the environment as one shop.

    Real tenants go through OAuth; this exists so the flow can be exercised
    end to end before the app is listed on the service market.
    """
    if not settings.dev_access_token:
        raise HTTPException(status_code=400, detail="环境里没有 ALIBABA_ACCESS_TOKEN")
    shop = Shop(
        user_id=user.id,
        name=payload.name,
        platform="alibaba_icbu",
        access_token=encrypt_secret(settings.dev_access_token),
        defaults_json=json.dumps(DEFAULT_TEMPLATE),
        status="active",
    )
    db.add(shop)
    db.commit()

    try:
        listing = shop_api(shop).list_products(1, 1)
        result = (listing.get("result") or {})
        shop.account = str(
            ((result.get("product_list") or {}).get("products") or [{}])[0].get("owner_member_display_name") or ""
        ) or shop.account
        db.commit()
    except (GopError, ShopNotConnected):
        pass

    return shop_view(shop)


@router.post("/shops/{shop_id}/defaults")
def save_defaults(
    payload: DefaultsIn,
    db: Session = Depends(get_db),
    shop: Shop = Depends(owned_shop),
) -> dict[str, Any]:
    merged = {**DEFAULT_TEMPLATE, **shop_defaults(shop), **payload.defaults}
    if payload.labels:
        merged["labels"] = {**(merged.get("labels") or {}), **payload.labels}
    shop.defaults_json = json.dumps(merged, ensure_ascii=False)
    if payload.publish_mode in {"draft", "online"}:
        shop.publish_mode = payload.publish_mode
    if payload.name:
        shop.name = payload.name
    db.commit()
    return shop_view(shop)


@router.delete("/shops/{shop_id}")
def unbind_shop(db: Session = Depends(get_db), shop: Shop = Depends(owned_shop)) -> dict[str, bool]:
    db.query(Draft).filter(Draft.shop_id == shop.id).delete()
    db.query(Job).filter(Job.shop_id == shop.id).delete()
    db.delete(shop)
    db.commit()
    return {"ok": True}


@router.get("/shops/{shop_id}/online")
def online_products(
    page: int = 1,
    page_size: int = 20,
    filter_type: str = "onSelling",
    db: Session = Depends(get_db),
    shop: Shop = Depends(owned_shop),
) -> dict[str, Any]:
    refresh_if_needed(db, shop)
    try:
        payload = shop_api(shop).list_products(page, page_size, filter_type)
    except ShopNotConnected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except GopError as exc:
        shop.last_error = str(exc)
        db.commit()
        raise HTTPException(status_code=502, detail=f"拉取在线商品失败：{exc}") from exc

    result = payload.get("result") or {}
    listing = result.get("product_list") or {}
    products = []
    for item in listing.get("products") or []:
        main = item.get("main_image") or {}
        images = main.get("images") or []
        products.append(
            {
                "id": str(item.get("product_id") or item.get("id") or ""),
                "subject": item.get("subject") or "",
                "category_id": str(item.get("category_id") or ""),
                "status": item.get("product_status_type") or item.get("status") or "",
                "image": images[0] if images else "",
                "modified": item.get("gmt_modified") or item.get("gmt_create") or "",
            }
        )
    total = result.get("total_item") or listing.get("total_item") or 0
    try:
        shop.online_count = int(total)
        db.commit()
    except (TypeError, ValueError):
        pass
    return {
        "products": products,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/shops/{shop_id}/default-options")
def default_options(
    category_id: str = "",
    db: Session = Depends(get_db),
    shop: Shop = Depends(owned_shop),
) -> dict[str, Any]:
    """Official option lists for the defaults form, so nothing is typed blind."""
    merged = {**DEFAULT_TEMPLATE, **shop_defaults(shop)}
    try:
        return defaults_service.options_view(
            db,
            shop_api(shop),
            shop,
            merged,
            category_id=category_id,
            language=str(merged.get("language") or "en_US"),
        )
    except ShopNotConnected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (GopError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=f"拉取官方选项失败：{exc}") from exc


@router.get("/shops/{shop_id}/photobank")
def photobank(
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    shop: Shop = Depends(owned_shop),
) -> dict[str, Any]:
    try:
        payload = shop_api(shop).list_images(0, page, page_size)
    except (GopError, ShopNotConnected) as exc:
        raise HTTPException(status_code=502, detail=f"拉取图片银行失败：{exc}") from exc
    listing = ((payload.get("result") or {}).get("pagination_query_list") or {}).get("list") or []
    return {
        "images": [
            {
                "id": str(item.get("id") or ""),
                "file_name": item.get("file_name") or "",
                "url": item.get("url") or "",
                "size": item.get("file_size") or 0,
            }
            for item in listing
        ]
    }


@router.post("/shops/{shop_id}/online/clone")
def clone_online(
    payload: CloneIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    shop: Shop = Depends(owned_shop),
) -> dict[str, Any]:
    """Official 'copy listing', but AI rewrites the title so it is not a repeat."""
    from .listings import draft_view

    try:
        draft = clone.clone_to_draft(
            db,
            user,
            shop,
            product_id=payload.product_id,
            category_id=payload.category_id,
            ai=AiClient.from_env_or_none(),
            differentiate=payload.differentiate,
        )
    except (GopError, ShopNotConnected, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return draft_view(draft, detailed=True)


@router.post("/shops/{shop_id}/online/learn-defaults")
def learn_defaults(
    payload: CloneIn,
    db: Session = Depends(get_db),
    shop: Shop = Depends(owned_shop),
) -> dict[str, Any]:
    try:
        return clone.learn_defaults(db, shop, product_id=payload.product_id, category_id=payload.category_id)
    except (GopError, ShopNotConnected, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/shops/{shop_id}/online/learn-template")
def learn_template(
    payload: CloneIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    shop: Shop = Depends(owned_shop),
) -> dict[str, Any]:
    try:
        row = clone.learn_template(
            db, user, shop, product_id=payload.product_id, category_id=payload.category_id, name=payload.name
        )
    except (GopError, ShopNotConnected, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return template_service.as_dict(row)
