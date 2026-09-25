#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Лист перебора настроек: оригинал x4 | прежний пак | вариант 1 | вариант 2 ... на тёмном полу боя.

Судим листом в полный рост, а не мерками (R-066). Кадры берутся из готовых папок перебора.

    py tools/hdart/sweep_sheet.py --terrain JUNGLE --block JUNGLE04 --out art/maps/paint/sweep/_jungle.png \
        pilot=art/maps/paint/JUNGLE_p1 str80=art/maps/paint/sweep/JUNGLE04_str80 ...
    --frames JUNGLE:3,JUNGLE:4   только эти кадры (по умолчанию все кадры карты)
"""
import argparse
import os
import sys

from PIL import Image, ImageDraw

sys.path[:0] = [os.path.dirname(os.path.abspath(__file__))]
import map_mockup as mm          # noqa: E402
import map_update as mu          # noqa: E402
import build_dataset as bd       # noqa: E402

DARK = (28, 26, 24)
MOD = os.path.join("Пиратки", "Dioxine_XPiratez", "user", "mods", "hd")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--terrain", required=True)
    ap.add_argument("--block", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--frames", default="")
    ap.add_argument("--mod", default=MOD)
    ap.add_argument("--per", type=int, default=16, help="кадров на лист")
    ap.add_argument("roots", nargs="+", help="имя=папка")
    a = ap.parse_args()
    world = mm.World()
    roots = [r.split("=", 1) for r in a.roots]
    if a.frames:
        keys = [(p.split(":")[0].upper(), int(p.split(":")[1])) for p in a.frames.split(",")]
    else:
        fr = mu.map_frames(world, a.terrain, a.block)
        keys = [(s, f) for s in sorted(fr) for f in sorted(fr[s])]
    k, cw, ch, lh = 4, 128, 160, 18
    cols = 2 + len(roots)
    fnt = bd.font()
    outs = []
    for page in range(0, len(keys), a.per):
        part = keys[page:page + a.per]
        im = Image.new("RGB", (cols * cw, lh + len(part) * (ch + lh)), (16, 16, 18))
        dr = ImageDraw.Draw(im)
        for j, name in enumerate(["оригинал", "прежний"] + [n for n, _ in roots]):
            dr.text((j * cw + 2, 1), name, fill=(200, 200, 120), font=fnt)
        for i, (s, f) in enumerate(part):
            y = lh + i * (ch + lh)
            dr.text((2, y + 1), "%s %d" % (s, f), fill=(200, 200, 200), font=fnt)
            spr = world.sprite(s, f, None)
            cells = [spr.resize((cw, ch), Image.NEAREST) if spr is not None else None]
            old = os.path.join(mu.mod_dir(a.mod, s), "%d.png" % f)
            cells.append(Image.open(old).convert("RGBA") if os.path.exists(old) else None)
            for _n, r in roots:
                p = os.path.join(r, s + ".PCK", "%d.png" % f)
                cells.append(Image.open(p).convert("RGBA") if os.path.exists(p) else None)
            for j, c in enumerate(cells):
                bg = Image.new("RGBA", (cw, ch), DARK + (255,))
                if c is not None:
                    bg.alpha_composite(c if c.size == (cw, ch) else c.resize((cw, ch), Image.LANCZOS))
                im.paste(bg.convert("RGB"), (j * cw, y + lh))
        name = a.out.replace(".png", "_%02d.png" % (page // a.per + 1))
        im.save(name)
        outs.append(name)
    print("\n".join(outs))


if __name__ == "__main__":
    main()
