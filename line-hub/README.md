# line-hub

一台服务器托管最多 5 个 LINE Official Account 的 webhook 服务。

完整图文教程（取密钥 + 公网 HTTPS 部署）：[docs/line-multi-account/README.md](../docs/line-multi-account/README.md)

```bash
cp .env.example .env   # 填入 5 套 SECRET / TOKEN 和 LINE_DOMAIN
docker compose up -d --build
```

本地：

```bash
pip install -r app/requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
pytest tests/test_signature.py -q
```
