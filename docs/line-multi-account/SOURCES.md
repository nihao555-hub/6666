# 配图来源

本教程配图分两类，都只用于教学标注，不用于商业再分发。

## 1. LINE 官方文档截图（叠加中文步骤标注）

从 [LINE Developers 文档](https://developers.line.biz/) 下载原图，用 `tools/annotate.py` 加上红框和中文说明。版权归 LINE Corporation。

| 本教程文件 | 官方原图 URL |
|---|---|
| `images/01-oa-manager-accounts.png` | https://developers.line.biz/media/messaging-api/getting-started/oa-manager-list-en.png |
| `images/03-provider-create.png` | https://developers.line.biz/media/liff/getting-started/create-provider-en.png |
| `images/04-console-channels.png` | https://developers.line.biz/media/messaging-api/getting-started/console-home-en.png |
| `images/07-webhook-url.png` | https://developers.line.biz/media/messaging-api/build-bot/webhook-url-example-com.png |
| `images/08-webhook-verify.png` | https://developers.line.biz/media/news/webhook-url-verify-button.png |
| `images/09-webhook-redelivery.png` | https://developers.line.biz/media/messaging-api/receiving-messages/enable-webhook-redelivery-en.png |
| `images/12-ip-allowlist.png` | https://developers.line.biz/media/messaging-api/build-bot/security-settings-input-en.png |

对应官方文档：

- [Get started with the Messaging API](https://developers.line.biz/en/docs/messaging-api/getting-started/)
- [Build a bot](https://developers.line.biz/en/docs/messaging-api/building-bot/)
- [Channel access token](https://developers.line.biz/en/docs/basics/channel-access-token/)
- [Verify the webhook URL](https://developers.line.biz/en/docs/messaging-api/verify-webhook-url/)

## 2. 控制台示意图（HTML 渲染）

`images/02-*.png`、`05-*.png`、`06-*.png`、`10-*.png`、`11-*.png`、`13-*.png` 由 `tools/mockups/*.html` 渲染。这些不是登录后的真实控制台截图：LINE Developers Console 需要登录才能看到 Channel secret / Access token 页面，公开文档里也没有这两页的完整截图。示意图按官方控制台的字段名、标签页和按钮文案绘制，并标出你要点的位置。

重新生成全部配图：

```bash
python3 docs/line-multi-account/tools/annotate.py
bash docs/line-multi-account/tools/render_mockups.sh
```
