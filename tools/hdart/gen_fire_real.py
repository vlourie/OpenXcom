#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Огонь с объёмом: Qwen-Image-2.1 дорисовывает готовые ровные кадры огня.

На вход идут не пиксели оригинала 32x40, а уже гладкие HD-кадры петли (gen_fx.py --fire-from,
или превью из art/fx_smooth_preview/ai_in): движение, площадь и цвета в них уже приняты, модель
добавляет только объём и настоящие языки. Одно зерно на всю петлю - кадры одна семья (иначе в игре
дёргается, R-040/gen_fire.py). cfg 4.0 - чтобы работал негатив (при 1.0 он не действует, R-040).

    E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/gen_fire_real.py ^
        --inputs art/fx_smooth_preview/ai_in --out art/fx_smooth_preview/ai_out

Кладёт в --out: <имя входа>_s<зерно>.png - ответ модели как есть (на подложке). Подложку снимает и
кадры выравнивает отдельный шаг без видеокарты.
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import gen_hd                                       # noqa: E402  (он же ставит HF_HOME)
import gen_fire                                     # noqa: E402
from PIL import Image                               # noqa: E402

PROMPT = (
    "<image1> is one animation phase of a burning fire for an isometric strategy game, shown on a flat "
    "grey preview panel. The panel is interface, not part of the sprite. "
    "Redraw this same fire as a realistic, volumetric photographic flame: many distinct sharp flame "
    "tongues with crisp edges, layered in depth, curling and licking upwards, fine flickering detail. "
    "Colours exactly as in <image1>: saturated bright yellow only at the bottom centre, orange body, "
    "red outer tongues, dark red tips. Keep the position, the height, the width and the outline of "
    "<image1>. Flat grey panel around the flame, nothing else."
)
NEGATIVE = ("white core, white flame, washed out, pastel, blurry, soft focus, smeared, blob, cartoon, "
            "pixel art, smoke, soot, black areas, embers on the panel, logs, wood, ground, background "
            "scenery, text, frame, border")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inputs", required=True, help="папка с кадрами петли (PNG RGBA)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--models", default=gen_hd.DEFAULT_MODELS_DIR)
    ap.add_argument("--model", default="")
    ap.add_argument("--seed", default="1234", help="зерна через запятую: по петле на каждое")
    ap.add_argument("--steps", type=int, default=40)
    ap.add_argument("--cfg", type=float, default=4.0)
    ap.add_argument("--mp", type=float, default=1.3)
    ap.add_argument("--zoom", type=int, default=8)
    ap.add_argument("--panel", default="90,90,96")
    ap.add_argument("--offload", default="model", choices=["model", "seq", "none"])
    args = ap.parse_args()

    names = sorted(n for n in os.listdir(args.inputs) if n.lower().endswith(".png"))
    if not names:
        raise SystemExit("нечего рисовать: в %s нет PNG" % args.inputs)
    seeds = [int(s) for s in args.seed.split(",") if s.strip()]
    panel = tuple(int(v) for v in args.panel.split(","))
    os.makedirs(args.out, exist_ok=True)
    todo = [(s, n) for s in seeds for n in names
            if not os.path.exists(os.path.join(args.out, "%s_s%d.png" % (n[:-4], s)))]
    print("кадров %d, зёрен %d, осталось нарисовать %d" % (len(names), len(seeds), len(todo)), flush=True)
    if not todo:
        return

    gen_fire.NEGATIVE = NEGATIVE                     # run_pass берёт негатив оттуда
    ns = argparse.Namespace(models=args.models, qwen21_model=args.model, qwen21_steps=args.steps,
                            qwen21_cfg=args.cfg, qwen21_mp=args.mp, qwen21_strength=0.0,
                            qwen21_offload=args.offload, qwen21_thrifty=False,
                            qwen21_ref="", qwen21_ref_mp=1.0, qwen21_prompt="strict",
                            qwen21_hint="off", qwen21_ref_order="ref-first")
    painter = gen_hd.Qwen21Painter(ns, {"ground": ("", "")})
    t0 = time.time()
    for k, (seed, n) in enumerate(todo, 1):
        frame = Image.open(os.path.join(args.inputs, n)).convert("RGBA")
        src = gen_fire.on_panel(frame, 1, panel).resize((frame.width * args.zoom, frame.height * args.zoom),
                                                        Image.LANCZOS)
        hd = gen_fire.run_pass(painter, args, PROMPT, src, seed)
        gen_hd.save_png(hd, os.path.join(args.out, "%s_s%d.png" % (n[:-4], seed)))
        el = time.time() - t0
        print("%d/%d %s зерно %d | %s, осталось ~%s" % (k, len(todo), n, seed, gen_hd.human_time(el),
                                                       gen_hd.human_time(el / k * (len(todo) - k))), flush=True)
    print("готово за %s" % gen_hd.human_time(time.time() - t0))


if __name__ == "__main__":
    main()
