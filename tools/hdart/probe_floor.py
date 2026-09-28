#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Проба полов: бесшовная фактура материала на изо-решётке вместо перерисовки клетки.

map_paint рисовал пол по сглаженному оригиналу, и модель повторяла пятна 32x40 - «кубики»
(Vitali 27.09, DECISIONS 2026-09-27). Предметы решены стилем strict (probe_object.py); пол так
рисовать нельзя: клетка обязана стыковаться со своими копиями по ромбу (R-005) и не давать
ромбической решётки на поле (R-039).

Способ:
  1. ромб оригинала «разворачивается» в квадрат вида сверху: u, v - оси клетки на карте
     (сдвиг на клетку (16, 8) - это u+1, (-16, 8) - v+1), кадр берётся из поля своих копий,
     поэтому у квадрата нет краёв;
  2. квадрат 4x4 раза - эскиз для Qwen-Image-2.1: «та же фактура, сверху, детально»;
  3. из ответа вырезается одна клетка периода и делается строго периодичной: окно cos^2
     на два периода, сложенное по модулю периода, - сумма окон ровно 1, шва нет;
     четыре разных центра окна - четыре варианта (<N>.png и .v1..v3, R-039);
  4. тон: либо средний цвет и разброс к оригиналу (raw), либо низкие частоты - из оригинала,
     высокие - из ответа (low, --sigma в пикселях квадрата 256);
  5. квадрат ложится обратно на ромб x4 той же заменой u, v; альфа - силуэт оригинала x4
     без сглаживания (стык ромбов точный, R-005).

Лист - полем, не кадром (R-039, R-079): 5x5 копий каждого кадра, варианты разложены узором,
как у движка (Canvas32::groundFrameFor), и все полы карты целиком.

    tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\probe_floor.py ^
        --terrain JUNGLETEMPLE_2 --block MUJUNGLE14 --hints art/maps/paint/hints_MUJUNGLE.json

Кладёт в art/probe_floor/<карта>/: <НАБОР>_<кадр>_1hd.png (ответ модели), <НАБОР>.PCK/<кадр>[.vN].png
(raw и low - в подпапках), листы sheet_frames.png и map_*.png. В пак НЕ идёт.
"""
import argparse
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import gen_hd                                       # noqa: E402  (он же ставит HF_HOME)
import numpy as np                                  # noqa: E402
from PIL import Image                               # noqa: E402

import map_mockup as mm                             # noqa: E402
import map_paint as mp_                             # noqa: E402

ENC = "utf-8-sig"
K = 4
TOP = (16, 24)                                      # верхняя вершина ромба пола в кадре 32x40
N_REP = 4                                           # эскиз - квадрат 4x4 раза
FLOOR = (24, 20, 18)
MOD_TERRAIN = "Пиратки/Dioxine_XPiratez/user/mods/hd/hd/TERRAIN"   # копия, которую читает игра (R-087)

# эскиз - только размытые пятна цвета: по резкому эскизу модель сделала камнем каждый пиксель
# оригинала (мостовая MUJUNGLE_2 39, первый прогон) - те же «кубики» (R-004)
PROMPT = (
    "<image1> is a blurry colour map of a repeating ground texture: {what}, seen from directly "
    "above, the same square tile repeated 4 x 4. It only gives the colours and the large patches, "
    "it has no detail. "
    "Paint a new detailed seamless top-down ground texture for an isometric strategy game: {what}. "
    "Invent all the fine detail yourself: natural shapes of different sizes, each square of the "
    "4 x 4 grid holds only a few large features, not a mosaic of dots. Follow the colours, the "
    "brightness and the large patches of <image1> and keep the 4 x 4 repetition. "
    "Flat even light, no perspective, crisp painted game art. "
    "Fill the whole image edge to edge. No standing objects, no frame, no grid lines, no text.")
# --free: без повтора - квадраты разные, и четыре варианта клетки (CENTRES) правда разные; при
# повторе 4 x 4 варианты вышли почти одинаковыми, и мох лёг ровной сеткой кустиков (проба 27.09)
PROMPT_FREE = (
    "<image1> is a blurry colour map of a ground texture: {what}, seen from directly above. It only "
    "gives the colours and the large patches, it has no detail. "
    "Paint a new detailed top-down ground texture for an isometric strategy game: {what}. Invent all "
    "the fine detail yourself: natural shapes of different sizes, irregular and never repeating, not "
    "a mosaic of dots. Follow the overall colours and brightness of <image1>, but vary the layout "
    "freely across the image. Flat even light, no perspective, crisp painted game art. "
    "Fill the whole image edge to edge. No standing objects, no frame, no grid lines, no text.")
NEGATIVE = ("pixel art, pixelated, blocky, jagged stair-stepped edges, dithering, blurry, smudged, "
            "perspective, horizon, sky, side view, tall objects, border, frame, vignette, grid lines, "
            "seams, text, watermark")
# центры окна в квадрате 4x4 периода: у каждого своя клетка ответа - свой вариант
CENTRES = ((1.5, 1.5), (2.5, 1.5), (1.5, 2.5), (2.5, 2.5))


# ------------------------------------------------------------------ геометрия

def field_of(spr, n=2):
    """Поле (2n+1)^2 копий кадра по изо-решётке и место центральной копии."""
    w = (2 * n + 1) * 32 + 32
    h = (2 * n + 1) * 16 + 40
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    cx, cy = w // 2 - 16, h // 2 - 20
    cells = sorted(((i - j) * 16, (i + j) * 8) for i in range(-n, n + 1) for j in range(-n, n + 1))
    for dx, dy in sorted(cells, key=lambda c: c[1]):
        im.alpha_composite(spr, (cx + dx, cy + dy))
    return im, (cx, cy)


def uv_to_screen(u, v):
    """Оси клетки -> точка кадра 32x40 (k=1)."""
    return TOP[0] + (u - v) * 16.0, TOP[1] + (u + v) * 8.0


def screen_to_uv(sx, sy):
    return (sx - TOP[0]) / 32.0 + (sy - TOP[1]) / 16.0, -(sx - TOP[0]) / 32.0 + (sy - TOP[1]) / 16.0


def bilinear(arr, x, y, wrap):
    """arr HxWxC, x/y - массивы координат в пикселях (центр пикселя = i + 0.5)."""
    h, w = arr.shape[:2]
    x = x - 0.5
    y = y - 0.5
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    fx = (x - x0)[..., None]
    fy = (y - y0)[..., None]
    if wrap:
        xa, xb, ya, yb = x0 % w, (x0 + 1) % w, y0 % h, (y0 + 1) % h
    else:
        xa, xb = np.clip(x0, 0, w - 1), np.clip(x0 + 1, 0, w - 1)
        ya, yb = np.clip(y0, 0, h - 1), np.clip(y0 + 1, 0, h - 1)
    a = arr[ya, xa] * (1 - fx) + arr[ya, xb] * fx
    b = arr[yb, xa] * (1 - fx) + arr[yb, xb] * fx
    return a * (1 - fy) + b * fy


def unroll(spr, size):
    """Ромб кадра -> квадрат size x size вида сверху (u вправо, v вниз), из гладкого поля копий."""
    fld, (cx, cy) = field_of(spr, 2)
    z = 8
    big = fld.resize((fld.width * z, fld.height * z), Image.BICUBIC)
    arr = np.asarray(big.convert("RGBA")).astype(np.float32)
    a = (np.arange(size) + 0.5) / size
    u, v = np.meshgrid(a, a)
    sx, sy = uv_to_screen(u, v)
    out = bilinear(arr, (sx + cx) * z, (sy + cy) * z, wrap=False)
    return out[..., :3]


def periodic(img, period, cx, cy):
    """Клетка period x period из рисунка: окно cos^2 на 2 периода вокруг (cx, cy), сложенное по модулю.
    w(t) + w(t - P) = cos^2 + sin^2 = 1 - значит шва нет при любом содержимом. Фаза - как у эскиза."""
    p = period
    t = np.arange(-p, p) + 0.5
    w = np.cos(math.pi * t / (2 * p)) ** 2
    blk = img[cy - p:cy + p, cx - p:cx + p] * (w[:, None] * w[None, :])[..., None]
    out = blk[:p, :p] + blk[:p, p:] + blk[p:, :p] + blk[p:, p:]
    return np.roll(out, (cy % p, cx % p), axis=(0, 1))


def blur_wrap(arr, sigma):
    """Гауссово размытие периодического квадрата (без краёв)."""
    fy = np.fft.fftfreq(arr.shape[0])[:, None]
    fx = np.fft.fftfreq(arr.shape[1])[None, :]
    g = np.exp(-2 * (math.pi * sigma) ** 2 * (fx * fx + fy * fy))
    return np.real(np.fft.ifft2(np.fft.fft2(arr, axes=(0, 1)) * g[..., None], axes=(0, 1)))


def tone_raw(tex, ref, amount=0.7):
    """Средний цвет и разброс по каналу к оригиналу; контраст не поднимать (gain <= 1)."""
    out = tex.copy()
    for c in range(3):
        m, s = tex[..., c].mean(), tex[..., c].std() + 1e-3
        gain = min(1.0, (ref[..., c].std() + 1e-3) / s)
        tgt = (tex[..., c] - m) * gain + ref[..., c].mean()
        out[..., c] = tex[..., c] + (tgt - tex[..., c]) * amount
    return np.clip(out, 0, 255)


def tone_low(tex, ref, sigma):
    """Низкие частоты - оригинала, высокие - ответа."""
    return np.clip(tex - blur_wrap(tex, sigma) + blur_wrap(ref, sigma), 0, 255)


def cell(spr, tex_uv):
    """Квадрат -> кадр x4 RGBA: каждая точка ромба берёт свой u, v по модулю клетки."""
    w, h = spr.width * K, spr.height * K
    px, py = np.meshgrid((np.arange(w) + 0.5) / K, (np.arange(h) + 0.5) / K)
    u, v = screen_to_uv(px, py)
    p = tex_uv.shape[0]
    rgb = bilinear(tex_uv, (u % 1.0) * p, (v % 1.0) * p, wrap=True)
    alpha = np.asarray(mp_.silhouette(spr, K, soft=False)).astype(np.float32)
    out = np.dstack([np.clip(rgb, 0, 255), alpha]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


# ------------------------------------------------------------------ узор вариантов, как у движка

def _hash01(ix, iy, seed):
    h = (ix * 374761393 + iy * 668265263 + seed * 2246822519) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return (h ^ (h >> 16)) / 4294967295.0


def ground_level(U, V, count, seed=7, scale=2.5):
    """Гладкий шум по карте -> уровень 0..count-1 (порядок вариантов - как у движка)."""
    x, y = U / scale, V / scale
    x0, y0 = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64)
    fx, fy = x - x0, y - y0
    fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    h = np.vectorize(lambda a, b: _hash01(int(a), int(b), seed))
    a = h(x0, y0) * (1 - fx) + h(x0 + 1, y0) * fx
    b = h(x0, y0 + 1) * (1 - fx) + h(x0 + 1, y0 + 1) * fx
    return (a * (1 - fy) + b * fy) * (count - 1)


def engine_order(variants):
    """[base, v1, v2, v3] -> порядок шкалы движка: base посередине, нечётные в одну сторону."""
    n = len(variants)
    mid = n // 2
    out = [None] * n
    out[mid] = variants[0]
    for j in range(1, n):
        out[mid - (j + 1) // 2 if j % 2 else mid + j // 2] = variants[j]
    return out


def cell_at(spr, texs, gx, gy, edge=0.2):
    """Кадр x4 на клетке карты (gx, gy): варианты смешаны по уровню узора в каждой точке."""
    if len(texs) == 1:
        return cell(spr, texs[0])
    w, h = spr.width * K, spr.height * K
    px, py = np.meshgrid((np.arange(w) + 0.5) / K, (np.arange(h) + 0.5) / K)
    u, v = screen_to_uv(px, py)
    lev = ground_level(gx + u, gy + v, len(texs))
    i = np.clip(np.floor(lev).astype(int), 0, len(texs) - 2)
    t = np.clip((lev - i - (0.5 - edge)) / (2 * edge), 0, 1)
    t = (t * t * (3 - 2 * t))[..., None]
    p = texs[0].shape[0]
    su, sv = (u % 1.0) * p, (v % 1.0) * p
    samples = [bilinear(tx, su, sv, wrap=True) for tx in texs]
    rgb = np.zeros((h, w, 3), np.float32)
    for k in range(len(texs) - 1):
        m = (i == k)[..., None]
        rgb += m * (samples[k] * (1 - t) + samples[k + 1] * t)
    alpha = np.asarray(mp_.silhouette(spr, K, soft=False)).astype(np.float32)
    return Image.fromarray(np.dstack([np.clip(rgb, 0, 255), alpha]).astype(np.uint8), "RGBA")


def field_sheet(spr, make, n=5):
    """Поле n x n копий кадра x4; make(gx, gy) -> картинка клетки."""
    w = n * 2 * 16 * K + 32 * K
    h = n * 2 * 8 * K + 40 * K
    out = Image.new("RGBA", (w, h), FLOOR + (255,))
    ox = (n - 1) * 16 * K
    for gy in range(n):
        for gx in range(n):
            out.alpha_composite(make(gx, gy), (ox + (gx - gy) * 16 * K, (gx + gy) * 8 * K))
    return out


# ------------------------------------------------------------------ ввод-вывод

def load_png(path):
    return Image.open(path).convert("RGBA") if os.path.exists(path) else None


def label(im, text):
    return gen_hd.label(im, text)


def board(rows, gap=8):
    w = max(sum(c.width for c in r) + gap * (len(r) - 1) for r in rows)
    h = sum(max(c.height for c in r) + gap for r in rows)
    out = Image.new("RGB", (w, h), (32, 32, 36))
    y = 0
    for r in rows:
        x = 0
        for c in r:
            out.paste(c.convert("RGB"), (x, y))
            x += c.width + gap
        y += max(c.height for c in r) + gap
    return out


def floor_keys(world, terrain, block, hints):
    _im, _own, inst = mp_.layout(world, terrain, block)
    uses = {}
    for d in inst:
        if d["part"] == 0:
            key = (d["set"], d["frame"])
            uses[key] = uses.get(key, 0) + 1
    keys = sorted(uses, key=lambda k: -uses[k])
    return [k for k in keys if "%s:%d" % k in hints], uses, inst


def map_floors(inst, make):
    """Все полы карты x4 (часть 0), в порядке рисования; make(d) -> картинка или None."""
    xs = [d["x"] for d in inst if d["part"] == 0]
    ys = [d["y"] for d in inst if d["part"] == 0]
    x0, y0 = min(xs), min(ys)
    w, h = (max(xs) - x0 + 32) * K, (max(ys) - y0 + 40) * K
    out = Image.new("RGBA", (w, h), FLOOR + (255,))
    for d in inst:
        if d["part"] != 0:
            continue
        im = make(d)
        if im is not None:
            out.alpha_composite(im, ((d["x"] - x0) * K, (d["y"] - y0) * K))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--terrain", default="JUNGLETEMPLE_2")
    ap.add_argument("--block", default="MUJUNGLE14")
    ap.add_argument("--hints", default="art/maps/paint/hints_MUJUNGLE.json")
    ap.add_argument("--frames", default="", help="НАБОР:кадр через запятую; пусто - все полы карты с описанием")
    ap.add_argument("--out", default="art/probe_floor")
    ap.add_argument("--period", type=int, default=256, help="сторона клетки в квадрате ответа")
    ap.add_argument("--sigma", type=float, default=24.0, help="low: размытие для низких частот, пикс. квадрата")
    ap.add_argument("--tone", type=float, default=0.7, help="raw: доля подгонки среднего и разброса")
    ap.add_argument("--free", action="store_true",
                    help="без повтора 4x4: варианты клетки разные (лист в <карта>_free)")
    ap.add_argument("--sketch-sigma", type=float, default=20.0,
                    help="размытие эскиза, пикс. квадрата: модели - только пятна цвета, не пиксели")
    ap.add_argument("--seed", type=int, default=2711)
    ap.add_argument("--steps", type=int, default=40)
    ap.add_argument("--cfg", type=float, default=4.0)
    ap.add_argument("--mp", type=float, default=1.0)
    ap.add_argument("--model", default="")
    ap.add_argument("--models", default=gen_hd.DEFAULT_MODELS_DIR)
    ap.add_argument("--offload", default="model", choices=["model", "seq", "none"])
    ap.add_argument("--recut", action="store_true", help="без видеокарты: из готовых *_1hd.png")
    args = ap.parse_args()

    with open(args.hints, encoding=ENC) as f:
        hints = json.load(f)
    world = mm.World()
    keys, uses, inst = floor_keys(world, args.terrain, args.block, hints)
    if args.frames:
        want = [(s.split(":")[0].upper(), int(s.split(":")[1])) for s in args.frames.split(",") if s.strip()]
        keys = [k for k in want if "%s:%d" % k in hints]
    out_dir = os.path.join(args.out, args.block + ("_free" if args.free else ""))
    os.makedirs(out_dir, exist_ok=True)
    print("полов с описанием: %d - %s" % (len(keys), ", ".join("%s %d (%d)" % (s, f, uses.get((s, f), 0))
                                                                 for s, f in keys)), flush=True)

    painter = None
    if not args.recut:
        import gen_fire
        ns = argparse.Namespace(models=args.models, qwen21_model=args.model, qwen21_steps=args.steps,
                                qwen21_cfg=args.cfg, qwen21_mp=args.mp, qwen21_strength=0.0,
                                qwen21_offload=args.offload, qwen21_thrifty=False,
                                qwen21_ref="", qwen21_ref_mp=1.0, qwen21_prompt="strict",
                                qwen21_hint="off", qwen21_ref_order="ref-first")
        painter = gen_hd.Qwen21Painter(ns, {"ground": ("", "")})
        gen_fire.NEGATIVE = NEGATIVE                # run_pass берёт негатив из модуля gen_fire

    p = args.period
    side = p * N_REP
    texs = {}                                       # key -> {"raw": [4 квадрата], "low": [...]}
    t0 = time.time()
    for n, (s, f) in enumerate(keys):
        spr = world.sprite(s, f, None)
        bb = spr.split()[3].getbbox()
        what = hints["%s:%d" % (s, f)]
        ref = unroll(spr, p)
        soft = blur_wrap(ref, args.sketch_sigma) if args.sketch_sigma > 0 else ref
        sketch = Image.fromarray(np.tile(soft, (N_REP, N_REP, 1)).clip(0, 255).astype(np.uint8), "RGB")
        gen_hd.save_png(sketch, os.path.join(out_dir, "%s_%d_sketch.png" % (s, f)))
        hd_path = os.path.join(out_dir, "%s_%d_1hd.png" % (s, f))
        print("[%d/%d] %s %d (габарит %s): %s" % (n + 1, len(keys), s, f, bb, what), flush=True)
        if args.recut or os.path.exists(hd_path):
            # готовый ответ не заказывать заново: прогон продолжается с места после падения
            if not os.path.exists(hd_path):
                continue
            hd = Image.open(hd_path)
        else:
            prompt = PROMPT_FREE if args.free else PROMPT
            hd = gen_fire.run_pass(painter, args, prompt.replace("{what}", what), sketch, args.seed + n)
            gen_hd.save_png(hd, hd_path)
            el = time.time() - t0
            print("  %s, осталось ~%s" % (gen_hd.human_time(el),
                                          gen_hd.human_time(el / (n + 1) * (len(keys) - n - 1))), flush=True)
        # ответ модели бывает RGBA - берём только цвет
        arr = np.asarray(hd.convert("RGB").resize((side, side), Image.LANCZOS)).astype(np.float32)
        var = {"raw": [], "low": []}
        for cxr, cyr in CENTRES:
            per = periodic(arr, p, int(cxr * p), int(cyr * p))
            var["raw"].append(tone_raw(per, ref, args.tone))
            var["low"].append(tone_low(per, ref, args.sigma))
        texs[(s, f)] = var
        for mode in ("raw", "low"):
            d = os.path.join(out_dir, mode, s + ".PCK")
            os.makedirs(d, exist_ok=True)
            for j, tx in enumerate(var[mode]):
                name = "%d.png" % f if j == 0 else "%d.v%d.png" % (f, j)
                gen_hd.save_png(cell(spr, tx), os.path.join(d, name))
            gen_hd.save_png(Image.fromarray(np.hstack(var[mode]).astype(np.uint8), "RGB"),
                            os.path.join(d, "%d_uv.png" % f))

    # лист кадров: поле 5x5 - оригинал x4 | прежний пак | raw | low
    rows = []
    for s, f in keys:
        if (s, f) not in texs:
            continue
        spr = world.sprite(s, f, None)
        x4 = spr.resize((spr.width * K, spr.height * K), Image.NEAREST)
        old = load_png(os.path.join(MOD_TERRAIN, s + ".PCK", "%d.png" % f))
        order = {m: engine_order(texs[(s, f)][m]) for m in ("raw", "low")}
        row = [label(field_sheet(spr, lambda gx, gy: x4), "%s %d orig x4" % (s, f))]
        if old is not None:
            row.append(label(field_sheet(spr, lambda gx, gy: old), "old pack"))
        for m in ("raw", "low"):
            row.append(label(field_sheet(spr, lambda gx, gy, m=m: cell_at(spr, order[m], gx, gy)), m))
        rows.append(row)
    if rows:
        gen_hd.save_png(board(rows), os.path.join(out_dir, "sheet_frames.png"))
        print("ЛИСТ %s" % os.path.join(out_dir, "sheet_frames.png"), flush=True)

    # вся карта: только полы
    cache = {}

    def orig(d):
        return d["spr"].resize((32 * K, 40 * K), Image.NEAREST)

    def old(d):
        key = ("old", d["set"], d["frame"])
        if key not in cache:
            cache[key] = load_png(os.path.join(MOD_TERRAIN, d["set"] + ".PCK", "%d.png" % d["frame"]))
        return cache[key] if cache[key] is not None else orig(d)

    def new(mode):
        def make(d):
            k = (d["set"], d["frame"])
            if k not in texs:
                return old(d)
            gx, gy = d["gx"], d["gy"]
            return cell_at(d["spr"], engine_order(texs[k][mode]), gx, gy)
        return make

    _sx, sy, sz, _cells = mm.read_block(world, args.block)
    for d in inst:
        # клетка карты обратно из экранных координат layout: x = sy*16 + (gx - gy)*16,
        # y = sz*24 + 8 + (gx + gy)*8 - z*24 - P_Level
        a = (d["x"] - sy * 16) // 16
        b = (d["y"] + d["z"] * 24 + d["p_level"] - sz * 24 - 8) // 8
        d["gx"], d["gy"] = (a + b) // 2, (b - a) // 2
    maps = [("orig x4", map_floors(inst, orig)), ("old pack", map_floors(inst, old)),
            ("raw", map_floors(inst, new("raw"))), ("low", map_floors(inst, new("low")))]
    for name, im in maps:
        gen_hd.save_png(im.convert("RGB"), os.path.join(out_dir, "map_%s.png" % name.split()[0]))
    # середина карты в полный размер x4 - 2x2
    w, h = maps[0][1].size
    box = (w // 2 - 640, h // 2 - 360, w // 2 + 640, h // 2 + 360)
    crops = [label(im.crop(box), name) for name, im in maps]
    gen_hd.save_png(board([crops[:2], crops[2:]]), os.path.join(out_dir, "map_crop.png"))
    print("ЛИСТ %s" % os.path.join(out_dir, "map_crop.png"), flush=True)
    print("готово за %s" % gen_hd.human_time(time.time() - t0), flush=True)


if __name__ == "__main__":
    main()
