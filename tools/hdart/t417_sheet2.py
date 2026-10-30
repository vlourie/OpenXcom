#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000417, круг 2: лист t417_cand2.png, листы 2x4, сцены PORTUFO21 / PORTUFO17 и установка выбранного зерна.

Кадры нового круга: art/tickets/t417/cand/n<зерно>/ (из t417_v3.py: нарезка по опорам классики, длинный холст 2x4; зерно 4181-4184).

    py -3.13 tools\hdart\t417_sheet2.py sheet                 лист t417_cand2.png, t417_cand2_2x4.png, сцены t417_cand2_scene_portufo21/17.png
    py -3.13 tools\hdart\t417_sheet2.py install --seed 4181    сухой прогон установки (кадры -> TERRAIN/PORTROADS.PCK/<кадр>.png)
    py -3.13 tools\hdart\t417_sheet2.py install --seed 4181 --yes    установить (под очередью правок, обе копии мода hd)
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                       # noqa: E402
from PIL import Image                    # noqa: E402
import t417_container_gen as g           # noqa: E402

K = g.K
SEEDS = [4181, 4182, 4183, 4184]


def load(d):
    return {f: Image.open(os.path.join(d, "%s_%d.png" % (g.SET, f))).convert("RGBA") for f in g.FRAMES}


def cand(seed):
    return load(os.path.join(g.CAND, "n%d" % seed))


def pilot():
    return load(os.path.join(g.ROOT, "art", "tickets", "t417", "cand_pilot_backup", "s4172"))


def variants(sc):
    return [("классика x4", g.classic_frames(sc)), ("HD сейчас", g.hd_now_frames(sc)), ("пилот 4172", pilot())] + \
           [("новое %d" % s, cand(s)) for s in SEEDS]


def do_sheet(a=None):
    import ticket_scene as ts
    sc = ts.Scene()
    items, W, H = g.make_items(g.C23)
    items4, W4, H4 = g.make_items(g.C24)
    vs = variants(sc)
    full = [(n, g.assemble(f, items, W, H, K, g.BGC)) for n, f in vs]
    zc = 3
    rows = [(n, im) for n, im in full]
    rows += [(n + ": борт слева-снизу", g.zoom_crop(im, (10, 20, 50, 46), zc)) for n, im in full]
    rows += [(n + ": верхняя кромка", g.zoom_crop(im, (12, 8, 52, 28), zc)) for n, im in full]
    rows += [(n + ": нижняя кромка у пола", g.zoom_crop(im, (14, 40, 54, 66), zc)) for n, im in full]
    rows += [(n + ": шов, середина", g.zoom_crop(im, (24, 20, 60, 44), zc)) for n, im in full]
    ts.sheet(rows, os.path.join(g.REV, "t417_cand2.png"), cols=len(vs))
    print("лист", os.path.join(g.REV, "t417_cand2.png"))
    full4 = [(n + ": 2x4", g.assemble(f, items4, W4, H4, K, g.BGC)) for n, f in vs]
    ts.sheet(full4, os.path.join(g.REV, "t417_cand2_2x4.png"), cols=4)
    print("лист", os.path.join(g.REV, "t417_cand2_2x4.png"))
    keys = [(g.SET, f) for f in g.FRAMES]
    ov = {n: {(g.SET, f): im for f, im in fr.items()} for n, fr in vs[2:]}
    for name, terrain, block, (w, h) in (("t417_cand2_scene_portufo21.png", "PORTTFTD5", "PORTUFO21", (150, 110)),
                                         ("t417_cand2_scene_portufo17.png", "PORTTFTD5", "PORTUFO17", (130, 110))):
        found = ts.find_cells(sc, terrain, block, keys)
        zmin = min(f[3] for f in found)
        box = ts.window([(f[0], f[1], tuple(v * K for v in f[2])) for f in found], w, h, K)
        panels = []
        for title, mode, o in [("классика", "classic", None), ("HD сейчас", "hd", None)] + [(n, "hd", ov[n]) for n, _ in vs[2:]]:
            im, _f = ts.Scene.render(sc, terrain, block, mode, override=o, k=K, maxz=zmin)
            panels.append((block + ": " + title, ts.crop_pad(im, box)))
        ts.sheet(panels, os.path.join(g.REV, name), cols=2)
        print("лист", os.path.join(g.REV, name))


def do_install(a):
    if not a.seed:
        raise SystemExit("нужно --seed N: зерно, которое выбрал Vitali")
    d = os.path.join(g.CAND, "n%d" % a.seed)
    files = {}
    for f in g.FRAMES:
        p = os.path.join(d, "%s_%d.png" % (g.SET, f))
        im = Image.open(p)
        if im.size != (128, 160) or im.mode != "RGBA":
            raise SystemExit("%s: ждали RGBA 128x160, а %s %s" % (p, im.mode, im.size))
        files["TERRAIN/%s.PCK/%d.png" % (g.SET, f)] = p
    import build_hd_pack as bp
    man = bp.load()
    for rel, p in files.items():
        old = man["files"].get(rel, {}).get("sha256", "")[:10] or "нет в манифесте"
        print("  %-34s <- n%d/%s  (манифест %s)" % (rel, a.seed, os.path.basename(p), old))
    if not a.yes:
        raise SystemExit("сухой прогон, кадров %d; --yes - записать в мод (под очередью правок)" % len(files))
    import ticket_scene as ts
    n = ts.install_files(files, "t417_sheet2", "XP-000417: контейнер, новый круг (толстые борта, ровный контур)",
                         "Vitali: выбор по листу t417_cand2.png, зерно %d" % a.seed,
                         "t417: жёлтый контейнер PORTROADS 81-86 одной картинкой, толстые борта, ровный контур (6 кадров, зерно %d)" % a.seed)
    print("установлено файлов:", n)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["sheet", "install"])
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    globals()["do_" + a.cmd](a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
