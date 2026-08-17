"""不连外网的单元测试：验签算法 + 账号加载 + webhook 路由。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os

import pytest
from fastapi.testclient import TestClient

from app.signature import verify_signature


def _sign(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def test_verify_ok():
    body = b'{"events":[]}'
    assert verify_signature("s3cret", body, _sign("s3cret", body))


def test_verify_wrong_secret():
    body = b'{"events":[]}'
    assert not verify_signature("s3cret", body, _sign("other", body))


def test_verify_empty_signature():
    assert not verify_signature("s3cret", b"{}", "")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ACC1_CHANNEL_SECRET", "secret-one")
    monkeypatch.setenv("ACC1_CHANNEL_TOKEN", "token-one")
    monkeypatch.setenv("ACC1_NAME", "客服一号")
    monkeypatch.setenv("ACC2_CHANNEL_SECRET", "secret-two")
    monkeypatch.setenv("ACC2_CHANNEL_TOKEN", "token-two")
    monkeypatch.setenv("ACC2_NAME", "客服二号")
    # 清掉可能残留的 3~5
    for n in (3, 4, 5):
        monkeypatch.delenv(f"ACC{n}_CHANNEL_SECRET", raising=False)
        monkeypatch.delenv(f"ACC{n}_CHANNEL_TOKEN", raising=False)

    # 必须在设置 env 之后再 import / 重建 app
    from importlib import reload
    import app.config as config
    import app.main as main

    reload(config)
    reload(main)
    with TestClient(main.app) as c:
        yield c


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["accounts"] == ["acc1", "acc2"]


def test_unknown_account(client):
    r = client.post("/webhook/acc9", content=b"{}", headers={"X-Line-Signature": "x"})
    assert r.status_code == 404


def test_bad_signature_403(client):
    body = json.dumps({"events": []}).encode()
    r = client.post(
        "/webhook/acc1",
        content=body,
        headers={"X-Line-Signature": _sign("wrong", body), "Content-Type": "application/json"},
    )
    assert r.status_code == 403


def test_good_signature_200(client):
    body = json.dumps({"events": []}).encode()
    r = client.post(
        "/webhook/acc1",
        content=body,
        headers={"X-Line-Signature": _sign("secret-one", body), "Content-Type": "application/json"},
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_acc2_uses_its_own_secret(client):
    body = json.dumps({"events": []}).encode()
    # acc1 的 secret 签给 acc2 应该失败
    r = client.post(
        "/webhook/acc2",
        content=body,
        headers={"X-Line-Signature": _sign("secret-one", body), "Content-Type": "application/json"},
    )
    assert r.status_code == 403
    r = client.post(
        "/webhook/acc2",
        content=body,
        headers={"X-Line-Signature": _sign("secret-two", body), "Content-Type": "application/json"},
    )
    assert r.status_code == 200
