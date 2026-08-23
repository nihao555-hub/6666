"""Create, resume, and drop unfinished listing paths."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..deps import current_user, get_db
from ..db import reload_db_from_blob_throttled
from ..models import User
from ..services import feed_sessions as sessions

router = APIRouter(prefix="/api/v1/feed-sessions", tags=["feed-sessions"])


class CreateIn(BaseModel):
    path: str
    shop_id: str = ""


class SaveIn(BaseModel):
    shop_id: str | None = None
    step: int | None = None
    reached: int | None = None
    payload: dict[str, Any] = {}
    status: str | None = None


@router.get("")
def list_sessions(shop_id: str = "", db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict[str, Any]:
    reload_db_from_blob_throttled(min_interval_seconds=2.0)
    db.expire_all()
    rows = sessions.list_open(db, user.id, shop_id)
    return {"sessions": [sessions.public_view(row) for row in rows]}


@router.post("")
def create_session(payload: CreateIn, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict[str, Any]:
    reload_db_from_blob_throttled(min_interval_seconds=2.0)
    db.expire_all()
    row = sessions.create(db, user.id, payload.path, payload.shop_id)
    return sessions.public_view(row)


@router.get("/{session_id}")
def get_session(session_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict[str, Any]:
    db.expire_all()
    row = sessions.get_owned(db, user.id, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="这条做到一半的记录不在了")
    return sessions.public_view(row)


@router.patch("/{session_id}")
def save_session(
    session_id: str,
    payload: SaveIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    db.expire_all()
    row = sessions.upsert_owned(
        db,
        user.id,
        session_id,
        path="doc",
        shop_id=payload.shop_id or "",
    )
    row = sessions.save(
        db,
        row,
        shop_id=payload.shop_id,
        step=payload.step,
        reached=payload.reached,
        payload=payload.payload,
        status=payload.status,
    )
    return sessions.public_view(row)


@router.post("/{session_id}/files")
async def upload_files(
    session_id: str,
    kind: str = Form("photos"),
    keep: str = Form(""),
    files: list[UploadFile] = File(default_factory=list),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    db.expire_all()
    row = sessions.upsert_owned(
        db,
        user.id,
        session_id,
        path="doc",
    )
    if kind not in {"photos", "batch", "excel", "excel_images", "doc"}:
        raise HTTPException(status_code=400, detail="这种文件不能存在半成品里")
    uploads = [(item.filename or "file", await item.read()) for item in files]
    uploads = [(name, content) for name, content in uploads if content]
    sessions.sync_files(
        row,
        kind,
        keep=[part.strip() for part in keep.split(",") if part.strip()],
        uploads=uploads,
    )
    sessions.save(db, row)
    return sessions.public_view(row)


@router.get("/{session_id}/files/{stored}")
def download_file(
    session_id: str,
    stored: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> FileResponse:
    db.expire_all()
    row = sessions.get_owned_with_retry(db, user.id, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="这条做到一半的记录不在了")
    path = sessions.file_path(row, stored)
    if path is None:
        raise HTTPException(status_code=404, detail="文件不在了")
    return FileResponse(path)


@router.delete("/{session_id}")
def drop_session(session_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict[str, Any]:
    db.expire_all()
    row = sessions.get_owned_with_retry(db, user.id, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="这条做到一半的记录不在了")
    sessions.save(db, row, status="dropped")
    return {"ok": True}
