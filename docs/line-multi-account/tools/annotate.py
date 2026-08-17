#!/usr/bin/env python3
"""只用 LINE 官方文档原图，加一两处短批注。不自己画界面。"""
from __future__ import annotations

import io
import os
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE = "https://developers.line.biz"
ROOT = Path(__file__).resolve().parents[1]
IMAGES = ROOT / "images"
CACHE = Path(os.environ.get("LINE_IMG_CACHE", "/tmp/lineimg"))
FONT = "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"
RED = (230, 40, 40)
WHITE = (255, 255, 255)


def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT, size)


def fetch(path: str) -> Image.Image:
    CACHE.mkdir(parents=True, exist_ok=True)
    local = CACHE / Path(path).name
    if not local.exists():
        req = urllib.request.Request(BASE + path, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            local.write_bytes(resp.read())
    return Image.open(io.BytesIO(local.read_bytes())).convert("RGB")


def mark(img: Image.Image, box: tuple[float, float, float, float], text: str, below: bool = False) -> None:
    """box 是相对坐标 0~1。只画红框 + 一句短批注。"""
    d = ImageDraw.Draw(img)
    w, h = img.size
    x0, y0, x1, y1 = box[0] * w, box[1] * h, box[2] * w, box[3] * h
    lw = max(3, int(w / 400))
    d.rectangle([x0, y0, x1, y1], outline=RED, width=lw)
    fnt = font(max(18, int(w / 55)))
    tw = fnt.getlength(text)
    th = 28 if w < 900 else 36
    pad = 8
    if below:
        tx, ty = x0, min(h - th - 8, y1 + 8)
    else:
        tx, ty = x0, max(6, y0 - th - 10)
        if tx + tw + pad * 2 > w:
            tx = w - tw - pad * 2 - 6
    d.rectangle([tx, ty, tx + tw + pad * 2, ty + th], fill=RED)
    d.text((tx + pad, ty + 4), text, font=fnt, fill=WHITE)


def fit(img: Image.Image, max_w: int = 1100) -> Image.Image:
    if img.width <= max_w:
        return img
    h = int(img.height * max_w / img.width)
    return img.resize((max_w, h), Image.Resampling.LANCZOS)


def save(img: Image.Image, name: str) -> None:
    IMAGES.mkdir(parents=True, exist_ok=True)
    img = fit(img)
    img.save(IMAGES / name, optimize=True)
    print("wrote", name, img.size)


def main() -> None:
    oa = fetch("/media/messaging-api/getting-started/oa-manager-list-en.png")
    mark(oa, (0.02, 0.27, 0.10, 0.33), "建号点这里")
    mark(oa, (0.24, 0.50, 0.97, 0.68), "Role 必须是 Administrator")
    save(oa, "o-accounts.png")

    ch = fetch("/media/messaging-api/getting-started/console-home-en.png")
    mark(ch, (0.53, 0.42, 0.98, 0.99), "点进这个 Messaging API channel")
    save(ch, "o-channel.png")

    wh = fetch("/media/messaging-api/build-bot/webhook-url-example-com.png")
    mark(wh, (0.24, 0.28, 0.62, 0.42), "改成 /webhook/acc1")
    mark(wh, (0.24, 0.76, 0.35, 0.94), "打开", below=True)
    save(wh, "o-webhook.png")

    vf = fetch("/media/news/webhook-url-verify-button.png")
    mark(vf, (0.26, 0.70, 0.52, 0.96), "服务器起来后再点", below=True)
    save(vf, "o-verify.png")


if __name__ == "__main__":
    main()
