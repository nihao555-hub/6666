# 用户流程（AI 少填 + 官方 Schema 发品）

原则：用户只提供机器推不出来的东西。类目、属性、英文标题、关键词、详情、图片银行、物流默认值都由系统和 AI 补。人只审红黄项和价格。

旧接口 `alibaba.icbu.product.add` 已不对新商家开放。发布必须走 Schema：

`schema.get` 拿规则 XML → 填 `itemParam` → `schema.add` 提交。

行业公理（领星）：**草稿 = 商品库（SPU）+ 刊登模板**。模板只填空，从不覆盖手填或已经填过的值。标题、图片、价格不是模板字段。

## 用户看见的几屏

```text
1. 店铺     授权自己的店，填一次产地 / 单位 / 物流 / 样品
2. 投料     拖图 + 货号 / 价格 / MOQ（同时写入商品库）
3. 商品库   图和识别结果只存一次；勾商品 × 勾店铺，一键铺多店
4. 模板     按店铺 + 叶子类目固化经营字段，只填空不覆盖
5. 审稿     只展开红黄项，绿项折叠；可看全部店铺
6. 队列     发布中 / 成功 / 失败可改再发
```

不要做成阿里后台的 40 字段表单。

## 完整链路

| 步 | 谁做 | 用户填什么 | 官方接口 |
|---|---|---|---|
| 1 授权店铺 | 用户点一次 | 官方 OAuth 确认，不交密码 | `openapi-auth.alibaba.com` → `/auth/token/create` |
| 2 店铺默认 | 用户填一次 | 询盘/一口价、币种、港口、付款、交期、运费模板、包装 | `product.group.get`；运费模板来自 schema 选项 |
| 3 入库 / 投料 | 用户每条做 | **图**；建议货号、FOB/售价、MOQ | 无（图先进本地商品库） |
| 4 看图理解 | AI，每个 SPU 一次 | 无 | 无（多模态模型） |
| 5 铺到店铺 | 用户勾选 | 选哪些店；可选差异化文案 | 每店各自 `/alibaba/icbu/photobank/upload` |
| 6 预测叶子类目 | AI，低置信度才问 | 偶尔选一下类目 | `/icbu/product/category/get` + `schema.get` |
| 7 拉发布规则 | 系统 | 无 | `/alibaba/icbu/product/schema/get` |
| 8 属性对齐 | AI，对不上标红 | 点选对不上的属性 | 无（对 schema option） |
| 9 写英文内容 | AI | 无；多店时换卖点角度 | 无，但必须过 schema 规则 |
| 10 套模板 | 系统 | 无 | 只填空，不覆盖标题/图/价 |
| 11 审稿 | 用户 | 确认红黄项，核对价格/MOQ | 无 |
| 12 排队发布 | 系统 | 点发布 | `/icbu/product/schema/add` 或 `schema.add/draft` |
| 13 在线商品 | 只读 | 看已上架 | `schema.render` / `product.list` / `product.get` |

## 用户每条商品最少填什么

必给：1～6 张图。  
建议给：货号、价格、MOQ。  
可以不给：标题、关键词、类目、属性、详情、港口、付款、交期、运费模板。

价格和 MOQ 是生意决策，AI 不代填。没有图就无法识别，也发不了品。

多店时图只丢一次。商品库勾店铺铺货，不会对每个店重新看图。

## Schema 字段怎么分

店铺默认 / 刊登模板（填一次就套用，只填空）：

- `market` 询盘=2 / 一口价=1
- `priceUnit` `paymentMethod` `port` `ladderPeriod`
- `shippingTemplateId` `pkgMeasure` `pkgWeight`
- `logisticsMode` `logisticsProperty`
- `origin` `marketSample`

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

平台按「标题 + 属性 + 图片」打重铺。同一 SPU 铺到第二家店起会换文案角度，并在提交前做本地重铺预检。

## 现在做到哪

做到第 12 步：授权 → 默认 → 入库/投料 → 商品库铺多店 → AI 成稿 → 模板填空 → 审红项 → `schema.add` 发询盘品。

还没做：Excel 探测导入、一口价 SKU 笛卡尔积、定时发布、子账号角色、字段级 source（防重新生成覆盖手改）、经营大类购买向导。
