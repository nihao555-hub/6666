"""Alibaba.com GOP / new Open Platform client.

Gateway: https://openapi-api.alibaba.com/rest
Auth:    https://openapi-auth.alibaba.com/oauth/authorize
Sign:    HMAC-SHA256(secret, api_path + sorted(key+value)), hex upper.

This is not the old TOP protocol (eco.taobao.com + session).
Docs: https://open.taobao.global / jaq-doc article 121120
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Any, Mapping
from urllib.parse import urlencode

import requests

GATEWAY = "https://openapi-api.alibaba.com/rest"
AUTHORIZE_URL = "https://openapi-auth.alibaba.com/oauth/authorize"
SIGN_SHA256 = "sha256"


class GopError(RuntimeError):
    def __init__(self, payload: Mapping[str, Any], status_code: int = 0):
        self.payload = dict(payload)
        self.status_code = status_code
        self.code = payload.get("code") or payload.get("error_code")
        self.msg = (
            payload.get("message")
            or payload.get("msg")
            or payload.get("error_message")
            or payload.get("error")
            or "GOP error"
        )
        super().__init__(f"{self.code or status_code} {self.msg}".strip())


def to_api_path(method: str) -> str:
    if method.startswith("/"):
        return method
    return "/" + method.replace(".", "/")


def sign_gop_request(api_path: str, params: Mapping[str, str], secret: str) -> str:
    pieces = api_path + "".join(f"{key}{params[key]}" for key in sorted(params) if params[key] not in (None, ""))
    return hmac.new(secret.encode("utf-8"), pieces.encode("utf-8"), hashlib.sha256).hexdigest().upper()


class GopClient:
    def __init__(
        self,
        app_key: str,
        app_secret: str,
        access_token: str | None = None,
        gateway: str = GATEWAY,
        authorize_url: str = AUTHORIZE_URL,
        append_operation_to_url: bool = False,
        timeout: float = 30.0,
    ) -> None:
        if not app_key or not app_secret:
            raise ValueError("app_key and app_secret are required")
        self.app_key = app_key
        self.app_secret = app_secret
        self.access_token = access_token
        self.gateway = gateway.rstrip("/")
        self.authorize_url = authorize_url.rstrip("/")
        self.append_operation_to_url = append_operation_to_url
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "GopClient":
        append = os.environ.get("ALIBABA_APPEND_OPERATION_TO_URL", "false").lower() in {"1", "true", "yes"}
        return cls(
            app_key=os.environ.get("ALIBABA_APP_KEY", ""),
            app_secret=os.environ.get("ALIBABA_APP_SECRET", ""),
            access_token=os.environ.get("ALIBABA_ACCESS_TOKEN") or None,
            gateway=os.environ.get("ALIBABA_GATEWAY", GATEWAY),
            authorize_url=os.environ.get("ALIBABA_AUTHORIZE_URL", AUTHORIZE_URL),
            append_operation_to_url=append,
            timeout=float(os.environ.get("ALIBABA_TIMEOUT_SECONDS", "30")),
        )

    def authorize_link(self, redirect_uri: str, state: str = "icbu") -> str:
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self.app_key,
                "redirect_uri": redirect_uri,
                "force_auth": "true",
                "state": state,
            }
        )
        return f"{self.authorize_url}?{query}"

    def execute(
        self,
        method: str,
        biz: Mapping[str, Any] | None = None,
        access_token: str | None = None,
        files: Mapping[str, bytes] | None = None,
    ) -> dict[str, Any]:
        api_path = to_api_path(method)
        token = access_token if access_token is not None else self.access_token
        public = {
            "app_key": self.app_key,
            "timestamp": str(int(time.time() * 1000)),
            "sign_method": SIGN_SHA256,
            "format": "json",
            "method": api_path,
        }
        if token:
            public["access_token"] = token

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
        public["sign"] = sign_gop_request(api_path, sign_source, self.app_secret)
        url = f"{self.gateway}{api_path}" if self.append_operation_to_url else self.gateway
        headers = {
            "X-Protocol": "GOP",
            "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
        }

        if files:
            headers.pop("Content-Type", None)
            response = requests.post(
                url,
                params=public,
                data=body,
                files={name: (name, content) for name, content in files.items()},
                headers={"X-Protocol": "GOP"},
                timeout=self.timeout,
            )
        else:
            response = requests.post(
                url,
                data={**public, **body},
                headers=headers,
                timeout=self.timeout,
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise GopError({"message": response.text[:500]}, response.status_code) from exc

        if response.status_code >= 400 or _is_gop_error(payload):
            raise GopError(payload, response.status_code)
        return payload


def _is_gop_error(payload: Mapping[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return True
    if payload.get("error_response"):
        return True
    code = payload.get("code")
    if code in {None, "", 0, "0", 200, "200", "SUCCESS"}:
        return False
    if isinstance(code, str) and code.upper() in {"SUCCESS", "OK"}:
        return False
    # GOP often returns code=None with a result, or code as business string.
    if "result" in payload or "data" in payload or "access_token" in payload:
        return False
    return bool(payload.get("message") or payload.get("error_message"))
