"""Copy a live listing the way the official backend does, then let AI rewrite.

Alibaba's own seller console can duplicate a product. That copy keeps the
title and the pictures, which is exactly what the repeat-listing detector
looks at. We keep the parts that already passed review (category, official
attributes, freight, origin) and ask the model for a new title and
keywords. The seller should still swap photos when they have them.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from ai import AiClient, Understanding  # noqa: E402
from schema import extract_values  # noqa: E402

from ..models import Draft, Product, Shop, Template, User
from . import catalog, pipeline, sources
from .images import BankImage
from .shop_client import shop_api, shop_defaults
from .templates import PROTECTED

CLONE_LOCK = {
    "icbuCatProp",
    "saleProp",
    "catId",
    "origin",
    "priceUnit",
    "paymentMethod",
    "port",
    "shippingTemplateId",
    "pkgMeasure",
    "pkgWeight",
    "logisticsMode",
    "logisticsProperty",
    "marketSample",
    "market",
    "scImages",
    "detailImage",
}


def render_xml(api: Any, category_id: str, product_id: str, language: str = "en_US") -> str:
    payload = api.schema_render(int(category_id), int(product_id), language)
    result = payload.get("result") or payload
    return str(result.get("data") or "")


def images_from_values(values: dict[str, Any]) -> list[BankImage]:
    block = values.get("scImages") or {}
    images: list[BankImage] = []
    if not isinstance(block, dict):
        return images
    for key, item in block.items():
        if not isinstance(item, dict):
            continue
        attrs = item.get("$attrs") or {}
        url = str(item.get("$value") or "")
        file_id = str(attrs.get("fileId") or attrs.get("file_id") or "")
        if url or file_id:
            images.append(BankImage(file_name=str(key), file_id=file_id, url=url))
    return images


def price_moq(values: dict[str, Any]) -> tuple[str, str]:
    ladder = values.get("ladderPrice") or {}
    first = ladder.get("ladderPrice_0") if isinstance(ladder, dict) else {}
    if not isinstance(first, dict):
        first = {}
    price = str(first.get("price") or values.get("scPrice") or "")
    moq = str(first.get("quantity") or values.get("minOrderQuantity") or "")
    return price, moq


def clone_to_draft(
    db: Session,
    user: User,
    shop: Shop,
    *,
    product_id: str,
    category_id: str,
    ai: AiClient | None = None,
    differentiate: bool = True,
) -> Draft:
    api = shop_api(shop)
    defaults = shop_defaults(shop)
    language = str(defaults.get("language") or "en_US")
    xml = render_xml(api, category_id, product_id, language)
    values = extract_values(xml)
    if not values:
        raise RuntimeError("回读在线商品没有拿到字段，可能是草稿或已删除")

    title = str(values.get("productTitle") or "")
    price, moq = price_moq(values)
    bank = images_from_values(values)
    understanding = Understanding(product_name=title, category_hint=title, confidence=0.7, raw={"cloned_from": product_id})

    if differentiate and ai is not None:
        try:
            copy = ai.write_copy(
                understanding,
                extra_facts={"category": category_id, "cloned_from": title, "moq": moq, "unit_price": price},
                angle="rewrite so it is not the same listing; keep the facts, change the wording and the buyer angle",
            )
            if copy.title:
                values["productTitle"] = copy.title
                title = copy.title
            if copy.keywords:
                values["productKeywords"] = {
                    f"productKeywords_{index}": word for index, word in enumerate(copy.keywords[:3])
                }
            if copy.highlights:
                values["textDesc"] = copy.highlights
        except Exception:
            pass

    product = Product(
        user_id=user.id,
        sku=f"clone-{product_id}"[-60:],
        name=title,
        price=price,
        moq=moq,
        note=f"复制自在线商品 {product_id}",
        understanding_json=json.dumps(understanding.raw, ensure_ascii=False),
    )
    db.add(product)
    db.commit()

    field_sources = sources.infer_initial(values)
    for key in CLONE_LOCK:
        if key in values:
            field_sources[key] = "clone"
    field_sources["productTitle"] = "ai" if differentiate else "clone"
    field_sources["productKeywords"] = "ai" if differentiate else "clone"

    issues = []
    if category_id:
        rule_xml = catalog.get_schema_xml(db, api, category_id, language)
        issues = [item.as_dict() for item in pipeline.revalidate(rule_xml, values)]
    issues.append(
        {
            "field_id": "scImages",
            "field_name": "产品图片",
            "level": "yellow",
            "message": "图片还是原listing的。平台按标题+属性+图片打重铺，有新图请换上。",
            "path": "scImages",
        }
    )
    if not price or not moq:
        issues.append(
            {
                "field_id": "price",
                "field_name": "价格 / 起订量",
                "level": "red",
                "message": "复制过来的价格或起订量是空的，要你来定",
                "path": "ladderPrice",
            }
        )

    node = catalog.get_node(db, api, category_id)
    draft = Draft(
        user_id=user.id,
        shop_id=shop.id,
        product_id=product.id,
        sku=product.sku,
        title=title,
        price=price,
        moq=moq,
        category_id=category_id,
        category_name=(f"{node.name} / {node.cn_name}" if node else category_id),
        category_confidence=0.95,
        values_json=json.dumps(values, ensure_ascii=False),
        images_json=json.dumps([item.as_dict() for item in bank], ensure_ascii=False),
        ai_json=json.dumps({"understanding": understanding.raw, "cloned_from": product_id}, ensure_ascii=False),
        issues_json=json.dumps(issues, ensure_ascii=False),
        sources_json=sources.dump(field_sources),
        status=pipeline.status_of(issues),
        updated_at=datetime.utcnow(),
    )
    db.add(draft)
    db.commit()
    return draft


def learn_defaults(db: Session, shop: Shop, *, product_id: str, category_id: str) -> dict[str, Any]:
    """Fill pullable shop defaults from one live listing. Never overwrite seller edits."""
    from . import defaults as defaults_service

    return defaults_service.pull_from_shop(
        db,
        shop_api(shop),
        shop,
        product_id=product_id,
        category_id=category_id,
        refresh=False,
    )


def learn_template(db: Session, user: User, shop: Shop, *, product_id: str, category_id: str, name: str = "") -> Template:
    api = shop_api(shop)
    language = str(shop_defaults(shop).get("language") or "en_US")
    values = extract_values(render_xml(api, category_id, product_id, language))
    kept = {key: value for key, value in values.items() if key not in PROTECTED}
    row = Template(
        user_id=user.id,
        shop_id=shop.id,
        name=name or f"从在线品 {product_id} 学到的模板",
        category_id=category_id,
        values_json=json.dumps(kept, ensure_ascii=False),
        is_auto=True,
    )
    db.add(row)
    db.commit()
    return row


def _nested(values: dict[str, Any], *keys: str) -> Any:
    current: Any = values
    for key in keys:
        if not isinstance(current, dict):
            return ""
        current = current.get(key)
    return current or ""


def _period_days(values: dict[str, Any]) -> str:
    raw = _nested(values, "ladderPeriod", "ladderPeriod_0") or values.get("ladderPeriod") or ""
    if isinstance(raw, dict):
        for key in ("period", "time", "days", "leadTime"):
            if raw.get(key):
                return str(raw[key])
        return ""
    return str(raw) if raw else ""
