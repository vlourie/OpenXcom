#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000477: камин целиком - низ WESTFLOOR:10 (+ MEDIEVAL:26) и звено ствола WESTFLOOR:8 (+ MEDIEVAL:24, копии классики) -
тем же путём и теми же настройками, что верх печной трубы WESTFLOOR:9 (тикет 379, зерно 3802): модуль t379_391_gen
(Qwen-Image-2.1 strict, 40 шагов, cfg 4, 1 Мп, вход - классика bicubic x16 на подложке pick_background, негатив
probe_object + battle_view, cut_out, match_tone 0.7, nofix без fix_holes, альфа - силуэт классики x4 спрямлённый xBRZ
(clip_smooth)). Ракурс и свет - только battle_view. Кирпич в описании - слово в слово тот же, что у chim9 (тёмно-винный,
тёмный раствор, левая грань чуть светлее правой). В карте камин - стопка: :10 на полу, над ним :8 (один-два раза), сверху :9.
В МОД НИЧЕГО НЕ СТАВИТ: кадры - art/tickets/t477/cand_v2/<НАБОР>_<кадр>.png; зёрна - art/tickets/t477/gen_v2/<задание>.

    py -3.13 tools\hdart\t477_gen.py prompts
    py -3 tools\gpuq.py add --name t477-chim10b -- tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\t477_gen.py render --jobs chim10v2
    py -3.13 tools\hdart\t477_gen.py recut
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (HERE, os.path.join(HERE, "..")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import t379_391_gen as m                              # noqa: E402
import t405_409_gen as g                              # noqa: E402

g.GEN = os.path.join(ROOT, "art", "tickets", "t477", "gen_v2")
m.GEN = g.GEN
os.makedirs(g.GEN, exist_ok=True)

BRICK = ("two side faces of dark wine-red maroon bricks with dark mortar lines, deeply shaded (the left face a "
         "little brighter than the right)")
JOBS = {
    "chim10v2": dict(
        t="477", nofix=True, members=[("WESTFLOOR", 10, (0, 0, 0))], seeds=[4781, 4782, 4783, 4784, 4785, 4786],
        what=("the square brick base block of a chimney that fills the whole tile, a plain block with flush sides: "
              + BRICK + "; the top face of the block is the same dark maroon brickwork laid flat, with no cap, no "
              "rim, no stone slab and no hole; in the lower part of the left face a tall arched fireplace opening "
              "with a rounded top, framed by a narrow arch of grey stone blocks, sooty jet black inside; the right "
              "face is plain brick with no opening"),
        neg=("solid wall without opening, closed arch, door, window, grate, overhanging cornice, ledge, flared "
             "top, stone cap, grey top rim, cream white arch, pink brick, salmon, orange brick, bright red, smoke, "
             "fire, grass, snow, text"), slab=False),
    "chim8v2": dict(
        t="477", nofix=True, members=[("WESTFLOOR", 8, (0, 0, 0))], seeds=[4791, 4792, 4793, 4794, 4795, 4796],
        what=("a square brick chimney shaft block that fills the whole tile, a plain block with flush sides: "
              + BRICK + "; the top face of the block is the same dark maroon brickwork laid flat, with a small "
              "square dark open flue hole in the middle of it, sooty jet black inside, with no stone cap and no "
              "overhanging rim"),
        neg=("solid top without hole, grey stone cap, overhanging cornice, ledge, flared top, pink brick, salmon, "
             "orange brick, bright red, smoke, fire, grass, snow, text"), slab=False),
}
for _j in JOBS.values():
    _j["neg"] = _j["neg"] + ", " + m.SLAB
g.JOBS = JOBS
g.BEST = {}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["prompts", "render", "recut"])
    ap.add_argument("--jobs", nargs="*", default=list(JOBS), choices=sorted(JOBS))
    a = ap.parse_args()
    if a.cmd == "prompts":
        for j in a.jobs:
            t, n = g.build_prompt(j)
            print("[%s]\n  PROMPT: %s\n  NEG: %s" % (j, t, n))
    elif a.cmd == "render":
        g.do_render(a.jobs)
    else:
        g.recut(a.jobs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
