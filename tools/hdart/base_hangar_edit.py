#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Ангар живой базы 22.10: Vitali - «в ангаре на полу нарисован меч ??? там должны быть 4 стрелки в разные
стороны типа место для посадки». Меч пришёл из описания base_rooms.tsv («sword emblem»). Одобренную картинку
не перерисовываем целиком (R-455 - поменяется расстановка): Edit-2511 правит только середину посадочного круга
по сырому ответу painted/raw/STR_HANGAR.png, три сида на выбор; альфа и размеры - как у gen_base_paint.finish.

Только через очередь:
    py -3.13 tools/gpuq.py add --name base-hangar-edit --prio 1 --cwd E:/OpenXCom -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/base_hangar_edit.py
Выход art/base_living/pilot/painted_hangar<сид>/: raw/STR_HANGAR.png, STR_HANGAR.png, STR_HANGAR@512.png;
лист art/base_living/hangar_edit.png (одобренная | три сида). В мод ничего не идёт."""
import os

os.environ["HF_HUB_OFFLINE"] = "1"      # до импорта diffusers (R-145, R-207)

import argparse                         # noqa: E402
import sys                              # noqa: E402
import time                             # noqa: E402

from PIL import Image                   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import gen_base_paint as gp             # noqa: E402

T = "STR_HANGAR"
SEEDS = (4100, 5200, 6300)
PROMPT = (
    "Edit <image1>. It is a top-down painted picture of an aircraft hangar floor in a base-building strategy game. "
    "In the middle of the big round golden-brass landing pad there is a sword emblem: remove the sword completely. "
    "In its place paint two more golden arrows exactly like the existing left and right arrows, one pointing straight "
    "up and one pointing straight down, so the pad shows four identical golden arrows pointing outward to the four "
    "sides (up, down, left, right) from the small ring in its centre - a landing pad marking. Keep everything else "
    "exactly as it is: the same pad, its rim and size, the same red camouflage floor, the walls, the hazard stripes, "
    "the vent, the hoses, the carts and crates in the same places, the same colours, light and painted style.")
NEGATIVE = "sword, blade, dagger, hilt, cross guard, emblem, letters, text, people, aircraft, blurry, deformed arrows"
STEPS, CFG = 40, 4.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="")
    ap.add_argument("--sheet-only", action="store_true", dest="sheet_only", help="только лист, без модели")
    a = ap.parse_args()
    os.chdir(gp.ROOT)
    rules, _ = gp.load_rules()
    fac = gp.Facility(rules[T], gp.sprites_map())
    _img, a4 = gp.facility_input(fac)
    src = Image.open(os.path.join(gp.OUT, "painted", "raw", T + ".png")).convert("RGB")
    if not a.sheet_only:
        import gen_hd
        import item_photo as ip
        import photo_ui as pu
        import torch
        import weapons_probe5 as wp5
        models = a.models or gen_hd.DEFAULT_MODELS_DIR
        ip.edit_model_check(models)
        pu.MODEL = os.path.join(models, "hub", "models--Qwen--Qwen-Image-Edit-2511", "snapshots", ip.EDIT_MODEL_REV)
        t0 = time.time()
        pipe, embeds = wp5.two_phase(models, [(src, PROMPT, NEGATIVE)])
        pe, pm, npe, npm = (t.to(torch.device("cuda")) for t in embeds[0])
        for seed in SEEDS:
            ts = time.time()
            g = torch.Generator("cuda").manual_seed(seed)
            with torch.no_grad():
                raw = pipe(image=[src], prompt=None, prompt_embeds=pe, prompt_embeds_mask=pm,
                           negative_prompt_embeds=npe, negative_prompt_embeds_mask=npm, true_cfg_scale=CFG,
                           num_inference_steps=STEPS, generator=g, width=src.width, height=src.height).images[0]
            d = os.path.join(gp.OUT, "painted_hangar%d" % seed)
            os.makedirs(os.path.join(d, "raw"), exist_ok=True)
            raw.save(os.path.join(d, "raw", T + ".png"))
            gp.finish(raw, a4, fac.cols, fac.rows, 32 * gp.K).save(os.path.join(d, T + ".png"))
            gp.finish(raw, a4, fac.cols, fac.rows, gp.MASTER).save(os.path.join(d, T + "@512.png"))
            print("  сид %d: %.0f с (всего %.0f мин)" % (seed, time.time() - ts, (time.time() - t0) / 60), flush=True)
    # лист: одобренная и три правки, по 512
    cells = [os.path.join(gp.OUT, "painted", T + "@512.png")]
    cells += [os.path.join(gp.OUT, "painted_hangar%d" % s, T + "@512.png") for s in SEEDS]
    sheet = Image.new("RGB", (4 * 520, 520), (30, 30, 30))
    for i, p in enumerate(cells):
        if os.path.exists(p):
            im = Image.open(p).convert("RGBA").resize((512, 512), Image.LANCZOS)
            sheet.paste(im, (i * 520 + 4, 4), im)
    out = os.path.join(gp.ROOT, "art", "base_living", "hangar_edit.png")
    sheet.save(out)
    print("лист:", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
