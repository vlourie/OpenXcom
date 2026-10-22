#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Вылет корабля 22.10, механизм 3: «взлёт именно ЭТОГО ТИПА корабля, не видя базы» (Vitali). Начальный кадр
ролика: корабль с его HD-картинки педии (тип узнаётся по ней) стоит на круглой площадке в общей шахте старта -
не на базе игрока. Edit-2511 по картинке педии, три сида на корабль. Потом по одобренному кадру видеомодель
снимает взлёт; посадка - тот же ролик назад. Проект: docs/research/craft-launch-2026-10-22.md.

Только через очередь:
    py -3.13 tools/gpuq.py add --name craft-launch-frames --prio 1 --cwd E:/OpenXCom -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/craft_launch_frames.py
Выход art/craft_launch/frames/<корабль>_<сид>.png и лист art/craft_launch/frames_sheet.png. В мод ничего не идёт."""
import os

os.environ["HF_HUB_OFFLINE"] = "1"      # до импорта diffusers (R-145, R-207)

import argparse                         # noqa: E402
import sys                              # noqa: E402
import time                             # noqa: E402

from PIL import Image, ImageDraw        # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

UI = os.path.join(ROOT, "user", "mods", "hd", "hd", "UI")
OUT = os.path.join(ROOT, "art", "craft_launch")
SEEDS = (4100, 5200, 6300)
STEPS, CFG = 40, 4.0

KEEP = ("Keep this exact {what} unchanged: the same shape and proportions, the same {parts}, the same hull colours, "
        "wear, markings and details as in the picture. ")
SHAFT = ("Replace the whole surroundings. The {what} now stands {stand} in the middle of a big round brass launch pad "
         "at the bottom of a tall vertical launch shaft inside a gritty underground pirate base. High above it the "
         "heavy armoured roof doors are sliding open and a strip of night sky with clouds shows through. Amber warning "
         "beacons glow on the shaft walls, yellow-black hazard stripes, steel catwalks, thick cables, a little steam. "
         "Cinematic wide shot from a low angle at the edge of the pad: the whole {what} is fully visible in the middle "
         "of the frame with plenty of free space above it for the take-off. Dramatic film lighting, the same realistic "
         "painted style as the original picture.")
GARAGE = ("Replace the whole surroundings. The {what} now {stand} a big round brass turntable in the middle of a "
          "gritty underground pirate base garage, turned towards a huge armoured gate in the back wall; the gate is "
          "rising and behind it a lit concrete tunnel with a smooth sloped driving ramp without any steps leads up "
          "and away. Amber warning beacons, yellow-black "
          "hazard stripes, oil stains, thick cables, a little exhaust smoke. Cinematic wide shot from a low angle "
          "behind and to the side of the {what}: the whole {what} is fully visible, the open gate and the tunnel ahead "
          "of it. Dramatic film lighting, the same realistic painted style as the original picture.")
NEGATIVE = ("people, person, crew, pilot visible, soldier, face, text, letters, watermark, signature, logo, blurry, "
            "deformed, duplicate vehicle, second aircraft, cropped vehicle, cut off wings, daylight outdoor landscape, "
            "base-building map, top-down view")

# корабль, картинка педии, класс (по maxAltitude рулсета), что, части, как стоит, свой негатив.
# Описание - ТОЛЬКО по картинке педии: 22.10 у МБТ было вписано «tracks», а это ховертанк - модель
# нарисовала гусеницы (Vitali: «у ховертанка НЕТ ГУСЕНИЦ»)
CRAFTS = [
    ("STR_DRAKKAR", "CA_2_CPAL.png", "air", "aircraft", "wings, tail fins, engines and cockpit",
     "on its landing gear, engines idle", ""),
    ("STR_HUEY", "CA_HUEY.png", "low", "helicopter", "fuselage, rotor, tail boom and skids",
     "on its skids, the rotor blades still", ""),
    ("STR_MBT", "MBT.png", "ground", "hover tank",
     "angular hull with flat hover skirts along the sides, turret and long gun, armour plates and pale sand colour",
     "floats half a metre above, on its air cushion with a faint shimmer of air under it, all hatches closed, over",
     "tracks, caterpillar tracks, track links, wheels, road wheels, crew, open hatch, stairs, steps, staircase"),
]


def prompt_for(what, parts, stand, cls):
    head = "Edit <image1>. " + KEEP.format(what=what, parts=parts)
    if cls == "ground":
        return head + GARAGE.format(what=what, stand=stand or "stands on")
    return head + SHAFT.format(what=what, stand=stand)


# второй проход по готовому кадру: экипаж с картинки педии переносится в кадр, негатив его не убирает
# (22.10, МБТ: 4 сида из 4 с людьми на башне)
CLEAN = ("Edit <image1>. Remove all the people from the vehicle: there must be nobody sitting or standing on the "
         "turret or the hull and nobody in the hatches; in their place show closed armoured hatch lids in the same "
         "pale sand colour. Keep everything else exactly as it is: the same vehicle, its shape, the hover cushion, "
         "the gun, the turntable, the garage, the gate, the tunnel, the light and the painted style.")
CLEAN_NEG = "people, person, crew, soldier, head, face, helmet, open hatch, tracks, wheels"


def negative_for(extra):
    return NEGATIVE + (", " + extra if extra else "")


def sheet(crafts, seeds, out_name="frames_sheet.png"):
    cells = []
    for name, pic, *_ in crafts:
        row = [os.path.join(UI, pic)] + [os.path.join(OUT, "frames", "%s_%d.png" % (name, s)) for s in seeds]
        cells.append((name, row))
    W, H = 480, 300
    im = Image.new("RGB", ((len(seeds) + 1) * (W + 8), len(cells) * (H + 30)), (24, 24, 24))
    d = ImageDraw.Draw(im)
    from PIL import ImageFont
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 18)     # у шрифта по умолчанию нет кириллицы
    for r, (name, row) in enumerate(cells):
        for c, p in enumerate(row):
            x, y = c * (W + 8), r * (H + 30)
            if os.path.exists(p):
                im.paste(Image.open(p).convert("RGB").resize((W, H), Image.LANCZOS), (x, y + 26))
            d.text((x + 4, y + 6), (name + "  педия") if c == 0 else "сид %d" % seeds[c - 1], fill=(230, 210, 150), font=font)
    out = os.path.join(OUT, out_name)
    im.save(out)
    print("лист:", out)


def clean(names, models_dir):
    """frames/<имя>.png -> frames/<имя>_clean<сид>.png, два сида на кадр, и лист frames_sheet_clean.png."""
    os.chdir(ROOT)
    import gen_hd
    import item_photo as ip
    import photo_ui as pu
    import torch
    import weapons_probe5 as wp5
    models = models_dir or gen_hd.DEFAULT_MODELS_DIR
    ip.edit_model_check(models)
    pu.MODEL = os.path.join(models, "hub", "models--Qwen--Qwen-Image-Edit-2511", "snapshots", ip.EDIT_MODEL_REV)
    srcs = [Image.open(os.path.join(OUT, "frames", n + ".png")).convert("RGB") for n in names]
    pipe, embeds = wp5.two_phase(models, [(s, CLEAN, CLEAN_NEG) for s in srcs])
    rows = []
    for n, src, emb in zip(names, srcs, embeds):
        pe, pm, npe, npm = (t.to(torch.device("cuda")) for t in emb)
        row = [src]
        for seed in (11, 22):
            g = torch.Generator("cuda").manual_seed(seed)
            with torch.no_grad():
                raw = pipe(image=[src], prompt=None, prompt_embeds=pe, prompt_embeds_mask=pm,
                           negative_prompt_embeds=npe, negative_prompt_embeds_mask=npm, true_cfg_scale=CFG,
                           num_inference_steps=STEPS, generator=g, width=src.width, height=src.height).images[0]
            raw.save(os.path.join(OUT, "frames", "%s_clean%d.png" % (n, seed)))
            row.append(raw)
            print("  %s чистка сид %d" % (n, seed), flush=True)
        rows.append(row)
    W, H = 640, 400
    im = Image.new("RGB", (3 * (W + 8), len(rows) * (H + 8)), (24, 24, 24))
    for r, row in enumerate(rows):
        for c, p in enumerate(row):
            im.paste(p.resize((W, H), Image.LANCZOS), (c * (W + 8), r * (H + 8)))
    im.save(os.path.join(OUT, "frames_sheet_clean.png"))
    print("лист:", os.path.join(OUT, "frames_sheet_clean.png"))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="")
    ap.add_argument("--sheet-only", action="store_true", dest="sheet_only", help="только лист, без модели")
    ap.add_argument("--only", default="", help="через запятую: STR_MBT,...")
    ap.add_argument("--seeds", default="", help="через запятую, вместо 4100,5200,6300")
    ap.add_argument("--sheet", default="frames_sheet.png", help="имя листа в art/craft_launch")
    ap.add_argument("--clean", default="", help="через запятую: готовые кадры frames/<имя>.png - убрать экипаж")
    a = ap.parse_args()
    if a.clean:
        return clean(a.clean.split(","), a.models)
    crafts = [c for c in CRAFTS if not a.only or c[0] in a.only.split(",")]
    seeds = tuple(int(s) for s in a.seeds.split(",")) if a.seeds else SEEDS
    os.chdir(ROOT)
    os.makedirs(os.path.join(OUT, "frames"), exist_ok=True)
    if not a.sheet_only:
        import gen_hd
        import item_photo as ip
        import photo_ui as pu
        import torch
        import weapons_probe5 as wp5
        models = a.models or gen_hd.DEFAULT_MODELS_DIR
        ip.edit_model_check(models)
        pu.MODEL = os.path.join(models, "hub", "models--Qwen--Qwen-Image-Edit-2511", "snapshots", ip.EDIT_MODEL_REV)
        jobs, srcs = [], []
        for name, pic, cls, what, parts, stand, extra in crafts:
            src = Image.open(os.path.join(UI, pic)).convert("RGB")
            srcs.append(src)
            jobs.append((src, prompt_for(what, parts, stand, cls), negative_for(extra)))
        t0 = time.time()
        pipe, embeds = wp5.two_phase(models, jobs)
        for (name, *_), src, emb in zip(crafts, srcs, embeds):
            pe, pm, npe, npm = (t.to(torch.device("cuda")) for t in emb)
            # размер кадра - как у картинки педии, кратно 16
            w, h = src.width // 16 * 16, src.height // 16 * 16
            for seed in seeds:
                ts = time.time()
                g = torch.Generator("cuda").manual_seed(seed)
                with torch.no_grad():
                    raw = pipe(image=[src], prompt=None, prompt_embeds=pe, prompt_embeds_mask=pm,
                               negative_prompt_embeds=npe, negative_prompt_embeds_mask=npm, true_cfg_scale=CFG,
                               num_inference_steps=STEPS, generator=g, width=w, height=h).images[0]
                raw.save(os.path.join(OUT, "frames", "%s_%d.png" % (name, seed)))
                print("  %s сид %d: %.0f с (всего %.0f мин)" % (name, seed, time.time() - ts, (time.time() - t0) / 60),
                      flush=True)
    sheet(crafts, seeds, a.sheet)
    return 0


if __name__ == "__main__":
    sys.exit(main())
