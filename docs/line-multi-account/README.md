# LINE 后台操作说明

图文版：[index.html](index.html)

按官方文档整理，截图均为官方原图：

- [Get started with the Messaging API](https://developers.line.biz/en/docs/messaging-api/getting-started/)
- [Build a bot](https://developers.line.biz/en/docs/messaging-api/building-bot/)
- [Channel access token](https://developers.line.biz/en/docs/basics/channel-access-token/)

## 密钥在哪拿

| 密钥 | 路径 |
|---|---|
| Channel secret | Developers Console → Provider → Messaging API channel → **Basic settings** → Channel secret |
| Channel access token | 同一 channel → **Messaging API** → Channel access token (long-lived) → **Issue** |

## 要改的设置

同一 channel 的 **Messaging API** 标签：Webhook URL 点 Edit 填入 → Update → Verify → 打开 Use webhook。建议关掉 Greeting / Auto-reply。
