#!/usr/bin/env python3
"""Download MP4s for ndjson rows that have no local_file yet,
by re-fetching fresh play URLs via TikHub hybrid endpoint."""
import functools
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor

import requests

print = functools.partial(print, flush=True)
API_KEY = os.environ["TIKHUB_KEY"]
OUT_DIR = "/home/ubuntu/tiktok_crawler"
VIDEO_DIR = os.path.join(OUT_DIR, "videos")
NDJSON = os.path.join(OUT_DIR, "viral_videos.ndjson")
session = requests.Session()
session.headers.update({"Authorization": f"Bearer {API_KEY}"})
lock = threading.Lock()


def fetch_play_urls(aweme_id):
    try:
        r = session.get(
            "https://api.tikhub.io/api/v1/tiktok/app/v3/fetch_one_video",
            params={"aweme_id": aweme_id}, timeout=60)
        d = r.json().get("data", {})
        a = (d.get("aweme_detail") or d.get("aweme_details") or [{}])
        if isinstance(a, list):
            a = a[0] if a else {}
        return ((a.get("video") or {}).get("play_addr") or {}).get("url_list") or []
    except Exception:
        return []


def download(row):
    cat = row.get("category", "Misc").split()[-1].replace("/", "_")
    cat_dir = os.path.join(VIDEO_DIR, cat)
    os.makedirs(cat_dir, exist_ok=True)
    fname = f"{row['likes']}likes_{row['comments']}cmt_{row['aweme_id']}.mp4"
    path = os.path.join(cat_dir, fname)
    if os.path.exists(path) and os.path.getsize(path) > 50_000:
        return os.path.relpath(path, OUT_DIR)
    urls = []
    if row.get("play_url"):
        urls.append(row["play_url"])
    urls += fetch_play_urls(row["aweme_id"])
    for url in urls[:4]:
        try:
            with requests.get(url, timeout=120, stream=True) as r:
                if r.status_code != 200:
                    continue
                with open(path, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
            if os.path.getsize(path) > 50_000:
                return os.path.relpath(path, OUT_DIR)
        except Exception:
            continue
    if os.path.exists(path):
        os.remove(path)
    return ""


def main():
    rows = {}
    with open(NDJSON) as f:
        for line in f:
            try:
                r = json.loads(line)
                rows[r["aweme_id"]] = r
            except Exception:
                pass
    todo = [r for r in rows.values() if not r.get("local_file")]
    print(f"backfilling {len(todo)} of {len(rows)}")

    def work(row):
        local = download(row)
        row["local_file"] = local
        print(("OK   " if local else "FAIL ") + row["aweme_id"] + " " + row.get("desc", "")[:40])

    with ThreadPoolExecutor(max_workers=30) as ex:
        list(ex.map(work, todo))

    with open(NDJSON, "w") as f:
        for r in rows.values():
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    ok = sum(1 for r in rows.values() if r.get("local_file"))
    print(f"done: {ok}/{len(rows)} have local files")


if __name__ == "__main__":
    main()
