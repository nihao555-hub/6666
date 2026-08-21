"""Tables.

Object model follows what the established listing tools converged on:

    Product   the seller's own catalogue entry (SPU), platform independent
    Template  per-category listing defaults, filled once and reused
    Draft     a Product mapped onto one shop's category schema
    Job       one publish attempt for one draft

Everything a tenant owns carries `user_id`, and every shop-scoped row also
carries `shop_id`, because one tenant may bind many shops.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    """Naive UTC. SQLite drops the offset on read, so storing aware values here
    would make in-session comparisons blow up on the first cache lookup."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    shops: Mapped[list["Shop"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    token: Mapped[str] = mapped_column(String(512), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Shop(Base):
    __tablename__ = "shops"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160), default="")
    platform: Mapped[str] = mapped_column(String(40), default="alibaba_icbu")
    account: Mapped[str] = mapped_column(String(160), default="")
    seller_id: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(24), default="active")  # active | expired | error
    # encrypted at rest
    access_token: Mapped[str] = mapped_column(Text, default="")
    refresh_token: Mapped[str] = mapped_column(Text, default="")
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    defaults_json: Mapped[str] = mapped_column(Text, default="{}")
    publish_mode: Mapped[str] = mapped_column(String(16), default="draft")  # draft | online
    last_error: Mapped[str] = mapped_column(Text, default="")
    online_count: Mapped[int] = mapped_column(Integer, default=-1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped[User] = relationship(back_populates="shops")

    __table_args__ = (Index("ix_shops_user_seller", "user_id", "seller_id"),)


class Product(Base):
    """Seller catalogue. Platform independent, reusable across shops."""

    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    sku: Mapped[str] = mapped_column(String(120), default="")
    name: Mapped[str] = mapped_column(String(400), default="")
    price: Mapped[str] = mapped_column(String(40), default="")
    moq: Mapped[str] = mapped_column(String(40), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    images_json: Mapped[str] = mapped_column(Text, default="[]")
    understanding_json: Mapped[str] = mapped_column(Text, default="{}")
    batch_id: Mapped[str] = mapped_column(String(32), default="", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (Index("ix_products_user_sku", "user_id", "sku"),)


class ProductImage(Base):
    """The seller's original file, stored once and reused for every shop."""

    __tablename__ = "product_images"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[str] = mapped_column(String(32), ForeignKey("products.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255), default="")
    path: Mapped[str] = mapped_column(String(500), default="")
    sort: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PhotobankAsset(Base):
    """Where one local image ended up in one shop's image bank.

    The image bank is per shop: the same picture published to three shops has
    to be uploaded three times and yields three different file ids. Caching the
    mapping is what stops a re-publish from re-uploading everything.
    """

    __tablename__ = "photobank_assets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    image_id: Mapped[str] = mapped_column(String(32), ForeignKey("product_images.id", ondelete="CASCADE"), index=True)
    shop_id: Mapped[str] = mapped_column(String(32), ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    file_id: Mapped[str] = mapped_column(String(64), default="")
    url: Mapped[str] = mapped_column(String(500), default="")
    file_name: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (UniqueConstraint("image_id", "shop_id", name="uq_photobank_image_shop"),)


class Template(Base):
    """Per-category trade and logistics defaults. Filled once, reused."""

    __tablename__ = "templates"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    shop_id: Mapped[str] = mapped_column(String(32), ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160), default="")
    category_id: Mapped[str] = mapped_column(String(40), default="")
    values_json: Mapped[str] = mapped_column(Text, default="{}")
    is_auto: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (Index("ix_templates_shop_cat", "shop_id", "category_id"),)


class Draft(Base):
    __tablename__ = "drafts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    shop_id: Mapped[str] = mapped_column(String(32), ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[str] = mapped_column(String(32), default="")
    batch_id: Mapped[str] = mapped_column(String(32), default="", index=True)

    sku: Mapped[str] = mapped_column(String(120), default="")
    title: Mapped[str] = mapped_column(String(400), default="")
    price: Mapped[str] = mapped_column(String(40), default="")
    moq: Mapped[str] = mapped_column(String(40), default="")

    category_id: Mapped[str] = mapped_column(String(40), default="")
    category_name: Mapped[str] = mapped_column(String(240), default="")
    category_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    category_candidates_json: Mapped[str] = mapped_column(Text, default="[]")

    status: Mapped[str] = mapped_column(String(24), default="red")  # red | yellow | green | publishing | published | failed
    values_json: Mapped[str] = mapped_column(Text, default="{}")
    issues_json: Mapped[str] = mapped_column(Text, default="[]")
    images_json: Mapped[str] = mapped_column(Text, default="[]")
    ai_json: Mapped[str] = mapped_column(Text, default="{}")
    sources_json: Mapped[str] = mapped_column(Text, default="{}")
    audit_json: Mapped[str] = mapped_column(Text, default="{}")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    product_online_id: Mapped[str] = mapped_column(String(64), default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (Index("ix_drafts_shop_status", "shop_id", "status"),)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    shop_id: Mapped[str] = mapped_column(String(32), ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    draft_id: Mapped[str] = mapped_column(String(32), index=True)
    batch_id: Mapped[str] = mapped_column(String(32), default="", index=True)

    status: Mapped[str] = mapped_column(String(24), default="queued")  # queued | running | success | failed
    mode: Mapped[str] = mapped_column(String(16), default="draft")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    product_online_id: Mapped[str] = mapped_column(String(64), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    error_fields_json: Mapped[str] = mapped_column(Text, default="[]")
    sku: Mapped[str] = mapped_column(String(120), default="")
    title: Mapped[str] = mapped_column(String(400), default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CategoryNode(Base):
    """Shared cache of the official category tree. Not tenant scoped."""

    __tablename__ = "category_nodes"

    category_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(240), default="")
    cn_name: Mapped[str] = mapped_column(String(240), default="")
    level: Mapped[int] = mapped_column(Integer, default=0)
    is_leaf: Mapped[bool] = mapped_column(Boolean, default=False)
    parent_id: Mapped[str] = mapped_column(String(40), default="", index=True)
    child_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SchemaCache(Base):
    """Shared cache of category publish rules."""

    __tablename__ = "schema_cache"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # f"{category_id}:{language}"
    category_id: Mapped[str] = mapped_column(String(40), index=True)
    language: Mapped[str] = mapped_column(String(16), default="en_US")
    xml: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class FeedSession(Base):
    """One in-progress listing path. Closing the tab must not lose it."""

    __tablename__ = "feed_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    shop_id: Mapped[str] = mapped_column(String(32), default="", index=True)
    path: Mapped[str] = mapped_column(String(16), default="photo")  # photo | ai | excel
    status: Mapped[str] = mapped_column(String(16), default="open")  # open | done | dropped
    title: Mapped[str] = mapped_column(String(240), default="")
    step: Mapped[int] = mapped_column(Integer, default=0)
    reached: Mapped[int] = mapped_column(Integer, default=0)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (Index("ix_feed_sessions_user_status", "user_id", "status"),)


class CategoryMemory(Base):
    """What the shop chose last time for a similar product."""

    __tablename__ = "category_memory"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    shop_id: Mapped[str] = mapped_column(String(32), index=True)
    signature: Mapped[str] = mapped_column(String(200), index=True)
    category_id: Mapped[str] = mapped_column(String(40))
    category_name: Mapped[str] = mapped_column(String(240), default="")
    hits: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (UniqueConstraint("shop_id", "signature", name="uq_memory_shop_signature"),)


class CategoryRecentPick(Base):
    """Explicit leaf picks in the category browser — quick re-select next time."""

    __tablename__ = "category_recent_picks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    shop_id: Mapped[str] = mapped_column(String(32), index=True)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    category_id: Mapped[str] = mapped_column(String(40))
    category_name: Mapped[str] = mapped_column(String(400), default="")
    picked_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint("shop_id", "user_id", "category_id", name="uq_recent_shop_user_cat"),
        Index("ix_recent_shop_user_picked", "shop_id", "user_id", "picked_at"),
    )
