#!/usr/bin/env python3
"""官方文档原图整张保留，只加一两处短批注。不裁切、不自己画界面。"""
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
    d = ImageDraw.Draw(img)
    w, h = img.size
    x0, y0, x1, y1 = box[0] * w, box[1] * h, box[2] * w, box[3] * h
    lw = max(4, int(w / 350))
    d.rectangle([x0, y0, x1, y1], outline=RED, width=lw)
    fnt = font(max(22, int(w / 50)))
    tw = fnt.getlength(text)
    th = int(fnt.size * 1.6)
    pad = 10
    if below:
        tx, ty = x0, min(h - th - 8, y1 + 10)
    else:
        tx, ty = x0, max(8, y0 - th - 12)
        if tx + tw + pad * 2 > w:
            tx = max(8, w - tw - pad * 2 - 8)
    d.rectangle([tx, ty, tx + tw + pad * 2, ty + th], fill=RED)
    d.text((tx + pad, ty + 6), text, font=fnt, fill=WHITE)


def save(img: Image.Image, name: str) -> None:
    IMAGES.mkdir(parents=True, exist_ok=True)
    img.save(IMAGES / name, optimize=True)
    print("wrote", name, img.size)


def main() -> None:
    oa = fetch("/media/messaging-api/getting-started/oa-manager-list-en.png")
    mark(oa, (0.018, 0.268, 0.105, 0.335), "建号点这里")
    mark(oa, (0.235, 0.50, 0.975, 0.68), "Role 必须是 Administrator")
    save(oa, "01-accounts.png")

    prov = fetch("/media/liff/getting-started/create-provider-en.png")
    mark(prov, (0.28, 0.24, 0.96, 0.36), "填一个名字，五个号共用")
    save(prov, "02-provider.png")

    ch = fetch("/media/messaging-api/getting-started/console-home-en.png")
    mark(ch, (0.527, 0.42, 0.985, 0.99), "点进这个 Messaging API channel")
    save(ch, "03-channel.png")

    # 官方较完整的 Webhook settings 整页
    wh = fetch("/media/messaging-api/receiving-messages/enable-webhook-redelivery-en.png")
    mark(wh, (0.28, 0.16, 0.62, 0.28), "填 https://你的域名/webhook/acc1")
    mark(wh, (0.22, 0.30, 0.36, 0.40), "先别点，填完再 Verify")
    mark(wh, (0.78, 0.42, 0.90, 0.50), "打开", below=True)
    save(wh, "04-webhook.png")


if __name__ == "__main__":
    main()
