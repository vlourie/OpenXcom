#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000410 (трава тропиков MOUNTTROP 0-3, FORESTRED:4): КАНДИДАТЫ по выбору Vitali 30.10 «вариант C - одной основой».
В МОД НИЧЕГО НЕ СТАВИТ: заготовки - art/tickets/t410/cand/<вариант>/<НАБОР>_<кадр>.png (RGBA 128x160), сырые и вырезанные
ответы - art/tickets/t410/gen/, листы - art/_review/tickets_2026-10-30/t410_*.png.

Три файла:
  t410_gen.py    общие константы, классика, ПРОБЫ по одной клетке (задания f0-f2 вид «пол», o0-o2 вид «предмет») - путь отвергнут:
                 модель рисует цельный ромб 4:3 с ободом и стеблями не над ромбом, а внутри (R-545); кадры проб лежат в gen/f*, gen/o*.
  t410_fld.py    РЕНДЕР: поле 6x6 клеток одной картинкой, Qwen-Image-2.1 strict (40 шагов, cfg 4, 1 Мп), вход - поле из кадров
                 классики на подложке (клетки наполовину зеркальные, R-118), ракурс и свет - ТОЛЬКО battle_view (вид floor).
                 Поля: g - все клетки кадр 0 (трава), s - кадр 2 (земля со стеблями), p - кадр 1, m - вперемешку 0/1/2.
  t410_build.py  сборка кандидатов из окон полей (G<g>S<s>: трава и земля по маске земли классики кадра; M<зерно>: окна поля m),
                 проверки швов (checks), листы (sheet, scene).

    py -3 tools\gpuq.py add --name t410-fld --prio 1 -- tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\t410_fld.py render --fields g s
    py -3.13 tools\hdart\t410_build.py build --variants G4401S4411 G4402S4412
    py -3.13 tools\hdart\t410_build.py sheet --variants G4401S4411 G4402S4412 --out art\_review\tickets_2026-10-30\t410_cand.png
    py -3.13 tools\hdart\t410_build.py scene --variants G4401S4411 G4402S4412
    py -3.13 tools\hdart\t410_build.py checks --variants G4401S4411 G4402S4412
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
from PIL import Image, ImageFilter                   # noqa: E402

STEPS, CFG, MP, ZOOM, SOFT, PAD, TONE = 40, 4.0, 1.0, 16, 40, 3, 0.7
GEN = os.path.join(ROOT, "art", "tickets", "t410", "gen")
CAND = os.path.join(ROOT, "art", "tickets", "t410", "cand")
REV = os.path.join(ROOT, "art", "_review", "tickets_2026-10-30")
SET = "mounttrop"

BLADES = ("upright green grass blades of many shades from deep green to bright light green, a few red-brown specks "
          "and a few thin grey-pink dry stalks")
JOBS = {}


def add(name, frame, kind, what, tail, neg, seeds):
    JOBS[name] = dict(frame=frame, kind=kind, what=what, tail=tail, neg=neg, seeds=seeds)


# --- вариант F: вид «пол» (ромб - содержание), стебли поднимаются над ромбом --------------------------------------
TAIL_F = ("Output one isolated patch of ground on the same flat panel: the ground fills the whole diamond to its "
          "edges, evenly, with no border, no frame, no dark rim and no darkening towards the edges; the blades stand "
          "up above the upper edges of the diamond exactly where the sketch shows them, with a ragged uneven outline "
          "against the panel. No other objects, no text.")
NEG_F = ("dark rim, dark outline, vignette, edge darkening, flowers, mushrooms, rocks, stones, bush, flat mowed lawn, "
         "straight cut edge, diamond frame")
add("f0", 0, "floor", "a ground tile entirely covered with dense lush " + BLADES + ", the blades rise above the diamond",
    TAIL_F, NEG_F, [4101, 4102])
add("f1", 1, "floor", "a ground tile of brown earth about half covered with lush " + BLADES + " in the upper part, bare "
    "brown soil in the lower left, the blades rise above the diamond", TAIL_F, NEG_F, [4111, 4112])
add("f2", 2, "floor", "a ground tile of bare brown earth with a few thin upright green grass stalks and dry stems "
    "standing up from it and rising above the diamond", TAIL_F, NEG_F, [4121, 4122])
# --- вариант O: вид «предмет» (куртина травы на ромбе-направляющей) ---------------------------------------------
TAIL_O = ("The tile diamond named above is only a placement guide: draw no slab, no border and no rim, the grass and "
          "soil fill the whole diamond edge to edge and the blades rise above it with a ragged outline. Output one "
          "isolated patch on the same flat panel. No other objects, no frame, no text.")
add("o0", 0, "object", "a dense carpet of lush " + BLADES + ", filling the whole diamond edge to edge, blades rising "
    "above it", TAIL_O, NEG_F, [4201, 4202])
add("o1", 1, "object", "a carpet of brown earth about half covered with lush " + BLADES + " in the upper part, bare "
    "brown soil in the lower left, filling the whole diamond edge to edge, blades rising above it", TAIL_O, NEG_F,
    [4211, 4212])
add("o2", 2, "object", "bare brown earth filling the whole diamond edge to edge with a few thin upright green grass "
    "stalks and dry stems rising above it", TAIL_O, NEG_F, [4221, 4222])


def world():
    import map_mockup as mm
    return mm.World()


def classic(s, f):
    return world().sprite(s.lower(), f, None).convert("RGBA")


def padded_box(img, pad=PAD):
    bb = img.split()[3].getbbox()
    return (max(0, bb[0] - pad), max(0, bb[1] - pad), min(img.width, bb[2] + pad), min(img.height, bb[3] + pad))


def build_prompt(job):
    import battle_view as bv
    import probe_object as po
    import ticket_q21_probe as q
    J = JOBS[job]
    kind = J["kind"]
    pb = bv.prompt_block(kind)
    what = J["what"]
    noun = "ground tile" if kind == "floor" else "patch"
    text = (q.PANEL_HINT.replace("{what}", what) + bv.view_sentence(kind) + " "
            + q.KEEP.replace("{noun}", noun).replace("{what}", what) + bv.light_sentence(kind) + " " + J["tail"])
    neg = po.NEGATIVE.replace("ground, grass tile, floor, ", "") + ", " + pb["negative"] + ", " + J["neg"]
    if kind == "object":
        neg += ", " + q.SLAB_NEG
    return text, neg


def cut_seed(job, seed):
    """Сырой ответ -> кадр x4 с альфой (cut_out, match_tone), без видеокарты."""
    import probe_object as po
    J = JOBS[job]
    full = classic("MOUNTTROP", J["frame"])
    box = padded_box(full)
    frame = full.crop(box)
    hd = Image.open(os.path.join(GEN, job, "raw", "%d.png" % seed)).convert("RGB")
    part = po.match_tone(po.cut_out(hd, frame, 2, SOFT, max_aspect=1.3), frame, TONE)
    cut = Image.new("RGBA", (full.width * 4, full.height * 4), (0, 0, 0, 0))
    cut.paste(part, (box[0] * 4, box[1] * 4))
    cut.save(os.path.join(GEN, job, "%d.png" % seed))


def do_render(jobs):
    import argparse as ap2
    import probe_object as po
    ns = ap2.Namespace(models=po.gen_hd.DEFAULT_MODELS_DIR, qwen21_model="", qwen21_steps=STEPS, qwen21_cfg=CFG,
                       qwen21_mp=MP, qwen21_strength=0.0, qwen21_offload="model", qwen21_thrifty=False, qwen21_ref="",
                       qwen21_ref_mp=1.0, qwen21_prompt="strict", qwen21_hint="off", qwen21_ref_order="ref-first")
    painter = po.gen_hd.Qwen21Painter(ns, {"ground": ("", "")})
    args = ap2.Namespace(steps=STEPS, cfg=CFG, mp=MP)
    t0, n = time.time(), 0
    for job in jobs:
        J = JOBS[job]
        sd = os.path.join(GEN, job)
        os.makedirs(os.path.join(sd, "raw"), exist_ok=True)
        text, neg = build_prompt(job)
        print("[%s]\n  PROMPT: %s\n  NEG: %s" % (job, text, neg), flush=True)
        po.gen_fire.NEGATIVE = neg
        full = classic("MOUNTTROP", J["frame"])
        box = padded_box(full)
        frame = full.crop(box)
        panel = po.pick_background(frame)
        src = frame.resize((frame.width * ZOOM, frame.height * ZOOM), Image.BICUBIC)
        flat = Image.new("RGBA", src.size, tuple(panel) + (255,))
        flat.alpha_composite(src)
        for seed in J["seeds"]:
            raw = os.path.join(sd, "raw", "%d.png" % seed)
            if os.path.exists(raw):
                print("[%s] зерно %d уже есть" % (job, seed), flush=True)
                continue
            hd = po.gen_fire.run_pass(painter, args, text, flat.convert("RGB"), seed)
            po.gen_hd.save_png(hd, raw)
            cut_seed(job, seed)
            n += 1
            print("[%s] зерно %d готово (%d), %.0f с" % (job, seed, n, time.time() - t0), flush=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["render", "recut", "prompts"])
    ap.add_argument("--jobs", nargs="*", default=list(JOBS), choices=sorted(JOBS))
    a = ap.parse_args()
    if a.cmd == "prompts":
        for j in a.jobs:
            t, n = build_prompt(j)
            print("[%s]\n  PROMPT: %s\n  NEG: %s" % (j, t, n))
    elif a.cmd == "render":
        do_render(a.jobs)
    else:
        for j in a.jobs:
            for s in JOBS[j]["seeds"]:
                if os.path.exists(os.path.join(GEN, j, "raw", "%d.png" % s)):
                    cut_seed(j, s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
