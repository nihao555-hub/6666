from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .blob_persist import enabled as blob_enabled, hydrate_sqlite, persist_sqlite
from .config import settings
from .models import Base
from .services.auth_bootstrap import ensure_demo_user

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}


def _sqlite_path() -> Path | None:
    if not settings.database_url.startswith("sqlite:///"):
        return None
    return Path(settings.database_url.removeprefix("sqlite:///"))


if blob_enabled():
    path = _sqlite_path()
    if path is not None:
        hydrate_sqlite(path)

engine = create_engine(settings.database_url, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
_last_blob_hydrate = 0.0


def init_db() -> None:
    Base.metadata.create_all(engine)
    _ensure_columns()
    with SessionLocal() as db:
        ensure_demo_user(db)
    path = _sqlite_path()
    if path is not None and blob_enabled() and path.is_file():
        persist_sqlite(path)


def _ensure_columns() -> None:
    """create_all will not add columns to an already-created SQLite table."""
    if not settings.database_url.startswith("sqlite"):
        return
    with engine.begin() as conn:
        rows = conn.exec_driver_sql("PRAGMA table_info(drafts)").fetchall()
        names = {row[1] for row in rows}
        if rows and "sources_json" not in names:
            conn.exec_driver_sql("ALTER TABLE drafts ADD COLUMN sources_json TEXT DEFAULT '{}'")
        if rows and "audit_json" not in names:
            conn.exec_driver_sql("ALTER TABLE drafts ADD COLUMN audit_json TEXT DEFAULT '{}'")
        if rows and "reviewed_at" not in names:
            conn.exec_driver_sql("ALTER TABLE drafts ADD COLUMN reviewed_at DATETIME")
        product_rows = conn.exec_driver_sql("PRAGMA table_info(products)").fetchall()
        product_names = {row[1] for row in product_rows}
        if product_rows and "batch_id" not in product_names:
            conn.exec_driver_sql("ALTER TABLE products ADD COLUMN batch_id TEXT DEFAULT ''")
        shop_rows = conn.exec_driver_sql("PRAGMA table_info(shops)").fetchall()
        shop_names = {row[1] for row in shop_rows}
        if shop_rows and "online_count" not in shop_names:
            conn.exec_driver_sql("ALTER TABLE shops ADD COLUMN online_count INTEGER DEFAULT -1")
        conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS category_smart_plans ("
            "shop_id VARCHAR(32) NOT NULL, "
            "category_id VARCHAR(40) NOT NULL, "
            "input_hash VARCHAR(64) DEFAULT '', "
            "planner VARCHAR(16) DEFAULT 'rules', "
            "plan_json TEXT DEFAULT '{}', "
            "updated_at DATETIME, "
            "PRIMARY KEY (shop_id, category_id), "
            "FOREIGN KEY(shop_id) REFERENCES shops (id) ON DELETE CASCADE"
            ")"
        )


@event.listens_for(Session, "after_commit")
def _persist_sqlite_after_commit(_session: Session) -> None:
    path = _sqlite_path()
    if path is not None:
        persist_sqlite(path)


def session_scope() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def persist_database() -> None:
    path = _sqlite_path()
    if path is not None:
        persist_sqlite(path)


def reload_db_from_blob() -> bool:
    """Re-download SQLite from Vercel Blob when this serverless instance is stale."""
    path = _sqlite_path()
    if path is None or not blob_enabled():
        return False
    return hydrate_sqlite(path)


def reload_db_from_blob_throttled(min_interval_seconds: float = 2.0) -> bool:
    """Avoid re-downloading the blob on every read during a burst of requests."""
    global _last_blob_hydrate
    now = time.monotonic()
    if now - _last_blob_hydrate < min_interval_seconds:
        return False
    if reload_db_from_blob():
        _last_blob_hydrate = now
        return True
    return False
