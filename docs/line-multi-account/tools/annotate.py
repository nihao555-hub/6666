#!/usr/bin/env python3
"""下载 LINE 官方文档中的控制台截图，叠加中文步骤标注，输出到 docs/line-multi-account/images/。

用法:
    python3 docs/line-multi-account/tools/annotate.py

依赖: pillow, 系统中文字体 (wqy-microhei / Droid Sans Fallback)。
截图版权归 LINE Corporation 所有，仅作教学引用，来源见 SOURCES.md。
"""
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

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
]

RED = (230, 40, 40)
DARK = (30, 32, 36)
WHITE = (255, 255, 255)


def font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    raise RuntimeError("找不到中文字体，请安装 fonts-wqy-microhei")


def fetch(remote: str) -> Image.Image:
    CACHE.mkdir(parents=True, exist_ok=True)
    local = CACHE / Path(remote).name
    if not local.exists():
        req = urllib.request.Request(BASE + remote, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            local.write_bytes(resp.read())
    return Image.open(io.BytesIO(local.read_bytes())).convert("RGB")


def wrap(text: str, fnt: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines, cur = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        if fnt.getlength(cur + ch) > max_width and cur:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def with_caption(img: Image.Image, title: str, note: str = "") -> Image.Image:
    """在截图上方加一条深色标题栏，写清这一步在做什么。"""
    width = img.width
    scale = max(1.0, width / 1000)
    title_font = font(int(26 * scale))
    note_font = font(int(20 * scale))
    pad = int(16 * scale)

    title_lines = wrap(title, title_font, width - 2 * pad)
    note_lines = wrap(note, note_font, width - 2 * pad) if note else []
    bar = pad * 2 + len(title_lines) * int(34 * scale) + (
        len(note_lines) * int(28 * scale) + int(6 * scale) if note_lines else 0
    )

    out = Image.new("RGB", (width, img.height + bar), WHITE)
    draw = ImageDraw.Draw(out)
    draw.rectangle([0, 0, width, bar], fill=DARK)
    y = pad
    for line in title_lines:
        draw.text((pad, y), line, font=title_font, fill=WHITE)
        y += int(34 * scale)
    if note_lines:
        y += int(6 * scale)
        for line in note_lines:
            draw.text((pad, y), line, font=note_font, fill=(168, 176, 188))
            y += int(28 * scale)
    out.paste(img, (0, bar))
    draw.rectangle([0, 0, width - 1, out.height - 1], outline=(210, 214, 220))
    return out


def annotate(img: Image.Image, marks: list[dict]) -> Image.Image:
    """marks: [{"box": (x0,y0,x1,y1) 相对坐标 0~1, "label": "①", "text": "说明", "side": "right"}]"""
    out = img.copy()
    draw = ImageDraw.Draw(out)
    scale = max(1.0, out.width / 1000)
    lw = max(3, int(3 * scale))
    badge_r = int(18 * scale)
    badge_font = font(int(24 * scale))
    text_font = font(int(22 * scale))

    for m in marks:
        x0, y0, x1, y1 = m["box"]
        box = [x0 * out.width, y0 * out.height, x1 * out.width, y1 * out.height]
        draw.rectangle(box, outline=RED, width=lw)

        cx, cy = box[0] - badge_r, box[1]
        if cx - badge_r < 0:  # 左侧放不下就把序号挪到框的上方
            cx = box[0] + badge_r
            cy = max(badge_r, box[1] - badge_r * 2)
        draw.ellipse([cx - badge_r, cy - badge_r, cx + badge_r, cy + badge_r], fill=RED)
        label = m.get("label", "")
        lb = draw.textbbox((0, 0), label, font=badge_font)
        draw.text((cx - (lb[2] - lb[0]) / 2, cy - (lb[3] - lb[1]) / 2 - lb[1]), label,
                  font=badge_font, fill=WHITE)

        text = m.get("text")
        if not text:
            continue
        tx, ty = box[2] + int(12 * scale), box[1]
        max_w = out.width - tx - int(10 * scale)
        if max_w < int(180 * scale):  # 右侧放不下就放到框下方
            tx, ty = box[0], box[3] + int(10 * scale)
            max_w = out.width - tx - int(10 * scale)
        lines = wrap(text, text_font, max_w)
        th = len(lines) * int(30 * scale)
        if ty + th > out.height:  # 下方放不下就挪到框上方
            ty = max(int(4 * scale), int(box[1]) - th - int(12 * scale))
        draw.rectangle([tx - int(6 * scale), ty - int(4 * scale),
                        tx + max(text_font.getlength(l) for l in lines) + int(6 * scale),
                        ty + th + int(4 * scale)], fill=(255, 246, 240), outline=RED)
        for line in lines:
            draw.text((tx, ty), line, font=text_font, fill=(140, 30, 20))
            ty += int(30 * scale)
    return out


def save(img: Image.Image, name: str) -> None:
    IMAGES.mkdir(parents=True, exist_ok=True)
    path = IMAGES / name
    img.save(path, optimize=True)
    print(f"wrote {path.relative_to(ROOT.parents[1])} {img.size}")


def main() -> None:
    # 步骤 1：LINE Official Account Manager 账号列表（五个号在这里逐个创建）
    oa = fetch("/media/messaging-api/getting-started/oa-manager-list-en.png")
    oa = annotate(oa, [
        {"box": (0.018, 0.272, 0.10, 0.325), "label": "1",
         "text": "Create new：每个 LINE 官方账号点一次，五个号重复五次"},
        {"box": (0.235, 0.50, 0.975, 0.68), "label": "2",
         "text": "账号列表；Role 必须是 Administrator 才能拿到密钥"},
    ])
    save(with_caption(oa, "步骤 1　在 LINE Official Account Manager 建好 5 个官方账号",
                      "https://manager.line.biz/ ；一个 Business ID 可以管理多个账号，五个号建在同一个登录账号下最省事"),
         "01-oa-manager-accounts.png")

    # 步骤 3：选择 / 新建 Provider
    prov = fetch("/media/liff/getting-started/create-provider-en.png")
    prov = annotate(prov, [
        {"box": (0.28, 0.24, 0.965, 0.36), "label": "1", "text": "填 Provider 名称，例如 my-line-hub"},
    ])
    save(with_caption(prov, "步骤 3　建立 / 选择 Provider（服务商）",
                      "五个账号建议挂在同一个 Provider 下，方便统一管理；注意 Provider 一旦绑定无法更换，且不同 Provider 下同一用户的 userId 不同"),
         "03-provider-create.png")

    # 步骤 4：Console 首页，进入 Channel
    home = fetch("/media/messaging-api/getting-started/console-home-en.png")
    home = annotate(home, [
        {"box": (0.527, 0.425, 0.978, 0.985), "label": "1",
         "text": "点进对应的 Messaging API channel"},
    ])
    save(with_caption(home, "步骤 4　在 LINE Developers Console 打开对应 Channel",
                      "https://developers.line.biz/console/ ；启用 Messaging API 后，每个官方账号会在这里出现一个 channel"),
         "04-console-channels.png")

    # 步骤 7：Webhook URL 设置
    wh = fetch("/media/messaging-api/build-bot/webhook-url-example-com.png")
    wh = annotate(wh, [
        {"box": (0.24, 0.28, 0.60, 0.42), "label": "1",
         "text": "填 https://你的域名/webhook/acc1"},
        {"box": (0.245, 0.44, 0.49, 0.60), "label": "2", "text": "点 Verify 自检"},
        {"box": (0.24, 0.76, 0.34, 0.94), "label": "3", "text": "打开 Use webhook"},
    ])
    save(with_caption(wh, "步骤 7　Messaging API 标签页：填写 Webhook URL 并开启 Use webhook",
                      "五个账号各填各自的路径：/webhook/acc1 … /webhook/acc5；必须是 HTTPS 且为受信任 CA 签发的证书，自签证书不被接受"),
         "07-webhook-url.png")

    # 步骤 8：Verify 成功
    verify = fetch("/media/news/webhook-url-verify-button.png")
    save(with_caption(verify, "步骤 8　点 Verify，出现 Success 才算联通",
                      "Verify 会向你的 Webhook URL 发一条空 events 的 POST；返回 200 即成功。失败常见原因见教程最后的排错表"),
         "08-webhook-verify.png")

    # 可选：Webhook redelivery
    redeliver = fetch("/media/messaging-api/receiving-messages/enable-webhook-redelivery-en.png")
    save(with_caption(redeliver, "建议开启　Webhook redelivery（失败重投）与 Error statistics aggregation",
                      "托管多个账号时，单机重启/发布会丢事件，开启重投可以显著降低丢消息概率"),
         "09-webhook-redelivery.png")

    # 可选：IP 白名单
    sec = fetch("/media/messaging-api/build-bot/security-settings-input-en.png")
    save(with_caption(sec, "可选加固　Security 标签页给长期 token 绑定服务器出口 IP",
                      "使用长期 channel access token 时，把服务器公网出口 IP 加进白名单，token 泄露也无法被别处调用"),
         "12-ip-allowlist.png")


if __name__ == "__main__":
    main()
