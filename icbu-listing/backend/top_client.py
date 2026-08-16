"""Official TOP (Taobao Open Platform) HTTP client.

Alibaba.com ICBU APIs are called through TOP. The console-generated SDK
is just a typed wrapper around this protocol. We implement the protocol
directly so any `alibaba.icbu.*` method can be called without the
per-app zip from the developer console.

Docs: https://developer.alibaba.com/docs/doc.htm?articleId=101617&docType=1
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Mapping
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import requests

GATEWAY_CN = "https://eco.taobao.com/router/rest"
GATEWAY_OVERSEAS = "https://api.taobao.com/router/rest"
OAUTH_AUTHORIZE = "https://oauth.taobao.com/authorize"
SIGN_MD5 = "md5"
SIGN_HMAC = "hmac"
SIGN_HMAC_SHA256 = "hmac-sha256"
CHINA = ZoneInfo("Asia/Shanghai")


class TopError(RuntimeError):
    def __init__(self, payload: Mapping[str, Any]):
        self.payload = dict(payload)
        error = payload.get("error_response") or payload
        self.code = error.get("code")
        self.msg = error.get("msg") or error.get("message") or "TOP error"
        self.sub_code = error.get("sub_code")
        self.sub_msg = error.get("sub_msg")
        super().__init__(f"{self.code} {self.msg} {self.sub_code or ''} {self.sub_msg or ''}".strip())


def sign_top_request(
    params: Mapping[str, str],
    secret: str,
    sign_method: str = SIGN_HMAC_SHA256,
) -> str:
    """Official TOP signature. Byte-array fields (images) are excluded by caller."""
    pieces = "".join(f"{key}{params[key]}" for key in sorted(params) if params[key] is not None and params[key] != "")
    method = sign_method.lower()
    if method == SIGN_MD5:
        digest = hashlib.md5(f"{secret}{pieces}{secret}".encode("utf-8")).digest()
    elif method == SIGN_HMAC:
        digest = hmac.new(secret.encode("utf-8"), pieces.encode("utf-8"), hashlib.md5).digest()
    elif method == SIGN_HMAC_SHA256:
        digest = hmac.new(secret.encode("utf-8"), pieces.encode("utf-8"), hashlib.sha256).digest()
    else:
        raise ValueError(f"unsupported sign_method: {sign_method}")
    return digest.hex().upper()


def china_timestamp(now: datetime | None = None) -> str:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(CHINA).strftime("%Y-%m-%d %H:%M:%S")


class TopClient:
    def __init__(
        self,
        app_key: str,
        app_secret: str,
        gateway: str = GATEWAY_CN,
        sign_method: str = SIGN_HMAC_SHA256,
        timeout: float = 30.0,
        session: str | None = None,
    ) -> None:
        if not app_key or not app_secret:
            raise ValueError("app_key and app_secret are required")
        self.app_key = app_key
        self.app_secret = app_secret
        self.gateway = gateway.rstrip("/")
        self.sign_method = sign_method
        self.timeout = timeout
        self.session = session

    @classmethod
    def from_env(cls) -> "TopClient":
        return cls(
            app_key=os.environ.get("ALIBABA_APP_KEY", ""),
            app_secret=os.environ.get("ALIBABA_APP_SECRET", ""),
            gateway=os.environ.get("ALIBABA_GATEWAY", GATEWAY_CN),
            session=os.environ.get("ALIBABA_SESSION_KEY") or None,
        )

    def authorize_url(self, redirect_uri: str, state: str = "icbu") -> str:
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self.app_key,
                "redirect_uri": redirect_uri,
                "view": "web",
                "state": state,
            }
        )
        return f"{OAUTH_AUTHORIZE}?{query}"

    def execute(
        self,
        method: str,
        biz: Mapping[str, Any] | None = None,
        session: str | None = None,
        files: Mapping[str, bytes] | None = None,
    ) -> dict[str, Any]:
        token = session if session is not None else self.session
        public = {
            "method": method,
            "app_key": self.app_key,
            "timestamp": china_timestamp(),
            "v": "2.0",
            "sign_method": self.sign_method,
            "format": "json",
            "simplify": "true",
        }
        if token:
            public["session"] = token

        body: dict[str, str] = {}
        for key, value in (biz or {}).items():
            if value is None:
                continue
            if isinstance(value, (dict, list)):
                body[key] = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            elif isinstance(value, bool):
                body[key] = "true" if value else "false"
            else:
                body[key] = str(value)

        sign_source = {**public, **body}
        public["sign"] = sign_top_request(sign_source, self.app_secret, self.sign_method)

        if files:
            # TOP requires system params on the query string when uploading bytes.
            response = requests.post(
                self.gateway,
                params=public,
                data=body,
                files={name: (name, content) for name, content in files.items()},
                timeout=self.timeout,
            )
        else:
            response = requests.post(
                self.gateway,
                data={**public, **body},
                timeout=self.timeout,
            )
        response.raise_for_status()
        payload = response.json()
        if "error_response" in payload:
            raise TopError(payload)
        return payload
