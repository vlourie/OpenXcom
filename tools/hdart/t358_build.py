#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000358: машина «Возьмёрка» (судно V8, набор CADILLAC, кадры 3-13) - ступени яркости и швы между кадрами.
Вариант A (выбор Vitali): вся машина на ОДНОМ холсте по раскладке MAPS/CADILLAC.MAP, порядок рисования как в движке;
тон и форма - от классики (низкие частоты: заливка, бикубика x4, край-сохраняющее сглаживание, как t337_probe.py),
мелкая фактура - высокие частоты ПРЕЖНИХ HD-кадров (art/tickets/t358/old), собранных на тот же холст,
множителем на тон; нарезка обратно по маскам классики (NEAREST x4). Перекрытия кадров несут одни и те же
пиксели - шва нет по построению. Видеокарта не нужна, в мод ничего не ставит (ставит t358_install.py).

    py -3.13 tools\hdart\t358_build.py            # кадры -> art/tickets/t358/cand
"""
import os
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parents[2] if (Path(__file__).resolve().parents[2] / "tools").exists() else Path("E:/OpenXCom")
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
os.chdir(ROOT)
import ticket_scene as ts  # noqa: E402

SET = "CADILLAC"
OLD = ROOT / "art" / "tickets" / "t358" / "old"
CAND = ROOT / "art" / "tickets" / "t358" / "cand"
MAPF = ROOT / "Пиратки/Dioxine_XPiratez/user/mods/Piratez/MAPS/CADILLAC.MAP"
MCDF = ROOT / "Пиратки/Dioxine_XPiratez/user/mods/Piratez/TERRAIN/Cadillac.mcd"
K = 4
PAD = 8
LUM = np.array([0.299, 0.587, 0.114], np.float32)
EDGE_LO, EDGE_SPAN, EDGE_AA = 45.0, 45.0, 1.0
SHARP = 0.55
HF_SIGMA = 3.0      # граница мелкой фактуры, пикселей x4
TONE_SIGMA = 24.0   # масштаб поправки тона к классике, пикселей x4
HF_GAIN = 0.8       # доля фактуры донора


def blur(a, s):
    return cv2.GaussianBlur(a, (0, 0), s, borderType=cv2.BORDER_REFLECT)


def layout():
    """[(порядок, xx, yy, слот, кадр)] кадров машины 3..13, в порядке рисования движка (дальние раньше)."""
    d = MAPF.read_bytes()
    sy, sx = d[0], d[1]
    mcd = MCDF.read_bytes()
    spr = [mcd[j * 62] for j in range(len(mcd) // 62)]
    items, i = [], 3
    for yy in range(sy):
        for xx in range(sx):
            for slot, v in enumerate(d[i:i + 4]):
                if v >= 2 and spr[v - 2] >= 3:
                    items.append((xx + yy, xx, yy, slot, spr[v - 2]))
            i += 4
    items.sort(key=lambda t: (t[0], t[1], t[3]))
    return items


ITEMS = layout()
XS = [(xx - yy) * 16 for _, xx, yy, _, _ in ITEMS]
YS = [(xx + yy) * 8 for _, xx, yy, _, _ in ITEMS]
X0, Y0 = min(XS) - PAD, min(YS) - PAD
CW = max(XS) - X0 + 32 + PAD
CH = max(YS) - Y0 + 40 + PAD


def pos(item):
    _, xx, yy, _, _ = item
    return (xx - yy) * 16 - X0, (xx + yy) * 8 - Y0


def classic_canvas(sc):
    rgb = np.zeros((CH, CW, 3), np.float32)
    msk = np.zeros((CH, CW), bool)
    own = {}
    for it in ITEMS:
        f = it[4]
        ox, oy = pos(it)
        c = np.asarray(sc.classic(SET, f).resize((32, 40), Image.NEAREST)).astype(np.float32)
        m = c[..., 3] > 0
        sub = np.zeros((CH, CW), bool)
        sub[oy:oy + 40, ox:ox + 32] = m
        own[f] = sub
        reg = rgb[oy:oy + 40, ox:ox + 32]
        reg[m] = c[..., :3][m]
        msk[oy:oy + 40, ox:ox + 32] |= m
    return rgb, msk, own


def fill_out(rgb, m, it=4):
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


def low_field(rgb, m):
    fl = fill_out(rgb, m)
    up = np.clip(cv2.resize(fl, (CW * K, CH * K), interpolation=cv2.INTER_CUBIC), 0, 255).astype(np.float32)
    lum = fl @ LUM
    rng = cv2.dilate(lum, np.ones((3, 3), np.uint8)) - cv2.erode(lum, np.ones((3, 3), np.uint8))
    rng = cv2.resize(rng, (CW * K, CH * K), interpolation=cv2.INTER_NEAREST)
    wedge = np.clip((blur(rng, 2.0) - EDGE_LO) / EDGE_SPAN, 0, 1)[..., None]
    near = cv2.GaussianBlur(cv2.resize(fl, (CW * K, CH * K), interpolation=cv2.INTER_NEAREST), (0, 0), EDGE_AA)
    up = up * (1 - wedge) + near * wedge
    for _ in range(2):
        up = cv2.bilateralFilter(up, 0, 28, 5)
    up = up + SHARP * (up - cv2.GaussianBlur(up, (0, 0), 2.0))
    return np.clip(up, 0, 255)


def mask_up(m):
    return cv2.resize(m.astype(np.uint8) * 255, (CW * K, CH * K), interpolation=cv2.INTER_NEAREST) > 0


def hd_old(f):
    return Image.open(OLD / ("%d.png" % f)).convert("RGBA")


def hf_canvas(erode=3, sigma=HF_SIGMA, feather=8.0):
    """Высокие частоты яркости прежних HD-кадров, посчитанные ВНУТРИ каждого кадра (нормированная свёртка по его
    маске, край кадра отброшен) и усреднённые на холсте с весом от края кадра (перекрытия плавно переходят друг в
    друга, фактура на границе не рвётся): тон ступеней и шов в них не попадают."""
    num = np.zeros((CH * K, CW * K), np.float32)
    den = np.zeros((CH * K, CW * K), np.float32)
    for it in ITEMS:
        f = it[4]
        ox, oy = pos(it)
        a = np.asarray(hd_old(f)).astype(np.float32)
        al = a[..., 3] > 128
        core = ndi.binary_erosion(al, iterations=erode)
        cf = core.astype(np.float32)
        lum = a[..., :3] @ LUM
        bl = blur(lum * cf, sigma) / np.maximum(blur(cf, sigma), 1e-3)
        hp = (lum - bl) / np.maximum(bl, 60.0)
        sd = hp[core].std() if core.any() else 1.0
        hp = np.clip(hp, -3 * sd, 3 * sd)
        w = np.clip(ndi.distance_transform_edt(core) / feather, 0, 1).astype(np.float32) * core + 1e-3 * core
        sl = (slice(oy * K, (oy + 40) * K), slice(ox * K, (ox + 32) * K))
        num[sl] += hp * w
        den[sl] += w
    ok = den > 1e-6
    hf = np.where(ok, num / np.maximum(den, 1e-6), 0).astype(np.float32)
    # дыры (кромка кадров у HD полупрозрачна, тут ни один кадр не дал фактуры): заполняются соседней фактурой
    for _ in range(6):
        v = ok.astype(np.float32)
        fl = blur(hf * v, 3.0) / np.maximum(blur(v, 3.0), 1e-3)
        new = (~ok) & (blur(v, 3.0) > 0.02)
        hf = np.where(new, fl, hf)
        ok = ok | new
    return hf


def build(gain=HF_GAIN, sigma=HF_SIGMA, tone_sigma=TONE_SIGMA):
    sc = ts.Scene()
    rgb, m, own = classic_canvas(sc)
    low = low_field(rgb, m)
    mk = mask_up(m)
    hf = hf_canvas(sigma=sigma)
    out = np.clip(low * (1.0 + gain * hf[..., None]), 0, 255)
    # тон целого холста - классический: фактура не должна ни светлить, ни темнить кадр; поправка плавная (по холсту,
    # а не по кадру), поэтому ступеней на границах кадров не даёт
    mf = mk.astype(np.float32)
    norm = np.maximum(blur(mf, tone_sigma), 1e-3)
    for _ in range(2):
        bo = blur((out @ LUM) * mf, tone_sigma) / norm
        bl = blur((low @ LUM) * mf, tone_sigma) / norm
        out = np.clip(out * np.clip(bl / np.maximum(bo, 1.0), 0.6, 1.6)[..., None], 0, 255)
    out[~mk] = 0
    frames = {}
    for it in ITEMS:
        f = it[4]
        ox, oy = pos(it)
        sub = out[oy * K:(oy + 40) * K, ox * K:(ox + 32) * K]
        mf = mask_up(own[f])[oy * K:(oy + 40) * K, ox * K:(ox + 32) * K]
        a = np.zeros((40 * K, 32 * K, 4), np.uint8)
        a[..., :3] = np.where(mf[..., None], sub, 0).astype(np.uint8)
        a[..., 3] = np.where(mf, 255, 0)
        frames[f] = Image.fromarray(a, "RGBA")
    return frames, low, out, mk


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    frames, low, out, mk = build()
    CAND.mkdir(parents=True, exist_ok=True)
    for f, im in frames.items():
        im.save(CAND / ("%d.png" % f))
    print("кадров %d -> %s; холст %dx%d" % (len(frames), CAND, CW, CH))


if __name__ == "__main__":
    main()
