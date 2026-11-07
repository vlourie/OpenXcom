#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Брони из нескольких вещей поверх готовых тел UBERGAL: тело и голова не перерисовываются, кадр общий на броню, разрез по слоям.

Отдача по настоящим сейвам 05.11: GANGER_OUTFIT 3 слоя - 50 кукол, PIR_CASTAWAY 2 - 31, RAGS 2 - 31, TAC_FULL 2 - 26.
CASTAWAY LIGHT и DARK одного силуэта, разница 706 точек из 1752 - кожа под чулками (мерка 05.11): у каждого свой кадр на теле этого цвета (R-725).
Сначала показать простым наложением: ничего не прикрывать и не дорисовывать (Vitali 05.11, R-713). В мод не ставит.

    py -3.13 tools\gpuq.py add --name doll_over -- E:\OpenXCom\tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\doll_armor_over.py
    E:\OpenXCom\tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\doll_armor_over.py --dry-run
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
import doll_armor_solo as S
import doll_b2_render as db
import doll_photo_pilot as dp
import vx_control as vc

OUT = os.path.join(db.ROOT, "art", "doll", "pipe_pilot", "armor_over")
BODIES = os.path.join(db.ROOT, "art", "doll", "pipe_pilot", "layers")
SEEDS = [0, 1]
NEGATIVE = S.NEGATIVE + ", extra limbs, nude, bare breasts"
# looks: первая - под кадр (самая частая у настоящих бойцов), все - на лист.
# Что на классике - глазами x6, 05.11
CASTAWAY = (
    "%s in shipwreck clothes: a torn dirty off-white short-sleeved shirt hanging open with ragged frayed edges and grey stains; a "
    "black leather belt low on the hips with a grey metal clasp in the middle over dirty pale cloth briefs; fine black fishnet "
    "stockings over the skin, torn at different heights; one worn black leather ankle boot on one leg, the other foot "
    "bare under the fishnet") % P.WHO
ARMORS = {
    "ganger": {"looks": ["M28", "M22"], "head": True, "gear": ["UBERGAL__3__BRA_LARGE_BLACK_LACE", "UBERGAL__6__FINGERLESS_GLOVES",
                                                               "UBERGAL__7__GANGER_MAIN", "UBERGAL__8__GANGER_JACKET"], "what": (
        "%s in a biker outfit: an open black leather jacket with long sleeves, padded shoulders and a row of small steel studs along the "
        "open edge, a round steel rivet badge on the chest and on the sleeve; a dark sheer mesh bra under the jacket; black leather "
        "shorts with a wide belt, a small square steel buckle and round steel studs; tall black leather boots above the knee with "
        "round steel studs on the knee and shin, straps round the ankle and worn grey toe caps") % P.WHO, "negative": ""},
    "castaway": {"looks": ["M5"], "head": True, "gear": ["UBERGAL__4__CASTAWAY_OUTFIT_LIGHT"], "what": CASTAWAY, "negative": ", clean new shirt"},
    "rags": {"looks": ["M59", "F20"], "head": True, "gear": ["UBERGAL__1__RAGS_BACK", "UBERGAL__9__RAGS"], "what": (
        "%s wearing a long tattered black cloak of rotten cloth and thick ropy strands of dark brown seaweed hanging from the "
        "shoulders down to the floor, a very dark violet lining inside, one black cloth sleeve, and thick dark coiling tentacles "
        "lying on the floor around her feet with small green wet glints") % P.WHO, "negative": ", clean cloth, fur"},
    "tac": {"looks": ["M3", "M41"], "head": False, "gear": ["UBERGAL__3__PANTIES_HCUT_BLACK", "UBERGAL__8__TAC_SUIT", "UBERGAL__14__TAC_HELMET"], "what": (
        "A person of athletic female build, fully covered by a closed tactical armour suit: a charcoal black flexible undersuit with "
        "segmented glossy bright green armour plates on the chest, stomach, round shoulders, forearms, hips, thighs and ribbed "
        "shins, green plated boots and gloves. A closed rounded green helmet with small side bumps, a narrow dark visor with two "
        "small pale lenses, a ribbed green breathing mask over the mouth and a black padded hood round the helmet"), "negative": ", face, skin, hair"},
    "castaway_dark": {"looks": ["M22", "M59"], "head": True, "gear": ["UBERGAL__4__CASTAWAY_OUTFIT_DARK"], "what": CASTAWAY.replace(
        "over the skin", "over dark brown skin"), "negative": ", clean new shirt, pale skin, orange skin"},
}


def is_done(n):
    return os.path.exists(os.path.join(BODIES, n.lower() + ".png"))


def done_layer(n):
    return Image.open(os.path.join(BODIES, n.lower() + ".png")).convert("RGBA")


def stack(a, i):
    """Слои куклы снизу вверх для внешности номер i - так же их кладёт движок (индекс слота в имени)."""
    look = a["looks"][i]
    names = ["UBERGAL__2__%s_NUDE" % look] + (["UBERGAL__10__HEAD_%s" % look] if a["head"] else [])
    names += a["gear"]
    return sorted(names, key=lambda n: int(n.split("__")[1]))


def visible(names):
    """Точки ещё не готовых вещей, не закрытые готовыми слоями выше: тело и волосы модель не трогает."""
    um = np.zeros((db.H, db.W), bool)
    for k, n in enumerate(names):
        if is_done(n):
            continue
        m = dp.layer_mask(P.FILES, n).copy()
        for x in names[k + 1:]:
            if is_done(x):
                m &= ~dp.layer_mask(P.FILES, x)
        um |= m
    return um


def jobs():
    S.common()
    res = []
    for j, (key, a) in enumerate(ARMORS.items()):
        names = stack(a, 0)
        canvas = Image.new("RGBA", (db.W * dp.K, db.H * dp.K), S.PANEL)
        for n in names:
            canvas.alpha_composite(done_layer(n) if is_done(n) else dp.b2_layer(n)[0])
        ctl = vc.control_map(dp.classic(P.FILES, P.PAL, names).crop(dp.CROP), dp.Z, "gray")
        for s in SEEDS:
            res.append({"key": key, "tag": "%s_s%d" % (key, s), "seed": P.RUN["seed"] + 300 + 10 * j + s, "prompt": P.ARMOR.format(style=S.STYLE, what=a["what"]),
                        "negative": NEGATIVE + a["negative"], "init": P.to8(canvas), "mask": P.mask8(visible(names), P.RUN["armor"]["grow8"]), "control": ctl})
    return res


def layers_of(j, rgb8):
    """Ответ кадра -> слои вещей: тон от классики, альфа - силуэт классики x4, скрытое верхними вещами - B2."""
    a = ARMORS[j["key"]]
    res = {}
    for i in range(len(a["looks"])):
        names = stack(a, i)
        if all(is_done(n) or n in res for n in names):
            continue
        f4, d0, d1 = P.tone_lock(P.full4(rgb8), names, visible(names))
        print("%s %s: тон dE %.1f -> %.1f" % (j["tag"], a["looks"][i], d0, d1), flush=True)
        for k, n in enumerate(names):
            if is_done(n) or n in res:
                continue
            mask = dp.layer_mask(P.FILES, n)
            above = np.zeros_like(mask)
            for x in names[k + 1:]:
                above |= dp.layer_mask(P.FILES, x)
            im = P.layer_from(f4, mask)
            hid = P.ws.sil4(mask & above) > 0.5
            x0, y0, x1, y1 = (v * dp.K for v in dp.CROP)
            inside = np.zeros_like(hid)
            inside[y0:y1, x0:x1] = True
            hid |= ~inside                                  # щупальца RAGS шире рамки кадра (x 34..121)
            if hid.any():
                px = np.asarray(im).copy()
                px[hid, :3] = np.asarray(dp.b2_layer(n)[0])[hid, :3]
                im = Image.fromarray(px, "RGBA")
            res[n] = im
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
        S.worker(frames, raw)
        return
    for j in frames:
        j["init"].convert("RGB").save(os.path.join(raw, j["tag"] + "_in.png"))
        j["mask"].save(os.path.join(raw, j["tag"] + "_mask.png"))
    if ns.dry_run:
        for key, a in ARMORS.items():
            m = visible(stack(a, 0))
            ys, xs = np.nonzero(m)
            print(key, stack(a, 0), "точек", int(m.sum()), "рамка", xs.min(), ys.min(), xs.max(), ys.max())
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
    box = tuple(v * dp.K for v in (32, 32, 128, 160))
    W, H = box[2] - box[0], box[3] - box[1]
    bg = (40, 42, 50, 255)
    rows = []
    for key, a in ARMORS.items():
        row = []
        painted = {}
        for s, j in zip(SEEDS, [x for x in frames if x["key"] == key]):
            painted[s] = layers_of(j, np.asarray(Image.open(os.path.join(raw, j["tag"] + "_out.png")).convert("RGB")))
            for n, im in painted[s].items():
                im.save(os.path.join(out, "%s_s%d.png" % (n.lower(), s)))
        for i in range(len(a["looks"])):
            names = stack(a, i)
            c = Image.new("RGBA", (db.W * dp.K, db.H * dp.K), bg)
            c.alpha_composite(dp.classic(P.FILES, P.PAL, names).resize(c.size, Image.NEAREST))
            row.append(c.crop(box).convert("RGB"))
            for s in SEEDS:
                c = Image.new("RGBA", (db.W * dp.K, db.H * dp.K), bg)
                for n in names:
                    c.alpha_composite(done_layer(n) if is_done(n) else painted[s][n])
                row.append(c.crop(box).convert("RGB"))
        rows.append(row)
    sheet = Image.new("RGB", (W * max(map(len, rows)), H * len(rows)), bg[:3])
    for y, row in enumerate(rows):
        for x, t in enumerate(row):
            sheet.paste(t, (x * W, y * H))
    fn = os.path.join(OUT, "armor_over.png")
    sheet.save(fn)
    print("лист:", fn, sheet.size, flush=True)


if __name__ == "__main__":
    main()
