"""Category-level market golden references for image generation.

Tries to pull live on-platform listings in the same leaf category (when the
gateway exposes category search), ranks them by listing-quality signals, and
returns composition/style hints for plan_stack. Seller product photos always
win as identity references; market golden URLs are style-only fallbacks.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Mapping, Sequence

from icbu_api import IcbuApi  # noqa: E402
from schema import extract_values  # noqa: E402

from .clone import images_from_values, render_xml
from .ecosystem_brief import INQUIRY_TERMS, SPAM_PHRASES, _listing_example_score, _subject_score
from .ecom_skill import clean_reference_urls
from .image_templates import pick_family

logger = logging.getLogger(__name__)

_CACHE_SECONDS = 30 * 60
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}

_BEST_GROUP = re.compile(r"best\s*seller|hot|top|爆款|热销", re.I)


def _listing_products(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    nested = result.get("product_list") if isinstance(result.get("product_list"), dict) else {}
    products = result.get("products")
    if not isinstance(products, list):
        nested_products = nested.get("products")
        products = nested_products if isinstance(nested_products, list) else []
    if not isinstance(products, list):
        products = []
    total = result.get("total_item") or nested.get("total_item") or len(products)
    return [item for item in products if isinstance(item, Mapping)], int(total or 0)


def _score_listing_summary(item: Mapping[str, Any], *, category_id: str) -> int:
    subject = str(item.get("subject") or item.get("title") or "").strip()
    if not subject:
        return 0
    cid = str(item.get("category_id") or "")
    category_match = not category_id or cid == str(category_id)
    score = _subject_score(subject, category_match=category_match)
    group = str(item.get("group_name") or "")
    if _BEST_GROUP.search(group):
        score += 18
    if str(item.get("display") or "").upper() == "Y":
        score += 8
    if item.get("is_rts"):
        score += 4
    lower = subject.lower()
    if any(term in lower for term in INQUIRY_TERMS):
        score += 10
    if any(phrase in lower for phrase in SPAM_PHRASES):
        score -= 12
    return score


def _detail_urls(values: Mapping[str, Any]) -> list[str]:
    urls: list[str] = []
    for image in images_from_values(dict(values)):
        url = str(getattr(image, "url", "") or "").strip()
        if url.startswith(("http://", "https://")):
            urls.append(url)
    return urls


def _try_render_listing(
    api: IcbuApi,
    *,
    category_id: str,
    product_id: str,
    subject: str,
    language: str,
) -> dict[str, Any] | None:
    try:
        xml = render_xml(api, category_id, product_id, language)
        values = extract_values(xml) if xml else {}
    except Exception:
        values = {}
    if values:
        score = _listing_example_score(values, subject=subject)
        urls = _detail_urls(values)
        if score >= 30 or urls:
            return {
                "product_id": product_id,
                "title": str(values.get("productTitle") or subject or "").strip(),
                "image_urls": urls[:6],
                "quality_score": score,
                "source": "platform_render",
            }
    return None


def search_category_listings(
    api: IcbuApi,
    *,
    category_id: str,
    subject: str = "",
    page_size: int = 20,
) -> list[dict[str, Any]]:
    """Best-effort same-category listing search (platform when gateway allows)."""
    if not category_id:
        return []
    queries: list[dict[str, Any]] = [
        {"category_id": int(category_id), "subject": subject or "", "language": "ENGLISH"},
        {"category_id": int(category_id), "language": "ENGLISH"},
    ]
    if subject:
        queries.append({"subject": subject, "language": "ENGLISH"})
    seen: set[str] = set()
    ranked: list[tuple[int, dict[str, Any]]] = []
    for params in queries:
        try:
            payload = api.search_products(
                category_id=params.get("category_id"),
                subject=str(params.get("subject") or ""),
                current_page=1,
                page_size=page_size,
                language=str(params.get("language") or "ENGLISH"),
            )
        except Exception as exc:
            logger.debug("market golden search skipped: %s", exc)
            continue
        products, _ = _listing_products(payload if isinstance(payload, dict) else {})
        for item in products:
            pid = str(item.get("product_id") or item.get("id") or "").strip()
            if not pid or pid in seen:
                continue
            cid = str(item.get("category_id") or "")
            if cid and cid != str(category_id):
                continue
            seen.add(pid)
            score = _score_listing_summary(item, category_id=category_id)
            ranked.append(
                (
                    score,
                    {
                        "product_id": pid,
                        "category_id": cid or category_id,
                        "title": str(item.get("subject") or "").strip(),
                        "pc_detail_url": str(item.get("pc_detail_url") or ""),
                        "group_name": str(item.get("group_name") or ""),
                        "pref_score": score,
                        "source": "platform_search",
                    },
                )
            )
        if ranked:
            break
    ranked.sort(key=lambda row: (-row[0], row[1].get("title") or ""))
    return [item for _, item in ranked[:page_size]]


def fetch_category_golden(
    api: IcbuApi,
    *,
    category_id: str,
    category_name: str = "",
    product_name: str = "",
    language: str = "en_US",
    limit: int = 3,
    render_limit: int = 6,
) -> dict[str, Any]:
    """Live golden listings for a leaf category + conversion slot DNA."""
    cache_key = f"{category_id}:{product_name[:40]}"
    cached = _CACHE.get(cache_key)
    if cached and time.time() - cached[0] < _CACHE_SECONDS:
        return cached[1]

    family = pick_family(product_name or category_name, category_name)
    candidates = search_category_listings(
        api,
        category_id=category_id,
        subject=product_name or category_name,
        page_size=max(render_limit, limit * 3),
    )
    enriched: list[dict[str, Any]] = []
    for candidate in candidates[:render_limit]:
        pid = str(candidate.get("product_id") or "")
        if not pid:
            continue
        detail = _try_render_listing(
            api,
            category_id=category_id,
            product_id=pid,
            subject=str(candidate.get("title") or ""),
            language=language,
        )
        if detail:
            merged = {**candidate, **detail}
            merged["quality_score"] = max(
                int(candidate.get("pref_score") or 0),
                int(detail.get("quality_score") or 0),
            )
            enriched.append(merged)
        elif int(candidate.get("pref_score") or 0) >= 20:
            enriched.append(dict(candidate))

    enriched.sort(key=lambda row: int(row.get("quality_score") or row.get("pref_score") or 0), reverse=True)
    top = enriched[:limit]
    style_urls: list[str] = []
    for item in top:
        for url in item.get("image_urls") or []:
            if url not in style_urls:
                style_urls.append(url)
            if len(style_urls) >= 2:
                break
        if len(style_urls) >= 2:
            break

    payload = {
        "category_id": category_id,
        "category_name": category_name,
        "source": "platform_category_search" if top else "category_conversion_dna",
        "listings": top,
        "style_reference_urls": clean_reference_urls(style_urls),
        "slot_priorities": [slot.name for slot in family.slots[:6]],
        "family": family.as_dict(),
        "note": (
            "Ranked by on-platform listing quality signals (title, completeness, active display). "
            "Style/composition reference only — never copy SKU identity."
        ),
    }
    _CACHE[cache_key] = (time.time(), payload)
    return payload


def apply_to_plan(plan: dict[str, Any], golden: Mapping[str, Any] | None) -> dict[str, Any]:
    """Merge market golden hints into an image plan stack."""
    if not golden:
        return plan
    out = dict(plan)
    seller_refs = list(out.get("reference_urls") or [])
    style_refs = [url for url in (golden.get("style_reference_urls") or []) if url]
    if not seller_refs and style_refs:
        out["style_reference_urls"] = style_refs[:2]
        out["reference_urls"] = style_refs[:1]
    out["market_golden"] = {
        "source": golden.get("source"),
        "listings": [
            {
                "title": item.get("title"),
                "quality_score": item.get("quality_score") or item.get("pref_score"),
                "image_count": len(item.get("image_urls") or []),
            }
            for item in (golden.get("listings") or [])[:3]
            if isinstance(item, Mapping)
        ],
        "slot_priorities": golden.get("slot_priorities") or [],
    }
    market_line = (
        "MARKET GOLDEN: match high-converting wholesale slot composition for this category "
        "(white main, detail macro, lifestyle, carton/MOQ, OEM). "
        "Use market references for layout/lighting only; keep the seller SKU identity."
    )
    if golden.get("listings"):
        titles = [str(item.get("title") or "") for item in golden.get("listings") or [] if item.get("title")][:2]
        if titles:
            market_line += " Top category listings emphasize: " + "; ".join(titles) + "."
    for slot in out.get("slots") or []:
        if not isinstance(slot, dict):
            continue
        prompt = str(slot.get("prompt") or "")
        if market_line not in prompt:
            slot["prompt"] = f"{prompt}\n{market_line}"
    out["platform_note"] = str(out.get("platform_note") or "") + " 出图参考同品类高转化布局（仅构图，不抄 SKU）。"
    return out
