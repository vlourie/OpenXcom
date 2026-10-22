#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000254: ракетная шахта (STR_MISSILE_DEFENSES, BASEBITS 23) - «ракета не лежит на дне шахты, она
стоит, готовая к пуску». Одобренная рисованная шахта (painted/raw/STR_MISSILE_DEFENSES.png) правится Edit-2511:
вместо лежащей по диагонали ракеты - ракета стоймя в круглой шахте, вид строго сверху на её нос; рамка,
пульты, полосы и стиль - как были. Три сида на выбор; альфа - силуэт постройки (gen_base_paint.finish),
одобренное не перезаписывается (тот же порядок, что base_pool_repair.py).

Только через очередь:
    py -3.13 tools/gpuq.py add --name t254-silo --prio 1 --cwd E:/OpenXCom -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/t254_silo_edit.py
Выход art/base_living/pilot/painted_silo<сид>/: raw/, STR_MISSILE_DEFENSES.png и @512;
лист art/tickets/t254/silo_sheet.png (вход | сейчас | три сида). В мод ничего не идёт."""
import os

os.environ["HF_HUB_OFFLINE"] = "1"      # до импорта diffusers (R-145, R-207)

import argparse                         # noqa: E402
import sys                              # noqa: E402
import time                             # noqa: E402

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import gen_base_paint as gp             # noqa: E402

T = "STR_MISSILE_DEFENSES"
SEEDS = (4100, 5200, 6300)
PROMPT = (
    "Edit <image1>. It is a top-down painted picture of a missile silo room in a base-building strategy game, "
    "seen strictly from directly above. Remove the long black missile lying diagonally on the floor and paint "
    "clean floor there. In the middle of the room paint a round open launch shaft with a heavy circular steel rim, "
    "and a missile standing upright inside it, ready for launch, seen from directly above: we look straight down "
    "at its pointed nose cone in the centre, a round dark-grey body around it with a red tip, four short fins "
    "sticking out in a cross at the edge of the body, thin launch rails and clamps on the shaft rim. "
    "Keep everything else exactly as it is: the octagonal golden frame and walls, the consoles, screens, lamps, "
    "cables, the yellow and black hazard stripes, the floor colour, the light and the painted style.")
NEGATIVE = ("missile lying down, diagonal missile, side view of a missile, perspective, people, text, blurry, "
            "smoke, fire, new rooms, moved consoles")
STEPS, CFG = 40, 4.0
SHEET = os.path.join(gp.ROOT, "art", "tickets", "t254", "silo_sheet.png")


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
            d = os.path.join(gp.OUT, "painted_silo%d" % seed)
            os.makedirs(os.path.join(d, "raw"), exist_ok=True)
            raw.save(os.path.join(d, "raw", T + ".png"))
            gp.finish(raw, a4, fac.cols, fac.rows, 32 * gp.K).save(os.path.join(d, T + ".png"))
            gp.finish(raw, a4, fac.cols, fac.rows, gp.MASTER).save(os.path.join(d, T + "@512.png"))
            print("  сид %d: %.0f с (всего %.0f мин)" % (seed, time.time() - ts, (time.time() - t0) / 60), flush=True)
    cells = [("вход (классика)", os.path.join(gp.OUT, "in", T + ".png")),
             ("сейчас", os.path.join(gp.OUT, "painted", T + "@512.png"))]
    cells += [("сид %d" % s, os.path.join(gp.OUT, "painted_silo%d" % s, T + "@512.png")) for s in SEEDS]
    sheet = Image.new("RGB", (len(cells) * 520, 550), (30, 30, 30))
    d = ImageDraw.Draw(sheet)
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 20)
    for i, (label, p) in enumerate(cells):
        d.text((i * 520 + 8, 6), label, fill=(240, 220, 160), font=font)
        if os.path.exists(p):
            im = Image.open(p).convert("RGBA").resize((512, 512), Image.NEAREST if i == 0 else Image.LANCZOS)
            sheet.paste(im, (i * 520 + 4, 34), im)
    os.makedirs(os.path.dirname(SHEET), exist_ok=True)
    sheet.save(SHEET)
    print("лист:", SHEET)
    return 0


if __name__ == "__main__":
    sys.exit(main())
