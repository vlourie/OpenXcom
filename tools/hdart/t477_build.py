#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000477, камин целиком: кандидаты из зёрен t477_gen.py и листы. В МОД НИЧЕГО НЕ СТАВИТ.

  seeds                       листы зёрен (стопка рядом с одобренным верхом 3802) -> art/_review/tickets_2026-11-02/t477_v2_seeds_*.png
  build --v1 10=4781 8=4791 --v2 10=4782 8=4792
                              кандидаты art/tickets/t477/cand_v2/V1|V2/<НАБОР>_<кадр>.png (низ :10, звено :8, копии MEDIEVAL:26/:24;
                              верх :9/MEDIEVAL:25 - уже стоящий 3802, для листа берётся из установки) + листы в census/tickets/XP-000477/files/
Альфа - clip_smooth из t379_391_gen (силуэт классики x4, спрямлённый xBRZ, R-121).
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (HERE, os.path.join(HERE, "..")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np                                    # noqa: E402
from PIL import Image                                 # noqa: E402

import t379_391_gen as m                              # noqa: E402
import t405_409_gen as g                              # noqa: E402
import ticket_scene as ts                             # noqa: E402
import t477_edge as ed                                # noqa: E402
import t477_tone as tn                                # noqa: E402

GEN = os.path.join(ROOT, "art", "tickets", "t477", "gen_v2")
CAND = os.path.join(ROOT, "art", "tickets", "t477", "cand_v2")
REV = os.path.join(ROOT, "art", "_review", "tickets_2026-11-02")
FILES = os.path.join(ROOT, "census", "tickets", "XP-000477", "files")
JOB = {10: "chim10v2", 8: "chim8v2"}
COPY = {10: ("MEDIEVAL", 26), 8: ("MEDIEVAL", 24)}
SHIFT = 96     # один уровень, x4


def seed_frame(f, seed):
    cut = Image.open(os.path.join(GEN, JOB[f], "%d.png" % seed)).convert("RGBA").crop((0, 0, 128, 160))
    im, out = m.clip_smooth(cut, g.classic_of("WESTFLOOR", f))
    im = tn.tone(im, f)
    im = ed.repaint_v(im) if f == 10 else ed.repaint_v(im, 14, 11)
    return im


def stack(frames, order, k_nearest=False):
    """frames {номер: RGBA 128x160}; order - снизу вверх, например [10, 9] или [10, 8, 8, 9]."""
    n = len(order)
    cv = Image.new("RGBA", (128, 160 + SHIFT * (n - 1)), (0, 0, 0, 0))
    for i, f in enumerate(order):
        cv.alpha_composite(frames[f], (0, SHIFT * (n - 1 - i)))
    return cv


def classic_frames():
    return {f: g.classic_of("WESTFLOOR", f).resize((128, 160), Image.NEAREST) for f in (8, 9, 10)}


def now_frames():
    return {f: g.hd_now("WESTFLOOR", f) for f in (8, 9, 10)}


def cand_frames(sel):
    fr = dict(now_frames())
    for f, seed in sel.items():
        fr[f] = seed_frame(f, seed)
    return fr


def panel(im, w=300):
    bg = Image.new("RGBA", im.size, (36, 36, 40, 255))
    bg.alpha_composite(im)
    return bg.resize((w, int(round(im.height * w / im.width))), Image.NEAREST if im is None else Image.LANCZOS)


def mean_brick(im, rows):
    a = np.asarray(im).astype(float)
    sl = a[rows[0]:rows[1]]
    m_ = sl[..., 3] > 250
    return tuple(int(v) for v in sl[m_][:, :3].mean(0))


def do_seeds():
    f9 = Image.open(os.path.join(ROOT, "art", "tickets", "t379", "cand", "WESTFLOOR_9.png")).convert("RGBA")
    for f in [x for x in (10, 8) if os.path.isdir(os.path.join(GEN, JOB[x]))]:
        panels = []
        cl = classic_frames()
        panels.append(("классика", panel(stack(cl, [f, 9]).resize((128, 160 + SHIFT), Image.NEAREST))))
        panels.append(("сейчас", panel(stack(now_frames(), [f, 9]))))
        seeds = [s for s in m.g.JOBS.get(JOB[f], {}).get("seeds", [])] if False else []
        for fn in sorted(os.listdir(os.path.join(GEN, JOB[f]))):
            if fn.endswith(".png"):
                seeds.append(int(fn[:-4]))
        for s in seeds:
            fr = dict(now_frames()); fr[f] = seed_frame(f, s); fr[9] = f9
            panels.append(("зерно %d" % s, panel(stack(fr, [f, 9]))))
        p = os.path.join(REV, "t477_v2_seeds_%d.png" % f)
        ts.sheet(panels, p, cols=4)
        print("лист:", p)


def scene_panel(sc, terrain, block, override, mode, box):
    im, _ = sc.render(terrain, block, mode, override=override, k=4)
    return ts.crop_pad(im, box)


def do_build(v1, v2):
    os.makedirs(REV, exist_ok=True)
    variants = {"V1": v1, "V2": v2}
    for name, sel in variants.items():
        if not sel:
            continue
        d = os.path.join(CAND, name)
        os.makedirs(d, exist_ok=True)
        for f, seed in sel.items():
            im = seed_frame(f, seed)
            im.save(os.path.join(d, "WESTFLOOR_%d.png" % f))
            cls = g.classic_of(*("MEDIEVAL", COPY[f][1]))
            assert g.same_px(g.classic_of("WESTFLOOR", f), cls)
            im.save(os.path.join(d, "%s_%d.png" % COPY[f]))
            print(name, "WESTFLOOR:%d зерно %d, копия %s:%d" % (f, seed, COPY[f][0], COPY[f][1]))
    # лист кадров: классика x4 | сейчас | V1 | V2; ряды: короткий камин 10+9 и длинный 10+8+8+9
    rows = []
    for order in ([10, 9], [10, 8, 8, 9]):
        cols = [("классика x4", classic_frames()), ("сейчас", now_frames())]
        for name, sel in variants.items():
            if sel:
                cols.append(("%s %s" % (name, " ".join("%d:%d" % kv for kv in sel.items())), cand_frames(sel)))
        row = []
        for t, fr in cols:
            if t.startswith("классика"):
                im = stack(fr, order)
                im = im.resize((im.width, im.height), Image.NEAREST)
            else:
                im = stack(fr, order)
            row.append((t + " (" + "+".join(str(o) for o in order) + ")", panel(im, 320)))
        rows.extend(row)
    ncol = 2 + sum(1 for s in variants.values() if s)
    p = os.path.join(FILES, "sheet_chimney_v2_frames.png")
    ts.sheet(rows, p, cols=ncol)
    print("лист:", p)
    # лист сцены: блок игрока (WESTOWN_05: :10 на полу, :9 над ним) и длинный камин (WESTOWN_11: 10, 8, 8, 9)
    sc = ts.Scene()
    panels = []
    for terrain, block, (w, h) in (("WESTOWN_MUD", "WESTOWN_05", (190, 135)),):
        f = ts.find_cells(sc, terrain, block, [("WESTFLOOR", 10), ("WESTFLOOR", 9)])
        box = ts.window([(a[0], a[1], tuple(v * 4 for v in a[2])) for a in f], w, h, 4)
        print('окно', box, [(a[0], a[1], a[2], a[3]) for a in f])
        for t, mode, ov in (("классика", "classic", None), ("HD сейчас", "hd", None)):
            panels.append((t, scene_panel(sc, terrain, block, ov, mode, box)))
        for name, sel in variants.items():
            if sel:
                ov = {("WESTFLOOR", f): seed_frame(f, s) for f, s in sel.items()}
                for f in sel:
                    ov[COPY[f]] = ov[("WESTFLOOR", f)]
                panels.append((name + " " + " ".join("%d:%d" % kv for kv in sel.items()),
                               scene_panel(sc, terrain, block, ov, "hd", box)))
    p = os.path.join(FILES, "sheet_chimney_v2_scene.png")
    ts.sheet(panels, p, cols=2)
    print("лист:", p)


def parse(items):
    out = {}
    for it in items or []:
        a, b = it.split("=")
        out[int(a)] = int(b)
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["seeds", "build"])
    ap.add_argument("--v1", nargs="*")
    ap.add_argument("--v2", nargs="*")
    a = ap.parse_args()
    if a.cmd == "seeds":
        do_seeds()
    else:
        do_build(parse(a.v1), parse(a.v2))


if __name__ == "__main__":
    main()
