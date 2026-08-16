"""从环境变量加载最多 5 个 LINE 账号的密钥。"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Account:
    slug: str
    channel_secret: str
    channel_token: str
    display_name: str


def _load_one(n: int) -> Account | None:
    secret = os.getenv(f"ACC{n}_CHANNEL_SECRET", "").strip()
    token = os.getenv(f"ACC{n}_CHANNEL_TOKEN", "").strip()
    if not secret or not token:
        return None
    name = os.getenv(f"ACC{n}_NAME", f"acc{n}").strip() or f"acc{n}"
    return Account(slug=f"acc{n}", channel_secret=secret, channel_token=token, display_name=name)


def load_accounts() -> dict[str, Account]:
    accounts = {}
    for n in range(1, 6):
        acc = _load_one(n)
        if acc:
            accounts[acc.slug] = acc
    if not accounts:
        raise RuntimeError(
            "没有加载到任何账号。请至少设置 ACC1_CHANNEL_SECRET 和 ACC1_CHANNEL_TOKEN。"
        )
    return accounts
