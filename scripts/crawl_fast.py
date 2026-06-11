#!/usr/bin/env python3
"""Concurrent crawler: search TikHub for viral TikTok shop videos
(likes>10K, comments>2K) and download MP4s. Streams progress."""
import csv
import functools
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

print = functools.partial(print, flush=True)

API_KEY = os.environ["TIKHUB_KEY"]
BASE = "https://api.tikhub.io/api/v1/tiktok/app/v3/fetch_video_search_result"
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

OUT_DIR = "/home/ubuntu/tiktok_crawler"
VIDEO_DIR = os.path.join(OUT_DIR, "videos")
NDJSON = os.path.join(OUT_DIR, "viral_videos.ndjson")
FIELDS = ["aweme_id", "category", "keyword", "desc", "author", "author_unique_id",
          "likes", "comments", "shares", "plays", "collects", "duration_s",
          "create_time", "has_product_anchor", "video_url", "local_file"]

KEYWORDS = {
    "Baby": ["viral baby gadgets", "newborn must haves viral", "baby essentials tiktok", "viral stroller", "baby toys viral tiktok"],
    "Hair": ["viral hair dryer brush", "hair mask viral tiktok", "viral wig tiktok", "hair straightener viral", "viral nail products tiktok", "press on nails viral"],
    "Outdoor": ["viral outdoor gadgets", "hiking gear viral tiktok", "viral garden products", "viral pool finds", "fishing gear viral"],
    "Factory": ["factory tour viral", "inside the factory tiktok", "how its made factory", "china factory viral", "factory process satisfying", "manufacturing process viral", "behind the scenes factory", "candy factory viral", "shoe factory tiktok", "toy factory viral", "food factory process", "garment factory tiktok", "production line satisfying", "factory machines viral"],
}

MIN_LIKES = 10_000
MIN_COMMENTS = 2_000
TARGET = 500
MAX_PAGES = 10

lock = threading.Lock()
results = {}
session = requests.Session()
session.headers.update(HEADERS)


def search_page(keyword, offset):
    for _ in range(4):
        try:
            r = session.get(BASE, params={
                "keyword": keyword, "offset": offset, "count": 20,
                "sort_type": 1, "publish_time": 0}, timeout=60)
            if r.status_code == 200:
                return r.json().get("data", {})
        except Exception:
            pass
        time.sleep(2)
    return {}


def extract(item, category, keyword):
    a = item.get("aweme_info") or {}
    if not a.get("aweme_id"):
        return None
    s = a.get("statistics", {})
    likes, comments = s.get("digg_count", 0), s.get("comment_count", 0)
    if likes < MIN_LIKES or comments < MIN_COMMENTS:
        return None
    author = a.get("author", {})
    video = a.get("video", {})
    play_urls = (video.get("play_addr") or {}).get("url_list") or []
    if not play_urls:
        return None
    row = {
        "aweme_id": a["aweme_id"],
        "category": category,
        "keyword": keyword,
        "desc": (a.get("desc") or "").replace("\n", " "),
        "author": author.get("nickname", ""),
        "author_unique_id": author.get("unique_id", ""),
        "likes": likes,
        "comments": comments,
        "shares": s.get("share_count", 0),
        "plays": s.get("play_count", 0),
        "collects": s.get("collect_count", 0),
        "duration_s": round(video.get("duration", 0) / 1000),
        "create_time": time.strftime("%Y-%m-%d", time.gmtime(a.get("create_time", 0))),
        "has_product_anchor": bool(a.get("anchors") or a.get("added_anchors")),
        "video_url": f"https://www.tiktok.com/@{author.get('unique_id','')}/video/{a['aweme_id']}",
        "local_file": "",
    }
    return row, play_urls


def download(row, play_urls):
    cat_dir = os.path.join(VIDEO_DIR, row["category"])
    os.makedirs(cat_dir, exist_ok=True)
    fname = f"{row['likes']}likes_{row['comments']}cmt_{row['aweme_id']}.mp4"
    path = os.path.join(cat_dir, fname)
    for url in play_urls[:3]:
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


def process_keyword(category, keyword):
    offset = 0
    for _ in range(MAX_PAGES):
        with lock:
            if len(results) >= TARGET:
                return
        data = search_page(keyword, offset)
        items = data.get("search_item_list") or []
        if not items:
            return
        for it in items:
            ex = extract(it, category, keyword)
            if not ex:
                continue
            row, play_urls = ex
            with lock:
                if row["aweme_id"] in results or len(results) >= TARGET:
                    continue
                results[row["aweme_id"]] = row
                n = len(results)
            local = download(row, play_urls)
            row["local_file"] = local
            with lock:
                with open(NDJSON, "a") as nf:
                    nf.write(json.dumps(row, ensure_ascii=False) + "\n")
            status = "OK " if local else "DLFAIL"
            print(f"#{n:3d} [{status}] [{row['category']:<11}] likes={row['likes']:>9,} cmt={row['comments']:>7,} @{row['author_unique_id']} | {row['desc'][:50]}")
        if not data.get("has_more"):
            return
        offset = data.get("cursor", offset + 20)


def main():
    os.makedirs(VIDEO_DIR, exist_ok=True)
    # resume from previous ndjson
    if os.path.exists(NDJSON):
        with open(NDJSON) as f:
            for line in f:
                try:
                    r = json.loads(line)
                    results[r["aweme_id"]] = r
                except Exception:
                    pass
        print(f"resumed with {len(results)} existing records")

    tasks = [(c, k) for c, kws in KEYWORDS.items() for k in kws]
    with ThreadPoolExecutor(max_workers=50) as ex:
        futs = [ex.submit(process_keyword, c, k) for c, k in tasks]
        for f in as_completed(futs):
            f.result()

    rows = sorted(results.values(), key=lambda r: -r["likes"])
    with open(os.path.join(OUT_DIR, "viral_videos.json"), "w") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    with open(os.path.join(OUT_DIR, "viral_videos.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"TOTAL: {len(rows)} videos")


if __name__ == "__main__":
    main()
