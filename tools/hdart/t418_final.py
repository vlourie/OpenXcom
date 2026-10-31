#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""XP-000418, лист для Vitali после правки низа будки (кадры cand/B, зерно 4196): классика | HD сейчас (в паке) | новое на сцене,
в полный размер (k=4, x2 без сглаживания). Сцены: основная семья PORTUFO21, INDUSTRIALSLUM05; перекраски - свои блоки. В мод ничего
не ставит.
    py -3.13 tools\hdart\t418_final.py
Выход: art/_review/tickets_2026-10-30/t418_final.png, t418_final_recolors.png"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from PIL import Image                      # noqa: E402
import ticket_scene as ts                  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
CAND = os.path.join(ROOT, "art", "tickets", "t418", "cand", "B")
REV = os.path.join(ROOT, "art", "_review", "tickets_2026-10-30")
KEYS = [("PORTROADS", 34), ("MILURBITSEXT", 18), ("MILWARE", 45), ("MILWAREGHOUL", 44), ("XBITSUFO", 44)]
MAIN = [("PORTUFO21", "PORTTFTD5", "PORTUFO21", ("PORTROADS", 34)),
        ("INDUSTRIALSLUM05", "INDUSTRIALSLUM", "INDUSTRIALSLUM05", ("PORTROADS", 34))]
RECOLOR = [("GOVBASE_D_02 (MILURBITSEXT:18)", "GOVT_BASE_DEFENSE", "GOVBASE_D_02", ("MILURBITSEXT", 18)),
           ("CHEMTOWN52 (MILWARE:45)", "CHEMTOWN", "CHEMTOWN52", ("MILWARE", 45)),
           ("CHEMTOWN52 гули (MILWAREGHOUL:44)", "CHEMTOWNGHOUL", "CHEMTOWN52", ("MILWAREGHOUL", 44)),
           ("CARGO00 (XBITSUFO:44)", "CARGO_LINER", "CARGO00", ("XBITSUFO", 44))]
ZOOM = 2


def load_family():
    return {k: Image.open(os.path.join(CAND, "%s_%d.png" % k)).convert("RGBA") for k in KEYS}


def panels_for(sc, name, terrain, block, key, ov, w=88, h=64):
    found = ts.find_cells(sc, terrain, block, [key])
    cell = max(found, key=lambda f: (-f[3], f[2][1]))
    box = ts.window([(cell[0], cell[1], tuple(v * 4 for v in cell[2]))], w, h, 4)
    out = []
    for title, mode, o in (("классика", "classic", None), ("HD сейчас", "hd", None), ("новое (зерно 4196)", "hd", ov)):
        im, _f = sc.render(terrain, block, mode, override=o, k=4, maxz=cell[3])
        im = ts.crop_pad(im, box)
        im = im.resize((im.width * ZOOM, im.height * ZOOM), Image.NEAREST)
        out.append(("%s: %s" % (name, title), im))
    return out


def vstack(rows, path, gap=8):
    W = max(sum(p.width for _t, p in r) + gap * (len(r) + 1) for r in rows)
    H = sum(max(p.height for _t, p in r) + 34 + gap for r in rows) + gap
    sh = Image.new("RGB", (W, H), (12, 12, 14))
    y = gap
    for r in rows:
        x = gap
        for t, p in r:
            lab = ts.label(p.convert("RGB"), t, 24)
            sh.paste(lab, (x, y))
            x += p.width + gap
        y += max(p.height for _t, p in r) + gap
    sh.save(path)
    print("лист:", path, sh.size)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sc = ts.Scene()
    fam = load_family()
    ov = {k: v for k, v in fam.items()}
    rows = [panels_for(sc, n, t, b, k, ov) for n, t, b, k in MAIN]
    vstack(rows, os.path.join(REV, "t418_final.png"))
    rows = [panels_for(sc, n, t, b, k, ov) for n, t, b, k in RECOLOR]
    vstack(rows, os.path.join(REV, "t418_final_recolors.png"))


if __name__ == "__main__":
    main()
