"""Ping TOP with current env credentials. Safe: only calls time.get / category tree."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow `python ping.py` from this folder.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from icbu_api import IcbuApi
from top_client import TopClient, TopError


def main() -> int:
    try:
        client = TopClient.from_env()
    except ValueError as exc:
        print(f"missing credentials: {exc}")
        print("set ALIBABA_APP_KEY and ALIBABA_APP_SECRET, then retry")
        return 2

    print(f"gateway={client.gateway}")
    print(f"app_key={client.app_key[:4]}***")
    print(f"session={'set' if client.session else 'missing (OAuth next)'}")

    try:
        clock = client.execute("taobao.time.get", {})
        print("time.get ok:", json.dumps(clock, ensure_ascii=False)[:300])
    except TopError as exc:
        print("time.get failed:", exc)
        return 1

    if not client.session:
        print("skip category tree: no session. open this URL after setting ALIBABA_REDIRECT_URI:")
        redirect = "http://localhost:5173/oauth/callback"
        print(client.authorize_url(redirect))
        return 0

    api = IcbuApi(client)
    try:
        tree = api.category_tree("zh")
        print("category.get.new ok:", json.dumps(tree, ensure_ascii=False)[:400])
    except TopError as exc:
        print("category.get.new failed:", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
