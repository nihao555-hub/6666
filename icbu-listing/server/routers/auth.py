from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import settings
from ..crypto import hash_password, sign_session, verify_password
from ..deps import current_user, get_db
from ..db import persist_database
from ..models import AuthSession, Shop, User
from ..services.shop_bootstrap import ensure_env_shop

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class RegisterIn(BaseModel):
    email: str = Field(min_length=3, max_length=180)
    password: str = Field(min_length=8, max_length=128)
    code: str = ""


class LoginIn(BaseModel):
    email: str
    password: str


def _open_session(db: Session, response: Response, user: User) -> None:
    token = sign_session(user.id, settings.session_days * 86400)
    expires = datetime.utcnow() + timedelta(days=settings.session_days)
    db.add(AuthSession(token=token, user_id=user.id, expires_at=expires))
    db.commit()
    persist_database()
    response.set_cookie(
        settings.session_cookie,
        token,
        max_age=settings.session_days * 86400,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def _profile(user: User) -> dict[str, str]:
    return {"id": user.id, "email": user.email, "display_name": user.display_name}


@router.post("/register")
def register(payload: RegisterIn, response: Response, db: Session = Depends(get_db)) -> dict[str, str]:
    if settings.registration_codes and payload.code not in settings.registration_codes:
        raise HTTPException(status_code=400, detail="注册码不对")
    email = payload.email.strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=400, detail="邮箱格式不对")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="这个邮箱已经注册过了")
    user = User(email=email, password_hash=hash_password(payload.password), display_name=email.split("@")[0])
    db.add(user)
    db.commit()
    _open_session(db, response, user)
    return _profile(user)


@router.post("/login")
def login(payload: LoginIn, response: Response, db: Session = Depends(get_db)) -> dict[str, str]:
    email = payload.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=400, detail="邮箱或密码不对")
    _open_session(db, response, user)
    if not db.query(Shop).filter(Shop.user_id == user.id).count():
        ensure_env_shop(db, user)
        persist_database()
    return _profile(user)


@router.post("/logout")
def logout(
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, bool]:
    db.query(AuthSession).filter(AuthSession.user_id == user.id).delete()
    db.commit()
    persist_database()
    response.delete_cookie(settings.session_cookie, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)) -> dict[str, str]:
    return _profile(user)
