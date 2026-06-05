#!/usr/bin/env python3
"""
generate_icon.py — AI Blog Generator アイコンを生成します
  デフォルト: AppIcon.icns (macOS)
  --ico フラグ指定時: AppIcon.ico (Windows)
"""
import math
import os
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw


def _draw(size: int) -> Image.Image:
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))

    # ── グラデーション背景（濃紺 → インディゴ）─────────────────
    bg = Image.new("RGB", (s, s))
    bg_draw = ImageDraw.Draw(bg)
    for y in range(s):
        t = y / max(s - 1, 1)
        bg_draw.line(
            [(0, y), (s - 1, y)],
            fill=(int(18 + t * 42), int(18 + t * 18), int(90 + t * 90)),
        )

    # 角丸マスクを適用
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, s - 1, s - 1], radius=int(s * 0.22), fill=255
    )
    img.paste(bg, mask=mask)
    draw = ImageDraw.Draw(img)

    # ── 書類（白いページ）──────────────────────────────────────
    px, py = int(s * 0.20), int(s * 0.14)
    pw, ph = int(s * 0.46), int(s * 0.56)
    fold = int(s * 0.09)

    draw.polygon(
        [
            (px, py),
            (px + pw - fold, py),
            (px + pw, py + fold),
            (px + pw, py + ph),
            (px, py + ph),
        ],
        fill=(235, 240, 255, 235),
    )
    # 折り返し三角形
    draw.polygon(
        [(px + pw - fold, py), (px + pw, py + fold), (px + pw - fold, py + fold)],
        fill=(170, 185, 215, 220),
    )

    # ── テキスト行（罫線）──────────────────────────────────────
    lx1 = px + int(s * 0.055)
    lx2 = px + pw - int(s * 0.11)
    lh = max(int(s * 0.022), 2)
    line_color = (150, 170, 210, 160)
    for i in range(4):
        ly = py + int(s * 0.13) + i * int(s * 0.09)
        if ly + lh < py + ph - int(s * 0.04):
            x2 = lx2 if i < 3 else lx1 + int((lx2 - lx1) * 0.65)
            draw.rectangle([lx1, ly, x2, ly + lh], fill=line_color)

    # ── えんぴつ────────────────────────────────────────────────
    angle = math.radians(-40)
    ca, sa = math.cos(angle), math.sin(angle)
    pcx, pcy = int(s * 0.635), int(s * 0.645)
    hl  = int(s * 0.285)   # ボディの半分の長さ
    hw  = int(s * 0.052)   # 半分の幅
    tip = int(s * 0.080)   # 先端三角の長さ
    erl = int(s * 0.055)   # 消しゴムの長さ

    def pt(dx: float, dy: float) -> tuple:
        return (round(pcx + ca * dx - sa * dy), round(pcy + sa * dx + ca * dy))

    # ボディ（黄色）
    draw.polygon(
        [pt(-hl + erl, -hw), pt(hl, -hw), pt(hl, hw), pt(-hl + erl, hw)],
        fill=(255, 214, 60, 255),
    )
    # 消しゴム（ピンク）
    draw.polygon(
        [pt(-hl, -hw), pt(-hl + erl, -hw), pt(-hl + erl, hw), pt(-hl, hw)],
        fill=(255, 150, 150, 255),
    )
    # 消しゴムの帯
    band = max(int(s * 0.008), 1)
    draw.polygon(
        [
            pt(-hl + erl - band, -hw), pt(-hl + erl, -hw),
            pt(-hl + erl, hw),         pt(-hl + erl - band, hw),
        ],
        fill=(190, 100, 100, 255),
    )
    # 木の部分（先端テーパー）
    draw.polygon(
        [pt(hl, -hw), pt(hl + tip, 0), pt(hl, hw)],
        fill=(210, 170, 110, 255),
    )
    # 芯（濃いグレー）
    lead = max(int(s * 0.018), 2)
    draw.polygon(
        [
            pt(hl + tip - lead, -int(hw * 0.25)),
            pt(hl + tip, 0),
            pt(hl + tip - lead, int(hw * 0.25)),
        ],
        fill=(60, 50, 40, 255),
    )

    return img


def create_icns(dest: str = "AppIcon.icns") -> str:
    iconset = "AppIcon.iconset"
    os.makedirs(iconset, exist_ok=True)

    base = _draw(1024)
    for sz in [16, 32, 128, 256, 512]:
        base.resize((sz, sz), Image.LANCZOS).save(f"{iconset}/icon_{sz}x{sz}.png")
        base.resize((sz * 2, sz * 2), Image.LANCZOS).save(f"{iconset}/icon_{sz}x{sz}@2x.png")

    subprocess.run(["iconutil", "-c", "icns", iconset, "-o", dest], check=True)
    shutil.rmtree(iconset)
    return dest


def create_ico(dest: str = "AppIcon.ico") -> str:
    base = _draw(256)
    sizes = [16, 32, 48, 64, 128, 256]
    imgs = [base.resize((s, s), Image.LANCZOS) for s in sizes]
    imgs[0].save(dest, format="ICO", append_images=imgs[1:])
    return dest


if __name__ == "__main__":
    if "--ico" in sys.argv:
        out = create_ico()
    else:
        out = create_icns()
    print(f"✅ {out} を作成しました")
