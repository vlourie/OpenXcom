#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Второй круг XP-000516 и XP-000517 по выбору Vitali 05.11 («Переделать»). В МОД НИЧЕГО НЕ СТАВИТ.

Ракеты: новые зёрна основы rockets, кадры 10, 11 и перекраски PLANE2:119, PLANE2R:119 (art/tickets/hb517/cand/rockets2<A|B>).
Кресла по заметке Vitali: основа chairs2 даёт 37 и 39, кадры 38 и 40 - их зеркала, вся семья из t517_family.tsv
(art/tickets/hb517/cand/chairs2<A|B>). Листы - art/tickets/hb517/sheets/v2_*.png.

    py -3.13 tools/hdart/hb517_v2.py
"""
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(os.path.dirname(os.path.dirname(HERE)))

import numpy as np                     # noqa: E402
from PIL import Image, ImageDraw       # noqa: E402

import hb517_build as b                # noqa: E402

ROCKETS = {"A": 5112, "B": 5114}
CHAIRS = {"A": 5384, "B": 5382}
FAMILY = os.path.join("art", "tickets", "hb517", "chair_family.tsv")
S, X = "U_WALL_G", "XB2BR"


def family():
    """{(набор, кадр): (базовый кадр U_WALL_G, одобрен ли)}: база - кадр с тем же силуэтом классики, а не первый по связи
    (по связи U_WALL02:38 и ему подобные брали чужой разворот: спинка рвалась об чужой силуэт)."""
    t = b.tg()
    masks = {f: np.asarray(t.classic_of(S, f))[..., 3] > 0 for f in (37, 38, 39, 40)}
    best = {}
    with open(FAMILY, encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            s, f = r["член"].rsplit(":", 1)
            key = (s, int(f))
            base = int(r["кадр"].rsplit(":", 1)[1])
            ok = bool(r["одобрен"].strip())
            if key in best:
                best[key] = (best[key][0], best[key][1] or ok)
                continue
            try:
                m = np.asarray(t.classic_of(*key))[..., 3] > 0
                base = max(masks, key=lambda bf: (m & masks[bf]).sum() / max((m | masks[bf]).sum(), 1))
            except TypeError:       # классика не читается: U_WALL02GOLD 35-38 идут по порядку 37-40
                base = 37 + key[1] - 35
            best[key] = (base, ok)
    return best


def build():
    t = b.tg()
    import obj_derive as od
    for ab, seed in ROCKETS.items():
        pc = b.pieces("rockets", seed)
        for key in ((X, 10), (X, 11)):
            b.put("rockets2" + ab, key[0], key[1], b.clip_smooth(pc[key], t.classic_of(*key)))
        n11 = b.cand("rockets2" + ab, X, 11)
        for key in b.ROCKET_FAM:
            cls = t.classic_of(*key)
            b.put("rockets2" + ab, key[0], key[1], b.clip_smooth(t.recolor_to(n11, (X, 11), key, layout_free=True), cls))
    fam = family()
    for ab, seed in CHAIRS.items():
        pc = b.pieces("chairs2", seed)
        base = {}
        for f, mf in ((37, 38), (39, 40)):
            cf, cm = t.classic_of(S, f), t.classic_of(S, mf)
            base[f] = b.clip_smooth(pc[(S, f)], cf)
            base[mf] = b.clip_smooth(od.derive(base[f], cf, cm, "зеркало"), cm)
        v = "chairs2" + ab
        for f, im in base.items():
            b.put(v, S, f, im)
        for (s, f), (bf, _ok) in sorted(fam.items()):
            if s == S and f in base:
                continue
            try:
                cls = t.classic_of(s, f)
            except TypeError:       # классика набора не читается (как MILURBAN:85): кадр в семье как копия базы
                print("классика не читается, копия базы:", s, f, "<-", bf, flush=True)
                b.put(v, s, f, base[bf])
                continue
            b.put(v, s, f, b.clip_smooth(t.recolor_to(base[bf], (S, bf), (s, f)), cls))
        print(v, "кадров", len(os.listdir(os.path.join(b.CAND, v))), flush=True)


def sheets():
    import ticket_scene as ts
    sc = ts.Scene()
    b.frames_sheet(sc, "v2_chairs_frames.png", "XP-000517 кресла U_WALL_G 37-40: оригинал | сейчас | A | B",
                   [(S, f, [("A", b.cand("chairs2A", S, f)), ("B", b.cand("chairs2B", S, f))]) for f in (37, 38, 39, 40)], Z=2)
    ov = {ab: {(S, f): b.cand("chairs2" + ab, S, f) for f in (37, 38, 39, 40)} for ab in "AB"}
    keep38 = {k: v for k, v in ov["A"].items() if k[1] != 38}
    b.scene_sheet(sc, "v2_chairs_scene.png", "XP-000517 карта VES_270, 2-й этаж: классика | сейчас | A | A, но кресло 38 старое",
                  [("классика", "classic"), ("HD сейчас", None), ("вариант A", ov["A"]), ("A, кресло 38 старое", keep38)],
                  2, (1000, 540, 2040, 1240), (3744, 3120))
    b.scene_sheet(sc, "v2_chairs_scene_B.png", "XP-000517 карта VES_270, 2-й этаж: B",
                  [("вариант B", ov["B"])], 2, (1000, 540, 2040, 1240), (3744, 3120))
    b.frames_sheet(sc, "v2_rockets_frames.png", "XP-000516 ракеты: оригинал | сейчас | A | B",
                   [(s, f, [("A", b.cand("rockets2A", s, f)), ("B", b.cand("rockets2B", s, f))])
                    for s, f in ((X, 10), (X, 11), ("PLANE2", 119), ("PLANE2R", 119))], Z=3)
    b.scene_sheet(sc, "v2_rockets_scene.png", "XP-000516 карта VES_270, 1-й этаж: классика | сейчас | A | B",
                  [("классика", "classic"), ("HD сейчас", None),
                   ("вариант A", {(X, f): b.cand("rockets2A", X, f) for f in (10, 11)}),
                   ("вариант B", {(X, f): b.cand("rockets2B", X, f) for f in (10, 11)})],
                  0, (130, 380, 1700, 1040), (2742, 2056))
    b.edge_sheet([("37A", ("chairs2A", S, 37)), ("39A", ("chairs2A", S, 39)), ("37B", ("chairs2B", S, 37)), ("39B", ("chairs2B", S, 39)),
                  ("ракеты 10A", ("rockets2A", X, 10)), ("ракеты 11A", ("rockets2A", X, 11)),
                  ("ракеты 10B", ("rockets2B", X, 10)), ("ракеты 11B", ("rockets2B", X, 11))],
                 "v2_edges.png", "края крупно x6 (NEAREST), низ и верх")
    # семья кресел варианта A: оригинал и новый кадр парами, одобренные прежде подписаны
    fam = family()
    box = b.common_box(sc, [(S, 37), (S, 38), (S, 39), (S, 40)])
    keys = sorted(fam)
    cols, z = 8, 2
    cw, ch = (box[2] - box[0]) * z, (box[3] - box[1]) * z
    rows = (len(keys) + cols - 1) // cols
    im = Image.new("RGB", (cols * (cw * 2 + 14) + 8, rows * (ch + 26) + 8), (12, 12, 14))
    d = ImageDraw.Draw(im)
    for i, (s, f) in enumerate(keys):
        x, y = 8 + (i % cols) * (cw * 2 + 14), 8 + (i // cols) * (ch + 26)
        ok = fam[(s, f)][1]
        d.text((x, y + 2), "%s:%d%s" % (s[:16], f, " одобрен" if ok else ""), fill=(255, 150, 90) if ok else (255, 220, 0), font=b.F(13))
        try:
            im.paste(b.cropped(sc.classic(s, f), box, z, True), (x, y + 20))
        except TypeError:
            d.text((x + 4, y + 40), "оригинал не читается", fill=(160, 160, 160), font=b.F(12))
        im.paste(b.cropped(b.cand("chairs2A", s, f), box, z), (x + cw + 2, y + 20))
    im.save(os.path.join(b.SHEETS, "v2_chairs_family.png"), optimize=True)
    print("семья", len(keys), im.size, "одобренных прежде", sum(1 for v in fam.values() if v[1]))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    build()
    sheets()
