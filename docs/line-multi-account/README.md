# 5 个 LINE 账号：取密钥并部署公网

**用浏览器看图文版：** [index.html](index.html)

每个号只要 2 个密钥 + 1 条 webhook。一台小 VPS 托管 5 个号。配套服务在 [`line-hub/`](../../line-hub/)。

## 每个号复制这两样

| 复制什么 | 在哪一页 | 填到哪里 |
|---|---|---|
| Channel secret | Basic settings | `ACC1_CHANNEL_SECRET` |
| Channel access token | Messaging API → Issue | `ACC1_CHANNEL_TOKEN` |

二号改成 `ACC2_…`，一直到 acc5。Webhook 分别是 `/webhook/acc1` … `/webhook/acc5`。

## 1. 拿密钥

1. [manager.line.biz](https://manager.line.biz/) 建 5 个官方账号。
2. 每个号：设置 → Messaging API → Enable。5 个号选**同一个 Provider**。
3. [developers.line.biz/console](https://developers.line.biz/console/) 点进对应 channel。
4. Basic settings 复制 **Channel secret**。
5. Messaging API 页点 **Issue**，复制 **token**。建议关掉自动回复。

重新 Issue 会让旧 token 立刻失效。

## 2. 先填 Webhook，先别 Verify

```
https://你的域名/webhook/acc1
https://你的域名/webhook/acc2
https://你的域名/webhook/acc3
https://你的域名/webhook/acc4
https://你的域名/webhook/acc5
```

必须 HTTPS，自签证书 LINE 不认。Use webhook 打开，Verify 等服务器起来再点。

## 3. 部署到公网

VPS（日本/新加坡更好）+ 域名 A 记录。放行 80/443。

```bash
sudo apt-get update
sudo apt-get install -y git docker.io docker-compose-v2
sudo usermod -aG docker "$USER"   # 重新登录一次

git clone <本仓库> && cd <仓库>/line-hub
cp .env.example .env
nano .env                         # 填 LINE_DOMAIN 和 5 套密钥

docker compose up -d --build
curl -I https://你的域名/healthz  # 要 200，且没有 SSL 报错
```

## 4. 回去点 Verify

5 个 channel 各点一次 Verify，出现 Success。手机给每个号发 ping，应回 `[客服N号] ping`。

## 不通就看这 4 条

| 现象 | 处理 |
|---|---|
| Verify 报证书错误 | 域名还没解析到这台机器，或 80/443 没放行 |
| Verify 403 | 这个号的 secret 贴错到另一个 ACC |
| Verify 成功但没回消息 | Use webhook 没打开，或自动回复还开着在抢答 |
| 发不出消息 401 | token 重新 Issue 过，把新的写进 `.env` 再 `docker compose up -d` |
