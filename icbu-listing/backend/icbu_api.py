"""ICBU methods used by the AI listing flow.

Old `alibaba.icbu.product.add` is closed to new sellers.
New products must go through the schema APIs.
"""

from __future__ import annotations

from typing import Any

from top_client import TopClient

# First-wave APIs. Keep this list short and mapped to user-visible steps.
METHODS = {
    "oauth_exchange": "taobao.top.auth.token.create",
    "oauth_refresh": "taobao.top.auth.token.refresh",
    "category_tree": "alibaba.icbu.category.get.new",
    "schema_get": "alibaba.icbu.product.schema.get",
    "schema_add": "alibaba.icbu.product.schema.add",
    "schema_render": "alibaba.icbu.product.schema.render",
    "schema_update": "alibaba.icbu.product.schema.update",
    "photobank_upload": "alibaba.icbu.photobank.upload",
    "photobank_list": "alibaba.icbu.photobank.list",
    "product_group_get": "alibaba.icbu.product.group.get",
    "shipping_templates": "alibaba.wholesale.shippingline.template.list",
    "product_list": "alibaba.icbu.product.list",
    "batch_display": "alibaba.icbu.product.batch.update.display",
}


class IcbuApi:
    def __init__(self, client: TopClient) -> None:
        self.client = client

    def exchange_code(self, code: str) -> dict[str, Any]:
        return self.client.execute(METHODS["oauth_exchange"], {"code": code}, session=None)

    def category_tree(self, language: str = "zh") -> dict[str, Any]:
        return self.client.execute(METHODS["category_tree"], {"language": language})

    def schema_get(self, cat_id: int, language: str = "zh") -> dict[str, Any]:
        return self.client.execute(
            METHODS["schema_get"],
            {"param_product_top_publish_request": {"cat_id": cat_id, "language": language}},
        )

    def schema_add(self, cat_id: int, xml: str, language: str = "en_US") -> dict[str, Any]:
        return self.client.execute(
            METHODS["schema_add"],
            {
                "param_product_top_publish_request": {
                    "cat_id": cat_id,
                    "language": language,
                    "xml": xml,
                }
            },
        )

    def schema_render(self, cat_id: int, product_id: int, language: str = "zh") -> dict[str, Any]:
        return self.client.execute(
            METHODS["schema_render"],
            {
                "param_product_top_publish_request": {
                    "cat_id": cat_id,
                    "product_id": product_id,
                    "language": language,
                }
            },
        )

    def upload_image(self, file_name: str, image_bytes: bytes, group_id: str | None = None) -> dict[str, Any]:
        biz = {"file_name": file_name}
        if group_id:
            biz["group_id"] = group_id
        return self.client.execute(
            METHODS["photobank_upload"],
            biz,
            files={"image_bytes": image_bytes},
        )

    def list_images(self, current_page: int = 1, page_size: int = 20) -> dict[str, Any]:
        return self.client.execute(
            METHODS["photobank_list"],
            {
                "current_page": current_page,
                "page_size": page_size,
                "location_type": "ALL_GROUP",
            },
        )

    def product_groups(self) -> dict[str, Any]:
        return self.client.execute(METHODS["product_group_get"], {})

    def shipping_templates(self) -> dict[str, Any]:
        return self.client.execute(METHODS["shipping_templates"], {})

    def list_products(self, current_page: int = 1, page_size: int = 20) -> dict[str, Any]:
        return self.client.execute(
            METHODS["product_list"],
            {"current_page": current_page, "page_size": page_size},
        )
