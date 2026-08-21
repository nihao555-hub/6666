"""Confirm publish / render / photobank path names."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gop_client import GopClient, GopError


def try_call(client: GopClient, path: str, biz: dict) -> None:
    try:
        payload = client.execute(path, biz)
        text = json.dumps(payload, ensure_ascii=False, default=str)[:220]
        print(f"OK  {path} -> {text}")
    except GopError as exc:
        print(f"ERR {path} -> {exc.code} {exc.msg}")


def main() -> int:
    client = GopClient.from_env()
    cat_id = 21110712
    product_id = 10000046695776
    calls = [
        ("/icbu/product/schema/add", {"cat_id": cat_id, "xml": "<itemParam/>"}),
        ("/icbu/product/schema/add", {"add_request": {"cat_id": cat_id, "xml": "<itemParam/>"}}),
        ("/alibaba/icbu/product/schema/add/draft", {"cat_id": cat_id, "xml": "<itemParam/>"}),
        ("/icbu/product/schema/add/draft", {"cat_id": cat_id, "xml": "<itemParam/>"}),
        ("/alibaba/icbu/product/schema/add.draft", {"cat_id": cat_id}),
        ("/icbu/product/schema/update", {"cat_id": cat_id, "product_id": product_id}),
        ("/alibaba/icbu/product/schema/update", {"cat_id": cat_id, "product_id": product_id}),
        (
            "/icbu/product/schema/render",
            {"render_request": {"cat_id": cat_id, "product_id": product_id, "language": "zh"}},
        ),
        (
            "/icbu/product/photobank/list",
            {"groupId": -1, "current_page": 1, "page_size": 2},
        ),
        (
            "/icbu/product/photobank/list",
            {"groupId": 0, "currentPage": 1, "pageSize": 2},
        ),
        ("/alibaba/icbu/product/batch/update/display", {"new_display": "on", "product_id_list": str(product_id)}),
        ("/icbu/product/list", {"current_page": 1, "page_size": 1}),
    ]
    for path, biz in calls:
        try_call(client, path, biz)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
