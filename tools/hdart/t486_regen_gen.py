#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""XP-000486: лестница IDT_FARM целиком (19 верх + 18 низ, одна картинка 48x48) - перегенерация одним стилем
(Vitali 04.11: «сделай перегенерацию одним стилем»). Путь серии: Qwen-Image-2.1 strict по эскизу классики,
ракурс и свет - блок battle_view (ticket_q21_probe.build_prompt), как у лестницы VILBAN 21+22 (stairs2).
Пишет ТОЛЬКО ответы модели raw_*.png в art/tickets/t486_regen/raw/ (в мод не пишет); вырезка по силуэту, нарезка
по клеткам, зеркала 14/15 - t486_regen_cut.py, без видеокарты.
Составной: IDT_FARM:19 в (-16,-8) от :18 (obj_series.composites по картам WESTOWN_SALOON и др.).

    tools/hdart/.venv-qwen21/Scripts/python.exe -u tools/hdart/t486_regen_gen.py            (через gpuq.py)
    ... --dry-run     только промпты
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.join(HERE, "..")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
ROOT = os.path.dirname(os.path.dirname(HERE))

from PIL import Image                                # noqa: E402

import map_mockup as mm                              # noqa: E402
import obj_series as osr                             # noqa: E402
import probe_object as po                            # noqa: E402
import ticket_q21_probe as q                         # noqa: E402

OUT = os.path.join(ROOT, "art", "tickets", "t486_regen")
K19, K18 = ("IDT_FARM", 19), ("IDT_FARM", 18)
MEMBERS = [(K19, (-16, -8, 0)), (K18, (0, 0, 0))]
PAD = 3
JOB = dict(
    kind="object", noun="object",
    what="a broad open wooden staircase of eight wide orange plank steps descending from the tall upper left to "
         "the lower right, built on dark brown wooden posts with cross-beams; every step is a separate plank "
         "with open air gaps between the steps, the posts and beams are thin and see-through between the steps",
    neg_extra="long thin ramp, narrow stairs, solid wall, closed side panel, solid block, ladder, handrail")
VARIANTS = [("a", 4861, ""), ("b", 4862, q.SHADE)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=40)
    ap.add_argument("--cfg", type=float, default=4.0)
    ap.add_argument("--mp", type=float, default=1.0)
    ap.add_argument("--zoom", type=int, default=16)
    ap.add_argument("--offload", default="model")
    ap.add_argument("--dry-run", action="store_true", dest="dry")
    args = ap.parse_args()
    raw_dir = os.path.join(OUT, "raw")
    os.makedirs(raw_dir, exist_ok=True)
    world = mm.World()
    spr = {k: world.sprite(k[0], k[1], None).convert("RGBA") for k, _o in MEMBERS}
    comp = {"members": MEMBERS, "spr": spr, "pl": {K19: 0, K18: 0}}
    full, at = osr.compose(comp)
    for suffix, seed, extra in VARIANTS:
        text, neg = q.build_prompt(JOB, extra)
        print("[idtfarm %s] seed %d\n  PROMPT: %s\n  NEG: %s" % (suffix, seed, text, neg), flush=True)
    if args.dry:
        return
    import argparse as ap2
    ns = ap2.Namespace(models=po.gen_hd.DEFAULT_MODELS_DIR, qwen21_model="", qwen21_steps=args.steps,
                       qwen21_cfg=args.cfg, qwen21_mp=args.mp, qwen21_strength=0.0, qwen21_offload=args.offload,
                       qwen21_thrifty=False, qwen21_ref="", qwen21_ref_mp=1.0, qwen21_prompt="strict",
                       qwen21_hint="off", qwen21_ref_order="ref-first")
    painter = po.gen_hd.Qwen21Painter(ns, {"ground": ("", "")})
    run_args = ap2.Namespace(mp=args.mp, steps=args.steps, cfg=args.cfg)
    bb = full.split()[3].getbbox()
    box = (max(0, bb[0] - PAD), max(0, bb[1] - PAD), min(full.width, bb[2] + PAD), min(full.height, bb[3] + PAD))
    frame = full.crop(box)
    t0 = time.time()
    for suffix, seed, extra in VARIANTS:
        p = os.path.join(raw_dir, "raw_idtfarm_%s.png" % suffix)
        if os.path.exists(p):
            print("готово, пропуск:", suffix, flush=True)
            continue
        text, neg = q.build_prompt(JOB, extra)
        po.gen_fire.NEGATIVE = neg
        panel = po.pick_background(frame)
        src = frame.resize((frame.width * args.zoom, frame.height * args.zoom), Image.BICUBIC)
        flat = Image.new("RGBA", src.size, tuple(panel) + (255,))
        flat.alpha_composite(src)
        hd = po.gen_fire.run_pass(painter, run_args, text, flat.convert("RGB"), seed)
        po.gen_hd.save_png(hd, p)
        print("[idtfarm %s] готово, %s" % (suffix, po.gen_hd.human_time(time.time() - t0)), flush=True)
    print("готово за %s, box=%s" % (po.gen_hd.human_time(time.time() - t0), box))


if __name__ == "__main__":
    main()
