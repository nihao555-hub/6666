"""Build an ICBU client bound to one shop's token.

Every call into Alibaba goes through here, so a tenant can never reach a shop
row they do not own: the caller must hand over a `Shop` that was already loaded
through the ownership dependency.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from gop_client import GopClient, GopError  # noqa: E402  (backend/ is on sys.path)
from icbu_api import IcbuApi  # noqa: E402

from ..config import settings
from ..crypto import decrypt_secret, encrypt_secret
from ..models import Shop


class ShopNotConnected(RuntimeError):
    pass


def platform_client(access_token: str | None = None) -> GopClient:
    """Client for calls that are not bound to a shop (token exchange)."""
    if not settings.has_platform_app:
        raise ShopNotConnected("平台还没有配置 ALIBABA_APP_KEY / ALIBABA_APP_SECRET")
    return GopClient(
        app_key=settings.app_key,
        app_secret=settings.app_secret,
        access_token=access_token,
        gateway=settings.gateway,
        authorize_url=settings.authorize_url,
        append_operation_to_url=settings.append_operation_to_url,
        timeout=settings.timeout_seconds,
    )


def shop_token(shop: Shop) -> str:
    token = decrypt_secret(shop.access_token)
    if not token:
        raise ShopNotConnected(f"店铺「{shop.name or shop.account}」还没有授权")
    return token


def shop_api(shop: Shop) -> IcbuApi:
    return IcbuApi(platform_client(shop_token(shop)))


def store_token(shop: Shop, payload: dict[str, Any]) -> None:
    """Persist the result of /auth/token/create or /auth/token/refresh."""
    access = payload.get("access_token") or payload.get("accessToken") or ""
    refresh = payload.get("refresh_token") or payload.get("refreshToken") or ""
    if access:
        shop.access_token = encrypt_secret(str(access))
    if refresh:
        shop.refresh_token = encrypt_secret(str(refresh))

    expires_in = payload.get("expires_in") or payload.get("expire_time") or payload.get("expiresIn")
    try:
        seconds = int(expires_in)
    except (TypeError, ValueError):
        seconds = 0
    if seconds > 10_000_000_000:  # some responses carry an absolute epoch in ms
        shop.token_expires_at = datetime.fromtimestamp(seconds / 1000, tz=timezone.utc).replace(tzinfo=None)
    elif seconds > 0:
        shop.token_expires_at = (datetime.now(timezone.utc) + timedelta(seconds=seconds)).replace(tzinfo=None)

    shop.seller_id = str(
        payload.get("seller_id") or payload.get("user_id") or payload.get("userId") or shop.seller_id or ""
    )
    account = payload.get("account") or payload.get("user_nick") or payload.get("account_platform") or ""
    if account:
        shop.account = str(account)
    if not shop.name:
        shop.name = shop.account or f"店铺 {shop.seller_id}"
    shop.status = "active"
    shop.last_error = ""


def refresh_if_needed(db: Session, shop: Shop) -> None:
    """Refresh a token that is about to expire, best effort."""
    if not shop.token_expires_at:
        return
    if shop.token_expires_at - datetime.utcnow() > timedelta(hours=6):
        return
    refresh = decrypt_secret(shop.refresh_token)
    if not refresh:
        return
    try:
        payload = platform_client().execute("/auth/token/refresh", {"refresh_token": refresh}, access_token=None)
    except GopError as exc:
        shop.status = "expired"
        shop.last_error = str(exc)
        db.commit()
        return
    store_token(shop, payload if isinstance(payload, dict) else {})
    db.commit()


def shop_defaults(shop: Shop) -> dict[str, Any]:
    try:
        value = json.loads(shop.defaults_json or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def authorize_url(state: str) -> str:
    return platform_client().authorize_link(settings.oauth_redirect_uri, state)
