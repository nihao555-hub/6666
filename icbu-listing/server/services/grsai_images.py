"""Grsai GPT Image client.

Docs: https://grsai.ai/dashboard/documents/gpt-image
Host + POST /v1/draw/completions, optional POST /v1/draw/result.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import requests

from ..config import settings


class GrsaiError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def api_key() -> str:
    return (os.environ.get("GRSAI_API_KEY") or os.environ.get("IMAGE_API_KEY") or settings.grsai_api_key or "").strip()


def base_url() -> str:
    raw = (os.environ.get("GRSAI_BASE_URL") or os.environ.get("IMAGE_BASE_URL") or settings.grsai_base_url or "").strip()
    if not raw:
        chat = (os.environ.get("OPENAI_BASE_URL") or "").strip()
        raw = chat if "grsai" in chat else "https://api.grsai.com"
    raw = raw.rstrip("/")
    if raw.endswith("/v1"):
        raw = raw[:-3]
    return raw


def image_model() -> str:
    return (os.environ.get("IMAGE_MODEL") or settings.image_model or "gpt-image-2").strip()


def timeout_seconds() -> float:
    raw = os.environ.get("IMAGE_TIMEOUT_SECONDS")
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return float(settings.image_timeout_seconds or 180)


def parse_response(text: str) -> dict[str, Any]:
    """Grsai may return JSON or an SSE stream of `data: {...}` lines."""
    blob = (text or "").strip()
    if not blob:
        raise GrsaiError("出图服务没有返回内容")
    if "data:" in blob:
        last = ""
        for line in blob.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload and payload != "[DONE]":
                last = payload
        if last:
            blob = last
    try:
        parsed = json.loads(blob)
    except json.JSONDecodeError as exc:
        raise GrsaiError("出图服务返回了读不懂的内容") from exc
    if not isinstance(parsed, dict):
        raise GrsaiError("出图服务返回格式不对")
    return parsed


def _error_from(payload: dict[str, Any], fallback: str) -> str:
    err = payload.get("error") or payload.get("message") or payload.get("msg")
    if isinstance(err, dict):
        err = err.get("message") or err.get("msg")
    text = str(err or "").strip()
    if not text:
        return fallback
    lowered = text.lower()
    if "invalid" in lowered and "key" in lowered:
        return "出图服务密钥无效"
    if "quota" in lowered or "credit" in lowered or "余额" in text:
        return "出图额度不够了"
    return fallback


def _result_urls(payload: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    results = payload.get("results")
    if isinstance(results, list):
        for item in results:
            if isinstance(item, dict) and item.get("url"):
                urls.append(str(item["url"]))
            elif isinstance(item, str) and item.startswith("http"):
                urls.append(item)
    direct = payload.get("url")
    if isinstance(direct, str) and direct.startswith("http"):
        urls.append(direct)
    return urls


def _post(path: str, body: dict[str, Any], *, timeout: float) -> dict[str, Any]:
    key = api_key()
    if not key:
        raise GrsaiError("平台还没接上出图服务")
    url = f"{base_url()}{path}"
    try:
        response = requests.post(
            url,
            json=body,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )
    except requests.Timeout as exc:
        raise GrsaiError("出图超时，请再试一次") from exc
    except requests.RequestException as exc:
        raise GrsaiError("连不上出图服务") from exc
    if response.status_code == 401:
        raise GrsaiError("出图服务密钥无效")
    if response.status_code == 429:
        raise GrsaiError("出图太频繁，稍后再试")
    if response.status_code >= 500:
        raise GrsaiError("出图服务暂时不可用")
    if response.status_code != 200:
        raise GrsaiError("出图请求没有成功")
    return parse_response(response.text)


def _wait_for_result(task_id: str, *, timeout: float) -> dict[str, Any]:
    deadline = time.time() + timeout
    last: dict[str, Any] = {}
    while time.time() < deadline:
        last = _post("/v1/draw/result", {"id": task_id}, timeout=min(30.0, timeout))
        status = str(last.get("status") or "").lower()
        if status in {"succeeded", "success", "completed"}:
            return last
        if status in {"failed", "error", "canceled", "cancelled"}:
            raise GrsaiError(_error_from(last, "这一张没画出来"))
        time.sleep(2)
    raise GrsaiError("出图超时，请再试一次")


def generate_one(
    prompt: str,
    *,
    urls: list[str] | None = None,
    aspect_ratio: str = "1:1",
) -> tuple[bytes, str]:
    """Draw one square listing frame. Returns (image_bytes, remote_url)."""
    timeout = timeout_seconds()
    payload = _post(
        "/v1/draw/completions",
        {
            "model": image_model(),
            "prompt": prompt,
            "urls": [item for item in (urls or []) if item],
            "shutProgress": True,
            "aspectRatio": aspect_ratio,
        },
        timeout=timeout,
    )
    status = str(payload.get("status") or "").lower()
    if status in {"pending", "processing", "running", "queued", "in_progress"} and payload.get("id"):
        payload = _wait_for_result(str(payload["id"]), timeout=timeout)
        status = str(payload.get("status") or "").lower()
    if status and status not in {"succeeded", "success", "completed"}:
        raise GrsaiError(_error_from(payload, "这一张没画出来"))
    remote_urls = _result_urls(payload)
    if not remote_urls:
        if payload.get("error") or payload.get("msg") or payload.get("message"):
            raise GrsaiError(_error_from(payload, "这一张没画出来"))
        raise GrsaiError("出图服务没有给出图片")
    return download_image(remote_urls[0]), remote_urls[0]


def download_image(url: str) -> bytes:
    try:
        response = requests.get(url, timeout=60)
    except requests.RequestException as exc:
        raise GrsaiError("图片画好了，但下载失败") from exc
    if response.status_code != 200 or not response.content:
        raise GrsaiError("图片画好了，但下载失败")
    return response.content


def generated_dir() -> Path:
    """Writable generated-image root (Vercel/Lambda use /tmp via settings)."""
    path = settings.generated_dir
    path.mkdir(parents=True, exist_ok=True)
    return path
