# 阿里国际站 AI 批量上品

目标：用户尽量少填，AI 按官方 Schema 自动成稿并发布。

## 为什么没有直接「下载官方 SDK 压缩包」

淘宝开放平台的完整 SDK **按应用权限在控制台生成**，不提供固定公网下载地址：

1. 打开 [open.taobao.com](https://open.taobao.com)
2. 开发 → 应用管理 → 你的国际站应用
3. SDK 下载 → 生成 Python / Java

公网 PyPI 的 `topsdk` 是淘宝客（联盟）包，里面没有 `alibaba.icbu.product.schema.*`，不能用。

官方文档同时允许按 [TOP 协议](https://developer.alibaba.com/docs/doc.htm?articleId=101617&docType=1) 自己封装 HTTP 调用。`backend/top_client.py` 就是这一层：签名、网关、session、图片上传。控制台 SDK 只是它上面的类型包装。

把控制台下好的压缩包放到 `vendor/official-sdk/` 即可，代码不用改。

## 目录

```text
icbu-listing/
  USER_FLOW.md          用户三屏和接口对照
  web/index.html        流程对照页
  backend/top_client.py 官方 TOP 协议客户端
  backend/icbu_api.py   发品用到的 ICBU 方法
  backend/schema.py     Schema XML 解析/回填
  backend/flow.py       流程步骤（和页面对齐）
  backend/ping.py       用环境变量探活
```

## 本地探活

```bash
cd icbu-listing
cp .env.example .env   # 填 APP_KEY / APP_SECRET，不要提交
set -a && source .env && set +a
python3 -m pip install -r backend/requirements.txt
python3 backend/ping.py
```

没有 `ALIBABA_SESSION_KEY` 时，`ping.py` 只打 `taobao.time.get` 验证密钥，并打印 OAuth 链接。

## 测试

```bash
python3 -m unittest discover -s icbu-listing/tests -v
```
