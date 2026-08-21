"""Draw numbered callouts on guide screenshots."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent / "shots"
INK = (23, 23, 23, 255)
RED = (196, 86, 74, 255)
WHITE = (255, 255, 255, 255)


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def annotate(name: str, marks: list[tuple[float, float, int, str]]) -> None:
    src = ROOT / f"{name}.png"
    image = Image.open(src).convert("RGBA")
    w, h = image.size
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    badge = max(28, int(h * 0.028))
    number_font = font(int(badge * 0.62))
    for x_pct, y_pct, number, _label in marks:
        x, y = int(w * x_pct), int(h * y_pct)
        box = (x - badge, y - badge, x + badge, y + badge)
        draw.ellipse(box, fill=RED if number >= 8 else INK)
        text = str(number)
        tw, th = draw.textbbox((0, 0), text, font=number_font)[2:]
        draw.text((x - tw / 2, y - th / 2 - 1), text, font=number_font, fill=WHITE)
    out = Image.alpha_composite(image, overlay).convert("RGB")
    dest = ROOT / f"{name}-ann.png"
    out.save(dest, "PNG", optimize=True)
    print(dest.name)


# Positions are fractions of width/height on the 1440×920 captures.
annotate("01-login", [(0.50, 0.48, 1, "邮箱"), (0.50, 0.58, 2, "密码"), (0.50, 0.68, 3, "进入"), (0.50, 0.76, 4, "开通")])
annotate("02-register", [(0.50, 0.42, 1, "邮箱"), (0.50, 0.52, 2, "密码"), (0.50, 0.62, 3, "注册码"), (0.50, 0.72, 4, "开通")])
annotate("03-overview", [(0.08, 0.28, 1, "导航"), (0.12, 0.12, 2, "切店"), (0.42, 0.38, 3, "推荐路径"), (0.88, 0.08, 4, "去投料")])
annotate("04-shops", [(0.90, 0.08, 1, "授权"), (0.82, 0.32, 2, "店铺默认"), (0.48, 0.32, 3, "已授权")])
annotate("05-shop-defaults", [(0.82, 0.22, 1, "发布模式"), (0.82, 0.42, 2, "产地单位"), (0.82, 0.62, 3, "包装"), (0.82, 0.78, 4, "付款港口交期")])
annotate("06-feed-photos", [(0.42, 0.22, 1, "三条路"), (0.42, 0.48, 2, "实拍图"), (0.55, 0.72, 3, "价和起订"), (0.38, 0.88, 4, "成稿")])
annotate("07-feed-excel", [(0.48, 0.42, 1, "谁填"), (0.42, 0.62, 2, "选类目"), (0.42, 0.72, 3, "下载"), (0.55, 0.86, 4, "传回")])
annotate("09-drafts", [(0.38, 0.22, 1, "红黄绿"), (0.62, 0.22, 2, "质量分"), (0.88, 0.08, 3, "发布")])
