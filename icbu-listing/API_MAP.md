# 已用真实 token 探通的 GOP 接口

网关：`https://openapi-api.alibaba.com/rest`  
签名：`HMAC-SHA256(secret, api_path + 排序参数)`  
授权：`access_token`，请求头 `X-Protocol: GOP`

| 用途 | Path | 必填参数 | 状态 |
|---|---|---|---|
| 商品列表 | `/alibaba/icbu/product/list` | `current_page` `page_size` `filter_type` | 已通，店铺 1227 条 |
| 商品详情 | `/icbu/product/get` | `product_get_request.productId` | 已通 |
| 发布规则 | `/alibaba/icbu/product/schema/get` | 顶层 `cat_id` `language` | 已通 |
| 回读已有品 | `/icbu/product/schema/render` | `render_request.{cat_id,product_id,language}` | 已通 |
| 正式发布 | `/icbu/product/schema/add` | `publish_request` | 路径有效，未发真品 |
| 发草稿 | `/icbu/product/schema/add/draft` | `param_product_top_publish_request` | 路径有效，未发真品 |
| 增量更新 | `/icbu/product/schema/update` | `xml`（及商品 id） | 路径有效 |
| 图片上传 | `/alibaba/icbu/photobank/upload` | `file_name` `image_bytes` | 路径有效 |
| 图片列表 | `/icbu/product/photobank/list` | `groupId` `currentPage` `pageSize` | 已通 |
| 商品分组 | `/alibaba/icbu/product/group/get` | `group_id=-1` 拿根分组 | 已通 |

注意：

- 不要把 `cat_id` 再包进 `param_product_top_publish_request` 去调 `schema.get`，会报缺参。
- `/alibaba/icbu/category/get/new` 在这个网关上无效。类目先从已有商品的 `category_id` 或 schema 里拿。
- 旧 TOP 的 `alibaba.icbu.product.add` 不要用。
