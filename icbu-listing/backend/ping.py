"""Probe the new GOP gateway with env credentials. Never prints secrets."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gop_client import GopClient, GopError
from icbu_api import IcbuApi
from schema import parse_schema, required_fields


def _brief(payload: object, limit: int = 360) -> str:
    text = json.dumps(payload, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + "..."


def main() -> int:
    try:
        client = GopClient.from_env()
    except ValueError as exc:
        print(f"missing credentials: {exc}")
        return 2

    print(f"gateway={client.gateway}")
    print(f"app_key={client.app_key[:3]}***")
    print(f"access_token={'set' if client.access_token else 'missing'}")

    if not client.access_token:
        print(client.authorize_link("http://127.0.0.1:8000/api/v1/alibaba/oauth/callback"))
        return 0

    api = IcbuApi(client)
    try:
        listed = api.list_products(page_size=1)
    except GopError as exc:
        print("product.list failed:", exc)
        return 1

    result = listed.get("result") or {}
    products = result.get("products") or []
    print(f"product.list ok: total_item={result.get('total_item')} sample={_brief(products[:1])}")
    if not products:
        return 0

    sample = products[0]
    cat_id = sample["category_id"]
    product_id = sample["id"]

    try:
        groups = api.product_groups(-1)
        print("product.group.get ok:", _brief(groups))
    except GopError as exc:
        print("product.group.get failed:", exc)

    try:
        images = api.list_images(group_id=0, page_size=2)
        print("photobank.list ok:", _brief(images))
    except GopError as exc:
        print("photobank.list failed:", exc)

    try:
        xml = api.schema_xml(cat_id, "zh")
        fields = parse_schema(xml)
        required = [f"{item.id}:{item.type}:{item.name}" for item in required_fields(fields) if item.id in {"productTitle", "scImages", "priceUnit", "scPrice", "saleType"}]
        print(f"schema.get ok: cat_id={cat_id} fields={len(fields)} highlight={required}")
    except GopError as exc:
        print("schema.get failed:", exc)
        return 1

    try:
        detail = api.get_product(product_id)
        print("product.get ok:", _brief(detail))
    except GopError as exc:
        print("product.get failed:", exc)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
