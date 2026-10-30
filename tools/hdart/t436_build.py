#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикеты XP-000436 / XP-000437 (снег POLAR и семья): вариант A (выбор Vitali) - разломы 2x2, проталины, камушки.
Кластер - один холст 2x2 (раскладка движка: a (x0,y0), a+1 (x0,y1), a+2 (x1,y0), a+3 (x1,y1)); одиночные плитки -
тот же приём на холсте из одной плитки. Фон - HD-плитка набора (POLAR: кадр 32 с крапом, варианты v0..v3; у наборов без
вариантов - зеркала плитки), ровно та же ромб-маска, что у соседнего фона, поэтому края с окружением не расходятся.
Рисунок - по классике: маска «не фон» (индексы палитры вне фона набора), края ровные (размытие + мягкий порог,
лесенки x4 нет); светлая кайма (индексы светлее порога) и тёмное ядро идут двумя масками: ядро - с меньшим размытием,
чтобы 1-px штрихи классики остались штрихами. Цвет - палитра классики (нормированная свёртка по маске). Нарезка на
кадры по холсту: шва между плитками нет по построению. Видеокарта не нужна, в мод ничего не ставит.

    py -3.13 tools\hdart\t436_build.py            # POLAR + семья -> art/tickets/t436/cand
"""
import os
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
os.chdir(ROOT)
import ticket_scene as ts  # noqa: E402
import water_build as wb   # noqa: E402

CAND = ROOT / "art" / "tickets" / "t436" / "cand"
K = 4
OFFS = [(16, 0), (0, 8), (32, 8), (16, 16)]     # a, a+1, a+2, a+3 на холсте (пиксели базы)
DRAW = [0, 2, 1, 3]                              # порядок рисования движка: y, затем x
CW, CH = 64, 56
LUM = np.array([0.299, 0.587, 0.114], np.float32)
P = dict(
    sig=0.6, sig2=1.2, edge=(0.38, 0.56),     # маска каймы (всё «не фон»)
    sigc=0.42, sig2c=0.8, edgec=(0.40, 0.58),  # маска тёмного ядра: 1-px штрихи остаются штрихами
    core_frac=0.58,                            # ядро - светлота < доли светлоты фона
    tsig=0.45, sharp=1.1, bil=1, fade=1.2, gain=1.0,
)

# фон набора: индексы фона и HD-плитка основы (набор, кадр, как делать варианты плиток)
CFG = {
    "POLAR": dict(bg=(1, 2), base=("POLAR", 32), vars="v"),
    "ASHEN1": dict(bg=(1, 2), base=("POLAR", 32), vars="v"),
    "FORESTSWAMP_SNOW": dict(bg=(1, 2, 3, 224, 225, 226), base=("FORESTSWAMP_SNOW", 22), vars=[22, 4, 35, 22]),
    "BEACH": dict(bg=(160,), base=("BEACH", 32), vars=[32, 32, 32, 32]),   # плоский песок - один кадр, как соседний фон
}
_SC = None


def scene():
    global _SC
    if _SC is None:
        _SC = ts.Scene()
    return _SC


def smooth(t, lo, hi):
    x = np.clip((t - lo) / (hi - lo), 0, 1)
    return x * x * (3 - 2 * x)


def base_tiles(cfg):
    sc = scene()
    s, f = cfg["base"]
    t0 = sc.hd(s, f)
    if cfg["vars"] == "v":
        return [t0] + sc.variants(s, f)
    if isinstance(cfg["vars"], list):
        return [sc.hd(s, g) for g in cfg["vars"]]
    # ромб лежит в строках 100-159 кадра: зеркала - только его, иначе ромб уезжает наверх кадра
    def fl(t, h, v):
        r = t.crop((0, 100, 128, 160))
        if h:
            r = ImageOps.mirror(r)
        if v:
            r = ImageOps.flip(r)
        o = Image.new("RGBA", t.size, (0, 0, 0, 0))
        o.paste(r, (0, 100))
        return o
    return [t0, fl(t0, 1, 0), fl(t0, 0, 1), fl(t0, 1, 1)]


def build(sset, frames, variants=(0, 1, 2, 3), **kw):
    """frames: список из 4 номеров кадров (кластер; None - плитка без разлома) или из 1 (одиночная плитка).
    Возвращает ({кадр: RGBA 128x160}, холст RGBA)."""
    p = dict(P)
    p.update(kw)
    cfg = CFG[sset]
    sc = scene()
    fr = wb.read_set(sset)
    pal = sc.pal
    n = len(frames)
    draw = DRAW if n == 4 else [0]
    idx = np.zeros((CH, CW), np.int32)
    for i in draw:
        if frames[i] is None:
            continue
        a = fr[frames[i]]
        ox, oy = OFFS[i]
        sub = idx[oy:oy + 40, ox:ox + 32]
        sub[a > 0] = a[a > 0]
    # плитки без кадра (None) - обычный фон: учитываем их ромб в объединении
    union = np.zeros((CH, CW), bool)
    refm = np.asarray(sc.classic("POLAR", 32).resize((32, 40), Image.NEAREST))[..., 3] > 0
    for i in draw:
        ox, oy = OFFS[i]
        union[oy:oy + 40, ox:ox + 32] |= refm
    snow = Image.new("RGBA", (CW * K, CH * K), (0, 0, 0, 0))
    tiles = base_tiles(cfg)
    for i in draw:
        snow.alpha_composite(tiles[variants[i] % len(tiles)], (OFFS[i][0] * K, OFFS[i][1] * K))
    snow = np.asarray(snow).astype(np.float32)
    # --- поля разлома
    crack = (idx > 0) & ~np.isin(idx, cfg["bg"])
    rgbc = pal[idx.clip(0, 255)][..., :3].astype(np.float32)
    lum = rgbc @ LUM
    bgl = float(np.median(pal[list(cfg["bg"])][:, :3].astype(np.float32) @ LUM))
    core = crack & (lum < p["core_frac"] * bgl)
    sz = (CW * K, CH * K)

    def field(m, sg, sg2, edge):
        mb = cv2.GaussianBlur(m.astype(np.float32), (0, 0), sg, borderType=cv2.BORDER_CONSTANT)
        up = cv2.resize(mb, sz, interpolation=cv2.INTER_CUBIC)
        up = cv2.GaussianBlur(up, (0, 0), sg2)
        return smooth(up, *edge)

    A = np.maximum(field(crack, p["sig"], p["sig2"], p["edge"]), field(core, p["sigc"], p["sig2c"], p["edgec"]))
    col = rgbc.copy()
    col[~crack] = 0
    cmf = crack.astype(np.float32)
    num = np.dstack([cv2.GaussianBlur(col[..., c] * cmf, (0, 0), p["tsig"]) for c in range(3)])
    den = cv2.GaussianBlur(cmf, (0, 0), p["tsig"])
    T = num / np.maximum(den, 1e-4)[..., None]
    T2 = np.clip(cv2.resize(T, sz, interpolation=cv2.INTER_CUBIC), 0, 255).astype(np.float32)
    for _ in range(p["bil"]):
        T2 = cv2.bilateralFilter(T2, 0, 26, 4)
    T2 = np.clip(T2 + p["sharp"] * (T2 - cv2.GaussianBlur(T2, (0, 0), 1.6)), 0, 255)
    # край кластера: разлом гаснет у внешней границы (иначе срез лесенкой по ромбу)
    um = cv2.resize(union.astype(np.uint8) * 255, sz, interpolation=cv2.INTER_NEAREST) > 0
    ud = cv2.distanceTransform(um.astype(np.uint8), cv2.DIST_L2, 5).astype(np.float32) / K
    ud = cv2.GaussianBlur(ud, (0, 0), 3.0)
    A = A * smooth(ud, 0.0, p["fade"]) * p["gain"]
    rgb = snow[..., :3] * (1 - A[..., None]) + T2 * A[..., None]
    out = np.zeros((CH * K, CW * K, 4), np.float32)
    out[..., :3] = rgb
    out[..., 3] = snow[..., 3]
    al = np.asarray(tiles[0])[..., 3] > 0
    res = {}
    for i in range(n):
        if frames[i] is None:
            continue
        ox, oy = OFFS[i if n == 4 else 0]
        a4 = np.zeros((160, 128, 4), np.uint8)
        sub = out[oy * K:(oy + 40) * K, ox * K:(ox + 32) * K]
        a4[..., :3] = np.where(al[..., None], np.clip(sub[..., :3], 0, 255), 0).astype(np.uint8)
        a4[..., 3] = np.where(al, 255, 0)
        res[frames[i]] = Image.fromarray(a4, "RGBA")
    canvas = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")
    return res, canvas


# --- что строить -------------------------------------------------------------------------------------------
CLUSTERS_POLAR = [40, 44, 48, 52, 56]
SINGLES_POLAR = [0, 1, 2, 3, 4, 5, 6, 33, 34, 35, 36, 37, 38, 39]


def jobs(sset):
    """[(кадры-список, «одиночная»)] для набора: номера кадров своего набора."""
    if sset in ("POLAR", "BEACH"):
        return [([b, b + 1, b + 2, b + 3]) for b in CLUSTERS_POLAR] + [[f] for f in SINGLES_POLAR]
    if sset == "FORESTSWAMP_SNOW":
        return [[36, 37, 38, 39], [40, 41, 42, 43], [44, 45, 46, 47], [None, 30, 31, 32]] + \
               [[f] for f in (0, 23, 24, 25, 26, 27, 28, 29)]
    if sset == "ASHEN1":
        return [[5], [6]]                    # 36-59 - побайтно классика POLAR, берутся копии кандидатов POLAR
    return []


def single_kw(f, sset):
    """одиночные камушки (серая шкала) - чётче; проталины - стандартно"""
    if sset == "POLAR" and f >= 33 or sset == "BEACH" and f >= 33 or sset == "FORESTSWAMP_SNOW" and f >= 23:
        return dict(tsig=0.4, sharp=1.2, sig=0.5, sig2=0.9)
    return {}


def run(sset, only=None, outdir=None):
    outdir = Path(outdir) if outdir else CAND / sset
    outdir.mkdir(parents=True, exist_ok=True)
    done = []
    for fl in jobs(sset):
        if only and not set(only) & set(x for x in fl if x is not None):
            continue
        if len(fl) == 1:
            res, cv = build(sset, fl, variants=(fl[0] % 4,) * 4, **single_kw(fl[0], sset))
        else:
            res, cv = build(sset, fl)
            cv.save(outdir / ("_canvas_%d.png" % [x for x in fl if x is not None][0]))
        for f, im in res.items():
            im.save(outdir / ("%d.png" % f))
            done.append(f)
    return sorted(done)


# ASHEN1:36-59 - побайтно классика POLAR; кадры с одобренным своим HD (манифест, tile_edge) не трогаем
ASHEN1_APPROVED = list(range(36, 41)) + list(range(44, 48))


def copy_ashen():
    import shutil
    d = CAND / "ASHEN1"
    d.mkdir(parents=True, exist_ok=True)
    out = []
    for f in range(36, 60):
        if f in ASHEN1_APPROVED:
            continue
        shutil.copyfile(CAND / "POLAR" / ("%d.png" % f), d / ("%d.png" % f))
        out.append(f)
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sets = sys.argv[1:] or ["POLAR", "BEACH", "FORESTSWAMP_SNOW", "ASHEN1"]
    for s in sets:
        d = run(s)
        if s == "ASHEN1":
            d = sorted(d + copy_ashen())
        print(s, len(d), "кадров:", d)


if __name__ == "__main__":
    main()
