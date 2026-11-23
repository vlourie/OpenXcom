#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Броня, закрывающая куклу целиком: один слой - вся кукла, тела и головы под ним нет.

Отдача по настоящим сейвам 05.11: JUGGERNAUT_SUIT 1 слой - 32 куклы, DOOM2 - 55 кукол. Три цвета DOOM2 одного силуэта,
различаются кожей рук и лица (мерка 05.11), поэтому рисунок один, цвет каждого слоя - от своей классики (tone_lock).
Сначала показать простым наложением: ничего не прикрывать и не дорисовывать (Vitali 05.11, R-713). В мод не ставит.

    py -3.13 tools\gpuq.py add --name doll_solo -- E:\OpenXCom\tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\doll_armor_solo.py
    E:\OpenXCom\tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\doll_armor_solo.py --dry-run
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import doll_pipe_pilot as P                          # до numpy: пилот ставит окружение модели
import numpy as np
from PIL import Image
import doll_b2_render as db
import doll_paint_pilot as pp
import doll_photo_pilot as dp
import vx_control as vc

OUT = os.path.join(db.ROOT, "art", "doll", "pipe_pilot", "armor_solo")
SEEDS = [0, 1]
STRENGTH = 0.7                                      # как у костюма LOKNAR: 0.85 уводит фигуру уже силуэта (R-712)
PANEL = (14, 14, 18, 255)                           # подложка кадра тёмная: остаток внутри силуэта читается контуром (R-089)
STYLE = P.STYLE.replace("on a flat grey panel", "on a flat very dark panel")
NEGATIVE = pp.NEGATIVE + (", toy, balloon, plastic figurine, cartoon, chibi, grey outline, child, teenager, underage, logo, "
                          "extra arms, extra fingers")
# что на классике - глазами x5, 05.11
ARMORS = {
    "juggernaut": {"names": ["UBERGAL__7__JUGGERNAUT_SUIT"], "text": (
        "{style} A massive suit of heavy powered armour standing with its arms slightly away from the body, no person visible, "
        "filling the outline of the input completely. Battered pale grey steel plates with dents, scratches and black bullet "
        "holes. A round steel helmet with one big dark green glass lens ringed in red and a small green lens beside it, a red "
        "painted slash across the helmet. Huge spiked shoulder plates, thick plated gauntlets, heavy plated legs with black "
        "rubber knee joints. Red painted marks exactly where they are in the input: on the chest, on the left forearm, a skull "
        "on the thigh and on the shin. Realistic worn metal, painted game art, not a photo."), "negative": ", clean shiny chrome, face, skin, hair"},
    "doom2": {"names": ["MHUMAN__2__DOOM2_ARMOR_LIGHT", "MHUMAN__2__DOOM2_ARMOR_DARK", "MHUMAN__2__DOOM2_ARMOR_PINK",
                        "MHUMAN__2__DOOM2_ARMOR_ALLOY"], "text": (
        "{style} A broad-shouldered adult man in his thirties standing with his arms slightly away from the body, in old military "
        "battle gear, filling the outline of the input completely. A round ribbed bronze-brown helmet with a silver visor over the "
        "eyes, the jaw and mouth below it. A sculpted dark blue armoured breastplate with big round dark blue shoulder plates. "
        "Bare muscular arms between the shoulder plates and the hands, in the same colour as the input. Black armoured gloves. "
        "A brown leather belt with pouches and a small green glass stone in the middle. Baggy bright green cloth trousers with "
        "big folds, round brown padded knee guards, brown boots. Realistic materials, painted game art, not a photo."), "negative": ""},
}


def common():
    P.FILES, P.PAL = db.sprite_files(), db.game_palette()


def jobs():
    common()
    res = []
    for key, a in ARMORS.items():
        base = a["names"][0]
        mask = dp.layer_mask(P.FILES, base)
        canvas = Image.new("RGBA", (db.W * dp.K, db.H * dp.K), PANEL)
        bl, _m = dp.b2_layer(base)
        canvas.alpha_composite(bl)
        ctl = vc.control_map(dp.classic(P.FILES, P.PAL, [base]).crop(dp.CROP), dp.Z, "gray")
        for s in SEEDS:
            res.append({"key": key, "tag": "%s_s%d" % (key, s), "seed": P.RUN["seed"] + 200 + s, "prompt": a["text"].format(style=STYLE),
                        "negative": NEGATIVE + a["negative"], "init": P.to8(canvas), "mask": P.mask8(mask, P.RUN["armor"]["grow8"]), "control": ctl})
    return res


def worker(frames, raw):
    painter = None
    for j in frames:
        done = os.path.join(raw, j["tag"] + "_out.png")
        if os.path.exists(done):
            continue
        if painter is None:
            painter = P.Painter([x["prompt"] for x in frames] + [x["negative"] for x in frames])
            print("модель загружена за %d с" % painter.load_s, flush=True)
        try:
            rgb, _s0 = painter.paint(j["init"], j["mask"], j["control"], j["prompt"], j["seed"], STRENGTH, P.RUN["item"]["control"], j["negative"])
        except Exception as e:                      # память карты: новый процесс продолжит
            print("кадр %s упал: %s" % (j["tag"], str(e)[:300]), flush=True)
            sys.exit(75)
        Image.fromarray(rgb).save(done)
        print("  %s готов" % j["tag"], flush=True)


def layers_of(j, rgb8):
    """Ответ кадра -> слои всех цветов: тон от классики этого цвета, альфа - силуэт классики x4."""
    res = {}
    for name in ARMORS[j["key"]]["names"]:
        f4, d0, d1 = P.tone_lock(P.full4(rgb8), [name], dp.layer_mask(P.FILES, name))
        res[name] = P.layer_from(f4, dp.layer_mask(P.FILES, name))
        print("%s %s: тон dE %.1f -> %.1f" % (j["tag"], name, d0, d1), flush=True)
    return res


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="только входы кадров, без карты")
    ap.add_argument("--worker", action="store_true", help="(служебное) рисовать недостающие кадры подряд")
    ns = ap.parse_args()
    raw, out = os.path.join(OUT, "raw"), os.path.join(OUT, "layers")
    os.makedirs(raw, exist_ok=True)
    os.makedirs(out, exist_ok=True)
    frames = jobs()
    if ns.worker:
        worker(frames, raw)
        return
    for j in frames:
        j["init"].convert("RGB").save(os.path.join(raw, j["tag"] + "_in.png"))
        j["mask"].save(os.path.join(raw, j["tag"] + "_mask.png"))
    if ns.dry_run:
        print("входы:", raw, len(frames))
        return
    for attempt in range(3):
        if all(os.path.exists(os.path.join(raw, j["tag"] + "_out.png")) for j in frames):
            break
        r = subprocess.run([sys.executable, os.path.abspath(__file__), "--worker"])
        print("рабочий процесс вышел с кодом %s (попытка %d)" % (r.returncode, attempt + 1), flush=True)
    missing = [j["tag"] for j in frames if not os.path.exists(os.path.join(raw, j["tag"] + "_out.png"))]
    if missing:
        raise SystemExit("не нарисованы: %s" % missing)
    box = tuple(v * dp.K for v in (40, 36, 120, 152))
    W, H = box[2] - box[0], box[3] - box[1]
    bg = (0, 0, 0, 255)
    rows = []
    for key, a in ARMORS.items():
        row = []
        for name in a["names"][:3]:
            c = Image.new("RGBA", (db.W * dp.K, db.H * dp.K), bg)
            c.alpha_composite(dp.classic(P.FILES, P.PAL, [name]).resize(c.size, Image.NEAREST))
            row.append(c.crop(box).convert("RGB"))
        for j in frames:
            if j["key"] != key:
                continue
            ls = layers_of(j, np.asarray(Image.open(os.path.join(raw, j["tag"] + "_out.png")).convert("RGB")))
            for i, (name, im) in enumerate(ls.items()):
                im.save(os.path.join(out, "%s_s%d.png" % (name.lower(), SEEDS[frames.index(j) % len(SEEDS)])))
                if i < 3:
                    c = Image.new("RGBA", im.size, bg)
                    c.alpha_composite(im)
                    row.append(c.crop(box).convert("RGB"))
        rows.append(row)
    sheet = Image.new("RGB", (W * max(map(len, rows)), H * len(rows)), bg[:3])
    for y, row in enumerate(rows):
        for x, t in enumerate(row):
            sheet.paste(t, (x * W, y * H))
    fn = os.path.join(OUT, "armor_solo.png")
    sheet.save(fn)
    print("лист:", fn, sheet.size, flush=True)


if __name__ == "__main__":
    main()
