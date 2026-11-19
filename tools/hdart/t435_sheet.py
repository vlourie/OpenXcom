#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""XP-000435: итоговый лист кандидатов art/_review/tickets_2026-10-30/t435_cand.png - по трём предметам: классика x4 | HD
сейчас | зёрна (лучшее с *) на тёмном; снизу сцена комнаты CULTHOUSE08 (классика, было, стало; окно вокруг предметов).
Нужны: art/tickets/t435/gen (зёрна), t435_cand_scene.png (t435_scene.py)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
from PIL import Image                                  # noqa: E402

import t435_gen as t                                   # noqa: E402
import ticket_scene as ts                              # noqa: E402

g = t.g
OUT = os.path.join(t.REV, "t435_cand.png")
SHOW = {"stand22": [4351, 4352, 4353, 4354], "sink31": [4361, 4362, 4363, 4364], "cooler51": [4381, 4382, 4383, 4384]}
NAMES = {"stand22": "CULTDECOR:22 стойка (семья 5)", "sink31": "CULTEXTRA:31 раковина (семья 19)",
         "cooler51": "CULTDECOR:51 кулер (1)"}
Z = 1.5


def scaled(im):
    return im.resize((int(im.width * Z), int(im.height * Z)), Image.LANCZOS)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    rows = []
    for job, J in t.JOBS.items():
        s, f, _o = J["members"][0]
        cls = g.classic_of(s, f).resize((128, 160), Image.NEAREST)
        ims = [("классика x4", g.on_dark(cls)), ("HD сейчас", g.on_dark(g.hd_now(s, f)))]
        for seed in SHOW[job]:
            ims.append(("зерно %d%s" % (seed, " *" if seed == t.BEST[job] else ""),
                        g.on_dark(Image.open(os.path.join(g.GEN, job, "%d.png" % seed)).convert("RGBA"))))
        rows.append((NAMES[job], ims))
    gap, hdr = 6, 34
    cw, ch = int(128 * Z), int(160 * Z)
    W = 6 * (cw + gap) + gap
    body = []
    for title, ims in rows:
        row = Image.new("RGB", (W, ch + hdr + 4), (12, 12, 14))
        for i, (lab, im) in enumerate(ims):
            p = ts.label(scaled(im).convert("RGB"), lab, 16)
            row.paste(p, (gap + i * (cw + gap), hdr))
        ts.label(row.crop((0, 0, W, 28)), "", 1)
        from PIL import ImageDraw
        ImageDraw.Draw(row).text((8, 6), title, fill=(255, 255, 255), font=ts.font(20))
        body.append(row)
    # сцена
    sc = Image.open(os.path.join(t.REV, "t435_cand_scene.png")).convert("RGB")
    H3 = (sc.height - 8) // 3
    pw = (W - 3 * gap) // 2
    ph = int(220 * pw / 280)
    sceneW = Image.new("RGB", (W, ph + 8), (12, 12, 14))
    for j, (i, lab) in enumerate(((1, "комната CULTHOUSE08: было (HD сейчас)"), (2, "стало (лучшие зёрна)"))):
        y0 = 40 + i * H3 + 110
        c = sc.crop((170, y0, 450, y0 + 220)).resize((pw, ph), Image.LANCZOS)
        sceneW.paste(ts.label(c, lab, 18), (gap + j * (pw + gap), 4))
    H = sum(r.height for r in body) + sceneW.height
    out = Image.new("RGB", (W, H), (12, 12, 14))
    y = 0
    for r in body + [sceneW]:
        out.paste(r, (0, y))
        y += r.height
    out.save(OUT)
    print("лист:", OUT, out.size)


if __name__ == "__main__":
    main()
