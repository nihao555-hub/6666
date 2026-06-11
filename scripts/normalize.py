#!/usr/bin/env python3
"""Normalize categories in ndjson + move video files into canonical dirs."""
import json
import os
import shutil

OUT_DIR = "/home/ubuntu/tiktok_crawler"
VIDEO_DIR = os.path.join(OUT_DIR, "videos")
NDJSON = os.path.join(OUT_DIR, "viral_videos.ndjson")

CANON = {
    "美妆护肤 Beauty/Skincare": "Beauty", "美护 Beauty/Skincare": "Beauty", "Beauty2": "Beauty", "Beauty3": "Beauty", "Beauty": "Beauty",
    "服装配饰 Fashion": "Fashion", "服配 Fashion": "Fashion", "Fashion2": "Fashion", "Fashion3": "Fashion", "Fashion": "Fashion",
    "家居生活 Home": "Home", "家生 Home": "Home", "Home2": "Home", "Home3": "Home", "Home": "Home",
    "厨房用品 Kitchen": "Kitchen", "厨用 Kitchen": "Kitchen", "Kitchen": "Kitchen",
    "电子数码 Electronics": "Electronics", "电数 Electronics": "Electronics", "Tech2": "Electronics", "Gadgets": "Electronics", "Electronics": "Electronics",
    "健康保健 Health": "Health", "健保 Health": "Health", "Wellness": "Health", "Health": "Health",
    "母婴用品 Baby": "Baby", "母用 Baby": "Baby", "Baby2": "Baby", "Baby": "Baby",
    "宠物用品 Pets": "Pets", "宠用 Pets": "Pets", "Pets2": "Pets", "Pets": "Pets",
    "美发美甲 Hair/Nails": "Hair", "Hair2": "Hair", "Hair": "Hair",
    "食品饮料 Food": "Food", "Food2": "Food", "Food": "Food",
    "运动健身 Fitness": "Fitness", "Sports2": "Fitness", "Fitness": "Fitness",
    "汽车用品 Car": "Car", "Car": "Car",
    "清洁用品 Cleaning": "Cleaning", "Cleaning": "Cleaning",
    "饰品珠宝 Jewelry": "Jewelry", "Acc2": "Jewelry", "Jewelry": "Jewelry",
    "鞋类箱包 Shoes/Bags": "Shoes_Bags", "Shoes_Bags": "Shoes_Bags",
    "玩具礼品 Toys/Gifts": "Toys_Gifts", "Gift2": "Toys_Gifts", "Toys_Gifts": "Toys_Gifts",
    "户外用品 Outdoor": "Outdoor", "Outdoor2": "Outdoor", "Outdoor": "Outdoor",
    "办公文具 Office": "Office", "Office": "Office",
    "Misc": "Misc", "Factory": "Factory",
}

rows = [json.loads(l) for l in open(NDJSON)]
for r in rows:
    canon = CANON.get(r["category"], r["category"])
    r["category"] = canon
    fname = f"{r['likes']}likes_{r['comments']}cmt_{r['aweme_id']}.mp4"
    new_rel = os.path.join("videos", canon, fname)
    new_abs = os.path.join(OUT_DIR, new_rel)
    old_abs = os.path.join(OUT_DIR, r.get("local_file") or "")
    if r.get("local_file") and os.path.exists(old_abs) and old_abs != new_abs:
        os.makedirs(os.path.dirname(new_abs), exist_ok=True)
        shutil.move(old_abs, new_abs)
    if os.path.exists(new_abs):
        r["local_file"] = new_rel

with open(NDJSON, "w") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

# remove empty dirs
for d in os.listdir(VIDEO_DIR):
    p = os.path.join(VIDEO_DIR, d)
    if os.path.isdir(p) and not os.listdir(p):
        os.rmdir(p)

import collections
c = collections.Counter(r["category"] for r in rows)
for k, v in sorted(c.items()):
    print(k, v)
