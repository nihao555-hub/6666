"""Request dependencies.

`current_user` and `owned_shop` are the only way handlers get at data, which is
what keeps one tenant out of another tenant's shops.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

from fastapi import Cookie, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from .config import settings
from .crypto import read_session_payload
from .db import SessionLocal, reload_db_from_blob
from .models import AuthSession, Draft, Shop, User


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _resolve_user(db: Session, user_id: str, email: str = "") -> User | None:
    if user_id:
        user = db.get(User, user_id)
        if user is not None:
            return user
    if reload_db_from_blob():
        db.expire_all()
        if user_id:
            user = db.get(User, user_id)
            if user is not None:
                return user
    if email:
        return db.query(User).filter(User.email == email.strip().lower()).first()
    return None


def current_user(
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias=settings.session_cookie),
) -> User:
    if not session_token:
        raise HTTPException(status_code=401, detail="请先登录")
    payload = read_session_payload(session_token)
    if payload:
        user_id = str(payload.get("user_id") or "").strip()
        email = str(payload.get("email") or "").strip().lower()
        user = _resolve_user(db, user_id, email)
        if user is not None:
            return user
    row = db.get(AuthSession, session_token)
    if row is None or row.expires_at < datetime.utcnow():
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    user = _resolve_user(db, row.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="账号不存在")
    return user


def owned_shop(
    shop_id: str = Path(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Shop:
    shop = db.get(Shop, shop_id)
    if shop is None or shop.user_id != user.id:
        raise HTTPException(status_code=404, detail="店铺不存在")
    return shop


def shop_for(db: Session, user: User, shop_id: str) -> Shop:
    shop = db.get(Shop, shop_id)
    if shop is not None and shop.user_id == user.id:
        return shop
    if reload_db_from_blob():
        db.expire_all()
        shop = db.get(Shop, shop_id)
        if shop is not None and shop.user_id == user.id:
            return shop
    raise HTTPException(status_code=404, detail="店铺不存在")


def owned_draft(
    draft_id: str = Path(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Draft:
    draft = db.get(Draft, draft_id)
    if draft is None or draft.user_id != user.id:
        raise HTTPException(status_code=404, detail="草稿不存在")
    return draft
