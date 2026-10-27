#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000280: песок MOUNTSAND:4 и :5 с золотыми кляксами. Варианты замены кадров по маске и цветам классики.
Видеокарта не нужна, в мод ничего не ставится. Листы - art/_review/xp280, кадры - art/tickets/t280/cand.

Что не так: HD 4 (sdxl_legacy) нарисовал крупные светлые кляксы-кольца по середине ромба, у 5 те же штрихи слабее;
классика - мелкий тёмно-коричневый песок с редкими светлыми крапинками. Фактура 3 и 6 годная.
Варианты 4: A - мелкое зерно HD 3 + цвет и крапины классики 4; B - зерно MOUNTMUD:5 (камешки t242) по рангу цветов
классики 4; C - прежний бесшовный кадр art/ground/sand-v1 с тоном классики 4.
Варианты 5: A - копия MOUNTMUD:5 HD (классика побайтно та же), B - зерно HD 3 + цвет классики 5,
C - sand-v1 5 с тоном классики.

    py -3.13 tools\hdart\t280_probe.py
"""
import os
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.chdir(ROOT)
import ticket_scene as ts  # noqa: E402

REV = ROOT / "art" / "_review" / "xp280"
CAND = ROOT / "art" / "tickets" / "t280" / "cand"
V1 = ROOT / "art" / "ground" / "sand-v1" / "TERRAIN" / "MOUNTSAND.PCK"
W = np.array([0.299, 0.587, 0.114], np.float32)


def arr(im):
    return np.asarray(im.convert("RGBA")).astype(np.float32)


def mblur(x, m, s):
    mm = m.astype(np.float32)
    den = np.maximum(cv2.GaussianBlur(mm, (0, 0), s), 1e-3)
    if x.ndim == 3:
        num = np.dstack([cv2.GaussianBlur(x[..., c] * mm, (0, 0), s) for c in range(3)])
        return num / den[..., None]
    return cv2.GaussianBlur(x * mm, (0, 0), s) / den


def classic_up(cl, smooth):
    """Классика 32x40 -> 128x160: цвета кубически внутри маски (без чёрной каймы), маска - NEAREST."""
    c = np.asarray(cl.convert("RGBA").resize((32, 40), Image.NEAREST)).astype(np.float32)
    m = c[..., 3] > 0
    rgb = c[..., :3].copy()
    for _ in range(3):
        d = cv2.dilate(rgb, np.ones((3, 3), np.uint8))
        rgb = np.where(m[..., None], rgb, d)
    up = cv2.resize(rgb, (128, 160), interpolation=cv2.INTER_CUBIC)
    if smooth:
        up = cv2.GaussianBlur(up, (0, 0), smooth)
    alpha = cv2.resize(m.astype(np.uint8) * 255, (128, 160), interpolation=cv2.INTER_NEAREST)
    return np.clip(up, 0, 255), alpha


def grain_transfer(src_hd, cl, smooth=1.4, gain=0.9, sigma=3.0, shift=None):
    """Цвет и крапины классики (сглажено на smooth px), мелкое зерно (высокие частоты) - из src_hd."""
    low, alpha = classic_up(cl, smooth)
    s = arr(src_hd)
    if shift == "flip":
        s = s[:, ::-1].copy()
    m = s[..., 3] > 128
    g = s[..., :3] - mblur(s[..., :3], m, sigma)
    out = low + gain * g
    res = np.dstack([np.clip(out, 0, 255), alpha.astype(np.float32)])
    res[alpha == 0] = 0
    return Image.fromarray(res.round().astype(np.uint8), "RGBA")


def tone_to(hd, cl, sigma=6.0):
    """Низкие частоты HD приводятся к низким частотам классики (сдвигом цвета); зерно HD цело."""
    h = arr(hd)
    low, alpha = classic_up(cl, 0)
    m = (h[..., 3] > 128) & (alpha > 0)
    out = h[..., :3] - mblur(h[..., :3], m, sigma) + mblur(low, m, sigma)
    res = h.copy()
    res[..., :3] = np.clip(out, 0, 255)
    res[..., 3] = np.where(alpha > 0, 255, 0)
    res[alpha == 0] = 0
    return Image.fromarray(res.round().astype(np.uint8), "RGBA")


def rank_to(hd, cl):
    """Цвета HD заменяются цветами классики по рангу яркости (тон классики, рисунок HD)."""
    h = arr(hd).copy()
    _low, alpha = classic_up(cl, 0)
    c = np.asarray(cl.convert("RGBA").resize((32, 40), Image.NEAREST)).astype(np.float32)
    cs = c[c[..., 3] > 0][:, :3]
    cs = cs[np.argsort(cs @ W)]
    mh = (h[..., 3] > 128) & (alpha > 0)
    lh = h[mh][:, :3] @ W
    oh = np.argsort(np.argsort(lh, kind="stable"), kind="stable")
    idx = (oh * (len(cs) - 1) / max(1, len(lh) - 1)).astype(int)
    h[mh, :3] = cs[idx]
    h[..., 3] = np.where(alpha > 0, 255, 0)
    h[alpha == 0] = 0
    return Image.fromarray(h.round().astype(np.uint8), "RGBA")


def build():
    sc = ts.Scene()
    c3, c4, c5 = (sc.classic("MOUNTSAND", f) for f in (3, 4, 5))
    h3 = sc.hd("MOUNTSAND", 3)
    m5 = sc.hd("MOUNTMUD", 5)
    v1_4 = Image.open(V1 / "4.png").convert("RGBA")
    v1_5 = Image.open(V1 / "5.png").convert("RGBA")
    return {
        "4_A_grain3": grain_transfer(h3, c4, 0.9, 1.3),
        "4_B_grit_mud5": rank_to(m5, c4),
        "4_C_sandv1_tone": tone_to(v1_4, c4),
        "5_A_copy_MOUNTMUD5": m5.copy(),
        "5_B_grain3": grain_transfer(h3, c5, 0.9, 1.3, shift="flip"),
        "5_C_sandv1_tone": tone_to(v1_5, c5),
    }


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    CAND.mkdir(parents=True, exist_ok=True)
    REV.mkdir(parents=True, exist_ok=True)
    for n, im in build().items():
        im.save(CAND / ("MOUNTSAND_%s.png" % n))
    print("кадры:", CAND)


if __name__ == "__main__":
    main()
