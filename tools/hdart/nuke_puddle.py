#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Лужа ядерной зоны NUKE_WATER_2 73, 74, 75 по маске классики, без видеокарты (XP-000507, слово Vitali 05.11).

Классика: 73 и 74 - NUKE1:15 с лужей, 75 - NUKE1:16 с лужей (отличий с полем столько же, сколько пикселей лужи).
Поле - кадр NUKE1 из пака, лужа - индексы 66..72 классики мягким x4, альфа - текущего кадра (ровная кромка XP-000497).

    py -3.13 tools\hdart\nuke_puddle.py           # заготовки в art/tickets/nuke_puddle
    py -3.13 tools\hdart\nuke_puddle.py --yes     # и в обе копии мода через манифест, под очередью правок
"""
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(os.path.dirname(HERE))
os.chdir(ROOT)

import numpy as np                  # noqa: E402
from PIL import Image               # noqa: E402

import build_hd_pack as bp          # noqa: E402
import water_build as wb            # noqa: E402

TERRAIN = os.path.join("user", "mods", "hd", "hd", "TERRAIN")
OUT = os.path.join("art", "tickets", "nuke_puddle")
BASE = {73: "15.png", 74: "15.v1.png", 75: "16.png"}
WORD = "XP-000507, вариант 1, Vitali 05.11 «да» по листу"
PUDDLE = np.zeros(256, bool)
PUDDLE[66:73] = True


def load(*p):
    return np.asarray(Image.open(os.path.join(*p)).convert("RGBA")).astype(np.float32)


def build(f, frames, pal):
    a = np.asarray(frames[f])
    m = PUDDLE[a] & (a != 0)
    ch = np.dstack([pal[a][..., :3].astype(np.float32) * m[..., None], m.astype(np.float32)])
    u = wb.up_float(np.pad(ch, ((2, 2), (2, 2), (0, 0))), 1.6)[2 * wb.K:-2 * wb.K, 2 * wb.K:-2 * wb.K]
    d = np.clip(u[..., 3], 0, 1)
    icol = u[..., :3] / np.maximum(d[..., None], 1e-3)
    alpha = load(TERRAIN, "NUKE_WATER_2.PCK", "%d.png" % f)[..., 3]
    base = load(TERRAIN, "NUKE1.PCK", BASE[f])[..., :3]
    # мокрая земля вокруг лужи: тот же рельеф, темнее
    col = base * (1 - 0.28 * np.clip((d - 0.12) / 0.3, 0, 1)[..., None])
    # лужа: цвета классики, рельеф поля чуть просвечивает
    w = np.clip((d - 0.42) / 0.16, 0, 1)[..., None]
    lum = base.mean(2, keepdims=True)
    col = col * (1 - w) + icol * (0.9 + 0.1 * lum / max(float(lum[alpha > 200].mean()), 1.0)) * w
    path = os.path.join(OUT, "%d.png" % f)
    Image.fromarray(np.dstack([np.clip(col, 0, 255), alpha]).round().astype(np.uint8), "RGBA").save(path)
    return path


def main():
    os.makedirs(OUT, exist_ok=True)
    pal = np.asarray(wb.palette())
    frames = wb.read_set("NUKE_WATER_2")
    paths = {f: build(f, frames, pal) for f in BASE}
    print("заготовки:", OUT)
    if "--yes" not in sys.argv:
        return
    man = bp.load()
    rels = []
    for f, path in paths.items():
        rel = "TERRAIN/NUKE_WATER_2.PCK/%d.png" % f
        bp.stage(man, rel, path, generator="nuke_puddle", generator_version="nuke_puddle 05.11: поле NUKE1:%s, лужа по маске классики" % BASE[f][:-4],
                 source_path=path.replace(os.sep, "/"), approved=True, approval=WORD)
        rels.append(rel)
    bp.save(man, why="NUKE_WATER_2 73-75: лужа по маске классики (%s)" % WORD)
    print("game:", bp.install(man, "game", only=rels))
    print("repo:", bp.install(man, "repo", only=rels))
    for root in bp.TARGETS.values():
        for rel in rels:
            with open(os.path.join(root, rel), "rb") as fh:
                if hashlib.sha256(fh.read()).hexdigest() != man["files"][rel]["sha256"]:
                    raise SystemExit("РАСХОДИТСЯ %s %s" % (root, rel))
    print("сверено: обе копии, файлов", len(rels))


if __name__ == "__main__":
    main()
