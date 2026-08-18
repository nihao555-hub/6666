"""Turn one catalogue product into one shop's draft.

Both entry points go through here: dropping a single product in for the current
shop, and fanning a batch of products out across several shops. Keeping it in
one place is what guarantees the two paths cannot drift apart.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from ai import AiClient  # noqa: E402

from ..models import Draft, Product, Shop, User
from . import dedup, pipeline, products as catalogue, sources, templates
from .fact_bundle import FactBundle
from .shop_client import shop_api, shop_defaults

# A product listed in several shops must not read like the same listing
# reworded: the platform folds those into one repeat-listing group and shows
# only one of them.
ANGLES: tuple[str, ...] = (
    "",
    "emphasise the buyer's use case and the setting the goods are used in",
    "emphasise material, construction and durability",
    "emphasise packaging, order sizes and what a reseller gets",
    "emphasise who it suits and which problem it solves for them",
)


def build_draft_for_shop(
    db: Session,
    user: User,
    shop: Shop,
    product: Product,
    *,
    price: str = "",
    moq: str = "",
    ai: AiClient | None = None,
    angle: str = "",
    batch_id: str = "",
    forced_category_id: str = "",
    seed_values: dict[str, Any] | None = None,
    provided_sources: dict[str, str] | None = None,
    extra_defaults: dict[str, Any] | None = None,
    fact_bundle: FactBundle | None = None,
) -> Draft:
    api = shop_api(shop)
    defaults = shop_defaults(shop)
    images = catalogue.images_of(db, product)
    bank, errors = catalogue.ensure_photobank(db, api, shop, images)

    final_price = price or product.price
    final_moq = moq or product.moq

    result = pipeline.build_draft(
        db,
        api,
        shop,
        understanding=catalogue.understanding_of(product),
        images=bank,
        price=final_price,
        moq=final_moq,
        defaults=defaults,
        ai=ai,
        forced_category_id=forced_category_id,
        language=str(defaults.get("language") or "en_US"),
        copy_angle=angle,
        extra_defaults=extra_defaults,
        fact_bundle=fact_bundle,
    )
    field_sources = sources.infer_initial(result.values, provided_sources)
    for path, payload in (result.ai.get("evidence") or {}).items():
        if path and path not in field_sources:
            field_sources[path] = str(payload.get("source") or "excel")
    if seed_values:
        result.values, field_sources = sources.apply_incoming(result.values, seed_values, field_sources, "excel")
        if seed_values.get("productTitle"):
            result.title = str(seed_values["productTitle"])
    if result.category_id:
        before = dict(result.values)
        filled = templates.apply_to_values(db, shop.id, result.category_id, result.values)
        if filled != result.values:
            field_sources = sources.mark_template_fills(before, filled, field_sources)
            result.values = filled
            result.ai["template_applied"] = True

    for message in errors:
        result.add_issue("scImages", "产品图片", "red", f"图片没能进图片银行：{message}")
        result.status = "red"
    if not bank:
        result.add_issue("scImages", "产品图片", "red", "没有可用的图片，发不了品")
        result.status = "red"

    draft = Draft(user_id=user.id, shop_id=shop.id, product_id=product.id, batch_id=batch_id)
    db.add(draft)
    _apply(draft, result, sku=product.sku, price=final_price, moq=final_moq, bank=bank, field_sources=field_sources)
    db.commit()

    # Needs to be committed before it can be compared against its siblings.
    risk = dedup.check(db, draft)
    if risk is not None:
        issues = list(result.issues) + [risk.as_issue()]
        draft.issues_json = json.dumps(issues, ensure_ascii=False)
        draft.status = pipeline.status_of(issues)
        db.commit()
    return draft


def failed_draft(db: Session, user_id: str, shop_id: str, product: Product | None, batch_id: str, error: str) -> None:
    """Record why one pair could not be drafted, instead of losing it."""
    db.add(
        Draft(
            user_id=user_id,
            shop_id=shop_id,
            product_id=product.id if product else "",
            batch_id=batch_id,
            sku=product.sku if product else "",
            status="red",
            issues_json=json.dumps(
                [{"field_id": "ai", "field_name": "成稿", "level": "red", "message": error[:300], "path": "ai"}],
                ensure_ascii=False,
            ),
        )
    )
    db.commit()


def _apply(
    draft: Draft,
    result: pipeline.DraftResult,
    *,
    sku: str,
    price: str,
    moq: str,
    bank: list[Any],
    field_sources: dict[str, str] | None = None,
) -> None:
    draft.sku = sku
    draft.price = price
    draft.moq = moq
    draft.title = result.title
    draft.category_id = result.category_id
    draft.category_name = result.category_name
    draft.category_confidence = result.category_confidence
    draft.category_candidates_json = json.dumps(result.category_candidates, ensure_ascii=False)
    draft.values_json = json.dumps(result.values, ensure_ascii=False)
    draft.images_json = json.dumps([item.as_dict() for item in bank], ensure_ascii=False)
    draft.ai_json = json.dumps(result.ai, ensure_ascii=False)
    draft.issues_json = json.dumps(result.issues, ensure_ascii=False)
    draft.sources_json = sources.dump(field_sources or sources.infer_initial(result.values))
    draft.status = result.status
    draft.updated_at = datetime.utcnow()
