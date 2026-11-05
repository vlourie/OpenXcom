#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""XP-000516 по заметкам Vitali 05-06.11: 4 крылатые ракеты на стенде, тело большое, оперение длинное, держатели широкие.
В МОД НИЧЕГО НЕ СТАВИТ.

Кадры 10 и 11 - один длинный предмет (11 за 10 на (16, -8)), основа rockets4 рисует его целиком; перекраски PLANE2 и
PLANE2R: 119 из нового кадра 11, 118 из нового кадра 10 (art/tickets/hb517/cand/rockets4<A|B>). Листы - art/tickets/hb517/sheets/v4_*.png.

    py -3.13 tools/hdart/hb516_v4.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(os.path.dirname(os.path.dirname(HERE)))

import hb517_build as b                # noqa: E402

JOB = "rockets4"
SEEDS = {"A": 5142, "B": 5141}
X = "XB2BR"
NOSE_FAM = [("PLANE2", 118), ("PLANE2R", 118)]     # пара к 119, ticket_family её не находит: другой цвет зажимов (R-743)


def build():
    t = b.tg()
    for ab, seed in SEEDS.items():
        v = JOB + ab
        pc = b.pieces(JOB, seed)
        for key in ((X, 10), (X, 11)):
            b.put(v, key[0], key[1], b.clip_smooth(pc[key], t.classic_of(*key)))
        for base, fam in ((11, b.ROCKET_FAM), (10, NOSE_FAM)):
            nb = b.cand(v, X, base)
            for key in fam:
                cls = t.classic_of(*key)
                b.put(v, key[0], key[1], b.clip_smooth(t.recolor_to(nb, (X, base), key, layout_free=True), cls))


def sheets():
    import ticket_scene as ts
    sc = ts.Scene()
    A, B = JOB + "A", JOB + "B"
    b.frames_sheet(sc, "v4_rockets_frames.png", "XP-000516 ракеты: оригинал | сейчас | A | B",
                   [(s, f, [("A", b.cand(A, s, f)), ("B", b.cand(B, s, f))])
                    for s, f in ((X, 10), (X, 11), ("PLANE2", 118), ("PLANE2", 119), ("PLANE2R", 118), ("PLANE2R", 119))], Z=3)
    b.scene_sheet(sc, "v4_rockets_scene.png", "XP-000516 карта VES_270, 1-й этаж: классика | сейчас | A | B",
                  [("классика", "classic"), ("HD сейчас", None),
                   ("вариант A", {(X, f): b.cand(A, X, f) for f in (10, 11)}),
                   ("вариант B", {(X, f): b.cand(B, X, f) for f in (10, 11)})],
                  0, (130, 380, 1700, 1040), (2742, 2056))
    b.edge_sheet([("10A", (A, X, 10)), ("11A", (A, X, 11)), ("10B", (B, X, 10)), ("11B", (B, X, 11))],
                 "v4_edges.png", "края крупно x6 (NEAREST), низ и верх")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    build()
    sheets()
