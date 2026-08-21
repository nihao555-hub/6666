"""Password hashing, shop-token encryption and signed OAuth state.

Shop access tokens are the keys to somebody else's storefront, so they are
encrypted at rest with a key that lives outside the database.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from cryptography.fernet import Fernet, InvalidToken

from .config import settings

PBKDF2_ROUNDS = 240_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return f"pbkdf2${PBKDF2_ROUNDS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, rounds, salt_b64, digest_b64 = stored.split("$")
    except ValueError:
        return False
    if algorithm != "pbkdf2":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), base64.b64decode(salt_b64), int(rounds))
    return hmac.compare_digest(digest, base64.b64decode(digest_b64))


def _fernet() -> Fernet:
    key = settings.token_encryption_key
    if not key:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY 没有配置，无法安全保存店铺 token")
    return Fernet(key.encode("utf-8") if isinstance(key, str) else key)


def encrypt_secret(value: str) -> str:
    if not value:
        return ""
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str) -> str:
    if not value:
        return ""
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("店铺 token 解密失败，TOKEN_ENCRYPTION_KEY 可能变了") from exc


def _state_key() -> bytes:
    return (settings.token_encryption_key or os.environ.get("ALIBABA_APP_SECRET", "state")).encode("utf-8")


def sign_state(payload: dict[str, object], ttl_seconds: int = 900) -> str:
    body = dict(payload)
    body["exp"] = int(time.time()) + ttl_seconds
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
    blob = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    signature = hmac.new(_state_key(), blob.encode("ascii"), hashlib.sha256).hexdigest()[:32]
    return f"{blob}.{signature}"


def read_state(state: str) -> dict[str, object] | None:
    try:
        blob, signature = state.split(".", 1)
    except ValueError:
        return None
    expected = hmac.new(_state_key(), blob.encode("ascii"), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(expected, signature):
        return None
    padded = blob + "=" * (-len(blob) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(padded))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("exp", 0) < time.time():
        return None
    return payload


def sign_session(user_id: str, ttl_seconds: int, email: str = "") -> str:
    payload: dict[str, object] = {"user_id": user_id, "kind": "session"}
    if email:
        payload["email"] = email.strip().lower()
    return sign_state(payload, ttl_seconds)


def read_session_payload(token: str) -> dict[str, object] | None:
    payload = read_state(token)
    if not payload or payload.get("kind") != "session":
        return None
    return payload


def read_session(token: str) -> str:
    payload = read_session_payload(token)
    if not payload:
        return ""
    return str(payload.get("user_id") or "").strip()
