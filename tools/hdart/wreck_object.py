#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Разрушить готовый HD-предмет по оригиналу: чистый рисунок probe_object -> такой же предмет, но разбитый.

Зачем: strict рисует по описанию целый предмет, а в оригинале он разрушен (банкомат URBAN_WASTE 109,
тикеты XP-000217 и XP-000167: Vitali 22.10 «разрушь эту картинку по эталону как у оригинала»). Модель
Qwen-Image-2.1 правит <image1> - ответ strict (<кадр>_strict_1hd.png), а <image2> - оригинальный спрайт
(тот же вход, что видел strict), по нему она берёт, ЧТО и ГДЕ разбито. Силуэт, ракурс и манера - из <image1>.

Вырезка и тон - как у probe_object (cut_out по габариту оригинала, match_tone). Кладёт в
<out>/<набор>/<кадр>_wreck_s<сид>_1hd.png и _cut.png (x4 RGBA). В пак НЕ идёт.

    tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\wreck_object.py --set URBAN_WASTE.PCK --frame 109 ^
        --clean art/_review/tickets_2210/qwen/URBAN_WASTE.PCK/109_strict_1hd.png --what "two red street cash machines" ^
        --damage "screens smashed out, ..." --out art/_review/tickets_2210/wreck --seeds 1,2,3
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
import probe_object as po                           # noqa: E402
from PIL import Image                               # noqa: E402

PROMPT = (
    "<image1> is a detailed hand-painted HD game sprite of {what}, shown on a flat preview panel. "
    "<image2> is the low-resolution original sprite of the very same object: in it the object is wrecked. "
    "The panel is interface, not part of the sprite. "
    "Edit <image1>: keep exactly its position, size, silhouette, camera angle (isometric, from above at 30 "
    "degrees), lighting and painting style, but make the object wrecked the way <image2> shows it - "
    "{damage}. Put the damage where <image2> has its dark holes and brown-orange patches. It stays the same "
    "object, recognisable, not a pile of rubble. Output one isolated object on the same flat panel. "
    "No ground, no tile, no other objects, no frame, no text.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", dest="set_name", required=True)
    ap.add_argument("--frame", type=int, required=True)
    ap.add_argument("--clean", required=True, help="ответ probe_object <кадр>_strict_1hd.png")
    ap.add_argument("--what", required=True)
    ap.add_argument("--damage", required=True)
    ap.add_argument("--seeds", default="1,2,3")
    ap.add_argument("--out", required=True)
    ap.add_argument("--sheets", default="art/TERRAIN")
    ap.add_argument("--models", default=gen_hd.DEFAULT_MODELS_DIR)
    ap.add_argument("--model", default="")
    ap.add_argument("--steps", type=int, default=40)
    ap.add_argument("--cfg", type=float, default=4.0, help="при 1.0 негатив не действует (R-040)")
    ap.add_argument("--mp", type=float, default=1.0)
    ap.add_argument("--zoom", type=int, default=16)
    ap.add_argument("--pad", type=int, default=3, help="как у probe_object: вход strict снят с той же рамки")
    ap.add_argument("--grow", type=int, default=2)
    ap.add_argument("--soft", type=int, default=40)
    ap.add_argument("--tone", type=float, default=0.7)
    ap.add_argument("--offload", default="model", choices=["model", "seq", "none"])
    args = ap.parse_args()

    _set_dir, lay, _hints, sheet = gen_fire.load_set(args.sheets, args.set_name)
    full = gen_fire.frame_of(sheet, lay, args.frame)
    box = (0, 0, full.width, full.height)
    bb = full.split()[3].getbbox()
    if args.pad >= 0 and bb:
        box = (max(0, bb[0] - args.pad), max(0, bb[1] - args.pad),
               min(full.width, bb[2] + args.pad), min(full.height, bb[3] + args.pad))
    frame = full.crop(box)
    panel = po.pick_background(frame)
    # оригинал - тем же гладким входом, что видел strict (R-004)
    orig = frame.resize((frame.width * args.zoom, frame.height * args.zoom), Image.BICUBIC)
    flat = Image.new("RGBA", orig.size, tuple(panel) + (255,))
    flat.alpha_composite(orig)
    orig = flat.convert("RGB")
    clean = Image.open(args.clean).convert("RGB")
    if clean.size != orig.size:
        clean = clean.resize(orig.size, Image.LANCZOS)

    ns = argparse.Namespace(models=args.models, qwen21_model=args.model, qwen21_steps=args.steps,
                            qwen21_cfg=args.cfg, qwen21_mp=args.mp, qwen21_strength=0.0,
                            qwen21_offload=args.offload, qwen21_thrifty=False,
                            qwen21_ref="", qwen21_ref_mp=1.0, qwen21_prompt="strict",
                            qwen21_hint="off", qwen21_ref_order="ref-first")
    painter = gen_hd.Qwen21Painter(ns, {"ground": ("", "")})
    torch = painter.torch
    W, H = gen_hd.qwen21_size(clean.width, clean.height, args.mp)
    prompt = PROMPT.replace("{what}", args.what).replace("{damage}", args.damage)
    print(prompt, flush=True)
    out_dir = os.path.join(args.out, args.set_name)
    os.makedirs(out_dir, exist_ok=True)
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    t0 = time.time()
    for n, seed in enumerate(seeds, 1):
        kw = {"prompt": prompt, "num_inference_steps": args.steps,
              "generator": torch.Generator("cuda").manual_seed(seed)}
        imgs = [clean.resize((W, H), Image.LANCZOS), orig.resize((W, H), Image.LANCZOS)]
        if "image" in painter.accepts:
            kw["image"] = imgs
        elif "images" in painter.accepts:
            kw["images"] = imgs
        else:
            raise SystemExit("конвейер не принимает входные картинки")
        if "negative_prompt" in painter.accepts:
            kw["negative_prompt"] = po.NEGATIVE
        if "true_cfg_scale" in painter.accepts:
            kw["true_cfg_scale"] = args.cfg
        elif "guidance_scale" in painter.accepts:
            kw["guidance_scale"] = args.cfg
        if "width" in painter.accepts:
            kw["width"], kw["height"] = W, H
        hd = painter.pipe(**kw).images[0]
        if hd.mode == "RGBA":
            fl = Image.new("RGB", hd.size, tuple(panel))
            fl.paste(hd, (0, 0), hd)
            hd = fl
        hd = hd.convert("RGB").resize(orig.size, Image.LANCZOS)
        gen_hd.save_png(hd, os.path.join(out_dir, "%d_wreck_s%d_1hd.png" % (args.frame, seed)))
        part = po.match_tone(po.cut_out(hd, frame, args.grow, args.soft), frame, args.tone)
        cut = Image.new("RGBA", (full.width * 4, full.height * 4), (0, 0, 0, 0))
        cut.paste(part, (box[0] * 4, box[1] * 4))
        gen_hd.save_png(cut, os.path.join(out_dir, "%d_wreck_s%d_cut.png" % (args.frame, seed)))
        el = time.time() - t0
        print("сид %d: %s, осталось ~%s" % (seed, gen_hd.human_time(el),
                                           gen_hd.human_time(el / n * (len(seeds) - n))), flush=True)


if __name__ == "__main__":
    main()
