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
| 正式发布 | `/icbu/product/schema/add` | `publish_request` | 路径有效；2026-08-23 克隆在线品 raw 调用成功 |
| 发官方草稿 | `/icbu/product/schema/add/draft` | `param_product_top_publish_request` | 路径有效；2026-08-23 实测 product_id=11000037689425 |

## 这个应用没有开通的接口

以下路径一律返回 `InvalidApiPath`，说明不在当前 AppKey 的权限范围内，要去开放平台单独申请：

- 改商品：`schema/update`、`product/update`（各种前缀都试过）
- 上下架：`product/batch/update/display`、`product/display/update`、`product/expire`
- 运费模板列表：`wholesale/shippingline/template/list`
- 图片分组：`photobank/group/list`

影响：「在线商品」页目前只能看，不能改价和上下架。

## 店铺默认值：能拉的别让用户填

`schema.get` 一次就把这些选项带回来了，所以「店铺默认」表单全是下拉，不是手打。
以彩铅类目 `21110712` 实测：

| 默认项 | schema 里的位置 | 实拉到 |
|---|---|---|
| 运费模板 | `shippingTemplate.shippingTemplateId` | 5 个，**是这家店自己的**：智能运费模板 / retails / 粉饼 / 画笔运费 / 买卖双方协商物流 |
| 计量单位 | `priceUnit` | 92 个 |
| 产地 | `icbuCatProp` 里名字含 Origin 的那个属性 | 257 个国家 |
| 物流属性 | `logisticsProperty` | 45 个，多选 |
| 样品服务 | `marketSample` | 2 个 |
| 售卖方式 / 定价方式 | `saleType` / `scPrice` | 2 个 / 3 个 |
| 箱规 | `boxPackaging` | 300 个 |

运费模板尤其别手填：那是 `2041723009` 这种店内 ID，用户不可能知道。

**付款方式、出运港口、market 在这个类目根本不存在。** 表单里问了也白问，发布时会被静默丢掉，所以现在按类目标成「官方没有这个字段」。

选项名会随语言变（同一个值 zh 返回「普货」、en_US 返回「Ordinary goods」），
所以默认值一律存官方 value（`general_cargo_0`），只把展示名另存一份快照给列表页看。

`productQuality` 在 `schema.get` 和 `schema.render` 里都只有桶名，没有分值，
`productQuality_score` 的 name 恒为 `0`。官方评分读不到，仍然只能本地预估。

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
