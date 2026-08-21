from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ai import AiClient, ImageInput  # noqa: E402

from ..db import SessionLocal
from ..deps import current_user, get_db, shop_for
from ..models import Draft, PhotobankAsset, Product, ProductImage, Shop, User, new_id
from ..services import distribution, pipeline, products as catalogue

router = APIRouter(prefix="/api/v1", tags=["products"])

MAX_IMAGES = 6


class DistributeIn(BaseModel):
    product_ids: list[str]
    shop_ids: list[str]
    price: str | None = None
    moq: str | None = None
    differentiate: bool = True


def _draft_counts(db: Session, user: User) -> dict[str, int]:
    rows = (
        db.query(Draft.product_id, func.count(Draft.id))
        .filter(Draft.user_id == user.id, Draft.product_id != "")
        .group_by(Draft.product_id)
        .all()
    )
    return {product_id: count for product_id, count in rows}


@router.post("/products")
async def create_product(
    sku: str = Form(""),
    name: str = Form(""),
    price: str = Form(""),
    moq: str = Form(""),
    note: str = Form(""),
    files: list[UploadFile] = File(default_factory=list),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Add one product to the catalogue and let the model look at it once."""
    uploads = [(item.filename or "image.jpg", await item.read()) for item in files[:MAX_IMAGES]]
    uploads = [(filename, content) for filename, content in uploads if content]
    if not uploads:
        raise HTTPException(status_code=400, detail="至少要传一张图")

    product = Product(user_id=user.id, sku=sku, name=name, price=price, moq=moq, note=note)
    db.add(product)
    db.commit()

    catalogue.save_images(db, user, product, uploads)

    ai = AiClient.from_env_or_none()
    understanding, error = pipeline.understand(
        ai, [ImageInput(filename=filename, content=content) for filename, content in uploads], note or name
    )
    product.understanding_json = json.dumps(understanding.raw, ensure_ascii=False)
    if not product.name:
        product.name = understanding.product_name
    if not product.sku:
        product.sku = uploads[0][0].rsplit(".", 1)[0][:60]
    db.commit()

    view = catalogue.product_view(db, product)
    view["ai_error"] = error
    return view


@router.get("/products")
def list_products(
    keyword: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[dict[str, Any]]:
    query = db.query(Product).filter(Product.user_id == user.id)
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(Product.name.like(like) | Product.sku.like(like))
    items = query.order_by(Product.created_at.desc()).limit(500).all()
    counts = _draft_counts(db, user)
    return [catalogue.product_view(db, item, counts) for item in items]


@router.get("/products/{product_id}")
def get_product(
    product_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    product = db.get(Product, product_id)
    if product is None or product.user_id != user.id:
        raise HTTPException(status_code=404, detail="商品不存在")
    return catalogue.product_view(db, product, _draft_counts(db, user))


@router.get("/products/{product_id}/images/{image_id}")
def product_image(
    product_id: str,
    image_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> FileResponse:
    product = db.get(Product, product_id)
    image = db.get(ProductImage, image_id)
    if product is None or image is None or product.user_id != user.id or image.product_id != product.id:
        raise HTTPException(status_code=404, detail="图片不存在")

    path = Path(image.path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="本地文件已丢失")
    return FileResponse(path, filename=image.filename)


@router.delete("/products/{product_id}")
def delete_product(
    product_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, bool]:
    product = db.get(Product, product_id)
    if product is None or product.user_id != user.id:
        raise HTTPException(status_code=404, detail="商品不存在")
    # Drafts already generated stay: they may be published or in review.
    images = db.query(ProductImage).filter(ProductImage.product_id == product.id).all()
    image_ids = [image.id for image in images]
    if image_ids:
        db.query(PhotobankAsset).filter(PhotobankAsset.image_id.in_(image_ids)).delete(synchronize_session=False)
    for image in images:
        path = Path(image.path)
        if path.exists():
            path.unlink(missing_ok=True)
        db.delete(image)
    db.delete(product)
    db.commit()
    return {"ok": True}


@router.post("/products/distribute")
def distribute(
    payload: DistributeIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Send chosen products to chosen shops, one draft per pair."""
    products = (
        db.query(Product).filter(Product.user_id == user.id, Product.id.in_(payload.product_ids)).all()
    )
    if not products:
        raise HTTPException(status_code=404, detail="没有找到选中的商品")
    shops = [shop_for(db, user, shop_id) for shop_id in payload.shop_ids]
    if not shops:
        raise HTTPException(status_code=400, detail="至少要选一个店铺")

    batch_id = new_id()
    pairs = [(product.id, shop.id) for product in products for shop in shops]
    threading.Thread(
        target=_run_distribute,
        args=(user.id, batch_id, pairs, payload.price, payload.moq, payload.differentiate),
        daemon=True,
    ).start()

    return {
        "batch_id": batch_id,
        "count": len(pairs),
        "products": len(products),
        "shops": len(shops),
    }


def _run_distribute(
    user_id: str,
    batch_id: str,
    pairs: list[tuple[str, str]],
    price: str | None,
    moq: str | None,
    differentiate: bool,
) -> None:
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if user is None:
            return
        ai = AiClient.from_env_or_none()
        seen_per_product: dict[str, int] = {}

        for product_id, shop_id in pairs:
            product = db.get(Product, product_id)
            shop = db.get(Shop, shop_id)
            if product is None or shop is None:
                continue

            index = seen_per_product.get(product_id, 0)
            seen_per_product[product_id] = index + 1
            angle = distribution.ANGLES[index % len(distribution.ANGLES)] if differentiate else ""

            try:
                distribution.build_draft_for_shop(
                    db, user, shop, product, price=price or "", moq=moq or "", ai=ai, angle=angle, batch_id=batch_id
                )
            except Exception as exc:  # one bad pair must not stop the batch
                distribution.failed_draft(db, user_id, shop_id, product, batch_id, str(exc))
    finally:
        db.close()
