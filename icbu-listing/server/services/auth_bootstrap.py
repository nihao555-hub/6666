"""Seed a demo tenant on serverless cold starts when configured."""

from __future__ import annotations

import os

from sqlalchemy.orm import Session

from ..crypto import hash_password
from ..models import User
from .shop_bootstrap import ensure_env_shop

DEFAULT_DEMO_EMAIL = "demo@auto-shoper.test"
DEFAULT_DEMO_PASSWORD = "AutoShoper2026"
DEMO_USER_ID = "00000000000000000000000000000001"


def _seed_enabled() -> bool:
    if os.environ.get("SEED_DEMO_USER", "").strip().lower() in {"0", "false", "no"}:
        return False
    if os.environ.get("SEED_DEMO_USER", "").strip().lower() in {"1", "true", "yes"}:
        return True
    return bool(os.environ.get("VERCEL"))


def ensure_demo_user(db: Session) -> User | None:
    """Create the public demo account when missing (Vercel / SEED_DEMO_USER)."""
    if not _seed_enabled():
        return None
    email = (os.environ.get("DEMO_USER_EMAIL") or DEFAULT_DEMO_EMAIL).strip().lower()
    password = (os.environ.get("DEMO_USER_PASSWORD") or DEFAULT_DEMO_PASSWORD).strip()
    if not email or "@" not in email or len(password) < 8:
        return None
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        user = User(
            id=DEMO_USER_ID,
            email=email,
            password_hash=hash_password(password),
            display_name=email.split("@")[0],
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    try:
        ensure_env_shop(db, user)
    except Exception:
        db.rollback()
    return user
