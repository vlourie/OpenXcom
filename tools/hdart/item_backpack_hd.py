#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""HD-кадры предметов-заглушек места РЮКЗАКА без чёрного квадрата (тикет XP-000537, Vitali 08.11 «все 42»).

В Пиратках предметы слота STR_BACK_PACK (INV_JETPACK_*, INV_OXYGEN_*, генератор, ранцы) нарисованы на чёрном ИНДЕКСЕ 15, а не на
прозрачном 0: на тёмно-коричневом HD-инвентаре видно чёрный прямоугольник по размеру кадра. Здесь по классике строится HD-кадр x4:
внешний чёрный (заливка индекса 15 от края кадра, через прозрачный 0) - прозрачный; чёрный внутри предмета (обводка, просветы
между лямками) остаётся. Силуэт - по маске классики: маска x4 бикубом, размытие, мягкий порог - прямые отрезки с
подавлением лесенки (правило 12); цвета внутри - классика x4 как есть, цвет за кромкой дотянут от ближайшей точки предмета.

Номер кадра HD - номер в игре: ключ из Piratez_Resources.rul + 1000 для ключей выше общих кадров (Gold 121 -> 1121, труп 2921 -> 3921).

    py -3.13 tools/hdart/item_backpack_hd.py            # собрать в census/items/redo/backpack/pack/BIGOBS.PCK + лист
    py -3.13 tools/hdart/item_backpack_hd.py --install  # поставить в обе копии мода hd (держа очередь правок)
"""
import argparse
import hashlib
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
ROOT = Path(HERE).resolve().parents[1]
BLANKS = ROOT / "Пиратки" / "Dioxine_XPiratez" / "user" / "mods" / "Piratez" / "Resources" / "Blanks"
PALETTE = ROOT / "census" / "items" / "redo" / "palette.pal.txt"
OUT = ROOT / "census" / "items" / "redo" / "backpack" / "pack" / "BIGOBS.PCK"
GAME = ROOT / "Пиратки" / "Dioxine_XPiratez" / "user" / "mods" / "hd" / "hd"
REPO = ROOT / "user" / "mods" / "hd" / "hd"
SET = "BIGOBS.PCK/"
MOD_OFFSET = 1000
K = 4
# ключ в рулсете Piratez -> файл Resources/Blanks (все кадры слота рюкзака с чёрным индексом 15, 15 штук)
FRAMES = {837: "Generator_4x3", 838: "Oxygen_4x3", 839: "Oxygen_2x3", 840: "Jetpack_A_3x3", 841: "Jetpack_B_3x3",
          842: "Jetpack_C_3x3", 843: "Jetpack_D_3x3", 844: "Jetpack_E_3x3", 845: "Jetpack_F_3x3", 849: "Jetpack_Small_A_2x2",
          3917: "BMMS_Pack2", 3918: "FlamerBackpackJet", 3921: "BMMS_Pack2Gnome", 4848: "Jetpack_Small_B_2x1",
          4849: "Jetpack_Central_2x3"}


def game_frame(key):
    return key + MOD_OFFSET


def palette():
    rows = [tuple(int(v) for v in l.split()) for l in PALETTE.read_text(encoding="ascii").split("\n") if l.strip()]
    assert len(rows) == 256
    return np.array(rows, np.uint8)


def outer_bg(ix):
    """Внешний фон: индексы 15 и 0, связные (4 соседа) с краем кадра через 15/0."""
    h, w = ix.shape
    free = (ix == 15) | (ix == 0)
    seen = np.zeros((h, w), bool)
    stack = [(y, x) for y in range(h) for x in range(w) if (y in (0, h - 1) or x in (0, w - 1)) and free[y, x]]
    for y, x in stack:
        seen[y, x] = True
    while stack:
        y, x = stack.pop()
        for yy, xx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
            if 0 <= yy < h and 0 <= xx < w and free[yy, xx] and not seen[yy, xx]:
                seen[yy, xx] = True
                stack.append((yy, xx))
    return seen


def build(ix, pal):
    h, w = ix.shape
    bg = outer_bg(ix)
    item = ~bg & (ix != 0)                    # непрозрачные точки: предмет, чёрное внутри него
    # силуэт: маска x4 бикубом (края в ровные скаты), размытие, мягкий порог
    m = Image.fromarray((item * 255).astype(np.uint8), "L")
    # поле вокруг, чтобы кромка кадра не резалась размытием и бикубом
    pad = 4
    mp = Image.new("L", (w + 2 * pad, h + 2 * pad), 0)
    mp.paste(m, (pad, pad))
    big = mp.resize(((w + 2 * pad) * K, (h + 2 * pad) * K), Image.BICUBIC).filter(ImageFilter.GaussianBlur(K * 0.55))
    a = np.asarray(big, np.float32) / 255.0
    lo, hi = 0.5 - 0.13, 0.5 + 0.13
    t = np.clip((a - lo) / (hi - lo), 0, 1)
    alpha = t * t * (3 - 2 * t)
    alpha = alpha[pad * K:(pad + h) * K, pad * K:(pad + w) * K]
    # цвет: классика x4; за кромкой (фон и прозрачное) - цвет ближайшей точки предмета, чтобы не было тёмной каймы
    rgb = pal[ix].astype(np.float32)
    have = item.copy()
    for _ in range(4):
        grow = np.zeros_like(have)
        acc = np.zeros_like(rgb)
        cnt = np.zeros(have.shape, np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            sh = np.roll(np.roll(have, dy, 0), dx, 1)
            shc = np.roll(np.roll(rgb, dy, 0), dx, 1)
            ok = sh & ~have
            acc += shc * ok[..., None]
            cnt += ok
        new = cnt > 0
        rgb = np.where(new[..., None], acc / np.maximum(cnt, 1)[..., None], rgb)
        have = have | new
    col = np.repeat(np.repeat(rgb, K, 0), K, 1)
    out = np.dstack([np.clip(col, 0, 255), alpha * 255.0]).round().astype(np.uint8)
    return Image.fromarray(out, "RGBA"), item, bg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--approval", default="Vitali 08.11: тикет XP-000537, все 42 (15 кадров слота рюкзака, чёрный 15 -> прозрачно)")
    a = ap.parse_args()
    os.chdir(ROOT)
    sys.stdout.reconfigure(encoding="utf-8")
    pal = palette()
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for key, name in FRAMES.items():
        src = Image.open(BLANKS / (name + ".png"))
        ix = np.array(src)
        emb = np.array(src.getpalette()[:768], np.uint8).reshape(256, 3)
        used = np.unique(ix)
        same = bool(np.all(emb[used] == pal[used]))
        im, item, bg = build(ix, pal)
        f = OUT / ("%d.wide.png" % game_frame(key))
        im.save(f)
        rows.append((key, name, src.size, int(bg.sum()), int(((ix == 15) & ~bg).sum()), same))
        print("%5d -> %5d %-22s %s внешнего фона %4d, чёрного внутри %3d, палитра файла = игры: %s" % (key, game_frame(key), name, src.size, rows[-1][3], rows[-1][4], same))
    if a.install:
        install(a.approval)


def install(approval):
    import build_hd_pack as bp
    man = bp.load()
    rels = []
    for f in sorted(OUT.glob("*.wide.png")):
        rel = SET + f.name
        old = man["files"].get(rel, {}).get("sha256")
        bp.stage(man, rel, str(f), generator="item_backpack_hd", generator_version="item_backpack_hd.py 08.11",
                 source_path=str(f.relative_to(ROOT)).replace(os.sep, "/"), approved=True, approval=approval,
                 source_frame="BIGOBS:" + f.name.split(".")[0], replaced=old)
        rels.append(rel)
    bp.save(man, why="item_backpack_hd: %d кадров BIGOBS, место рюкзака без чёрного (XP-000537)" % len(rels))
    print("game:", bp.install(man, "game", only=rels))
    print("repo:", bp.install(man, "repo", only=rels))
    bad = 0
    for r in rels:
        for root in (GAME, REPO):
            if hashlib.sha256((root / r).read_bytes()).hexdigest() != man["files"][r]["sha256"]:
                print("РАСХОДИТСЯ", root, r)
                bad += 1
    print("сверка: расхождений", bad)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
