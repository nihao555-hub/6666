# 用户流程（AI 少填 + 官方 Schema 发品）

原则：用户只提供机器推不出来的东西。类目、属性、英文标题、关键词、详情、图片银行、物流默认值都由系统和 AI 补。人只审红黄项和价格。

旧接口 `alibaba.icbu.product.add` 已不对新商家开放。发布必须走 Schema：

`schema.get` 拿规则 XML → 填 `itemParam` → `schema.add` 提交。

## 用户看见的三屏

```text
1. 投料     拖图 + 货号/价格/MOQ（店铺默认只在第一次问）
2. 审稿     只展开红黄项，绿项折叠
3. 队列     发布中 / 成功 / 失败可改再发
```

不要做成阿里后台的 40 字段表单。

## 完整链路

| 步 | 谁做 | 用户填什么 | 官方接口 |
|---|---|---|---|
| 1 授权店铺 | 用户点一次 | 官方 OAuth 确认，不交密码 | `oauth.taobao.com` → `taobao.top.auth.token.create` |
| 2 店铺默认 | 用户填一次 | 询盘/一口价、币种、港口、付款、交期、运费模板、包装 | `product.group.get`、`shippingline.template.list` |
| 3 投料 | 用户每条做 | **图**；建议货号、FOB/售价、MOQ | 无 |
| 4 看图理解 | AI | 无 | 无（多模态模型） |
| 5 预测叶子类目 | AI，低置信度才问 | 偶尔选一下类目 | `alibaba.icbu.category.get.new` |
| 6 拉发布规则 | 系统 | 无 | `alibaba.icbu.product.schema.get` |
| 7 属性对齐 | AI，对不上标红 | 点选对不上的属性 | 无（对 schema option） |
| 8 写英文内容 | AI | 无 | 无，但必须过 schema 规则 |
| 9 图进图片银行 | 系统 | 无 | `alibaba.icbu.photobank.upload` |
| 10 审稿 | 用户 | 确认红黄项，核对价格/MOQ | 无 |
| 11 排队发布 | 系统 | 点发布 | `alibaba.icbu.product.schema.add` |
| 12 在线商品 | 第二期 | 改价、上下架 | `schema.render` / `schema.update` / `batch.update.display` |

## 用户每条商品最少填什么

必给：1～6 张图。  
建议给：货号、价格、MOQ。  
可以不给：标题、关键词、类目、属性、详情、港口、付款、交期、运费模板。

价格和 MOQ 是生意决策，AI 不代填。没有图就无法识别，也发不了品。

## Schema 字段怎么分

店铺默认（填一次就套用）：

- `market` 询盘=2 / 一口价=1
- `priceUnit` `paymentMethod` `port` `ladderPeriod`
- `shippingTemplateId` `pkgMeasure` `pkgWeight`
- `logisticsMode` `logisticsProperty`

AI 生成：

- `productTitle`（≤128 字节，禁中文/邮箱/HTML）
- `productKeywords`（1～3 个）
- `icbuCatProp`（必须对齐官方 option）
- `superText` / `productDescType`
- `scImages`（先 upload，再写 url + fileId）

用户每条确认：

- `fob` 或 `ladderPrice` / `scPrice`
- `minOrderQuantity`

## 审稿规则

- 绿 ≥0.85：自动采用，折叠
- 黄 0.6–0.85：预填，可略过
- 红 <0.6 或必填空：必须点一下

类目选错后面属性全废。前 20 条建议看一眼，同类目记住后不再问。

## 第一期做到哪

做到第 11 步：授权 → 默认 → 传图出价 → AI 成稿 → 审红项 → `schema.add` 发询盘品。

先不做一口价 SKU 笛卡尔积、多店复制、采集搬家。
