#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Лист «классика | было | стало» после установки тикета (t1031_install.py): было - резерв
art/_backup/t<N>_2026-10-31/, стало - файл, реально лежащий в игре (Пиратки hd), классика - g.classic_of.

    py -3.13 tools\hdart\t1031_sheet.py 379
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
os.chdir(ROOT)

from PIL import Image                                # noqa: E402

import t379_391_gen as t3                            # noqa: E402  (подтягивает t405_409_gen как g)
import t1031_install as ins                          # noqa: E402
import build_hd_pack as bp                           # noqa: E402
import ticket_scene as ts                            # noqa: E402

g = t3.g
OUT = os.path.join(ROOT, "art", "_review", "tickets_2026-10-31")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t = sys.argv[1]
    files = ins.collect(t)
    backup = os.path.join(ROOT, "art", "_backup", "t%s_2026-10-31" % t)
    game = bp.TARGETS["game"]
    panels = []
    for rel in files:
        pck, name = rel.split("/")[1][:-4], int(rel.split("/")[2][:-4])
        with Image.open(os.path.join(backup, rel)) as a, Image.open(os.path.join(game, rel)) as b:
            old, new = a.convert("RGBA"), b.convert("RGBA")
        cl = g.classic_of(pck, name).resize(old.size, Image.NEAREST).convert("RGBA")
        box = t3.union_box([cl, old, new])
        w = 300 if len(files) <= 5 else 200
        c = cl.crop(box)
        c = c.resize((w, int(round(c.height * w / c.width))), Image.NEAREST)
        ims = [g.on_dark(c), t3.fit(old, box, w), t3.fit(new, box, w)]
        H = max(i.height for i in ims)
        out = Image.new("RGB", (w * 3 + 12, H + 36), (14, 14, 16))
        for i, im in enumerate(ims):
            out.paste(im, (i * (w + 6), 36))
        panels.append(("%s:%d - классика | было | стало" % (pck, name), out))
    cols = 1 if len(panels) <= 5 else 4
    p = os.path.join(OUT, "install_%s.png" % t)
    ts.sheet(panels, p, cols=cols)
    print("лист:", p)


if __name__ == "__main__":
    main()
