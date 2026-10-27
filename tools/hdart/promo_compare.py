# -*- coding: utf-8 -*-
r"""Кадр «классика / HD» для страницы mod.io (docs/research/modio-launcher-page-2026-10-27.md): один экран при k=1
(классика, 480x270) и при k=4 (HD, 1920x1080) со стенда hdbench, левая часть - классика крупными пикселями, правая - HD,
косой шов и подписи. Подписи на английском.

    py -3.13 tools/hdart/promo_compare.py <классика.png> <hd.png> <итог.png> [--split 0.5]
"""
import argparse

from PIL import Image, ImageDraw, ImageFont


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("classic")
    ap.add_argument("hd")
    ap.add_argument("out")
    ap.add_argument("--split", type=float, default=0.5, help="доля ширины слева под классику (по середине шва)")
    ap.add_argument("--slant", type=int, default=160, help="наклон шва в пикселях на всю высоту")
    a = ap.parse_args()
    hd = Image.open(a.hd).convert("RGB")
    w, h = hd.size
    classic = Image.open(a.classic).convert("RGB").resize((w, h), Image.NEAREST)
    x0 = int(w * a.split)
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    d.polygon([(0, 0), (x0 + a.slant // 2, 0), (x0 - a.slant // 2, h), (0, h)], fill=255)
    out = hd.copy()
    out.paste(classic, (0, 0), mask)
    d = ImageDraw.Draw(out)
    d.line([(x0 + a.slant // 2, 0), (x0 - a.slant // 2, h)], fill=(140, 220, 0), width=6)
    font = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 44)
    for text, x, anchor in (("CLASSIC", 32, "lb"), ("HD", w - 32, "rb")):
        d.text((x, h - 28), text, font=font, fill=(255, 255, 255), anchor=anchor, stroke_width=4, stroke_fill=(0, 0, 0))
    out.save(a.out)
    print("ok", a.out, out.size)


if __name__ == "__main__":
    main()
