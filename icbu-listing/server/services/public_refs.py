"""Short-lived public URLs so the image model can see the seller's main photo.

Grsai fetches `urls` from the public internet. Local bytes have to be hosted
first. The id is a random hex; the file is not listed.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Request

from ..config import settings
from ..models import new_id

_SUFFIX = {".png": ".png", ".jpg": ".jpg", ".jpeg": ".jpg", ".webp": ".webp"}


def store(content: bytes, filename: str = "") -> str:
    if not content:
        raise ValueError("empty")
    ext = Path(filename or "photo.jpg").suffix.lower()
    suffix = _SUFFIX.get(ext, ".jpg")
    ref_id = new_id()
    folder = settings.generated_dir / "refs"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{ref_id}{suffix}"
    path.write_bytes(content)
    return ref_id


def path_of(ref_id: str) -> Path | None:
    if not ref_id or "/" in ref_id or "\\" in ref_id:
        return None
    folder = settings.generated_dir / "refs"
    for suffix in (".jpg", ".png", ".webp"):
        candidate = folder / f"{ref_id}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def public_url(base: str, ref_id: str) -> str:
    root = (base or "").rstrip("/")
    return f"{root}/api/v1/public-refs/{ref_id}"


def request_base(request: Request | None = None) -> str:
    """Public origin Grsai can fetch. Prefer env, then the browser Origin / Host."""
    configured = (settings.public_base_url or "").strip().rstrip("/")
    if configured:
        return configured
    if request is None:
        return ""
    origin = (request.headers.get("origin") or "").strip().rstrip("/")
    if origin.startswith("http://") or origin.startswith("https://"):
        return origin
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(",")[0].strip()
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "http").split(",")[0].strip()
    if host:
        return f"{proto}://{host}".rstrip("/")
    return str(request.base_url).rstrip("/")
