"""Ensure a dev/test shop exists when ALIBABA_ACCESS_TOKEN is configured."""

from __future__ import annotations

import json
from typing import Any

from gop_client import GopError  # noqa: E402
from sqlalchemy.orm import Session

from ..config import settings
from ..crypto import encrypt_secret
from ..models import Shop, User
from ..services import defaults as defaults_service
from ..services.shop_client import ShopNotConnected, shop_api

DEMO_SHOP_ID = "00000000000000000000000000000002"
DEMO_USER_ID = "00000000000000000000000000000001"

DEFAULT_TEMPLATE: dict[str, Any] = {
    "origin": "China",
    "priceUnit": "Piece/Pieces",
    "saleType": "Unit",
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


def _listing_products(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    nested = result.get("product_list") if isinstance(result.get("product_list"), dict) else {}
    products = result.get("products")
    if not isinstance(products, list):
        products = nested.get("products") if isinstance(nested.get("products"), list) else []
    total = result.get("total_item") or nested.get("total_item") or 0
    return products, int(total or 0)


def ensure_env_shop(db: Session, user: User, *, name: str = "测试店铺") -> Shop | None:
    """Bind the platform access token as this user's shop when none exists."""
    if not settings.dev_access_token:
        return None
    if user.id == DEMO_USER_ID:
        shop = db.get(Shop, DEMO_SHOP_ID)
        if shop is not None and shop.user_id == user.id:
            if not shop.access_token:
                shop.access_token = encrypt_secret(settings.dev_access_token)
                shop.status = "active"
                db.commit()
            return shop
    existing = (
        db.query(Shop)
        .filter(Shop.user_id == user.id, Shop.platform == "alibaba_icbu")
        .order_by(Shop.created_at)
        .all()
    )
    if existing:
        shop = existing[0]
        if not shop.access_token:
            shop.access_token = encrypt_secret(settings.dev_access_token)
            shop.status = "active"
            db.commit()
        return shop

    shop = Shop(
        id=DEMO_SHOP_ID if user.id == DEMO_USER_ID else None,
        user_id=user.id,
        name=name,
        platform="alibaba_icbu",
        access_token=encrypt_secret(settings.dev_access_token),
        defaults_json=json.dumps(DEFAULT_TEMPLATE),
        status="active",
    )
    db.add(shop)
    db.commit()
    db.refresh(shop)

    try:
        products, total = _listing_products(shop_api(shop).list_products(1, 1))
        owner = str((products[0] if products else {}).get("owner_member_display_name") or "")
        if owner:
            shop.account = owner
            if shop.name in {"", "测试店铺", "环境店铺"}:
                shop.name = owner
        shop.online_count = total
        db.commit()
        defaults_service.pull_from_shop(db, shop_api(shop), shop)
    except (GopError, ShopNotConnected, RuntimeError, TypeError, ValueError):
        pass

    return shop
