"""The seller's own catalogue, one layer below any platform.

Keeping products separate from drafts is what makes multi-shop cheap: the
photos are stored once, the model looks at them once, and publishing the same
product to another shop reuses both. Only the image-bank upload has to be
repeated, because that bank belongs to the shop rather than to us.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from sqlalchemy.orm import Session

from ai import Understanding  # noqa: E402
from icbu_api import IcbuApi  # noqa: E402

from ..config import settings
from ..models import PhotobankAsset, Product, ProductImage, Shop, User, new_id
from .images import BankImage, upload


def save_images(db: Session, user: User, product: Product, uploads: Sequence[tuple[str, bytes]]) -> list[ProductImage]:
    folder = Path(settings.upload_dir) / user.id / product.id
    folder.mkdir(parents=True, exist_ok=True)

    stored: list[ProductImage] = []
    for index, (filename, content) in enumerate(uploads):
        safe = Path(filename).name or f"image-{index}.jpg"
        target = folder / f"{index:02d}-{safe}"
        target.write_bytes(content)
        image = ProductImage(
            user_id=user.id,
            product_id=product.id,
            filename=safe,
            path=str(target),
            sort=index,
        )
        db.add(image)
        stored.append(image)
    db.commit()
    return stored


def images_of(db: Session, product: Product) -> list[ProductImage]:
    return (
        db.query(ProductImage)
        .filter(ProductImage.product_id == product.id)
        .order_by(ProductImage.sort)
        .all()
    )


def read_uploads(images: Sequence[ProductImage]) -> list[tuple[str, bytes]]:
    uploads: list[tuple[str, bytes]] = []
    for image in images:
        path = Path(image.path)
        if path.exists():
            uploads.append((image.filename, path.read_bytes()))
    return uploads


def ensure_photobank(db: Session, api: IcbuApi, shop: Shop, images: Sequence[ProductImage]) -> tuple[list[BankImage], list[str]]:
    """Make sure every picture exists in this shop's image bank."""
    bank: list[BankImage] = []
    errors: list[str] = []

    cached = {
        asset.image_id: asset
        for asset in db.query(PhotobankAsset)
        .filter(
            PhotobankAsset.shop_id == shop.id,
            PhotobankAsset.image_id.in_([image.id for image in images] or [""]),
        )
        .all()
    }

    for image in images:
        asset = cached.get(image.id)
        if asset is not None and asset.url:
            bank.append(BankImage(file_name=asset.file_name, file_id=asset.file_id, url=asset.url))
            continue

        path = Path(image.path)
        if not path.exists():
            errors.append(f"{image.filename}: 本地文件已丢失")
            continue
        try:
            uploaded = upload(api, image.filename, path.read_bytes())
        except Exception as exc:  # keep going; the draft will be flagged red
            errors.append(f"{image.filename}: {exc}")
            continue

        db.add(
            PhotobankAsset(
                image_id=image.id,
                shop_id=shop.id,
                file_id=uploaded.file_id,
                url=uploaded.url,
                file_name=uploaded.file_name,
            )
        )
        bank.append(uploaded)
    db.commit()
    return bank, errors


def understanding_of(product: Product) -> Understanding:
    try:
        payload = json.loads(product.understanding_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    return Understanding.from_payload(payload if isinstance(payload, dict) else {})


def product_view(db: Session, product: Product, draft_counts: dict[str, int] | None = None) -> dict[str, Any]:
    images = images_of(db, product)
    understanding = understanding_of(product)
    return {
        "id": product.id,
        "sku": product.sku,
        "name": product.name or understanding.product_name,
        "price": product.price,
        "moq": product.moq,
        "note": product.note,
        "image_count": len(images),
        "images": [
            {
                "id": image.id,
                "filename": image.filename,
                "url": f"/api/v1/products/{product.id}/images/{image.id}",
            }
            for image in images
        ],
        "understanding": {
            "product_name": understanding.product_name,
            "category_hint": understanding.category_hint,
            "material": understanding.material,
            "colors": understanding.colors,
            "confidence": understanding.confidence,
        },
        "draft_count": (draft_counts or {}).get(product.id, 0),
        "created_at": product.created_at.isoformat(),
    }
