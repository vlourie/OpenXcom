#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000417, круг 3: лист t417_cand3.png, лист 2x4, сцены PORTUFO21 / PORTUFO17 и установка (процедурный контейнер t417_proc.py).

Кадры: art/tickets/t417/cand/p<тег>/ (из t417_proc.py build --tag <тег>).

    py -3.13 tools\hdart\t417_sheet3.py sheet [--tag a]          t417_cand3.png, t417_cand3_2x4.png, t417_cand3_scene_portufo21/17.png
    py -3.13 tools\hdart\t417_sheet3.py install [--tag a]        сухой прогон установки (кадры -> TERRAIN/PORTROADS.PCK/<кадр>.png)
    py -3.13 tools\hdart\t417_sheet3.py install --tag a --yes    установить (под очередью правок, обе копии мода hd) - только после выбора Vitali
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from PIL import Image                    # noqa: E402
import t417_container_gen as g           # noqa: E402

K = g.K


def load(d):
    return {f: Image.open(os.path.join(d, "%s_%d.png" % (g.SET, f))).convert("RGBA") for f in g.FRAMES}


def variants(sc, tag):
    return [("классика x4", g.classic_frames(sc)), ("HD сейчас", g.hd_now_frames(sc)),
            ("новое (процедурно)", load(os.path.join(g.CAND, "p" + tag)))]


def do_sheet(a):
    import ticket_scene as ts
    sc = ts.Scene()
    items, W, H = g.make_items(g.C23)
    items4, W4, H4 = g.make_items(g.C24)
    vs = variants(sc, a.tag)
    full = [(n, g.assemble(f, items, W, H, K, g.BGC)) for n, f in vs]
    zc = 3
    rows = list(full)
    rows += [(n + ": борт слева-снизу", g.zoom_crop(im, (10, 20, 50, 46), zc)) for n, im in full]
    rows += [(n + ": верхняя кромка", g.zoom_crop(im, (12, 8, 52, 28), zc)) for n, im in full]
    rows += [(n + ": нижняя кромка у пола", g.zoom_crop(im, (14, 40, 54, 66), zc)) for n, im in full]
    rows += [(n + ": стык кадров, середина", g.zoom_crop(im, (24, 20, 60, 44), zc)) for n, im in full]
    out = os.path.join(g.REV, "t417_cand3.png")
    ts.sheet(rows, out, cols=len(vs))
    print("лист", out)
    full4 = [(n + ": 2x4", g.assemble(f, items4, W4, H4, K, g.BGC)) for n, f in vs]
    out = os.path.join(g.REV, "t417_cand3_2x4.png")
    ts.sheet(full4, out, cols=len(vs))
    print("лист", out)
    keys = [(g.SET, f) for f in g.FRAMES]
    ov = {vs[2][0]: {(g.SET, f): im for f, im in vs[2][1].items()}}
    for name, terrain, block, (w, h) in (("t417_cand3_scene_portufo21.png", "PORTTFTD5", "PORTUFO21", (150, 110)),
                                         ("t417_cand3_scene_portufo17.png", "PORTTFTD5", "PORTUFO17", (130, 110))):
        found = ts.find_cells(sc, terrain, block, keys)
        zmin = min(f[3] for f in found)
        box = ts.window([(f[0], f[1], tuple(v * K for v in f[2])) for f in found], w, h, K)
        panels = []
        for title, mode, o in [("классика", "classic", None), ("HD сейчас", "hd", None), (vs[2][0], "hd", ov[vs[2][0]])]:
            im, _f = ts.Scene.render(sc, terrain, block, mode, override=o, k=K, maxz=zmin)
            panels.append((block + ": " + title, ts.crop_pad(im, box)))
        out = os.path.join(g.REV, name)
        ts.sheet(panels, out, cols=3)
        print("лист", out)


def do_install(a):
    d = os.path.join(g.CAND, "p" + a.tag)
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
        print("  %-34s <- p%s/%s  (манифест %s)" % (rel, a.tag, os.path.basename(p), old))
    if not a.yes:
        raise SystemExit("сухой прогон, кадров %d; --yes - записать в мод (под очередью правок)" % len(files))
    import ticket_scene as ts
    n = ts.install_files(files, "t417_sheet3", "XP-000417: контейнер, процедурный (та же форма, что в классике, ровные стенки)",
                         "Vitali: выбор по листу t417_cand3.png",
                         "t417: жёлтый контейнер PORTROADS 81-86 - та же форма, что в классике, чётко и ровно (процедурный рисунок, 6 кадров)")
    print("установлено файлов:", n)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["sheet", "install"])
    ap.add_argument("--tag", default="a")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    globals()["do_" + a.cmd](a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
