#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000423: стол вскрытия U_DISEC2 5-9 (туша коровы на столе, голова коровы вместо человеческого черепа). Пилот варианта C
(Vitali 30.10: «голова коровы»): ВЕСЬ стол одной картинкой и нарезка по клеткам, как контейнер 417 (t417_container_gen.py - оттуда
берутся fit_polygon, raster_aa, Lattice, territory_owners, slice_frames, assemble и проверки). В МОД НИЧЕГО НЕ СТАВИТ без
`install --yes` и слова Vitali: кадры - art/tickets/t423/cand/s<зерно>/U_DISEC2_<кадр>.png, листы - art/_review/tickets_2026-10-30/.

Раскладка по карте RETDUNG_10 (и VES_SNAKEBOAT; в D_RET_BASE то же без головы 5):
    столешница 2x2 - 9 (16,3), 7 (17,3), 8 (16,4), 6 (17,4); голова 5 (17,5) отдельной клеткой. Порядок рисования движка 9, 7, 8, 6, 5.
Рецепт как у 417: вход - классика всего стола xBRZ x4 + бикубика x16 на подложке pick_background -> Qwen-Image-2.1 strict (40 шагов,
cfg 4, 1 Мп), ракурс и свет - только battle_view.prompt_block("object"), 3 зерна; контур - ровные прямые по маске классики (R-121),
внутри контура альфа 255 (R-439), свободные сплошные пиксели несут все кадры, чьё окно их содержит (R-547).
Отличия от 417:
  - стол - часть предмета: хвост промпта без «no slab / no base plate», негатив без SLAB_NEG;
  - нижняя кромка у пола (правило 12): пиксели кадра, которые следующая по порядку рисования клетка пола накрывает своим ромбом,
    срезаются прямой по ромбу с отступом FLOOR_INSET пикселей HD (как base_lines в t418) - без ступеньки 8x4 у стыка с полом.

    py -3.13 tools\hdart\t423_carcass_gen.py preview
    py -3 tools\gpuq.py add --name t423-carcass -- tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\t423_carcass_gen.py render
После генерации - t423_post.py (build | family | sheet | cand | install): ответ модели рисует стол уже и мельче классики, поэтому габарит по bbox
не годится - подгонка оптическим потоком по силуэтам (flow_fit), потом нарезка 417, срез у пола, перекраски GOLD.
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (HERE, os.path.join(HERE, "..")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np                                   # noqa: E402
from PIL import Image                                # noqa: E402
import t417_container_gen as g                       # noqa: E402

SET = "U_DISEC2"
SEEDS = [4231, 4232, 4233]
SEEDS_R2 = [4241, 4242, 4243]          # круг 2 (Vitali 30.10: голова перевёрнута, лежит на темечке, рот сверху)
K = g.K
GEN = os.path.join(ROOT, "art", "tickets", "t423", "gen")
CAND = os.path.join(ROOT, "art", "tickets", "t423", "cand")
REV = os.path.join(ROOT, "art", "_review", "tickets_2026-10-30")
# клетки по карте RETDUNG_10: (кадр, колонка, ряд) = (кадр, x - 16, y - 3), в порядке рисования движка (y, потом x)
CELLS = [(9, 0, 0), (7, 1, 0), (8, 0, 1), (6, 1, 1), (5, 1, 2)]
FRAMES = [5, 6, 7, 8, 9]
FLOOR_INSET = 1.0            # пикселей HD: на сколько срез у пола отступает от ромба соседней клетки
# настройка t417 под этот стол
g.SET, g.C23, g.FRAMES, g.GEN, g.CAND, g.REV = SET, CELLS, FRAMES, GEN, CAND, REV
g.TONE = 0.7

WHAT = ("a skinned cow carcass lying on its back on a mortuary dissection table. The carcass is flayed, the raw muscle is "
        "tan-beige with darker brown shading, the belly faces up and the four legs stick up into the air, bent, each leg "
        "ending in a red cut stump. At the lower left end of the carcass the beige head of the cow hangs over the end of the "
        "table: a long cow muzzle pointing down to the lower left, one dark eye, one dark nostril, a short ear, no horns, "
        "no skull. The table is a low, wide, rounded pale cream-white tray with thick side walls, a raised rim and a thin "
        "lilac blood groove running along its top")
WHAT_R2 = ("a skinned cow carcass lying on its back on a mortuary dissection table. The carcass is flayed, the raw muscle is "
           "tan-beige with darker brown shading, the belly faces up and the four legs stick up into the air, bent, each leg "
           "ending in a red cut stump. At the lower left end of the carcass the beige head of the cow hangs over the end of the "
           "table, UPSIDE DOWN: the cow head is turned over and rests on the top of its skull (the poll), so the lower jaw and "
           "the open-lipped mouth face UP, the nostrils face up and outward, the chin points up and to the left, the ears hang "
           "down under the head, the eye is closed and seen from below the brow; long cow muzzle, no horns, no skull. The "
           "table is a low, wide, rounded pale cream-white tray with thick side walls, a raised rim and a thin lilac blood "
           "groove running along its top")
NEG_R2 = ", head facing the viewer, forehead facing up, face looking up, head lying on its cheek, head resting on its chin, normal head"
NEG = ("human skull, skeleton, bones, teeth, grin, eye sockets, alien head, cylinder, tube, flasks, bottles, jars, hole, "
       "horns, antlers, living animal, fur, hide, skin on the legs, knife, surgeon, people, robot arms, text, labels, "
       "blood puddle, floor, ground, wall, extra table")
TAIL = ("The tile diamonds named above are only invisible placement guides: the dissection table is part of the object and is "
        "drawn together with the carcass and the head, as one object. Output one isolated object on the same flat panel. "
        "No floor, no ground, no other objects, no frame, no text.")


def prompt(r2=False):
    import battle_view as bv
    import ticket_q21_probe as q
    import probe_object as po
    pb = bv.prompt_block("object")
    what = WHAT_R2 if r2 else WHAT
    text = (q.PANEL_HINT.replace("{what}", what) + bv._sentence(pb["positive"]) + " "
            + q.KEEP.replace("{noun}", "object").replace("{what}", what) + TAIL)
    neg = po.NEGATIVE + ", " + pb["negative"] + ", " + NEG + (NEG_R2 if r2 else "")
    return text, neg


def model_input(sc):
    """Вход модели: классика всего стола (k=1) -> xBRZ x4 -> бикубика x16 на подложке (long_object.model_input, R-121)."""
    import long_object as lo
    items, W, H = g.make_items(CELLS)
    full = g.compose_k1(sc, items, W, H)
    box = g.padded_box(full)
    frame = full.crop(box)
    return full, box, frame, lo.model_input(frame, g.ZOOM, "xbrz")


def do_preview(a=None):
    import ticket_scene as ts
    sc = ts.Scene()
    full, box, frame, flat = model_input(sc)
    os.makedirs(os.path.join(GEN, "raw"), exist_ok=True)
    flat.convert("RGB").save(os.path.join(GEN, "raw", "input.png"))
    t, n = prompt(getattr(a, "r2", False))
    print("холст %dx%d, габарит %s, вход %s\nPROMPT: %s\nNEG: %s" % (full.width, full.height, box, flat.size, t, n))


def do_render(a=None):
    import argparse as ap_
    import ticket_scene as ts
    import probe_object as po
    sc = ts.Scene()
    flat = model_input(sc)[3]
    os.makedirs(os.path.join(GEN, "raw"), exist_ok=True)
    ns = ap_.Namespace(models=po.gen_hd.DEFAULT_MODELS_DIR, qwen21_model="", qwen21_steps=g.STEPS, qwen21_cfg=g.CFG,
                       qwen21_mp=g.MP, qwen21_strength=0.0, qwen21_offload="model", qwen21_thrifty=False, qwen21_ref="",
                       qwen21_ref_mp=1.0, qwen21_prompt="strict", qwen21_hint="off", qwen21_ref_order="ref-first")
    painter = po.gen_hd.Qwen21Painter(ns, {"ground": ("", "")})
    args = ap_.Namespace(steps=g.STEPS, cfg=g.CFG, mp=g.MP)
    text, neg = prompt(a.r2)
    print("PROMPT:", text, "\nNEG:", neg, flush=True)
    po.gen_fire.NEGATIVE = neg
    t0 = time.time()
    for n, seed in enumerate(a.seeds or (SEEDS_R2 if a.r2 else SEEDS), 1):
        dst = os.path.join(GEN, "raw", "%d.png" % seed)
        if os.path.exists(dst):
            print("[%d] зерно %d уже есть" % (n, seed), flush=True)
            continue
        hd = po.gen_fire.run_pass(painter, args, text, flat.convert("RGB"), seed)
        po.gen_hd.save_png(hd, dst)
        print("[%d] зерно %d готово, %.0f с" % (n, seed, time.time() - t0), flush=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["preview", "render", "build", "sheet", "install"])
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--seeds", type=int, nargs="*")
    ap.add_argument("--r2", action="store_true", help="круг 2: голова перевёрнута (WHAT_R2, зёрна 4241-4243)")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    globals()["do_" + a.cmd](a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
