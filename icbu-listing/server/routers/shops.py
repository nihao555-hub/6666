from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from gop_client import GopError  # noqa: E402

from ..config import settings
from ..crypto import encrypt_secret, read_state, sign_state
from ..deps import current_user, get_db, owned_shop
from ..models import Draft, Job, Shop, User
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
    "logisticsProperty": "普货",
    "marketSample": "Unavailable",
    "shippingTemplateId": "",
    "pkgWeight": "",
    "pkgLength": "",
    "pkgWidth": "",
    "pkgHeight": "",
    "brand": "",
    "language": "en_US",
}


class BindEnvIn(BaseModel):
    name: str = "环境店铺"


class DefaultsIn(BaseModel):
    defaults: dict[str, Any]
    publish_mode: str | None = None
    name: str | None = None


def _oauth_error(reason: str, message: str) -> RedirectResponse:
    """Send the seller back with something they can act on.

    A silent bounce back to the shop list is the worst outcome here: the most
    common failure is a redirect_uri that was never registered on the open
    platform, and nothing on screen would say so.
    """
    separator = "&" if "?" in settings.oauth_error_url else "?"
    query = urlencode({"reason": reason, "message": message})
    return RedirectResponse(f"{settings.oauth_error_url}{separator}{query}", status_code=302)


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
def oauth_start(user: User = Depends(current_user)) -> dict[str, str]:
    if not settings.has_platform_app:
        raise HTTPException(status_code=400, detail="平台还没有配置国际站应用的 AppKey / AppSecret")
    state = sign_state({"user_id": user.id})
    return {"url": authorize_url(state), "redirect_uri": settings.oauth_redirect_uri}


@router.get("/alibaba/oauth/callback")
def oauth_callback(code: str = "", state: str = "", db: Session = Depends(get_db)) -> RedirectResponse:
    payload = read_state(state)
    if not code or payload is None:
        return _oauth_error("state", "授权回跳的校验参数无效或已过期，请重新点一次授权")

    user_id = str(payload.get("user_id") or "")
    user = db.get(User, user_id)
    if user is None:
        return _oauth_error("user", "找不到发起授权的账号，请重新登录后再试")

    try:
        raw = platform_client().execute(
            "/auth/token/create",
            {"code": code, "redirect_uri": settings.oauth_redirect_uri},
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
    return RedirectResponse(settings.oauth_success_url, status_code=302)


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
    return {
        "products": products,
        "total": result.get("total_item") or listing.get("total_item") or 0,
        "page": page,
        "page_size": page_size,
    }


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
