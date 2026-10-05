#!/usr/bin/env python3
"""
Как ляжет трассер: лист «как сейчас | как станет» по настоящей траектории.

Зачем отдельный скрипт: трассер - это не один кадр, а 35 оттисков кадра 3x3 вдоль
выстрела, по вокселю друг от друга. Судить о нём по кадру нельзя (те же грабли, что
R-039 у ковровых плиток): всё решает то, как оттиски складываются в полосу. Поэтому
здесь строится поле - траектория переводится в экранные координаты ровно так же, как
это делает Camera::convertVoxelToScreen, и кадры накладываются в том же порядке.

Расчёт круглой точки повторяет HdSprites::makeDots один в один. Меняешь формулу в
движке - поменяй и здесь, иначе лист начнёт врать.

    py -3.13 tools\\hdart\\tracer_preview.py
    ... --sheet <путь к PNG набора> --types 0,2,6,14
    ... --scale 4 --out "Claude outputs\\tracer.png"
    ... --style "bright;fade=0.35"     третья строка: стиль из hd/FX/weapons.txt (tracer)
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image
import common

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BULLET_SPRITES = 35      # Map.h: столько кадров на один трассер
SUB = 3                  # subX/subY набора Projectiles
MAX_DOT = 4              # HdSprites.cpp: кадр не больше этого - точка, а не картинка

PIRATEZ = os.path.join(common.PIRATEZ,
                       "Resources", "Smoke", "Projectiles_DIO.png")
VANILLA = os.path.join("bin", "standard", "xcom1", "Resources", "BulletSprites",
                       "BulletSprites.png")


def parse_style(text):
    """Строка tracer из hd/FX/weapons.txt - как HdFx::tracerStyle."""
    st = {"classic": False, "bright": False, "width": 1.0, "fade": 1.0, "head": None}
    for opt in filter(None, text.split(";")):
        key, _, value = opt.partition("=")
        if key in ("classic", "bright"):
            st[key] = True
        elif key in ("width", "fade"):
            st[key] = float(value)
        elif key == "head":
            st["head"] = np.array([float(v) for v in value.split(",")])
    return st


def row_of(frames):
    """Трассер целиком: самый яркий пиксель и самый живой цвет на полной яркости - как rowOf в makeDots."""
    px = np.concatenate([f[..., :3][f[..., 3] > 0] for f in frames if (f[..., 3] > 0).any()])
    max_lum = max(1.0, float((px[:, 0] * 2 + px[:, 1] * 5 + px[:, 2]).max()))
    v = px.max(axis=1)
    ok = (v * 10 >= v.max() * 6) & (v > 0)
    score = np.where(ok, (v - px.min(axis=1)) / np.maximum(v, 1) * v, -1.0)
    best = px[score.argmax()]
    return max_lum, best * 255.0 / best.max()


def dot(frame, k, style=None, row=None):
    """Кадр движка вместо кадра bw x bh - повторяет HdSprites::makeDots."""
    bh, bw = frame.shape[:2]
    if bw < 2 or bh < 2 or bw > MAX_DOT or bh > MAX_DOT:
        return None
    lit = frame[..., 3] > 0
    n = int(lit.sum())
    if n == 0:
        return None
    rgb = frame[..., :3].astype(np.float64)
    body = rgb[lit].mean(axis=0)
    lum = rgb[..., 0] * 2 + rgb[..., 1] * 5 + rgb[..., 2]
    lum = np.where(lit, lum, -1.0)
    peak = rgb[np.unravel_index(lum.argmax(), lum.shape)]
    fill = n / float(bw * bh)
    # шахматка - это классическая полупрозрачность: клуб на весь кадр в половину альфы
    ey, ex = np.nonzero(lit)
    even = int(((ey + ex) % 2 == 0).sum())
    dithered = n * 2 >= bw * bh and (even == 0 or even == n)
    cover = 1.0 if dithered else fill
    fade = 0.5 if dithered else 1.0
    radius = (0.37 + 0.63 * np.sqrt(cover)) * (min(bw, bh) / 2.0)
    core = peak + (255.0 - peak) * (0.35 * fill)
    if style:
        max_lum, vivid = row
        lumv = rgb[..., 0] * 2 + rgb[..., 1] * 5 + rgb[..., 2]
        rel = float(lumv[lit].mean()) / max_lum
        projectile = not dithered and n * 2 >= bw * bh and rel >= 0.55
        radius *= style["width"]
        to = None
        if projectile and style["head"] is not None:
            to = style["head"]
        elif projectile and style["bright"]:
            to = vivid
        if to is not None:
            body, core = to, to + (255.0 - to) * 0.55
        elif not projectile and style["fade"] < 1.0:
            body, core = vivid, vivid + (255.0 - vivid) * 0.3
            fade *= style["fade"] * min(1.0, rel)

    w, h = bw * k, bh * k
    xs = (np.arange(w) + 0.5) / k - bw / 2.0
    ys = (np.arange(h) + 0.5) / k - bh / 2.0
    dx, dy = np.meshgrid(xs, ys)
    t = np.sqrt(dx * dx + dy * dy) / radius
    fall = 1.0 - t * t
    hot = np.clip(1.0 - (t / 0.55) ** 2, 0.0, None)
    out = np.zeros((h, w, 4), np.float64)
    out[..., :3] = body + (core - body) * hot[..., None]
    # тонкая точка уже шага оттисков: край плотнее, чтобы луч не рассыпался на бусины
    power = 1.6 * min(1.0, style["width"]) if style else 1.6
    out[..., 3] = np.where(fall > 0.0, np.power(np.clip(fall, 0.0, None), power) * 255.0 * fade, 0.0)
    return out


def read_sheet(path):
    """Лист набора как RGBA, где индекс 0 прозрачен - ровно как его видит движок.
    У ванильного BulletSprites.png нулевой индекс розовый, и без этого лист врёт."""
    im = Image.open(path)
    if im.mode != "P":
        return np.asarray(im.convert("RGBA")).astype(np.float64)
    idx = np.asarray(im).astype(np.int32)
    pal = np.asarray(im.getpalette()[:768], np.float64).reshape(256, 3)
    out = np.zeros(idx.shape + (4,), np.float64)
    out[..., :3] = pal[idx]
    out[..., 3] = np.where(idx == 0, 0.0, 255.0)
    return out


def bresenham(p0, p1):
    p0, p1 = np.array(p0, float), np.array(p1, float)
    n = int(max(abs(p1 - p0)))
    return [tuple(np.round(p0 + (p1 - p0) * i / n).astype(int)) for i in range(n + 1)]


def to_screen(v, k):
    """Camera::convertVoxelToScreen без начала координат карты."""
    x, y, z = v
    return (int(x - y) * k, int(x / 2.0 + y / 2.0 - z) * k)


def over(dst, src, x, y):
    h, w = src.shape[:2]
    H, W = dst.shape[:2]
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return
    s = src[y0 - y:y1 - y, x0 - x:x1 - x]
    d = dst[y0:y1, x0:x1]
    a = s[..., 3:4] / 255.0
    d[..., :3] = s[..., :3] * a + d[..., :3] * (1.0 - a)


def strip(frames, traj, k, new, size, origin, bg, style=None):
    W, H = size
    dst = np.zeros((H, W, 4), np.float64)
    dst[..., :3] = bg
    dst[..., 3] = 255
    row = row_of(frames) if style else None
    if style and style["classic"]:
        new = False          # classic: кадр остаётся спрайтом, один оттиск на воксель
    for i, f in enumerate(frames):
        if i >= len(traj):
            break
        if f[..., 3].sum() == 0:
            continue
        g = dot(f, k, style, row) if new else np.repeat(np.repeat(f.astype(np.float64), k, 0), k, 1)
        if g is None:
            continue
        sx, sy = to_screen(traj[i], k)
        # шаг до следующего вокселя заполняется оттисками - повторяет Map.cpp
        steps, tx, ty = 1, 0, 0
        if new and i + 1 < len(traj):
            nx, ny = to_screen(traj[i + 1], k)
            gap = max(abs(nx - sx), abs(ny - sy))
            stride = max(1, g.shape[1] // 3)
            steps = max(1, min(4, -(-gap // stride)))
            tx, ty = nx - sx, ny - sy
        # Map.cpp сдвигает кадр на k * половину базового размера
        ox = sx + origin[0] - (f.shape[1] // 2) * k
        oy = sy + origin[1] - (f.shape[0] // 2) * k
        for st in range(steps):
            over(dst, g, ox + tx * st // steps, oy + ty * st // steps)
    return dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", default="", help="PNG набора Projectiles; по умолчанию оба известных")
    ap.add_argument("--types", default="0,2,6,14", help="номера трассеров через запятую")
    ap.add_argument("--scale", type=int, default=4)
    ap.add_argument("--from", dest="src", default="70,40,12", help="начало выстрела в вокселях")
    ap.add_argument("--to", dest="dst", default="10,30,10", help="конец выстрела в вокселях")
    ap.add_argument("--bg", default="36,40,32", help="цвет пола под трассером")
    ap.add_argument("--style", default="", help="стиль трассера (строка tracer): третья строка каждого трассера")
    ap.add_argument("--out", default=os.path.join("Claude outputs", "tracer.png"))
    args = ap.parse_args()

    k = args.scale
    bg = tuple(int(v) for v in args.bg.split(","))
    traj = bresenham([int(v) for v in args.src.split(",")],
                     [int(v) for v in args.dst.split(",")])
    pts = [to_screen(v, k) for v in traj[:BULLET_SPRITES]]
    pad = 4 * k
    W = max(p[0] for p in pts) - min(p[0] for p in pts) + 2 * pad
    H = max(p[1] for p in pts) - min(p[1] for p in pts) + 2 * pad
    origin = (pad - min(p[0] for p in pts), pad - min(p[1] for p in pts))

    sheets = [args.sheet] if args.sheet else [PIRATEZ, VANILLA]
    rows = []
    for path in sheets:
        if not os.path.exists(path):
            print("нет файла:", path)
            continue
        arr = read_sheet(path)
        total = (arr.shape[0] // SUB) * (arr.shape[1] // SUB)
        print("%s: %dx%d, %d кадров, %d трассеров"
              % (path, arr.shape[1], arr.shape[0], total, total // BULLET_SPRITES))
        cols = arr.shape[1] // SUB
        for t in [int(v) for v in args.types.split(",")]:
            base = t * BULLET_SPRITES
            if base + BULLET_SPRITES > total:
                continue
            frames = [arr[(j // cols) * SUB:(j // cols) * SUB + SUB,
                          (j % cols) * SUB:(j % cols) * SUB + SUB]
                      for j in range(base, base + BULLET_SPRITES)]
            rows.append(strip(frames, traj, k, False, (W, H), origin, bg))
            rows.append(strip(frames, traj, k, True, (W, H), origin, bg))
            if args.style:
                rows.append(strip(frames, traj, k, True, (W, H), origin, bg, parse_style(args.style)))
    if not rows:
        print("нечего показывать")
        return 1
    img = np.concatenate(rows, axis=0)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGBA").save(args.out)
    print("лист:", args.out, "- на трассер: классика, точки" + (", точки со стилем" if args.style else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
