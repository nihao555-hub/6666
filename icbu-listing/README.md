# Auto Shoper · 阿里国际站多租户批量上品

每个用户自己注册账号、自己授权自己的国际站店铺，一个账号可以绑多个店。平台只持有 AppKey/AppSecret，店铺 `access_token` 加密后按租户隔离存储。

用户每条商品只提供机器推不出来的东西：**图 + 价格 + 起订量**。类目、类目属性、英文标题、关键词、详情、图片银行、物流默认值由系统和 AI 补齐，人只审红黄项。

## 现在能跑通什么

已用真实店铺（1227 条在线商品）验证：

- 注册登录、多租户隔离、一个账号绑多个店铺
- 店铺默认设置（产地、计量单位、物流属性、样品、运费模板）
- 拉真实类目树、真实发布规则 schema、真实在线商品、真实图片银行
- 商品库（SPU）：图和识别结果只存一次，和店铺无关
- 投料 → 同时入库 → AI 看图 → 定叶子类目 → 属性对齐官方选项 → 生成英文标题/关键词/详情 → 图片进图片银行 → 产出通过校验的 `itemParam`
- 一键多店铺铺货：勾商品 × 勾店铺；第二家店起换文案角度，降低重铺风险
- 按卖家当前情况推荐最快路径（新店丢图 / 老店复制 / Excel / 先审红项）
- Excel 导入：领星资料库 / 店小秘按模板 / 马帮导出 / 阿里官方类目表 / 智能探测
- 从在线商品复制：回读 schema.render，保留已过审属性，AI 换标题防重铺
- 字段来源：手改和 Excel 填过的值，重新成稿不会覆盖
- 刊登模板：按店铺 + 叶子类目固化经营字段，只填空不覆盖标题/图/价
- 提交前本地自检（必填、字节长度、正则、选项合法性）
- 没图时按类目生成 6 张国际站套图（白底主图 / 尺寸 / 细节 / 场景 / 外箱 / OEM），再填价格成稿；有实拍仍走上传
- 重复铺货风险预检
- 发布队列，失败原因翻成中文

`backend/smoke_draft.py` 可以把一张图跑到「将要提交的 XML」为止，不会真的发品。

## 目录

```text
icbu-listing/
  backend/            协议层，也能当脚本单独跑
    gop_client.py     新版 GOP 签名与网关
    icbu_api.py       ICBU 方法
    schema.py         规则解析 / itemParam 生成 / 本地校验
    ai.py             看图理解、类目候选、文案生成
    ping.py           拿环境变量探活
    smoke_draft.py    单图端到端演练（不发布）
  server/             多租户 FastAPI 服务
    routers/          auth / shops / products / templates / excel / listings / overview / image-templates
    services/         shop_client · catalog · pipeline · images · publisher · dedup
                      products · distribution · templates · sources · excel_import
                      image_templates · grsai_images · image_jobs
  webapp/             Vue 3 + Element Plus 控制台
  tests/
```

## 启动

```bash
cd icbu-listing
cp .env.example .env          # 填 AppKey / AppSecret / 模型 key，不要提交
python3 -m pip install -r backend/requirements.txt
cd webapp && npm install && npm run build && cd ..

set -a && source .env && set +a
python3 -m uvicorn server.main:app --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000`，用 `REGISTRATION_CODES` 里的注册码开一个租户。

前后端分开开发时：

```bash
python3 -m uvicorn server.main:app --reload --port 8000
cd webapp && npm run dev          # http://127.0.0.1:5173，已配 /api 代理
```

## 店铺授权

正式租户走官方 OAuth：`店铺授权 → 授权新店铺`。

`ALIBABA_OAUTH_REDIRECT_URI` 必须和开放平台控制台里登记的回调地址**完全一致**，并且指向本服务的 `/api/v1/alibaba/oauth/callback`，不能指向 alibaba.com。不一致时阿里会直接报 `Redirect uri does not match the callback url of the APP`。

本地调试可以用「用环境 token 接入」，把 `ALIBABA_ACCESS_TOKEN` 直接绑成一个店铺，跳过 OAuth。

## 发布模式

每个店铺有一个开关，默认 `只发草稿`：提交到官方草稿箱，不上架。跑顺了再切 `直接上架`。

## 测试

```bash
python3 -m unittest discover -s tests -v
```

不需要密钥，也不会打网络。

## 文档

- [`docs/guide/index.html`](docs/guide/index.html)：带截图批注的网页使用说明
- [`docs/使用说明.md`](docs/使用说明.md)：同一份的 Markdown 版
- `API_MAP.md`：实测通了哪些接口、哪些没权限、schema 的结构坑
- `USER_FLOW.md`：用户三屏和每步对应的官方接口
