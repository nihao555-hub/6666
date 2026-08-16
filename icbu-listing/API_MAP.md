# 已用真实店铺 token 探通的 GOP 接口

网关：`https://openapi-api.alibaba.com/rest`  
签名：`HMAC-SHA256(secret, api_path + 排序参数)`  
授权：`access_token`，请求头 `X-Protocol: GOP`

## 可用

| 用途 | Path | 必填参数 | 状态 |
|---|---|---|---|
| 类目树 | `/icbu/product/category/get` | `cat_id`（`0` 是根） | 已通，返回 `name` `cn_name` `level` `leaf_category` `child_ids` `parent_ids` |
| 商品列表 | `/alibaba/icbu/product/list` | `current_page` `page_size` `filter_type` | 已通，店铺 1227 条 |
| 商品详情 | `/icbu/product/get` | `product_get_request.productId` | 已通 |
| 发布规则 | `/alibaba/icbu/product/schema/get` | 顶层 `cat_id` `language` | 已通，彩铅类目 46 个顶层字段 |
| 回读已有品 | `/icbu/product/schema/render` | `render_request.{cat_id,product_id,language}` | 已通 |
| 图片上传 | `/alibaba/icbu/photobank/upload` | `file_name` `image_bytes` | 已通，返回 `file_id` + `photobank_url` |
| 图片列表 | `/icbu/product/photobank/list` | `groupId` `currentPage` `pageSize` | 已通 |
| 商品分组 | `/alibaba/icbu/product/group/get` | `group_id=-1` 拿根分组 | 已通 |
| 正式发布 | `/icbu/product/schema/add` | `publish_request` | 路径有效（参数校验已触发），尚未发真品 |
| 发官方草稿 | `/icbu/product/schema/add/draft` | `param_product_top_publish_request` | 路径有效，尚未发真品 |

## 这个应用没有开通的接口

以下路径一律返回 `InvalidApiPath`，说明不在当前 AppKey 的权限范围内，要去开放平台单独申请：

- 改商品：`schema/update`、`product/update`（各种前缀都试过）
- 上下架：`product/batch/update/display`、`product/display/update`、`product/expire`
- 运费模板列表：`wholesale/shippingline/template/list`
- 图片分组：`photobank/group/list`

影响：「在线商品」页目前只能看，不能改价和上下架。

## 坑

- `cat_id` 不要包进 `param_product_top_publish_request` 去调 `schema.get`，会报缺参。
- `/alibaba/icbu/category/get/new` 在这个网关无效，类目只能用 `/icbu/product/category/get`。
- 运费模板不需要单独接口：`schema.get` 返回的 `shippingTemplate.shippingTemplateId` 里就带着该店铺的模板选项。
- 旧 TOP 的 `alibaba.icbu.product.add` 不要用，已不对新商家开放。

## schema 的结构（最容易写错的地方）

规则文档里，`complex` / `multiComplex` 的子字段定义在 `<fields>` 里，但**值不写在那**。
回读一条线上商品可以看到，值放在 `<complex-value>`（单个）和 `<complex-values>`（多个）里：

```xml
<field id="scImages" type="complex">
  <complex-value>
    <field id="scImages_0" type="input">
      <value fileFlag="no" fileId="30038322709">//sc04.alicdn.com/kf/xxx.png</value>
    </field>
  </complex-value>
  <fields><!-- 这里只是规则定义 --></fields>
</field>
```

`backend/schema.py` 按这个结构生成 `itemParam`，`tests/test_schema_engine.py` 锁住了这个行为。
