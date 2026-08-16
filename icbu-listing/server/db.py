from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import settings
from .models import Base

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_db() -> None:
    Base.metadata.create_all(engine)
    _ensure_columns()


def _ensure_columns() -> None:
    """create_all will not add columns to an already-created SQLite table."""
    if not settings.database_url.startswith("sqlite"):
        return
    with engine.begin() as conn:
        rows = conn.exec_driver_sql("PRAGMA table_info(drafts)").fetchall()
        names = {row[1] for row in rows}
        if rows and "sources_json" not in names:
            conn.exec_driver_sql("ALTER TABLE drafts ADD COLUMN sources_json TEXT DEFAULT '{}'")
        product_rows = conn.exec_driver_sql("PRAGMA table_info(products)").fetchall()
        product_names = {row[1] for row in product_rows}
        if product_rows and "batch_id" not in product_names:
            conn.exec_driver_sql("ALTER TABLE products ADD COLUMN batch_id TEXT DEFAULT ''")


def session_scope() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
