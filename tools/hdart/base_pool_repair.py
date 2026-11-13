#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Большие продвинутые жилые (бассейн 2x2) 22.10: Vitali - «бассейн и комнатки вокруг - совсем не то а вот в
разрушенной его версии - почти точно». Целый зал делается из одобренного разрушенного (painted/raw/
STR_LIVING_QUARTERS_ADVANCED_LARGE_DAMAGED.png) правкой Edit-2511: убрать дыры, копоть и обломки, починить
пол и мебель, расстановку комнаток и бассейна не трогать. Три сида на выбор; альфа - силуэт целого зала
(gen_base_paint.finish), одобренное не перезаписывается.

Только через очередь:
    py -3.13 tools/gpuq.py add --name base-pool-repair --prio 1 --cwd E:/OpenXCom -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/base_pool_repair.py
Выход art/base_living/pilot/painted_repair<сид>/: raw/, STR_LIVING_QUARTERS_ADVANCED_LARGE.png и @512;
лист art/base_living/pool_repair.png (оригинал | разрушенный | три сида). В мод ничего не идёт."""
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

T = "STR_LIVING_QUARTERS_ADVANCED_LARGE"
SRC = T + "_DAMAGED"
SEEDS = (4100, 5200, 6300)
PROMPT = (
    "Edit <image1>. It is a top-down painted picture of a large luxury living quarters hall in a base-building "
    "strategy game, damaged in a battle. Repair it completely: remove every black blast crater and hole, the "
    "scorch marks, cracks, rubble and debris, and paint clean intact floor there that matches the floor around it; "
    "mend any broken furniture. Keep everything else exactly as it is: the same layout of the small rooms, beds, "
    "desks and furniture in the same places, the same long blue pool in the middle with the green hedges on both "
    "sides, the same orange floor paths, the same walls and golden frame, the same colours, light and painted style.")
NEGATIVE = ("crater, hole, scorch, burn marks, debris, rubble, cracks, damage, smoke, people, text, blurry, "
            "new rooms, moved furniture")
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
    src = Image.open(os.path.join(gp.OUT, "painted", "raw", SRC + ".png")).convert("RGB")
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
            d = os.path.join(gp.OUT, "painted_repair%d" % seed)
            os.makedirs(os.path.join(d, "raw"), exist_ok=True)
            raw.save(os.path.join(d, "raw", T + ".png"))
            gp.finish(raw, a4, fac.cols, fac.rows, 32 * gp.K).save(os.path.join(d, T + ".png"))
            gp.finish(raw, a4, fac.cols, fac.rows, gp.MASTER).save(os.path.join(d, T + "@512.png"))
            print("  сид %d: %.0f с (всего %.0f мин)" % (seed, time.time() - ts, (time.time() - t0) / 60), flush=True)
    cells = [os.path.join(gp.OUT, "in", T + ".png"), os.path.join(gp.OUT, "painted", SRC + "@512.png")]
    cells += [os.path.join(gp.OUT, "painted_repair%d" % s, T + "@512.png") for s in SEEDS]
    sheet = Image.new("RGB", (len(cells) * 520, 520), (30, 30, 30))
    for i, p in enumerate(cells):
        if os.path.exists(p):
            im = Image.open(p).convert("RGBA").resize((512, 512), Image.NEAREST if i == 0 else Image.LANCZOS)
            sheet.paste(im, (i * 520 + 4, 4), im)
    out = os.path.join(gp.ROOT, "art", "base_living", "pool_repair.png")
    sheet.save(out)
    print("лист:", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
