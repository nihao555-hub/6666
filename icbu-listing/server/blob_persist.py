"""Persist the SQLite file to Vercel Blob between serverless invocations."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import requests

from .config import settings

log = logging.getLogger(__name__)

BLOB_API = "https://blob.vercel-storage.com"
_lock = threading.Lock()


def _headers(*, json: bool = False) -> dict[str, str]:
    token = settings.blob_read_write_token
    if not token:
        return {}
    headers = {"Authorization": f"Bearer {token}"}
    if json:
        headers["Content-Type"] = "application/json"
    return headers


def enabled() -> bool:
    return bool(settings.blob_read_write_token and settings.database_url.startswith("sqlite:///"))


SQLITE_MAGIC = b"SQLite format 3\x00"


def _looks_like_sqlite(data: bytes) -> bool:
    return len(data) >= 16 and data[:16] == SQLITE_MAGIC


def hydrate_sqlite(dest: Path) -> bool:
    """Download the latest SQLite snapshot into dest, if one exists."""
    if not enabled():
        return False
    prefix = settings.blob_db_pathname.rsplit("/", 1)[0] + "/"
    try:
        response = requests.get(
            f"{BLOB_API}?prefix={prefix}",
            headers=_headers(),
            timeout=settings.blob_timeout_seconds,
        )
        response.raise_for_status()
        blobs = response.json().get("blobs") or []
        match = next((item for item in blobs if item.get("pathname") == settings.blob_db_pathname), None)
        if match is None and blobs:
            match = sorted(blobs, key=lambda item: item.get("uploadedAt") or "", reverse=True)[0]
        if match is None:
            return False
        blob = requests.get(
            match["url"],
            headers=_headers(),
            timeout=settings.blob_timeout_seconds,
        )
        blob.raise_for_status()
        if not _looks_like_sqlite(blob.content):
            log.warning("blob hydrate skipped: snapshot is not a SQLite file")
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(blob.content)
        return True
    except requests.RequestException as exc:
        log.warning("blob hydrate failed: %s", exc)
        return False


def persist_sqlite(source: Path) -> bool:
    """Upload the SQLite file to Vercel Blob (overwrite)."""
    if not enabled() or not source.is_file():
        return False
    with _lock:
        try:
            response = requests.put(
                f"{BLOB_API}/{settings.blob_db_pathname}",
                headers={
                    **_headers(),
                    "Content-Type": "application/octet-stream",
                    "x-vercel-blob-access": "private",
                    "x-vercel-blob-add-random-suffix": "0",
                    "x-vercel-blob-allow-overwrite": "1",
                },
                data=source.read_bytes(),
                timeout=settings.blob_timeout_seconds,
            )
            response.raise_for_status()
            return True
        except requests.RequestException as exc:
            log.warning("blob persist failed: %s", exc)
            return False
