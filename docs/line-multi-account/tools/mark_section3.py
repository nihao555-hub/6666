#!/usr/bin/env python3
"""第三节配图：官方原图 + 在真实控件上精准红框。

- 点进 channel：官方 console-home-en.png
- Channel secret：官方 channel-secret-en.png（Basic settings 那一行）
- Channel access token：官方没有这一行的截图，用官方 secret 同一套控件拼出 long-lived token 行
  （Issue / 复制图标直接从官方 secret 图裁出）
- Webhook：官方 webhook-url-example-com.png
"""
from __future__ import annotations

import io
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE = "https://developers.line.biz"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "images"
CACHE = Path("/tmp/lineoff")
FONT = "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"
RED = (230, 40, 40)
WHITE = (255, 255, 255)


def font(n: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT, n)


def fetch(path: str) -> Image.Image:
    CACHE.mkdir(parents=True, exist_ok=True)
    local = CACHE / Path(path).name
    if not local.exists():
        req = urllib.request.Request(BASE + path, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            local.write_bytes(resp.read())
    return Image.open(io.BytesIO(local.read_bytes())).convert("RGB")


def mark(img: Image.Image, box: tuple[int, int, int, int], text: str, side: str = "top") -> None:
    """box 是像素坐标 (x0,y0,x1,y1)。"""
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box
    d.rectangle([x0, y0, x1, y1], outline=RED, width=4)
    fnt = font(22)
    tw = fnt.getlength(text)
    th, pad = 32, 8
    if side == "top":
        tx, ty = x0, max(4, y0 - th - 8)
    elif side == "bottom":
        tx, ty = x0, min(img.height - th - 4, y1 + 8)
    else:  # right
        tx, ty = min(img.width - tw - pad * 2 - 4, x1 + 8), y0
    if tx + tw + pad * 2 > img.width:
        tx = img.width - tw - pad * 2 - 4
    d.rectangle([tx, ty, tx + tw + pad * 2, ty + th], fill=RED)
    d.text((tx + pad, ty + 5), text, font=fnt, fill=WHITE)


def frame(inner: Image.Image, tab: str, title: str) -> Image.Image:
    """套一层和官方 Console 一样的顶栏 + 标签，方便对照点哪里。"""
    w = max(inner.width + 48, 900)
    head = 132
    out = Image.new("RGB", (w, head + inner.height + 36), WHITE)
    d = ImageDraw.Draw(out)
    d.text((24, 16), title, font=font(20), fill=(30, 32, 36))
    tabs = ["Basic settings", "Messaging API", "LIFF", "Security"]
    x = 24
    for t in tabs:
        d.text((x, 58), t, font=font(16), fill=(30, 32, 36) if t == tab else (120, 126, 134))
        tw = font(16).getlength(t)
        if t == tab:
            d.rectangle([x, 86, x + tw, 90], fill=(6, 199, 85))
        x += int(tw) + 28
    d.line([(0, 96), (w, 96)], fill=(230, 232, 235), width=1)
    out.paste(inner, (24, head))
    return out


def save(img: Image.Image, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    img.save(OUT / name, optimize=True)
    print("wrote", name, img.size)


def main() -> None:
    # 1) 点进 Messaging API channel
    ch = fetch("/media/messaging-api/getting-started/console-home-en.png")
    # Sample channel 卡片：右半边那张（官方原图像素）
    mark(ch, (848, 580, 1588, 1360), "1. 点进这个 Messaging API channel", "top")
    save(ch, "s3-open-channel.png")

    # 2) Channel secret：官方原图那一行
    sec = fetch("/media/messaging-api/verify-webhook-signature/channel-secret-en.png")
    # 放大一倍方便看
    sec = sec.resize((sec.width * 2, sec.height * 2), Image.Resampling.NEAREST)
    mark(sec, (330, 20, 980, 140), "2. 复制 Channel secret", "top")
    framed = frame(sec, "Basic settings", "LINE Developers Console  →  Basic settings")
    save(framed, "s3-secret.png")

    # 3) Channel access token：官方没有单独截图。
    #    用官方 secret 行同一套控件（Issue / 复制图标从官方图裁出），只改标签。
    raw = fetch("/media/messaging-api/verify-webhook-signature/channel-secret-en.png")
    token_row = raw.copy()
    d = ImageDraw.Draw(token_row)
    d.rectangle([0, 0, 155, 82], fill=WHITE)
    d.text((8, 28), "Channel access token", font=font(15), fill=(30, 32, 36))
    d.text((8, 48), "(long-lived)", font=font(13), fill=(110, 116, 124))
    # 中间那串是官方 secret 图上的值，盖掉以免和 token 搞混
    d.rectangle([165, 22, 455, 58], fill=WHITE)
    d.text((168, 30), "eyJhbGciOiJIUzI1NiJ9.xxxxx", font=font(14), fill=(30, 32, 36))
    token_row = token_row.resize((token_row.width * 2, token_row.height * 2), Image.Resampling.NEAREST)
    mark(token_row, (1640, 20, 1940, 150), "3. 点 Issue，再复制 token", "top")
    framed = frame(token_row, "Messaging API", "LINE Developers Console  →  Messaging API")
    save(framed, "s3-token.png")

    # 4) Webhook：官方原图
    wh = fetch("/media/messaging-api/build-bot/webhook-url-example-com.png")
    # 先量过：URL 大约在右侧中部，Verify/Edit 在 URL 下，开关在底部
    mark(wh, (170, 70, 430, 105), "4. Edit 后填 /webhook/accN", "top")
    mark(wh, (170, 108, 250, 148), "5. 再点 Verify", "bottom")
    mark(wh, (168, 188, 240, 232), "6. 打开 Use webhook", "bottom")
    framed = frame(wh, "Messaging API", "LINE Developers Console  →  Messaging API  →  Webhook settings")
    save(framed, "s3-webhook.png")


if __name__ == "__main__":
    main()
