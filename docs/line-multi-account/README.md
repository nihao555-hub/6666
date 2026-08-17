# LINE 官方账号操作说明

**图文版：** [index.html](index.html)

给运营用：在 LINE 后台建号、拿密钥、填 Webhook。截图都是 [LINE 官方文档](https://developers.line.biz/en/docs/messaging-api/getting-started/) 原图整张，只加了红框。

每个账号做三件事：

1. **Basic settings** 复制 Channel secret  
2. **Messaging API** 页点 Issue，复制 Channel access token  
3. 同一页填写 Webhook URL（`/webhook/acc1` … `/webhook/acc5`），打开 Use webhook，再 Verify  

5 个号做 5 遍。Role 必须是 Administrator。5 个号选同一个 Provider。
