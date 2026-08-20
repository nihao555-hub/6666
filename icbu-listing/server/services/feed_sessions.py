"""In-progress listing paths. One row per unfinished job, many per seller."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ..config import settings
from ..models import FeedSession, utcnow

PATHS = {
    "photo": {"label": "有实拍", "steps": ("上传图片", "填价格", "生成草稿")},
    "ai": {"label": "平台画图", "steps": ("写出品名", "生成套图", "填价格", "生成草稿")},
    "excel": {"label": "填表批量", "steps": ("选类目", "下载表格", "传回表格", "图怎么处理", "开始成稿")},
    "full": {
        "label": "填表批量（旧）",
        "steps": ("选类目", "下载表格", "传回表格", "图怎么处理", "开始成稿"),
    },
}

SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def _payload(row: FeedSession) -> dict[str, Any]:
    try:
        data = json.loads(row.payload_json or "{}")
    except json.JSONDecodeError:
        data = {}
    return data if isinstance(data, dict) else {}


def _title_for(path: str, payload: dict[str, Any], files: list[dict[str, Any]]) -> str:
    if path == "ai":
        name = str((payload.get("aiForm") or {}).get("productName") or "").strip()
        return name or "平台画图"
    if path in {"excel", "full"}:
        excel = payload.get("excel") or {}
        name = str(payload.get("categoryName") or excel.get("categoryName") or "").strip()
        count = payload.get("rowCount")
        if name and count:
            return f"{name} · {count} 个"
        if path == "full":
            return name or "完全自己填"
        return name or "填表批量"
    sku = str((payload.get("form") or {}).get("sku") or "").strip()
    photos = [item for item in files if item.get("kind") in {"photos", "batch"}]
    if sku:
        return sku
    if photos:
        return f"实拍 · {len(photos)} 张"
    return "有实拍"


def session_dir(user_id: str, session_id: str) -> Path:
    path = settings.upload_dir / "feed-sessions" / user_id / session_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe(name: str) -> str:
    cleaned = SAFE_NAME.sub("_", (name or "file").rsplit("/", 1)[-1])[:80]
    return cleaned or "file"


def list_files(row: FeedSession) -> list[dict[str, Any]]:
    folder = session_dir(row.user_id, row.id)
    items: list[dict[str, Any]] = []
    if not folder.is_dir():
        return items
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.name.startswith("."):
            continue
        kind, _, filename = path.name.partition("__")
        if not filename:
            kind, filename = "file", path.name
        items.append(
            {
                "kind": kind,
                "name": filename,
                "stored": path.name,
                "url": f"/api/v1/feed-sessions/{row.id}/files/{path.name}",
                "size": path.stat().st_size,
            }
        )
    return items


def file_bytes(row: FeedSession, kind: str) -> list[tuple[str, bytes]]:
    out: list[tuple[str, bytes]] = []
    for item in list_files(row):
        if item["kind"] != kind:
            continue
        path = session_dir(row.user_id, row.id) / item["stored"]
        if path.is_file():
            out.append((item["name"], path.read_bytes()))
    return out


def file_path(row: FeedSession, stored: str) -> Path | None:
    if not stored or "/" in stored or "\\" in stored or stored.startswith("."):
        return None
    path = session_dir(row.user_id, row.id) / stored
    return path if path.is_file() else None


def public_view(row: FeedSession) -> dict[str, Any]:
    payload = _payload(row)
    files = list_files(row)
    spec = PATHS.get(row.path) or PATHS["photo"]
    steps = spec["steps"]
    step = max(0, min(int(row.step or 0), len(steps) - 1))
    return {
        "id": row.id,
        "path": row.path,
        "path_label": spec["label"],
        "status": row.status,
        "title": row.title or _title_for(row.path, payload, files),
        "step": step,
        "reached": max(int(row.reached or 0), step),
        "step_label": steps[step],
        "shop_id": row.shop_id,
        "payload": payload,
        "files": files,
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
    }


def list_open(db: Session, user_id: str, shop_id: str = "") -> list[FeedSession]:
    query = db.query(FeedSession).filter(FeedSession.user_id == user_id, FeedSession.status == "open")
    if shop_id:
        query = query.filter((FeedSession.shop_id == shop_id) | (FeedSession.shop_id == ""))
    return query.order_by(FeedSession.updated_at.desc()).all()


def get_owned(db: Session, user_id: str, session_id: str) -> FeedSession | None:
    row = db.get(FeedSession, session_id)
    if row is None or row.user_id != user_id:
        return None
    return row


def create(db: Session, user_id: str, path: str, shop_id: str = "") -> FeedSession:
    if path not in PATHS:
        path = "photo"
    row = FeedSession(
        user_id=user_id,
        shop_id=shop_id or "",
        path=path,
        status="open",
        title=PATHS[path]["label"],
        payload_json="{}",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def save(
    db: Session,
    row: FeedSession,
    *,
    shop_id: str | None = None,
    step: int | None = None,
    reached: int | None = None,
    payload: dict[str, Any] | None = None,
    status: str | None = None,
) -> FeedSession:
    if shop_id is not None:
        row.shop_id = shop_id
    if step is not None:
        row.step = max(0, int(step))
    if reached is not None:
        row.reached = max(int(row.reached or 0), int(reached), int(row.step or 0))
    if payload is not None:
        current = _payload(row)
        current.update(payload)
        row.payload_json = json.dumps(current, ensure_ascii=False)
    if status in {"open", "done", "dropped"}:
        row.status = status
    row.title = _title_for(row.path, _payload(row), list_files(row))
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return row


def sync_files(
    row: FeedSession,
    kind: str,
    *,
    keep: list[str],
    uploads: list[tuple[str, bytes]],
) -> None:
    folder = session_dir(row.user_id, row.id)
    keep_set = {item for item in keep if item}
    uploaded_names = set()
    for name, content in uploads:
        filename = _safe(name)
        uploaded_names.add(filename)
        dest = folder / f"{kind}__{filename}"
        dest.write_bytes(content)
    for item in list_files(row):
        if item["kind"] != kind:
            continue
        if item["name"] in keep_set or item["name"] in uploaded_names:
            continue
        path = folder / item["stored"]
        if path.is_file():
            path.unlink()
