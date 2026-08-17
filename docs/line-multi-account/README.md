# 5 个 LINE 账号：取密钥并部署公网

**图文版：** [index.html](index.html)

截图都来自 [LINE 官方文档](https://developers.line.biz/en/docs/messaging-api/getting-started/)，只加了红框短批注。配套服务：[`line-hub/`](../../line-hub/)。

每个号复制 2 个密钥：

| 复制什么 | 在哪一页 | 填到 .env |
|---|---|---|
| Channel secret | Basic settings | `ACC1_CHANNEL_SECRET` |
| Channel access token | Messaging API → Issue | `ACC1_CHANNEL_TOKEN` |

Webhook：`/webhook/acc1` … `/webhook/acc5`。

1. [manager.line.biz](https://manager.line.biz/) 建 5 个号 → 每个号 Enable Messaging API（同一个 Provider）→ [Console](https://developers.line.biz/console/) 点进 channel，复制 secret / Issue token。
2. 先填 Webhook，先不 Verify。必须 HTTPS。
3. VPS + 域名，放行 80/443，`cd line-hub && cp .env.example .env && docker compose up -d --build`。
4. 回去点 Verify，发一条 ping。
