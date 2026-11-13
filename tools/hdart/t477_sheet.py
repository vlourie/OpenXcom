#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000477: лист установки «классика | было | стало» -> art/_review/tickets_2026-11-02/install_477.png.
Запускать ДО установки (было = то, что стоит в паке установки игры); стало = art/tickets/t477/cand_v2/V1.
Ряды: короткий камин 10+9, длинный 10+8+8+9, сцена WESTOWN_05 (камин игрока), низ камина на полной сцене крупно (край, R-121)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from PIL import Image                                 # noqa: E402

import t477_build as b                                # noqa: E402
import ticket_scene as ts                             # noqa: E402

V1 = os.path.join(b.CAND, "V1")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    new = {f: Image.open(os.path.join(V1, "WESTFLOOR_%d.png" % f)).convert("RGBA") for f in (10, 8)}
    now = b.now_frames()
    cls = b.classic_frames()
    after = dict(now)
    after.update(new)
    panels = []
    for order in ([10, 9], [10, 8, 8, 9]):
        for t, fr in (("классика", cls), ("было", now), ("стало V1", after)):
            panels.append(("%s (%s)" % (t, "+".join(str(o) for o in order)), b.panel(b.stack(fr, order), 500)))
    sc = ts.Scene()
    terrain, block = "WESTOWN_MUD", "WESTOWN_05"
    f = ts.find_cells(sc, terrain, block, [("WESTFLOOR", 10), ("WESTFLOOR", 9)])
    box = ts.window([(a[0], a[1], tuple(v * 4 for v in a[2])) for a in f], 190, 135, 4)
    ov = {("WESTFLOOR", 10): new[10], ("MEDIEVAL", 26): new[10], ("WESTFLOOR", 8): new[8], ("MEDIEVAL", 24): new[8]}
    ims = []
    for t, mode, o in (("классика", "classic", None), ("было", "hd", None), ("стало V1", "hd", ov)):
        im, _ = sc.render(terrain, block, mode, override=o, k=4)
        full = ts.crop_pad(im, box)
        ims.append((t, full))
        panels.append(("сцена %s: %s" % (block, t), full.resize((500, int(full.height * 500 / full.width)), Image.LANCZOS)))
    # низ камина крупно, 1:1 (x4 базы): клетка :10 на полу
    r10 = tuple(v * 4 for v in [a for a in f if a[0] == "WESTFLOOR" and a[1] == 10][0][2])
    edge = (r10[0] - 40, r10[3] - 260, r10[2] + 40, r10[3] + 40)
    for t, mode, o in (("классика", "classic", None), ("было", "hd", None), ("стало V1", "hd", ov)):
        im, _ = sc.render(terrain, block, mode, override=o, k=4)
        c = ts.crop_pad(im, edge)
        panels.append(("низ камина у пола 1:1 (x4 базы), " + t, c))
    out = os.path.join(b.REV, "install_477.png")
    ts.sheet(panels, out, cols=3)
    print("лист:", out)


if __name__ == "__main__":
    main()
