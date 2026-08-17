"""校验 LINE webhook 的 X-Line-Signature（HMAC-SHA256 + Base64）。"""
from __future__ import annotations

import base64
import hashlib
import hmac


def verify_signature(channel_secret: str, body: bytes, signature: str) -> bool:
    if not signature:
        return False
    digest = hmac.new(channel_secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, signature)
