"""ICBU methods on the new Alibaba.com GOP gateway.

Paths and parameter names were verified against a live shop token.
"""

from __future__ import annotations

from typing import Any

from gop_client import GopClient

METHODS = {
    "oauth_exchange": "/auth/token/create",
    "oauth_refresh": "/auth/token/refresh",
    "category_get": "/icbu/product/category/get",
    "schema_get": "/alibaba/icbu/product/schema/get",
    "schema_add": "/icbu/product/schema/add",
    "schema_add_draft": "/icbu/product/schema/add/draft",
    "schema_render": "/icbu/product/schema/render",
    "photobank_upload": "/alibaba/icbu/photobank/upload",
    "photobank_list": "/icbu/product/photobank/list",
    "product_group_get": "/alibaba/icbu/product/group/get",
    "product_list": "/alibaba/icbu/product/list",
    "product_get": "/icbu/product/get",
}


class IcbuApi:
    def __init__(self, client: GopClient) -> None:
        self.client = client

    def exchange_code(self, code: str) -> dict[str, Any]:
        return self.client.execute(METHODS["oauth_exchange"], {"code": code}, access_token=None)

    def get_category(self, cat_id: int | str) -> dict[str, Any]:
        """Category node: name, cn_name, level, leaf_category, child_ids, parent_ids.

        `cat_id=0` is the root. This is the only category endpoint this gateway
        exposes; `category.get.new` and the suggestion endpoints are not routed.
        """
        return self.client.execute(METHODS["category_get"], {"cat_id": int(cat_id)})

    def schema_get(self, cat_id: int, language: str = "zh") -> dict[str, Any]:
        return self.client.execute(METHODS["schema_get"], {"cat_id": cat_id, "language": language})

    def schema_xml(self, cat_id: int, language: str = "zh") -> str:
        payload = self.schema_get(cat_id, language)
        return ((payload.get("result") or {}).get("data")) or ""

    def schema_add(self, cat_id: int, xml: str, language: str = "en_US") -> dict[str, Any]:
        return self.client.execute(
            METHODS["schema_add"],
            {"publish_request": {"cat_id": cat_id, "language": language, "xml": xml}},
        )

    def schema_add_draft(self, cat_id: int, xml: str, language: str = "en_US") -> dict[str, Any]:
        return self.client.execute(
            METHODS["schema_add_draft"],
            {"param_product_top_publish_request": {"cat_id": cat_id, "language": language, "xml": xml}},
        )

    def schema_render(self, cat_id: int, product_id: int, language: str = "zh") -> dict[str, Any]:
        return self.client.execute(
            METHODS["schema_render"],
            {"render_request": {"cat_id": cat_id, "product_id": product_id, "language": language}},
        )

    def upload_image(self, file_name: str, image_bytes: bytes, group_id: str | None = None) -> dict[str, Any]:
        biz = {"file_name": file_name}
        if group_id:
            biz["group_id"] = group_id
        return self.client.execute(METHODS["photobank_upload"], biz, files={"image_bytes": image_bytes})

    def list_images(self, group_id: int = 0, current_page: int = 1, page_size: int = 20) -> dict[str, Any]:
        return self.client.execute(
            METHODS["photobank_list"],
            {"groupId": group_id, "currentPage": current_page, "pageSize": page_size},
        )

    def product_groups(self, group_id: int = -1) -> dict[str, Any]:
        return self.client.execute(METHODS["product_group_get"], {"group_id": group_id})

    def list_products(self, current_page: int = 1, page_size: int = 20, filter_type: str = "onSelling") -> dict[str, Any]:
        return self.client.execute(
            METHODS["product_list"],
            {"current_page": current_page, "page_size": page_size, "filter_type": filter_type},
        )

    def get_product(self, product_id: int | str) -> dict[str, Any]:
        return self.client.execute(
            METHODS["product_get"],
            {"product_get_request": {"productId": product_id}},
        )
