#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Лист «классика | было | стало» из УСТАНОВЛЕННЫХ файлов мода hd (repo) и резерва art/_backup/t<NNN>_2026-10-31/.
Только чтение. Новые кадры (варианты ковра .vN) в колонке «было» - прочерк.

    py -3.13 tools\hdart\t1031b_sheet.py 384 [--out путь]
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
os.chdir(ROOT)

from PIL import Image, ImageDraw, ImageFont          # noqa: E402

import t1031b_install as ti                          # noqa: E402

BG = (92, 92, 100, 255)
FONT = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 14)


def order(rel):
    m = re.fullmatch(r"TERRAIN/(.+)\.PCK/(\d+)(\.v\d+)?\.png", rel)
    return (m.group(1), int(m.group(2)), m.group(3) or "")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    t = ti.TICKETS[args[0]]
    out = os.path.join(ROOT, "art", "_review", "tickets_2026-10-31", "install_%s.png" % args[0])
    if "--out" in sys.argv:
        out = sys.argv[sys.argv.index("--out") + 1]
    files = ti.collect(os.path.join(ROOT, "art", "tickets", t["cand"], "cand"))
    backup = os.path.join(ROOT, "art", "_backup", "%s_2026-10-31" % t["cand"])
    import t410_gen as g
    rows = []
    for rel in sorted(files, key=order):
        st, fr, var = order(rel)
        with Image.open(os.path.join(ti.REPO_PACK, rel)) as im:
            after = im.convert("RGBA")
        bp = os.path.join(backup, rel)
        before = None
        if os.path.exists(bp):
            with Image.open(bp) as im:
                before = im.convert("RGBA")
        try:
            cl = g.classic(st, fr)
            cl = cl.resize((cl.width * 4, cl.height * 4), Image.NEAREST)
        except Exception:
            cl = None
        rows.append((st, fr, var, cl, before, after))
    cw = 136
    W = 8 + 3 * cw
    per = 6 if len(rows) > 24 else len(rows)
    cols = (len(rows) + per - 1) // per
    rh = 160 + 22
    sheet = Image.new("RGBA", (cols * W, 30 + per * rh), BG)
    d = ImageDraw.Draw(sheet)
    d.text((6, 6), "XP-000%s: классика | было | стало (установленные файлы мода hd, repo)" % args[0], fill=(255, 220, 0), font=FONT)
    for i, (st, fr, var, cl, before, after) in enumerate(rows):
        c, r = divmod(i, per)
        x0, y0 = c * W, 30 + r * rh
        d.text((x0 + 4, y0 + 2), "%s:%d%s" % (st, fr, var), fill=(255, 255, 255), font=FONT)
        for k, im in enumerate((cl, before, after)):
            x = x0 + 4 + k * cw
            if im is None:
                d.text((x + 50, y0 + 90), "-", fill=(255, 255, 255), font=FONT)
            else:
                sheet.alpha_composite(im, (x, y0 + 20))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sheet.convert("RGB").save(out)
    print("лист:", out, "кадров", len(rows))


if __name__ == "__main__":
    main()
