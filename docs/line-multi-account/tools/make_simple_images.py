#!/usr/bin/env python3
"""生成精简教程用的小图：只框出真正要复制/要点的那一块。"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "images"
CACHE = Path("/tmp/lineimg")

FONT = "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"
INK = (26, 29, 33)
MUTED = (92, 101, 112)
GREEN = (6, 199, 85)
RED = (230, 40, 40)
LINE = (230, 232, 235)
WHITE = (255, 255, 255)
BG = (247, 248, 250)


def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT, size)


def card(w: int, h: int, title: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    im = Image.new("RGB", (w, h), WHITE)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, w - 1, h - 1], outline=LINE, width=2)
    d.rectangle([0, 0, w, 56], fill=(17, 20, 24))
    d.text((20, 16), title, font=font(22), fill=WHITE)
    return im, d


def save(im: Image.Image, name: str) -> None:
    path = OUT / name
    im.save(path, optimize=True)
    print("wrote", path.name, im.size)


def crop_official(src: str, box: tuple[int, int, int, int], name: str, caption: str) -> None:
    im = Image.open(CACHE / src).convert("RGB")
    im = im.crop(box)
    # 加一条很短的标题，不再铺大段说明
    w, h = im.size
    bar = 48
    out = Image.new("RGB", (w, h + bar), WHITE)
    d = ImageDraw.Draw(out)
    d.rectangle([0, 0, w, bar], fill=(17, 20, 24))
    d.text((16, 13), caption, font=font(20), fill=WHITE)
    out.paste(im, (0, bar))
    save(out, name)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    # 1) secret：只画要复制的那一行
    im, d = card(980, 220, "Basic settings  →  复制 Channel secret")
    d.text((28, 80), "Channel secret", font=font(18), fill=MUTED)
    d.rounded_rectangle([28, 112, 620, 168], 8, fill=BG, outline=RED, width=3)
    d.text((44, 126), "8f14e45fceea167a5a36dedd4bea2543", font=font(22), fill=INK)
    d.text((640, 128), "复制到 ACC1_CHANNEL_SECRET", font=font(18), fill=RED)
    save(im, "s-secret.png")

    # 2) token：只画 Issue + 复制
    im, d = card(980, 260, "Messaging API  →  Issue 后复制 token")
    d.text((28, 80), "Channel access token (long-lived)", font=font(18), fill=MUTED)
    d.rounded_rectangle([28, 112, 700, 168], 8, fill=BG, outline=RED, width=3)
    d.text((44, 126), "eyJhbGciOiJIUzI1NiJ9.xxxxx…", font=font(22), fill=INK)
    d.rounded_rectangle([28, 184, 140, 230], 6, fill=(43, 48, 56))
    d.text((58, 194), "Issue", font=font(20), fill=WHITE)
    d.text((160, 194), "第一次点它生成；复制到 ACC1_CHANNEL_TOKEN", font=font(18), fill=RED)
    save(im, "s-token.png")

    # 3) webhook：官方原图裁中间那一块
    crop_official(
        "webhook-url-example-com.png",
        (0, 0, 704, 250),
        "s-webhook.png",
        "每个号填自己的地址：https://你的域名/webhook/acc1",
    )
    crop_official(
        "webhook-url-verify-button.png",
        (0, 0, 407, 177),
        "s-verify.png",
        "服务器起来后再点 Verify，看到 Success",
    )

    # 4) 一张极简对照表
    rows = [
        ("账号", "secret → .env", "token → .env", "Webhook"),
        ("acc1", "ACC1_CHANNEL_SECRET", "ACC1_CHANNEL_TOKEN", "/webhook/acc1"),
        ("acc2", "ACC2_CHANNEL_SECRET", "ACC2_CHANNEL_TOKEN", "/webhook/acc2"),
        ("acc3", "ACC3_CHANNEL_SECRET", "ACC3_CHANNEL_TOKEN", "/webhook/acc3"),
        ("acc4", "ACC4_CHANNEL_SECRET", "ACC4_CHANNEL_TOKEN", "/webhook/acc4"),
        ("acc5", "ACC5_CHANNEL_SECRET", "ACC5_CHANNEL_TOKEN", "/webhook/acc5"),
    ]
    col_w = [90, 280, 270, 280]
    x0, y0, rh = 16, 70, 42
    w = sum(col_w) + 32
    h = y0 + rh * len(rows) + 16
    im, d = card(w, h, "5 个号只要对上这三列")
    x = x0
    for i, head in enumerate(rows[0]):
        d.rectangle([x, y0, x + col_w[i], y0 + rh], fill=BG)
        d.text((x + 10, y0 + 10), head, font=font(16), fill=MUTED)
        x += col_w[i]
    for r, row in enumerate(rows[1:], 1):
        x = x0
        yy = y0 + r * rh
        for i, cell in enumerate(row):
            d.rectangle([x, yy, x + col_w[i], yy + rh], outline=LINE)
            d.text((x + 10, yy + 10), cell, font=font(16), fill=INK)
            x += col_w[i]
    save(im, "s-table.png")


if __name__ == "__main__":
    main()
