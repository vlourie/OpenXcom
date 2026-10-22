#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Ствол турели отдельным слоем (живая база, 22.10; R-459). У лазерной, плазменной и гаусс-турели Пираток ствол
доходит до внутренних углов креста: поворот круга картинки (HdBaseScene spin/swing) либо отрывал концы стволов,
либо крутил стены. Здесь картинка клетки режется на две (слой HdBase::layer, строка swing сцены):

    <N>.spin.png   головка со стволом - шар (или кольцо) и ствол, остальное прозрачно; поворачивается вокруг
                   центра шара. Шар при повороте ложится сам на себя, поэтому под ним ничего дорисовывать не надо;
    <N>.under.png  картинка клетки без ствола: под стволом дорисован пол и лапа станины, остальное - пиксель
                   в пиксель <N>.png. Движок кладёт её в круге swing и сверху - повёрнутую головку.

<N>.png остаётся как есть (со стволом) - без живой базы клетка та же, что была.

Что под стволом, рисует:
    telea   - OpenCV по краю дыры, процессор (запасной вариант);
    s<сид>  - Qwen-Image-Edit-2511: «убери ствол, дорисуй пол», ответ берётся только внутри маски заплатки.

Размах поворота считает модель: головка, повёрнутая на угол, не должна заходить на полосу стен креста
и мебель (пол креста по картинке, TURRETS floor) - берётся наибольший угол с запасом MARGIN.

    py -3.13 tools/hdart/base_turret_split.py               маски, telea, лист (без видеокарты)
    py -3.13 tools/gpuq.py add --name base-turret-split --prio 1 --cwd E:/OpenXCom -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/base_turret_split.py --edit
Выход art/base_living/turret/: <ТИП>/{spin,under_<вариант>}{,@512}.png, debug_<ТИП>.png, swing_<ТИП>_<вариант>.gif,
лист art/base_living/turret_sheet.png, angles.json. В мод ничего не идёт (арт - сначала показать Vitali)."""
import os

os.environ["HF_HUB_OFFLINE"] = "1"      # до импорта diffusers (R-145, R-207)

import argparse                         # noqa: E402
import json                             # noqa: E402
import math                             # noqa: E402
import sys                              # noqa: E402
import time                             # noqa: E402

import numpy as np                      # noqa: E402
from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import gen_base_paint as gp             # noqa: E402

M = 512                                 # координаты ниже - в запасной картинке 512 на клетку
OUT = os.path.join(gp.ROOT, "art", "base_living", "turret")
PAINTED = os.path.join(gp.OUT, "painted")
FLOOR_MID = 176                         # верх средней полосы креста (под гранью стен внутренних углов), из 512
MARGIN = 2.0                            # градусов запаса от касания стены
MOST = 25.0                             # больше не надо: турель «водит», а не крутится
GROW = 7                                # заплатка шире ствола (тень и ореол края), пикселей из 512
SEEDS = (3100, 4200)
STEPS, CFG = 40, 4.0

# Головка: круг шара (x y r), ствол - многоугольники; ось поворота - центр круга.
TURRETS = {
    "STR_LASER_DEFENSES": {
        "ball": (258, 262, 47),
        "barrel": [[(245, 93), (272, 93), (272, 190), (280, 188), (280, 234), (238, 234), (238, 188), (245, 190)]],
        "axis": [(258, 100, 258, 226)],
        "floor": (148, 316, 40, [(158, 30, 208, 98), (220, 30, 278, 78)]),
        "what": "the long red-and-white striped cannon barrel with its grey collar that points up from the white "
                "ball turret head",
        "under": "the clean concrete floor and the closed end of the purple turret mount",
    },
    "STR_PLASMA_DEFENSES": {
        "ball": (256, 250, 44),
        "barrel": [[(236, 116), (277, 116), (285, 150), (288, 214), (225, 214), (228, 150)]],
        "axis": [(256, 124, 256, 206)],
        "floor": (148, 316, 40, [(146, 36, 174, 136), (300, 36, 320, 106)]),
        "what": "the top arm of the turret - the long blue emitter with the glowing green tip that points up from "
                "the round purple orb housing",
        "under": "the clean sandy floor and the black hoses and blue base plate under it",
    },
    "STR_GAUSS_DEFENSES": {
        "ball": (256, 265, 44),
        "barrel": [[(199, 93), (230, 93), (244, 240), (200, 240)], [(284, 93), (312, 93), (312, 240), (268, 240)],
                   [(234, 194), (280, 194), (280, 232), (234, 232)]],
        "axis": [(214.5, 102, 221.8, 232), (298.5, 102, 284, 232), (240, 214, 274, 214)],
        "floor": (148, 316, 52, [(313, 36, 324, 96)]),
        "what": "the two long black gun barrels with their brackets that point up from the dark steel ball turret "
                "head",
        "under": "the clean orange floor and the grey turret base plate under it",
    },
}


def poly_mask(size, shapes, scale, ss=4):
    """Маска круга и многоугольников (в координатах 512) размера size, с краем по сглаживанию ss."""
    w, h = size
    im = Image.new("L", (w * ss, h * ss), 0)
    d = ImageDraw.Draw(im)
    k = scale * ss
    for kind, data in shapes:
        if kind == "circle":
            x, y, r = data
            d.ellipse([(x - r) * k, (y - r) * k, (x + r) * k, (y + r) * k], fill=255)
        else:
            d.polygon([(x * k, y * k) for x, y in data], fill=255)
    return np.asarray(im.resize((w, h), Image.LANCZOS), np.float32) / 255.0


def masks(spec, raw):
    """(головка, заплатка) в размере картинки raw. Многоугольники - только где искать: сама головка вырезается
    по рисунку (GrabCut: внутри многоугольника - скорее ствол, кольцо вокруг - скорее пол, шар и ось ствола
    (axis) - точно ствол), иначе вместе со стволом поворачивался бы кусок пола. Шар - кругом целиком.
    Заплатка - ствол без шара, шире на GROW (край и тень)."""
    import cv2
    size = raw.size
    scale = size[0] / float(M)
    bx, by, br = spec["ball"]
    ball = poly_mask(size, [("circle", spec["ball"])], scale)
    barrel = poly_mask(size, [("poly", p) for p in spec["barrel"]], scale)
    hard = (np.maximum(ball, barrel) > 0.5).astype(np.uint8)
    near = cv2.dilate(hard, np.ones((int(24 * scale) | 1,) * 2, np.uint8))
    core = np.zeros(hard.shape, np.uint8)
    for x0, y0, x1, y1 in spec["axis"]:
        cv2.line(core, (int(x0 * scale), int(y0 * scale)), (int(x1 * scale), int(y1 * scale)), 1, int(4 * scale))
    gc = np.full(hard.shape, cv2.GC_BGD, np.uint8)
    gc[near > 0] = cv2.GC_PR_BGD
    gc[hard > 0] = cv2.GC_PR_FGD
    gc[(core > 0) | (ball > 0.98)] = cv2.GC_FGD
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    img = np.ascontiguousarray(np.asarray(raw, np.uint8)[..., ::-1])
    cv2.grabCut(img, gc, None, bgd, fgd, 6, cv2.GC_INIT_WITH_MASK)
    cut = ((gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD)).astype(np.uint8) & hard
    # без крошек: одна связная головка, дырки внутри залиты
    n, lab, stats, _ = cv2.connectedComponentsWithStats(cut, 8)
    if n > 1:
        cut = (lab == 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))).astype(np.uint8)
    cut = cv2.morphologyEx(cut, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    soft = cv2.GaussianBlur(cut.astype(np.float32), (0, 0), 0.8 * scale)
    gun = np.maximum(soft * (barrel > 0.02), ball)
    grow = max(1, int(round(GROW * scale)))
    stem = (soft * (barrel > 0.02) * 255).astype(np.uint8)
    patch = np.asarray(Image.fromarray(stem, "L").filter(ImageFilter.MaxFilter(2 * grow + 1))
                       .filter(ImageFilter.GaussianBlur(grow / 2.0)), np.float32) / 255.0
    inner = poly_mask(size, [("circle", (bx, by, br - 1.5))], scale)
    return gun, np.clip(patch - inner, 0, 1)


def rotate(rgba, deg, pivot):
    """RGBA (float, альфа не умножена) поворотом вокруг pivot: премультипликация, билинейно."""
    a = rgba[..., 3:4]
    pm = np.concatenate([rgba[..., :3] * a, a], -1)
    chans = [np.asarray(Image.fromarray(pm[..., c].astype(np.float32), "F")
                        .rotate(deg, Image.BILINEAR, center=pivot), np.float32) for c in range(4)]
    out = np.stack(chans, -1)
    al = out[..., 3:4]
    out[..., :3] = np.where(al > 1e-4, out[..., :3] / np.maximum(al, 1e-4), 0)
    return out


def over(dst, src):
    """src поверх dst (RGBA float 0..255 цвет, 0..1 альфа)."""
    a = src[..., 3:4]
    out = dst.copy()
    out[..., :3] = src[..., :3] * a + dst[..., :3] * (1 - a)
    out[..., 3:4] = a + dst[..., 3:4] * (1 - a)
    return out


def walls(spec):
    """Где головке нельзя быть (512): всё, кроме пола верхнего плеча креста (x от xl до xr ниже ytop) и
    средней полосы ниже FLOOR_MID; мебель плеча - коробки. Силуэт классики не годится: в нём тень справа и
    снизу, а внутренние углы креста он не закрывает (картинка рисована с толщиной стен)."""
    xl, xr, ytop, boxes = spec["floor"]
    free = Image.new("L", (M, M), 0)
    d = ImageDraw.Draw(free)
    d.rectangle([xl, ytop, xr, M], fill=255)
    d.rectangle([40, FLOOR_MID, M - 40, M], fill=255)
    for box in boxes:
        d.rectangle(box, fill=0)
    return np.asarray(free) < 128


def amplitude(gun512, wall, pivot):
    """Наибольшие углы влево и вправо (по часовой - плюс), при которых головка не заходит на стены и мебель."""
    rgba = np.zeros(gun512.shape + (4,), np.float32)
    rgba[..., 3] = gun512
    most = []
    for sign in (-1, 1):
        best = 0.0
        for deg10 in range(5, int(MOST * 10) + 1, 5):
            # PIL крутит против часовой при плюсе, у нас плюс - по часовой (как HdBaseScene::drawMotion)
            if ((rotate(rgba, -sign * deg10 / 10.0, pivot)[..., 3] > 0.25) & wall).any():
                break
            best = deg10 / 10.0
        most.append(best)
    return most[0], most[1]


def swing_of(left, right):
    """Качание без касания: (размах в каждую сторону, середина) по наибольшим углам влево и вправо."""
    left, right = max(0.0, left - MARGIN), max(0.0, right - MARGIN)
    return (left + right) / 2.0, (right - left) / 2.0


def load(t):
    raw = Image.open(os.path.join(PAINTED, "raw", t + ".png")).convert("RGB")
    rules, _ = gp.load_rules()
    fac = gp.Facility(rules[t], gp.sprites_map())
    _img, a4 = gp.facility_input(fac)
    return raw, a4


def telea(raw, patch):
    import cv2
    rgb = np.asarray(raw, np.uint8)
    hole = (patch > 0.02).astype(np.uint8)
    fill = cv2.inpaint(np.ascontiguousarray(rgb[..., ::-1]), hole, 9, cv2.INPAINT_TELEA)[..., ::-1]
    return Image.fromarray(fill, "RGB")


def blend(raw, painted, patch):
    """Ответ модели только внутри заплатки, вокруг - исходник. Edit-2511 сдвигает тон всей картинки (у гаусса
    пол светлее на полтона), поэтому ответ подгоняется по кольцу вокруг заплатки: там пол тот же, и отношение
    средних исходника и ответа по каналу - поправка."""
    import cv2
    a = patch[..., None]
    src = np.asarray(raw, np.float32)
    edit = np.asarray(painted.convert("RGB").resize(raw.size, Image.LANCZOS), np.float32)
    hole = (patch > 0.02).astype(np.uint8)
    ring = (cv2.dilate(hole, np.ones((25, 25), np.uint8)) > 0) & (hole == 0)
    if ring.sum() > 100:
        gain = src[ring].mean(0) / np.maximum(edit[ring].mean(0), 1.0)
        edit = edit * np.clip(gain, 0.7, 1.4)
    out = edit * a + src * (1 - a)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")


def pieces(t, raw, a4, under_raw, gun_raw, patch_raw, per_cell):
    """Готовые к паку (HdBase::layer): картинка клетки без ствола (<N>.under.png, альфа - силуэт, как у <N>.png)
    и головка (<N>.spin.png), per_cell на клетку. under_raw уже исходник вне заплатки (blend/telea)."""
    size = (per_cell, per_cell)
    under = gp.finish(under_raw, a4, 1, 1, per_cell)
    # головка: премультипликация до уменьшения, иначе край тянет фон
    rgb = np.asarray(raw, np.float32)
    pm = np.dstack([rgb * gun_raw[..., None], gun_raw * 255])
    small = _resize_f(pm, size)
    al = small[..., 3:4] / 255.0
    col = np.where(al > 1e-3, small[..., :3] / np.maximum(al, 1e-3), 0)
    gun = Image.fromarray(np.clip(np.dstack([col, al[..., 0] * 255]), 0, 255).astype(np.uint8), "RGBA")
    return under, gun


def _resize_f(arr, size):
    return np.stack([np.asarray(Image.fromarray(arr[..., c].astype(np.float32), "F").resize(size, Image.LANCZOS),
                                np.float32) for c in range(arr.shape[-1])], -1)


def frame(still, under, gun, deg, pivot):
    """Клетка как в игре: неподвижная картинка, заплатка, головка повёрнутая на deg (по часовой - плюс)."""
    base = np.asarray(still.convert("RGBA"), np.float32)
    base[..., 3] /= 255.0
    u = np.asarray(under, np.float32)
    u[..., 3] /= 255.0
    g = np.asarray(gun, np.float32)
    g[..., 3] /= 255.0
    out = over(over(base, u), rotate(g, -deg, pivot))
    out[..., 3] *= 255.0
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")


def on_dark(im, size=None):
    bg = Image.new("RGBA", im.size, (34, 34, 38, 255))
    bg.alpha_composite(im.convert("RGBA"))
    return bg if size is None else bg.resize(size, Image.LANCZOS)


def checker(im):
    w, h = im.size
    bg = Image.new("RGBA", (w, h), (200, 200, 200, 255))
    d = ImageDraw.Draw(bg)
    for y in range(0, h, 16):
        for x in range(0, w, 16):
            if (x // 16 + y // 16) % 2:
                d.rectangle([x, y, x + 15, y + 15], fill=(150, 150, 150, 255))
    bg.alpha_composite(im.convert("RGBA"))
    return bg


def edit_all(jobs):
    """jobs: {(тип, сид): (картинка, промпт, негатив)} -> {(тип, сид): ответ}. Одна загрузка модели."""
    import gen_hd
    import item_photo as ip
    import photo_ui as pu
    import torch
    import weapons_probe5 as wp5
    models = gen_hd.DEFAULT_MODELS_DIR
    ip.edit_model_check(models)
    pu.MODEL = os.path.join(models, "hub", "models--Qwen--Qwen-Image-Edit-2511", "snapshots", ip.EDIT_MODEL_REV)
    types = sorted({t for t, _s in jobs})
    first = {t: jobs[(t, SEEDS[0])] for t in types}
    pipe, embeds = wp5.two_phase(models, [first[t] for t in types])
    out = {}
    t0 = time.time()
    done = 0
    for i, t in enumerate(types):
        src = first[t][0]
        pe, pm, npe, npm = (x.to(torch.device("cuda")) for x in embeds[i])
        for seed in SEEDS:
            ts = time.time()
            g = torch.Generator("cuda").manual_seed(seed)
            with torch.no_grad():
                out[(t, seed)] = pipe(image=[src], prompt=None, prompt_embeds=pe, prompt_embeds_mask=pm,
                                      negative_prompt_embeds=npe, negative_prompt_embeds_mask=npm,
                                      true_cfg_scale=CFG, num_inference_steps=STEPS, generator=g,
                                      width=src.width, height=src.height).images[0]
            done += 1
            print("  [%d/%d] %s сид %d: %.0f с, осталось ~%.0f мин" % (
                done, len(jobs), t, seed, time.time() - ts,
                (time.time() - t0) / done * (len(jobs) - done) / 60), flush=True)
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--edit", action="store_true", help="и варианты Edit-2511 (только через gpuq)")
    ap.add_argument("--only", default="", help="типы через запятую")
    a = ap.parse_args()
    os.chdir(gp.ROOT)
    types = [t for t in TURRETS if not a.only or t in a.only.split(",")]
    prep = {}
    for t in types:
        raw, a4 = load(t)
        gun_raw, patch_raw = masks(TURRETS[t], raw)
        prep[t] = (raw, a4, gun_raw, patch_raw)
    edits = {}
    if a.edit:
        jobs = {}
        for t in types:
            s = TURRETS[t]
            prompt = ("Edit <image1>. It is a top-down painted picture of a defense turret room in a base-building "
                      "strategy game. Remove %s, together with its shadow, and paint there what lies under it: %s, "
                      "continuing the surroundings seamlessly. Keep the round turret head itself, its legs, the "
                      "walls, the golden frame, the furniture, the colours, the light and the painted style exactly "
                      "as they are." % (s["what"], s["under"]))
            neg = "cannon, gun barrel, barrel, tube, pipe pointing up, new objects, people, text, blurry"
            for seed in SEEDS:
                jobs[(t, seed)] = (prep[t][0], prompt, neg)
        edits = edit_all(jobs)
    angles = {}
    sheet_rows = []
    for t in types:
        raw, a4, gun_raw, patch_raw = prep[t]
        d = os.path.join(OUT, t)
        os.makedirs(d, exist_ok=True)
        variants = {"telea": telea(raw, patch_raw)}
        for seed in SEEDS:
            p = os.path.join(d, "raw_s%d.png" % seed)
            if (t, seed) in edits:
                edits[(t, seed)].save(p)
            if os.path.exists(p):
                variants["s%d" % seed] = blend(raw, Image.open(p), patch_raw)
        still512 = gp.finish(raw, a4, 1, 1, gp.MASTER)
        still128 = gp.finish(raw, a4, 1, 1, 128)
        packed = os.path.join(PAINTED, t + ".png")
        if os.path.exists(packed) and not np.array_equal(np.asarray(Image.open(packed).convert("RGBA")),
                                                           np.asarray(still128)):
            print("!! %s: finish(raw) не совпал с painted/%s.png - пак мог быть собран из другого" % (t, t))
        bx, by, _br = TURRETS[t]["ball"]
        gun512 = np.asarray(Image.fromarray((gun_raw * 255).astype(np.uint8), "L").resize((M, M), Image.LANCZOS),
                            np.float32) / 255.0
        wall = walls(TURRETS[t])
        left, right = amplitude(gun512, wall, (bx, by))
        amp, mid = swing_of(left, right)
        # круг строки swing: вся головка в нём при любом угле (HdBaseScene::drawMotion кладёт под ним <N>.under)
        ys, xs = np.nonzero(gun512 > 0.02)
        reach = float(np.sqrt((xs + 0.5 - bx) ** 2 + (ys + 0.5 - by) ** 2).max()) / 4.0 + 2.0
        angles[t] = {"pivot128": [bx / 4.0, by / 4.0], "radius128": round(reach, 1), "swing": amp, "middle": mid,
                     "period": 8.0, "left": left, "right": right}
        print("%-22s ось %.1f %.1f (из 128), до стен влево %.1f° вправо %.1f° -> %.1f° +-%.1f°" % (
            t, bx / 4.0, by / 4.0, left, right, mid, amp))
        # отладка: маски и полоса стен
        dbg = np.asarray(still512.convert("RGB"), np.float32).copy()
        p512 = np.asarray(Image.fromarray((patch_raw * 255).astype(np.uint8), "L").resize((M, M)), np.float32) / 255
        dbg[wall] = dbg[wall] * 0.5 + np.array([255, 0, 0]) * 0.5
        dbg = dbg * (1 - 0.45 * gun512[..., None]) + np.array([0, 255, 255]) * 0.45 * gun512[..., None]
        dbg = dbg * (1 - 0.5 * p512[..., None]) + np.array([255, 255, 0]) * 0.5 * p512[..., None]
        Image.fromarray(np.clip(dbg, 0, 255).astype(np.uint8)).save(os.path.join(OUT, "debug_%s.png" % t))
        row = {"t": t, "still": still512, "amp": amp, "mid": mid, "variants": {}}
        for name, under_raw in variants.items():
            u512, g512 = pieces(t, raw, a4, under_raw, gun_raw, patch_raw, gp.MASTER)
            u128, g128 = pieces(t, raw, a4, under_raw, gun_raw, patch_raw, 128)
            u512.save(os.path.join(d, "under_%s@512.png" % name))
            u128.save(os.path.join(d, "under_%s.png" % name))
            g512.save(os.path.join(d, "spin@512.png"))
            g128.save(os.path.join(d, "spin.png"))
            frames = []
            for i in range(24):
                deg = mid + amp * math.sin(i / 24.0 * 2 * math.pi)
                frames.append(on_dark(frame(still512, u512, g512, deg, (bx, by)), (320, 320)).convert("RGB"))
            frames[0].save(os.path.join(OUT, "swing_%s_%s.gif" % (t, name)), save_all=True,
                           append_images=frames[1:], duration=8000 // 24, loop=0)
            # без головки - что видно под стволом
            bare = frame(still512, u512, Image.new("RGBA", g512.size, (0, 0, 0, 0)), 0, (bx, by))
            row["variants"][name] = (bare, frame(still512, u512, g512, mid - amp, (bx, by)),
                                     frame(still512, u512, g512, mid + amp, (bx, by)))
        row["gun"] = Image.open(os.path.join(d, "spin@512.png"))
        sheet_rows.append(row)
    with open(os.path.join(OUT, "angles.json"), "w", encoding="utf-8-sig") as f:
        json.dump(angles, f, ensure_ascii=False, indent=1)
    # лист: оригинал | головка | по варианту: под стволом, -угол, +угол (центр клетки 320 из 512)
    C, crop = 320, (96, 40, 416, 360)
    names = list(sheet_rows[0]["variants"])
    W = (2 + 3 * len(names)) * (C + 6) + 6
    H = len(sheet_rows) * (C + 30) + 30
    sheet = Image.new("RGB", (W, H), (24, 24, 26))
    d = ImageDraw.Draw(sheet)
    heads = ["original", "gun"] + ["%s %s" % (n, s) for n in names for s in ("under", "-max", "+max")]
    for i, h in enumerate(heads):
        d.text((6 + i * (C + 6), 8), h, fill=(230, 230, 230))
    for r, row in enumerate(sheet_rows):
        y = 30 + r * (C + 30)
        cells = [on_dark(row["still"]), checker(row["gun"])]
        for n in names:
            cells += list(row["variants"][n])
        for i, c in enumerate(cells):
            sheet.paste(on_dark(c).crop(crop).convert("RGB"), (6 + i * (C + 6), y))
        d.text((6, y + C + 4), "%s  %.1f..%.1f deg" % (row["t"], row["mid"] - row["amp"], row["mid"] + row["amp"]),
               fill=(255, 220, 120))
    out = os.path.join(gp.ROOT, "art", "base_living", "turret_sheet.png")
    sheet.save(out)
    print("лист:", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
