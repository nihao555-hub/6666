#!/usr/bin/env python3
"""Verify Alibaba ICBU publish APIs with the configured shop token.

Clones an online listing (render → tweak title → submit). Tries the same
publisher.publish path the app uses; if local schema validation blocks, falls
back to a direct schema/add/draft call to confirm the platform accepts the payload.

    cd icbu-listing
    set -a && source .env && set +a
    python3 scripts/verify_publish_live.py
    python3 scripts/verify_publish_live.py --online
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from gop_client import GopClient, GopError  # noqa: E402
from icbu_api import IcbuApi  # noqa: E402
from schema import build_item_param, extract_values, parse_schema  # noqa: E402

from server.services import publisher  # noqa: E402


def _api() -> IcbuApi:
    client = GopClient.from_env()
    if not client.access_token:
        raise SystemExit("ALIBABA_ACCESS_TOKEN missing — authorize a shop first")
    return IcbuApi(client)


def _pick_product(api: IcbuApi) -> tuple[int, int]:
    listed = api.list_products(page_size=5)
    products = (listed.get("result") or {}).get("products") or []
    if not products:
        raise SystemExit("Shop has no online products to clone for publish test")
    sample = products[0]
    return int(sample["id"]), int(sample["category_id"])


def _unique_title(title: str) -> str:
    base = re.sub(r"\s+", " ", (title or "Auto Shoper verify").strip())[:120]
    stamp = str(int(time.time()))[-6:]
    return f"{base} verify-{stamp}"[:128]


def _raw_publish(api: IcbuApi, category_id: int, schema_xml: str, values: dict, *, mode: str, language: str) -> publisher.PublishOutcome:
    fields = parse_schema(schema_xml)
    xml = build_item_param(fields, values)
    if mode == "online":
        payload = api.schema_add(category_id, xml, language)
    else:
        payload = api.schema_add_draft(category_id, xml, language)
    return publisher.parse_publish_response(payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--online", action="store_true", help="Use schema/add instead of draft")
    parser.add_argument("--product-id", type=int, default=0)
    parser.add_argument("--category-id", type=int, default=0)
    args = parser.parse_args()

    api = _api()
    mode = "online" if args.online else "draft"
    language = "en_US"
    if args.product_id and args.category_id:
        product_id, category_id = args.product_id, args.category_id
    else:
        product_id, category_id = _pick_product(api)

    print(f"mode={mode} product_id={product_id} category_id={category_id}")

    rendered = api.schema_render(category_id, product_id, language=language)
    xml = ((rendered.get("result") or {}).get("data")) or ""
    if not xml:
        print("FAIL: schema.render returned empty xml", json.dumps(rendered, ensure_ascii=False)[:400])
        return 1

    schema_xml = api.schema_xml(category_id, language=language)
    values = extract_values(xml)
    if not values:
        print("FAIL: could not extract values from render xml")
        return 1
    values["productTitle"] = _unique_title(str(values.get("productTitle") or ""))

    outcome = publisher.publish(api, str(category_id), schema_xml, values, mode=mode, language=language)
    if outcome.ok:
        label = "live product" if mode == "online" else "official draft"
        print(json.dumps({"ok": True, "path": "publisher.publish", "product_id": outcome.product_id}, ensure_ascii=False))
        print(f"SUCCESS: {label} id={outcome.product_id}")
        return 0

    print("publisher.publish blocked:", outcome.error[:240])
    raw = _raw_publish(api, category_id, schema_xml, values, mode=mode, language=language)
    print(json.dumps({"ok": raw.ok, "path": "raw schema/add*", "product_id": raw.product_id, "error": raw.error}, ensure_ascii=False))
    if raw.ok:
        label = "live product" if mode == "online" else "official draft"
        print(f"SUCCESS (raw API): {label} id={raw.product_id}")
        print("NOTE: local validate_values may be stricter than Alibaba for cloned listings.")
        return 0
    print("FAIL:", raw.error)
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GopError as exc:
        print(f"GOP error: {exc.code} {exc.msg}")
        raise SystemExit(3) from exc
