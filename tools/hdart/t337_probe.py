#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000337: двухтайловые койки XB1BR:52+53 и перекраски LAM_BASE2:14+12, 19+18 собраны из разных поколений HD,
посередине шов. Здесь койка рисуется ЦЕЛИКОМ на холсте обеих клеток и режется обратно на кадры. Видеокарта не нужна,
в мод ничего не ставится (ставит t337_install.py по слову Vitali). Кадры - art/tickets/t337/cand/<вариант>/.

Рецепт (как t262/t277/t280, R-265: свет и тон с целого холста, не по клетке):
  1. классика обеих клеток склеивается на холсте 48x48 базы по раскладке карты (53 в (16,0), 52 под ним слева в (0,8);
     у LAM 18/19 - 18 в (0,0), 19 в (16,8)); порядок рисования как в движке (z, y, x: позже - сверху);
  2. цвета классики внутри маски заливаются на край (без чёрной каймы), бикубика x4, мягкая крупная сглаживающая
     фильтрация без размытия границ (bilateral) - тон, форма и свет ЦЕЛОГО холста, один на обе клетки;
  3. мелкая фактура - высокие частоты донора (кадр HD из пака или из бэкапа SDXL), куски 16x16, растушёвка hanning,
     множителем на тон (светлее/темнее в процентах), а не прибавкой цвета - оттенок остаётся классическим;
  4. нарезка: у каждого кадра маска и размер как у классики (NEAREST x4) - геометрия клетки та же, что у кадров пака.

Варианты (фактура разная, форма и тон одни):
  A  зерно из текущего кадра головной половины (XB1BR:52 / LAM_BASE2:14) - тёмное зернистое SDXL 24.09
  B  зерно из полной половины (XB1BR:53 из бэкапа SDXL 62e87b78 / LAM_BASE2:12) - мельче, ближе к гладкому
  C  без зерна - чистое сглаженное увеличение классики по маске (+ едва заметный шум против «пластика»)

    py -3.13 tools\hdart\t337_probe.py            # кадры всех вариантов в art/tickets/t337/cand
    py -3.13 tools\hdart\t337_probe.py --stats    # меры: тон против классики, шов, совпадение маски
"""
import argparse
import os
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.chdir(ROOT)
import ticket_scene as ts  # noqa: E402

CAND = ROOT / "art" / "tickets" / "t337" / "cand"
BACKUP = ROOT / "art" / "_backup" / "TERRAIN_before_lora_20260924_1057"
K = 4
LUM = np.array([0.299, 0.587, 0.114], np.float32)

# пара: порядок рисования (позже - сверху) и положение клетки на холсте базы 48x48
PAIRS = {
    "XB": {"label": "XB1BR 52+53", "cells": [("XB1BR", 53, 16, 0), ("XB1BR", 52, 0, 8)],
           "donor": {"A": ("XB1BR", 52, None), "B": ("XB1BR", 53, "backup")}},
    "LAM12": {"label": "LAM_BASE2 14+12", "cells": [("LAM_BASE2", 12, 16, 0), ("LAM_BASE2", 14, 0, 8)],
              "donor": {"A": ("LAM_BASE2", 14, None), "B": ("LAM_BASE2", 12, None)}},
    "LAM18": {"label": "LAM_BASE2 19+18", "cells": [("LAM_BASE2", 18, 0, 0), ("LAM_BASE2", 19, 16, 8)],
              "donor": {"A": ("LAM_BASE2", 19, None), "B": ("LAM_BASE2", 18, None)}},
}
CW, CH = 48, 48
VARIANTS = {"A": "A_зерно_головной", "B": "B_зерно_полной", "C": "C_чисто"}
VDIR = {"A": "A_g_head", "B": "B_g_full", "C": "C_clean"}
# сила зерна (доля тона) по семье: койки XB - дерево, зерно заметнее; LAM - позолота и серая сетка, зерно слабее
GAIN = {"XB": {"A": 0.11, "B": 0.09, "C": 0.03}, "LAM12": {"A": 0.065, "B": 0.055, "C": 0.025},
        "LAM18": {"A": 0.065, "B": 0.055, "C": 0.025}}
EDGE_LO, EDGE_SPAN, EDGE_AA = 45.0, 45.0, 1.0    # размах яркости в 3x3 базы: резкий край от 45, полностью с 90
SHARP = 0.55    # нерезкая маска после увеличения: возвращает чёткость краям, потерянную при сглаживании ступенек


def blur(a, s):
    return cv2.GaussianBlur(a, (0, 0), s, borderType=cv2.BORDER_REFLECT)


def classic_base(sc, s, f):
    """Классика 32x40 (цвета палитры Пираток, альфа 0/255)."""
    return np.asarray(sc.classic(s, f).resize((32, 40), Image.NEAREST)).astype(np.float32)


def classic_canvas(sc, pair):
    """Склейка классики на холсте 48x48: цвета, маска, маска каждой клетки."""
    rgb = np.zeros((CH, CW, 3), np.float32)
    msk = np.zeros((CH, CW), bool)
    own = {}
    for s, f, ox, oy in PAIR_CELLS(pair):
        c = classic_base(sc, s, f)
        m = c[..., 3] > 0
        sub = np.zeros((CH, CW), bool)
        sub[oy:oy + 40, ox:ox + 32] = m
        own[(s, f)] = sub
        reg = rgb[oy:oy + 40, ox:ox + 32]
        reg[m] = c[..., :3][m]
        msk[oy:oy + 40, ox:ox + 32] |= m
    return rgb, msk, own


def PAIR_CELLS(pair):
    return PAIRS[pair]["cells"]


def fill_out(rgb, m, it=4):
    """Цвета с края маски выдавливаются наружу нормированной сверткой (без чёрной каймы и без ярких максимумов)."""
    rgb = rgb.copy()
    known = m.copy()
    for _ in range(it):
        w = known.astype(np.float32)
        num = np.dstack([cv2.blur(rgb[..., c] * w, (3, 3)) for c in range(3)])
        den = cv2.blur(w, (3, 3))
        new = num / np.maximum(den, 1e-3)[..., None]
        grow = (~known) & (den > 0.05)
        rgb[grow] = new[grow]
        known = known | grow
    return rgb


def low_field(rgb48, m48):
    """Тон и форма целого холста: бикубика x4 по заполненным цветам (плавные места), у резких краёв классики - её
    ступеньки почти как есть (иначе переход свет/тьма размазывается и при наложении соседней клетки остаётся тёмной
    бахромой по диагонали клетки), затем сглаживание, не размывающее границ."""
    fl = fill_out(rgb48, m48)
    up = cv2.resize(fl, (CW * K, CH * K), interpolation=cv2.INTER_CUBIC)
    up = np.clip(up, 0, 255).astype(np.float32)
    lum = fl @ LUM
    rng = cv2.dilate(lum, np.ones((3, 3), np.uint8)) - cv2.erode(lum, np.ones((3, 3), np.uint8))
    rng = cv2.resize(rng, (CW * K, CH * K), interpolation=cv2.INTER_NEAREST)
    wedge = np.clip((blur(rng, 2.0) - EDGE_LO) / EDGE_SPAN, 0, 1)[..., None]
    near = cv2.GaussianBlur(cv2.resize(fl, (CW * K, CH * K), interpolation=cv2.INTER_NEAREST), (0, 0), EDGE_AA)
    up = up * (1 - wedge) + near * wedge
    # ступеньки классики 1 px -> 4 px гасятся билатеральным: резкие края (проём, монитор, кольца бочки) остаются
    for _ in range(2):
        up = cv2.bilateralFilter(up, 0, 28, 5)
    up = up + SHARP * (up - cv2.GaussianBlur(up, (0, 0), 2.0))
    return np.clip(up, 0, 255)


def mask_up(m48):
    return cv2.resize(m48.astype(np.uint8) * 255, (CW * K, CH * K), interpolation=cv2.INTER_NEAREST) > 0


def donor_image(sc, spec):
    s, f, src = spec
    if src == "backup":
        return Image.open(BACKUP / (s + ".PCK") / ("%d.png" % f)).convert("RGBA")
    return sc.hd(s, f)


def donor_bank(img, P=16):
    """Куски высоких частот яркости донора (отн. к местному тону) внутри его маски."""
    a = np.asarray(img.convert("RGBA")).astype(np.float32)
    al = a[..., 3] > 128
    lum = a[..., :3] @ LUM
    reg = ndi.binary_erosion(al, iterations=3)
    hp = (lum - blur(lum, 2.5)) / np.maximum(blur(lum, 2.5), 60.0)
    hp = np.clip(hp, -3 * hp[reg].std(), 3 * hp[reg].std())
    ys, xs = np.nonzero(reg)
    bank = []
    for y, x in zip(ys[::3], xs[::3]):
        if y + P <= hp.shape[0] and x + P <= hp.shape[1] and reg[y:y + P, x:x + P].mean() > 0.95:
            bank.append(hp[y:y + P, x:x + P])
    return bank


def grain_field(bank, shape, seed, P=16):
    H, W = shape
    out = np.zeros(shape, np.float32)
    wsum = np.zeros(shape, np.float32)
    if not bank:
        return out
    r = np.random.RandomState(seed)
    h1 = np.hanning(P + 2)[1:-1].astype(np.float32)
    win = np.outer(h1, h1)
    for _ in range(int(H * W / (P * P) * 8)):
        y = r.randint(-P // 2, H - P // 2)
        x = r.randint(-P // 2, W - P // 2)
        p = bank[r.randint(len(bank))]
        if r.rand() < 0.5:
            p = p[:, ::-1]
        if r.rand() < 0.5:
            p = p[::-1]
        y0, x0 = max(y, 0), max(x, 0)
        y1, x1 = min(y + P, H), min(x + P, W)
        if y1 <= y0 or x1 <= x0:
            continue
        out[y0:y1, x0:x1] += (p * win)[y0 - y:y1 - y, x0 - x:x1 - x]
        wsum[y0:y1, x0:x1] += win[y0 - y:y1 - y, x0 - x:x1 - x]
    out = out / np.maximum(wsum, 1e-3)
    return out / (out.std() + 1e-6)


def compose_pair(sc, pair, variant, seed=337):
    """Цельная койка на холсте 192x192 (RGB) + маска + маски клеток (x4). Один свет и один тон на обе клетки."""
    rgb48, m48, own = classic_canvas(sc, pair)
    low = low_field(rgb48, m48)
    mk = mask_up(m48)
    own = {key: mask_up(m) for key, m in own.items()}
    mk0 = mk
    if variant == "C":
        g = np.random.RandomState(seed).randn(CH * K, CW * K).astype(np.float32)
        g = blur(g, 1.2)
        g /= g.std() + 1e-6
    else:
        bank = donor_bank(donor_image(sc, PAIRS[pair]["donor"][variant]))
        g = grain_field(bank, (CH * K, CW * K), seed)
    # зерно слабее в самых тёмных местах (проём бочки чёрный - шума там не надо) и в самых светлых бликах
    lum = low @ LUM
    amp = GAIN[pair][variant] * np.clip(lum / 90.0, 0.15, 1.0) * np.clip((250.0 - lum) / 60.0, 0.4, 1.0)
    out = low * (1.0 + amp[..., None] * g[..., None])
    out = np.clip(out, 0, 255)
    # средний тон сохраняется: зерно не должно ни темнить, ни светлить кадр целиком (оттенок классики)
    k = (low[mk0] @ LUM).mean() / max((out[mk0] @ LUM).mean(), 1e-3)
    out = np.clip(out * k, 0, 255)
    out[~mk] = 0
    return out, mk, own


def cut(sc, pair, out, mk, own):
    """Кадры 128x160: маска клетки классики x4 (NEAREST), цвета - с холста."""
    frames = {}
    for s, f, ox, oy in PAIR_CELLS(pair):
        sub = out[oy * K:(oy + 40) * K, ox * K:(ox + 32) * K]
        m = own[(s, f)][oy * K:(oy + 40) * K, ox * K:(ox + 32) * K]
        a = np.zeros((40 * K, 32 * K, 4), np.uint8)
        a[..., :3] = np.where(m[..., None], np.clip(sub, 0, 255), 0).astype(np.uint8)
        a[..., 3] = np.where(m, 255, 0)
        frames[(s, f)] = Image.fromarray(a, "RGBA")
    return frames


def build(sc=None, variants=("A", "B", "C")):
    """{вариант: {(НАБОР, кадр): PIL 128x160}} - полный набор кадров на вариант."""
    sc = sc or ts.Scene()
    res = {}
    for v in variants:
        res[v] = {}
        for pair in PAIRS:
            out, mk, own = compose_pair(sc, pair, v)
            res[v].update(cut(sc, pair, out, mk, own))
    return res


def assemble(frames, pair, k=K, bg=ts.BG):
    """Пара в сборе (холст 48x48 базы x k), порядок рисования как в движке."""
    im = Image.new("RGBA", (CW * k, CH * k), bg + (255,))
    for s, f, ox, oy in PAIR_CELLS(pair):
        fr = frames.get((s, f))
        if fr is None:
            continue
        if fr.width != 32 * k:
            fr = fr.resize((32 * k, 40 * k), Image.NEAREST if fr.width < 64 else Image.LANCZOS)
        im.alpha_composite(fr, (ox * k, oy * k))
    return im


def stats(sc, res):
    """Меры: средний тон кадра против классики, совпадение маски с кадром пака, шов (скачок яркости через стык клеток)."""
    print("%-18s %-6s %9s %9s %9s" % ("кадр", "вар", "тон/клас", "маска=HD", "шов"))
    for pair, spec in PAIRS.items():
        for v in res:
            fr = res[v]
            for s, f, ox, oy in spec["cells"]:
                new = np.asarray(fr[(s, f)]).astype(np.float32)
                cl = np.asarray(sc.classic(s, f)).astype(np.float32)
                hd = np.asarray(sc.hd(s, f)).astype(np.float32)
                mc = cl[..., 3] > 0
                mn = new[..., 3] > 0
                tone = (new[..., :3][mn] @ LUM).mean() / max((cl[..., :3][mc] @ LUM).mean(), 1e-3)
                mh = hd[..., 3] > 128
                iou = (mn & mh).sum() / max((mn | mh).sum(), 1)
                print("%-18s %-6s %9.3f %9.3f" % ("%s:%d" % (s, f), v, tone, iou))
            im = np.asarray(assemble(fr, pair).convert("RGB")).astype(np.float32) @ LUM
            # шов: разность яркости по обе стороны границы клеток (вертикаль x = 16 базы для обеих пар) против обычного градиента
            xs = 16 * K
            grad = np.abs(im[:, xs] - im[:, xs - 1])
            nxt = np.abs(im[:, xs + 6] - im[:, xs + 5])
            print("%-18s %-6s %9s %9s %9.2f (шов %.2f против соседнего %.2f)" % (spec["label"], v, "", "", grad.mean(), grad.mean(), nxt.mean()))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--stats", action="store_true")
    a = ap.parse_args()
    sc = ts.Scene()
    res = build(sc)
    for v, frames in res.items():
        d = CAND / VDIR[v]
        d.mkdir(parents=True, exist_ok=True)
        for (s, f), im in frames.items():
            im.save(d / ("%s_%d.png" % (s, f)))
        print("вариант %s: %d кадров -> %s" % (v, len(frames), d))
    if a.stats:
        stats(sc, res)


if __name__ == "__main__":
    main()
