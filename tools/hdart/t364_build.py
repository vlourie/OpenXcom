#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000364: бочка 2x2 (RUSTSHACKS2:43-46) и труба (RUSTSHACKS2:3, 4, 5, 7, 9, 11) - вариант A (выбор Vitali 28.10).

Причина жалобы: четыре кадра бочки в HD-паке (sdxl_legacy, 21.09) нарисованы каждый отдельно - у каждого свой верх,
по границам ромбов заклёпочный шов, у переднего кадра зубчатая кромка крышки; труба - те же мягкие картинки.
Лечение по рецепту t358_build.py (машина V8): объект целиком на ОДНОМ холсте по раскладке карты, порядок рисования
как в движке; тон и форма - от классики (заливка, бикубика x4, край-сохраняющее сглаживание); мелкая фактура -
высокие частоты яркости донора, собранные на тот же холст (множитель на тон); нарезка обратно по маскам классики
(NEAREST x4). Перекрытия кадров несут одни и те же пиксели - шва нет по построению.

  бочка   раскладка DSRTREFI (сейв игрока: (21,34) задняя 46, (22,34) правая 44, (21,35) левая 45, (22,35) передняя 43);
          донор фактуры - одобренный HD MADDECOR_WASTE 75-78 (только чтение, не меняется); тонкая вертикальная линия
          донора по середине крышки вырезается и достраивается по соседним столбцам
  труба   сеть труб блока DSRTREFI_12 (x 43..54, y 22..34): колена 9 и 7, прямая 11, заглушка 3, прямая 5, тройник 8
          (8 - одобрен, в холст идёт классикой и прежним HD, кадр не выводится), заглушка 4; донор фактуры - прежний HD
          самих кадров (их высокие частоты, как у машины 358). Кадры 8, MADDECOR_WASTE 75-78 не трогаются.

Видеокарта не нужна; в мод ничего не ставит (ставит t364_install.py). Прежние кадры - art/tickets/t364/old.

    py -3.13 tools\hdart\t364_build.py            # кадры -> art/tickets/t364/cand
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

SET = "RUSTSHACKS2"
OLD = ROOT / "art" / "tickets" / "t364" / "old"
CAND = ROOT / "art" / "tickets" / "t364" / "cand"
K = 4
PAD = 8
LUM = np.array([0.299, 0.587, 0.114], np.float32)
EDGE_LO, EDGE_SPAN, EDGE_AA = 45.0, 45.0, 1.0
SHARP = 0.55
HF_SIGMA = 3.0
TONE_SIGMA = 24.0

# бочка: (x, y, кадр, донор (набор, кадр)); раскладка из сейва игрока, кадр -> роль в 2x2
BARREL = [(21, 34, 46, ("MADDECOR_WASTE", 75)), (22, 34, 44, ("MADDECOR_WASTE", 76)),
          (21, 35, 45, ("MADDECOR_WASTE", 77)), (22, 35, 43, ("MADDECOR_WASTE", 78))]
BARREL_OUT = {46: (21, 34), 44: (22, 34), 45: (21, 35), 43: (22, 35)}
BARREL_GAIN = 0.8

# труба: сеть блока DSRTREFI_12 по сейву: ряд y=22 (колено 9, колено 7, прямая 11 x8, колено 7, заглушка 3),
# ряд y=23 (9, тройник 8, 3), столбец x=44 (прямая 5, тройник 8 через три клетки), заглушка 4 в конце
PIPE_RAW = ([(43, 22, 9), (44, 22, 7)] + [(x, 22, 11) for x in range(45, 53)] + [(53, 22, 7), (54, 22, 3),
             (43, 23, 9), (44, 23, 8), (45, 23, 3), (52, 23, 9), (53, 23, 8), (54, 23, 3)]
            + [(44, y, 5) for y in (24, 25, 27, 28, 30, 31, 33)] + [(53, y, 5) for y in (24, 25)]
            + [(43, 26, 9), (44, 26, 8), (45, 26, 3), (44, 34, 4)])
# экземпляр кадра для вывода (середина серии, где у кадра есть соседи с обеих сторон)
PIPE_OUT = {11: (48, 22), 9: (43, 22), 7: (44, 22), 3: (45, 23), 5: (44, 28), 4: (44, 34)}
PIPE_GAIN = 0.8


def blur(a, s):
    return cv2.GaussianBlur(a, (0, 0), s, borderType=cv2.BORDER_REFLECT)


class Canvas:
    def __init__(self, sc, items):
        """items: [(x, y, кадр, донор или None)] в порядке движка (по сумме x+y, затем по x)."""
        self.sc = sc
        self.items = sorted(items, key=lambda t: (t[0] + t[1], t[0]))
        xs = [(x - y) * 16 for x, y, _, _ in self.items]
        ys = [(x + y) * 8 for x, y, _, _ in self.items]
        self.x0, self.y0 = min(xs) - PAD, min(ys) - PAD
        self.cw = max(xs) - self.x0 + 32 + PAD
        self.ch = max(ys) - self.y0 + 40 + PAD

    def pos(self, it):
        x, y = it[0], it[1]
        return (x - y) * 16 - self.x0, (x + y) * 8 - self.y0

    def classic(self):
        rgb = np.zeros((self.ch, self.cw, 3), np.float32)
        msk = np.zeros((self.ch, self.cw), bool)
        for it in self.items:
            ox, oy = self.pos(it)
            c = np.asarray(self.sc.classic(SET, it[2]).resize((32, 40), Image.NEAREST)).astype(np.float32)
            m = c[..., 3] > 0
            reg = rgb[oy:oy + 40, ox:ox + 32]
            reg[m] = c[..., :3][m]
            msk[oy:oy + 40, ox:ox + 32] |= m
        return rgb, msk

    def own_mask(self, it):
        ox, oy = self.pos(it)
        c = np.asarray(self.sc.classic(SET, it[2]).resize((32, 40), Image.NEAREST))[..., 3] > 0
        sub = np.zeros((self.ch, self.cw), bool)
        sub[oy:oy + 40, ox:ox + 32] = c
        return sub


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


def low_field(cv, rgb, m):
    fl = fill_out(rgb, m)
    W, H = cv.cw * K, cv.ch * K
    up = np.clip(cv2.resize(fl, (W, H), interpolation=cv2.INTER_CUBIC), 0, 255).astype(np.float32)
    lum = fl @ LUM
    rng = cv2.dilate(lum, np.ones((3, 3), np.uint8)) - cv2.erode(lum, np.ones((3, 3), np.uint8))
    rng = cv2.resize(rng, (W, H), interpolation=cv2.INTER_NEAREST)
    wedge = np.clip((blur(rng, 2.0) - EDGE_LO) / EDGE_SPAN, 0, 1)[..., None]
    near = cv2.GaussianBlur(cv2.resize(fl, (W, H), interpolation=cv2.INTER_NEAREST), (0, 0), EDGE_AA)
    up = up * (1 - wedge) + near * wedge
    for _ in range(2):
        up = cv2.bilateralFilter(up, 0, 28, 5)
    up = up + SHARP * (up - cv2.GaussianBlur(up, (0, 0), 2.0))
    return np.clip(up, 0, 255)


def mask_up(cv, m):
    return cv2.resize(m.astype(np.uint8) * 255, (cv.cw * K, cv.ch * K), interpolation=cv2.INTER_NEAREST) > 0


def donor_img(sc, donor, own_set_old):
    """HD-картинка донора 128x160: прежний HD кадра (из art/tickets/t364/old) или чужой набор из пака."""
    s, f = donor
    if s == SET:
        return Image.open(OLD / ("%d.png" % f)).convert("RGBA")
    return sc.hd(s, f).convert("RGBA")


def hf_canvas(sc, cv, erode=3, sigma=HF_SIGMA, feather=8.0):
    """Высокие частоты яркости донорских кадров, посчитанные внутри каждого кадра (нормированная свёртка по его
    маске, край отброшен) и усреднённые на холсте с весом от края кадра: тон и шов донора в них не попадают."""
    num = np.zeros((cv.ch * K, cv.cw * K), np.float32)
    den = np.zeros((cv.ch * K, cv.cw * K), np.float32)
    for it in cv.items:
        a = np.asarray(donor_img(sc, it[3], None)).astype(np.float32)
        al = a[..., 3] > 128
        core = ndi.binary_erosion(al, iterations=erode)
        cf = core.astype(np.float32)
        lum = a[..., :3] @ LUM
        bl = blur(lum * cf, sigma) / np.maximum(blur(cf, sigma), 1e-3)
        hp = (lum - bl) / np.maximum(bl, 60.0)
        sd = hp[core].std() if core.any() else 1.0
        hp = np.clip(hp, -3 * sd, 3 * sd)
        w = np.clip(ndi.distance_transform_edt(core) / feather, 0, 1).astype(np.float32) * core + 1e-3 * core
        ox, oy = cv.pos(it)
        sl = (slice(oy * K, (oy + 40) * K), slice(ox * K, (ox + 32) * K))
        num[sl] += hp * w
        den[sl] += w
    ok = den > 1e-6
    hf = np.where(ok, num / np.maximum(den, 1e-6), 0).astype(np.float32)
    for _ in range(6):
        v = ok.astype(np.float32)
        fl = blur(hf * v, 3.0) / np.maximum(blur(v, 3.0), 1e-3)
        new = (~ok) & (blur(v, 3.0) > 0.02)
        hf = np.where(new, fl, hf)
        ok = ok | new
    return hf


def kill_vertical_seam(hf, mk, cx, span=6 * K, half=5):
    """Вертикальная линия донора по середине крышки и борта (граница левого и правого кадров донора): ищем столбец
    с наибольшим вертикально-когерентным перепадом около середины холста cx (пикселей x4) и закрываем полосу
    +-half столбцов фактурой соседних полос: слева и справа от неё взяты столбцы на ширину полосы дальше и
    сведены по ширине (линейная интерполяция по соседним столбцам оставляла строчки). Возвращает
    (hf, найденный столбец, отношение пика к медиане)."""
    lo, hi = cx - span, cx + span
    prof = []
    for c in range(lo, hi):
        d = np.abs(hf[:, c] - 0.5 * (hf[:, c - 3] + hf[:, c + 3]))
        prof.append(d[mk[:, c]].mean() if mk[:, c].any() else 0.0)
    prof = np.array(prof)
    c0 = lo + int(prof.argmax())
    ratio = float(prof.max() / max(np.median(prof), 1e-6))
    out = hf.copy()
    w = 2 * half + 2
    a, b = c0 - half, c0 + half
    for c in range(a, b + 1):
        t = (c - a + 0.5) / (b - a + 1)
        out[:, c] = hf[:, c - w] * (1 - t) + hf[:, c + w] * t
    return out, c0, ratio


def build_canvas(sc, items, gain, seam_center=None, tone_sigma=TONE_SIGMA):
    cv = Canvas(sc, items)
    rgb, m = cv.classic()
    low = low_field(cv, rgb, m)
    mk = mask_up(cv, m)
    hf = hf_canvas(sc, cv)
    info = {}
    if seam_center is not None:
        hf, c0, ratio = kill_vertical_seam(hf, mk, seam_center(cv))
        info["seam_col"], info["seam_ratio"] = c0, ratio
    out = np.clip(low * (1.0 + gain * hf[..., None]), 0, 255)
    # тон целого холста - классический: фактура не должна ни светлить, ни темнить кадр; поправка плавная (по холсту)
    mf = mk.astype(np.float32)
    norm = np.maximum(blur(mf, tone_sigma), 1e-3)
    for _ in range(2):
        bo = blur((out @ LUM) * mf, tone_sigma) / norm
        bl = blur((low @ LUM) * mf, tone_sigma) / norm
        out = np.clip(out * np.clip(bl / np.maximum(bo, 1.0), 0.6, 1.6)[..., None], 0, 255)
    out[~mk] = 0
    return cv, low, out, mk, info


def slice_frame(cv, out, it, iso=None):
    """Кадр из холста по маске его классики. Пиксели, которые в этой раскладке перекрыты позже нарисованными клетками
    (у бочки - тёмные внутренние грани, у трубы - стык с соседней), берутся из того же кадра в одиночку (iso): иначе в
    них осела бы картинка соседа, а труба стоит в разных раскладках (R-457: кадр должен оставаться самим собой)."""
    ox, oy = cv.pos(it)
    sub = out[oy * K:(oy + 40) * K, ox * K:(ox + 32) * K]
    cm = np.asarray(cv.sc.classic(SET, it[2]).resize((32, 40), Image.NEAREST))[..., 3] > 0
    mf = cv2.resize(cm.astype(np.uint8) * 255, (32 * K, 40 * K), interpolation=cv2.INTER_NEAREST) > 0
    if iso is not None:
        later = np.zeros((cv.ch, cv.cw), bool)
        after = False
        for jt in cv.items:
            if jt is it:
                after = True
                continue
            if after:
                later |= cv.own_mask(jt)
        lm = later[oy:oy + 40, ox:ox + 32]
        hid = cv2.resize(lm.astype(np.uint8) * 255, (32 * K, 40 * K), interpolation=cv2.INTER_NEAREST) > 0
        sub = np.where(hid[..., None], iso, sub)
    a = np.zeros((40 * K, 32 * K, 4), np.uint8)
    a[..., :3] = np.where(mf[..., None], sub, 0).astype(np.uint8)
    a[..., 3] = np.where(mf, 255, 0)
    return Image.fromarray(a, "RGBA")


def isolated(sc, it, gain, seam_center=None):
    """Кадр один на холсте: его собственное увеличение (для пикселей, перекрытых соседями)."""
    cv, low, out, mk, info = build_canvas(sc, [(0, 0, it[2], it[3])], gain, None)
    ox, oy = cv.pos(cv.items[0])
    return out[oy * K:(oy + 40) * K, ox * K:(ox + 32) * K]


def build(barrel_gain=BARREL_GAIN, pipe_gain=PIPE_GAIN):
    sc = ts.Scene()
    frames, canv = {}, {}
    # бочка: центр холста по x - граница левого и правого кадров (клетка (22,34)/(21,35) -> x=(0)*16 между ними)
    def seam_center(cv):
        return (int(cv.pos((21, 35, 45))[0]) + 32) * K
    cv, low, out, mk, info = build_canvas(sc, BARREL, barrel_gain, seam_center)
    canv["barrel"] = (cv, low, out, mk, info)
    for it in cv.items:
        frames[it[2]] = slice_frame(cv, out, it, isolated(sc, it, barrel_gain))
    # труба
    items = [(x, y, f, (SET, f)) for x, y, f in PIPE_RAW]
    cv, low, out, mk, info = build_canvas(sc, items, pipe_gain)
    canv["pipe"] = (cv, low, out, mk, info)
    for f, (x, y) in PIPE_OUT.items():
        it = [t for t in cv.items if (t[0], t[1]) == (x, y)][0]
        assert it[2] == f, (f, it)
        frames[f] = slice_frame(cv, out, it, isolated(sc, it, pipe_gain))
    return frames, canv


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    frames, canv = build()
    CAND.mkdir(parents=True, exist_ok=True)
    for f, im in frames.items():
        im.save(CAND / ("%d.png" % f))
    print("кадров %d -> %s" % (len(frames), CAND))
    for k, v in canv.items():
        print(k, "холст %dx%d" % (v[0].cw, v[0].ch), v[4])


if __name__ == "__main__":
    main()
