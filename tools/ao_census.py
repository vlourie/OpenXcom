#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Этап 0 HD-теней: сколько разных сеток затенения углов (AO) дают карты Пираток.

Проект - docs/research/hd-shadows-ao-2026-10-30.md, §5. Движок не трогается, данные игры только читаются
чтецами collapse_census (MAP как BattlescapeGenerator::loadMAP, MCD как MapDataSet::loadData, патчи MCD);
сам collapse_census не правится (замок модели обрушения, R-419).

Сетка клетки с полом - занятость нижнего яруса (слои LOFT 0-1, нижние 4 вокселя) 18x18: ромб 16x16 и по
вокселю соседей. Бит LOFT - как TileEngine::voxelCheck: строка = y, бит = 15 - x. Источники: свои западная
и северная стены и предмет, западная стена и предмет клетки (x+1, y), северная стена и предмет (x, y+1),
предметы (x-1, y) и (x, y-1). Вес источника - по высоте: верхний занятый слой LOFT, min(1, (верх + 1) / 6).
Размытие - гаусс sigma 1.5 вокселя в окне 7x7, сумма с потолком 1, затем 16 уровней. Сетка из одних нулей
не рисуется и в кэш не идёт.

Не затеняются: клетка, где свой предмет закрывает >= 230 из 256 вокселей пола (пола не видно), и части
с верхним слоем LOFT 0 (плоские накладки до 2 вокселей). Уровень 1 из 16 и выше идёт в сетку.

Счёт по всем блокам террейна - верхняя оценка; «бой» - блоки наугад до площади 60x60, 200 повторов, медиана
и максимум (стыки блоков, корабль, двери и разрушения добавят - см. отчёт). Память - число сеток x 32 КБ
(ромб 32k x 16k RGBA при k = 4).

    py -3.13 tools\ao_census.py
    py -3.13 tools\ao_census.py --terrains CULTA,URBAN,...

Выход - census\ao\terrains.tsv (census в гит не идёт).
"""
import argparse
import os
import random
import sys
import time
import zlib

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_census as cc                      # noqa: E402
import pck_census as pc                           # noqa: E402

ENC = "utf-8-sig"
REC = 62
LAYERS = (0, 1)                                   # нижний ярус: воксели 0-3 над полом
MIN_TOP = 1                                       # верхний слой LOFT 0 - до 2 вокселей высоты
HIDDEN = 230                                      # свой предмет занимает столько из 256 - пола не видно
SIGMA = 1.5
LEVELS = 16
MIN_LEVEL = 1
K4_BYTES = 32 * 4 * 16 * 4 * 4                    # ромб 128 x 64 RGBA
BATTLE_CELLS = 60 * 60                            # оценка боя: блоки наугад, пока не наберётся площадь 60x60
BATTLE_RUNS = 200


def load_voxels(files):
    path = files.find(os.path.join("TERRAIN", "LOFTEMPS.DAT")) \
        or files.find(os.path.join("GEODATA", "LOFTEMPS.DAT"))
    with open(path, "rb") as f:
        data = f.read()
    vals = [data[i] | (data[i + 1] << 8) for i in range(0, len(data) - 1, 2)]
    n = len(vals) // 16
    grids = np.zeros((n, 16, 16), dtype=bool)
    for t in range(n):
        for y in range(16):
            row = vals[t * 16 + y]
            for x in range(16):
                grids[t, y, x] = bool(row & (1 << (15 - x)))
    return path, grids


def read_lofts(files, name, cache):
    """Номера LOFT 12 слоёв каждой записи MCD с патчами LOFTS (как MCDPatch::modifyData)."""
    if name in cache:
        return cache[name]
    path = files.find(os.path.join("TERRAIN", name + ".MCD"))
    recs = []
    if path:
        with open(path, "rb") as f:
            d = f.read()
        for i in range(0, len(d) - REC + 1, REC):
            recs.append(list(d[i + 8:i + 20]))
    for m in cc.PATCHES.get(name, ()):
        i = m.get("MCDIndex")
        if isinstance(i, int) and i < len(recs) and "LOFTS" in m:
            recs[i] = list(m["LOFTS"][:12]) + [0] * max(0, 12 - len(m["LOFTS"]))
    cache[name] = recs
    return recs


class Shapes:
    """(набор, запись) -> (занятость нижнего яруса 16x16, вес по высоте)."""

    def __init__(self, files, voxels):
        self.files, self.vox = files, voxels
        self.lofts = {}
        self.memo = {}

    def get(self, part):
        if part is None:
            return None
        if part in self.memo:
            return self.memo[part]
        s, idx = part
        recs = read_lofts(self.files, s, self.lofts)
        res = None
        if idx < len(recs):
            ids = recs[idx]
            n = len(self.vox)
            occ = np.zeros((16, 16), dtype=bool)
            for layer in LAYERS:
                if 0 < ids[layer] < n:
                    occ |= self.vox[ids[layer]]
            top = max((i for i, v in enumerate(ids) if 0 < v < n and self.vox[v].any()), default=-1)
            if occ.any() and top >= MIN_TOP:     # плоская накладка (обломки, плита) ничего не загораживает
                res = (occ, min(1.0, (top + 1) / 6.0))
        self.memo[part] = res
        return res


def kernel():
    r = 3
    ax = np.arange(-r, r + 1)
    g = np.exp(-(ax[:, None] ** 2 + ax[None, :] ** 2) / (2 * SIGMA * SIGMA))
    return g / g[r, r] * 0.5                     # соседний воксель стены даёт ~0.4, через 3 - ~0.05


KER = kernel()


def ao_grid(occ18):
    """Размытая занятость 18x18 -> квантованная сетка ромба 16x16 (байты) или None, если пусто."""
    p = np.pad(occ18, 3)
    out = np.zeros((16, 16))
    for dy in range(7):
        for dx in range(7):
            w = KER[dy, dx]
            out += w * p[dy + 1:dy + 17, dx + 1:dx + 17]
    q = np.minimum(LEVELS - 1, np.round(np.minimum(1.0, out) * (LEVELS - 1))).astype(np.uint8)
    q[q < MIN_LEVEL] = 0                         # слабее этого на полу не видно (альфа < 2 %)
    if not q.any():
        return None
    return q.tobytes()


def cell_key(blk, x, y, z):
    """Части, от которых зависит сетка клетки: свои W, N, O; (x+1,y) W, O; (x,y+1) N, O; (x-1,y) O; (x,y-1) O."""
    def part(k, xx, yy):
        key = blk.lv[z][k].get((xx, yy))
        if key is None:
            return None
        p = blk.parts[key]
        return (p["set"], p["idx"])
    return (part("w", x, y), part("n", x, y), part("o", x, y),
            part("w", x + 1, y), part("o", x + 1, y),
            part("n", x, y + 1), part("o", x, y + 1),
            part("o", x - 1, y), part("o", x, y - 1))


def build(shapes, key):
    own_w, own_n, own_o, e_w, e_o, s_n, s_o, w_o, n_o = (shapes.get(p) for p in key)
    if own_o is not None and own_o[0].sum() >= HIDDEN:
        return None
    g = np.zeros((18, 18))                       # [y + 1, x + 1]
    def put(sh, ys, xs, src_ys, src_xs):
        if sh is None:
            return
        occ, w = sh
        g[ys, xs] = np.maximum(g[ys, xs], occ[src_ys, src_xs] * w)
    full = slice(0, 16)
    for sh in (own_w, own_n, own_o):
        put(sh, slice(1, 17), slice(1, 17), full, full)
    for sh in (e_w, e_o):                        # столбец x = 0 соседа справа -> наш x = 16
        put(sh, slice(1, 17), 17, full, 0)
    for sh in (s_n, s_o):                        # строка y = 0 соседа снизу -> наш y = 16
        put(sh, 17, slice(1, 17), 0, full)
    put(w_o, slice(1, 17), 0, full, 15)
    put(n_o, 0, slice(1, 17), 15, full)
    return ao_grid(g)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", default=os.path.join("Пиратки", "Dioxine_XPiratez"))
    ap.add_argument("--mod", default="Piratez")
    ap.add_argument("--master", default="xcom1")
    ap.add_argument("--out", default=os.path.join("census", "ao"))
    ap.add_argument("--terrains", default="", help="через запятую; пусто - все")
    args = ap.parse_args()
    only = {t.strip().upper() for t in args.terrains.split(",") if t.strip()}

    t0 = time.time()
    mod_dir, files, _, loft_occ = cc.open_data(args)
    loft_path, voxels = load_voxels(files)
    print("LOFT: %s, %d шаблонов" % (loft_path, len(voxels)))
    shapes = Shapes(files, voxels)
    grid_of = {}                                 # ключ частей -> сетка или None
    block_of = {}                                # (блок, наборы) -> сводка блока; блок на тех же наборах - тот же
    all_grids = set()
    errors = 0
    mcd_cache, sizes = {}, {}
    rows = []
    # каждый террейн со всеми своими блоками: cc.all_blocks пропускает блок, уже встреченный в другом
    # террейне на тех же наборах, и занижал бы счёт террейнов-близнецов
    for tname, (kind, t) in sorted(cc.collect(mod_dir).items()):
        if only and tname.upper() not in only:
            continue
        blocks = []
        for b in t.get("mapBlocks") or []:
            bname = b.get("name") if isinstance(b, dict) else None
            if not bname:
                continue
            sig = (bname, tuple(t.get("mapDataSets") or []))
            if sig not in block_of:
                blk, _ = cc.load_block(files, tname, kind, t, bname, mcd_cache, loft_occ, sizes)
                if blk is None:
                    errors += 1
                    block_of[sig] = None
                    continue
                s = {"name": bname, "area": blk.sx * blk.sy, "cells": 0, "ao": 0, "keys": set(), "grids": set()}
                for z in range(blk.sz):
                    for (x, y) in blk.lv[z]["f"]:
                        s["cells"] += 1
                        key = cell_key(blk, x, y, z)
                        if key not in grid_of:
                            grid_of[key] = build(shapes, key)
                        g = grid_of[key]
                        if g is not None:
                            s["ao"] += 1
                            s["keys"].add(key)
                            s["grids"].add(g)
                block_of[sig] = s
            if block_of[sig] is not None:
                blocks.append(block_of[sig])
        if not blocks:
            continue
        grids = set().union(*(b["grids"] for b in blocks))
        all_grids |= grids
        big = max(blocks, key=lambda b: len(b["grids"]))
        # бой: блоки наугад, пока не наберётся площадь BATTLE_CELLS (повторяемо: зерно от имени террейна)
        rnd = random.Random(zlib.crc32(tname.encode("utf-8")))
        battle = []
        for _ in range(BATTLE_RUNS):
            got, area = set(), 0
            while area < BATTLE_CELLS:
                b = rnd.choice(blocks)
                got |= b["grids"]
                area += max(1, b["area"])
            battle.append(len(got))
        battle.sort()
        rows.append((tname, kind, len(blocks), sum(b["cells"] for b in blocks), sum(b["ao"] for b in blocks),
                     len(set().union(*(b["keys"] for b in blocks))), len(grids), big["name"], len(big["grids"]),
                     battle[len(battle) // 2], battle[-1], round(len(grids) * K4_BYTES / 2 ** 20, 1)))
    rows.sort(key=lambda r: -r[6])
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, "terrains.tsv")
    with open(path, "w", encoding=ENC, newline="") as f:
        f.write("terrain\tkind\tblocks\tfloor_cells\tao_cells\tpart_keys\tgrids\tblock_max_name\tblock_max"
                "\tbattle_median\tbattle_max\tmb_k4\n")
        for r in rows:
            f.write("\t".join(str(v) for v in r) + "\n")
    print("террейнов %d, блоков с ошибкой %d, ключей частей %d, сеток всего %d (%.1f МБ при k=4), %.0f с"
          % (len(rows), errors, len(grid_of), len(all_grids), len(all_grids) * K4_BYTES / 2 ** 20, time.time() - t0))
    print("->", path)


if __name__ == "__main__":
    main()
