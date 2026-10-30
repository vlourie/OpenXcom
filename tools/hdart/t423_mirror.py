# -*- coding: utf-8 -*-
"""XP-000423, круг 4 (Vitali 30.10): голова коровы с зерна 4251 (круг 3) отражается зеркально, уши остаются на месте теми же пикселями.

Работа над ответом модели (raw 1120x896) до подгонки к силуэту классики и нарезки - дальше обычный t423_post.py --round 4.
  1. Корова отделяется от стола и подложки по насыщенности (шкура рыже-бежевая, стол кремовый, подложка серая), дыры заполняются.
  2. Уши (ближнее и дальний рог за теменем) выкладываются из слоя коровы, чтобы голова не унесла их с собой.
  3. Слой коровы (цвет и альфа) отражается относительно оси, идущей вдоль шеи через морду (шея и голова лежат почти на одной прямой,
     контуры по обе стороны оси почти симметричны - голова ложится на своё место). У шеи отражённая картинка плавно (рампа T0..T1 вдоль оси)
     переходит в исходную: шва нет, двойной контур незаметен.
  4. Свет: низкие частоты яркости отражённой головы берутся от исходной (свет остаётся слева сверху, как у battle_view), высокие
     (морщины, глаз, ноздря) - от отражённой.
  5. Подложка там, где голова ушла, - cv2.inpaint по исходнику без коровы; уши кладутся поверх теми же пикселями (мягкий край 1.5).

  py -3.13 tools\\hdart\\t423_mirror.py neck    ось вдоль шеи через морду -> raw_r4/4251.png
  py -3.13 tools\\hdart\\t423_mirror.py head    ось вдоль самой головы (чуть положе) -> raw_r4/4255.png
"""
import argparse
import os
import sys

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

SRC = os.path.join(ROOT, "art", "tickets", "t423", "gen", "raw", "4251.png")
OUT = os.path.join(ROOT, "art", "tickets", "t423", "gen", "raw_r4")
VARIANTS = {"mid": 4251, "neck": 4255, "head": 4256}
AXES = {"mid": ((250.0, 735.0), (0.66, -0.75)),
        "neck": ((250.0, 735.0), (0.66, -0.75)),          # через кончик морды вдоль шеи
        "head": ((250.0, 735.0), (0.80, -0.60))}          # через кончик морды вдоль головы
T0, T1 = 165.0, 240.0          # вдоль оси от морды: до T0 отражение полное, после T1 - исходник
SIGMA_LIGHT = 7.0
SAT = 0.24                     # порог насыщенности шкуры

EAR_NEAR = [(382, 652), (395, 648), (412, 652), (427, 660), (435, 673), (438, 690), (438, 703), (428, 706), (412, 703),
            (398, 696), (388, 686), (383, 675), (380, 662)]
HORN = [(205, 569), (225, 566), (250, 568), (257, 573), (257, 598), (250, 599), (232, 591), (214, 581)]


def poly_mask(shape, pts, grow=0, feather=0.0):
    m = np.zeros(shape[:2], np.uint8)
    cv2.fillPoly(m, [np.array(pts, np.int32)], 255)
    if grow:
        m = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow + 1, 2 * grow + 1)))
    m = m.astype(np.float32) / 255.0
    if feather:
        m = cv2.GaussianBlur(m, (0, 0), feather)
    return m


def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def lowpass(img, wgt, sg):
    num = cv2.GaussianBlur(img * wgt[..., None], (0, 0), sg)
    den = cv2.GaussianBlur(wgt, (0, 0), sg)[..., None]
    return num / np.maximum(den, 1e-3)


def cow_mask(hd, seed=(300, 650)):
    """Шкура: насыщенное и непрозрачное, дыры залиты, только компонента с головой."""
    import obj_photo as op
    a = np.asarray(hd.convert("RGB"))
    hsv = cv2.cvtColor(a, cv2.COLOR_RGB2HSV).astype(np.float32)
    sat = hsv[..., 1] / 255.0
    m = (op.edge_matte(hd) > 0.5) & (sat > SAT)
    m = m.astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    cnt, lab = cv2.connectedComponents(m)
    m = (lab == lab[seed[1], seed[0]]).astype(np.uint8)
    ff = m.copy()
    h, w = m.shape
    pad = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(ff, pad, (0, 0), 2)
    m = ((ff != 2) | (m == 1)).astype(np.uint8)          # дыры внутри
    return m.astype(np.float32)


def mirror(hd, mode):
    a = np.asarray(hd.convert("RGB")).astype(np.float32)
    H, W = a.shape[:2]
    (ox, oy), (dx, dy) = AXES[mode]
    O = np.array([ox, oy], np.float32)
    D = np.array([dx, dy], np.float32)
    D /= np.hypot(*D)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    px = np.stack([xx, yy], -1)
    rel = px - O
    t = rel @ D
    N = np.array([-D[1], D[0]], np.float32)
    n = rel @ N
    refl = O + 2 * (t[..., None] * D) - rel

    ear = poly_mask(a.shape, EAR_NEAR, 0, 1.5)
    ear_fill = poly_mask(a.shape, EAR_NEAR, 3) > 0.5
    horn_fill = poly_mask(a.shape, HORN, 4) > 0.5
    cow = cow_mask(hd)
    cow_head = cow * (poly_mask(a.shape, [(0, 0), (1119, 0), (1119, 895), (0, 895)]) > 0)      # вся шкура (дальше режется рампой)
    ear_poly = poly_mask(a.shape, EAR_NEAR, 0) > 0.5
    horn_poly = poly_mask(a.shape, HORN, 2) > 0.5
    cow_noear = cow_head * (~(ear_poly | horn_poly)).astype(np.float32)
    # край у основания рога - сгладить (открытие и закрытие только вокруг рога), чтобы не осталось выемки
    zone_h = cv2.dilate(horn_poly.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (61, 61))) > 0
    sm = cv2.morphologyEx(cow_noear.astype(np.uint8), cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13)))
    sm = cv2.morphologyEx(sm, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13)))
    cow_noear = np.where(zone_h, sm.astype(np.float32), cow_noear)
    cow_soft = cv2.GaussianBlur(cow_noear, (0, 0), 0.9)
    if mode == "mid":
        # ось - средняя линия поперечных сечений шкуры (без ушей): контур отображается сам на себя, шея и голова остаются на месте
        cm = cow_noear > 0.5
        ys, xs = np.nonzero(cm)
        tt = (np.stack([xs, ys], -1).astype(np.float32) - O) @ D
        nn = (np.stack([xs, ys], -1).astype(np.float32) - O) @ N
        tb = np.round(tt).astype(np.int32)
        ok = (tb >= 0) & (tb <= int(T1) + 120)
        nb = int(T1) + 121
        lo_n = np.full(nb, np.inf, np.float32)
        hi_n = np.full(nb, -np.inf, np.float32)
        np.minimum.at(lo_n, tb[ok], nn[ok])
        np.maximum.at(hi_n, tb[ok], nn[ok])
        have = np.isfinite(lo_n) & np.isfinite(hi_n)
        cen = (lo_n + hi_n) / 2
        idx = np.arange(nb)
        cen = np.interp(idx, idx[have], cen[have])
        k = np.exp(-0.5 * (np.arange(-24, 25) / 4.0) ** 2)
        k /= k.sum()
        cen = np.convolve(np.pad(cen, 24, mode="edge"), k, mode="valid")
        cp = np.interp(np.clip(t, 0, nb - 1), idx, cen)
        refl = O + t[..., None] * D + (2 * cp - n)[..., None] * N
        print("средняя линия: n(t=0)=%.1f n(t=150)=%.1f n(t=220)=%.1f" % (cen[0], cen[150], cen[min(220, nb - 1)]))
    # подложка: исходник; закрашивается только рог (контур шкуры не меняется, освободившихся мест нет)
    hole = horn_fill.astype(np.uint8) * 255
    x0, y0, x1, y1 = 120, 480, 700, 800
    crop = np.ascontiguousarray(a[y0:y1, x0:x1].astype(np.uint8))
    bgc = np.median(a[780:880, 150:600].reshape(-1, 3), 0)            # серая подложка панели (плоская): под рогом - она
    inp = np.empty_like(crop)
    inp[:] = bgc.astype(np.uint8)
    plate = a.copy()
    sel = hole[y0:y1, x0:x1] > 0
    sub = plate[y0:y1, x0:x1]
    sub[sel] = inp[sel]
    # слой коровы без ушей: цвет заливается соседями под ушами (чтобы отражение не принесло пятен)
    layer_fill = cv2.inpaint(crop, np.ascontiguousarray(((ear_fill | horn_fill)[y0:y1, x0:x1]).astype(np.uint8) * 255), 5, cv2.INPAINT_TELEA)
    layer = a.copy()
    sub = layer[y0:y1, x0:x1]
    sel2 = (ear_fill | horn_fill)[y0:y1, x0:x1]
    sub[sel2] = layer_fill[sel2]
    # отражение слоя
    mx, my = refl[..., 0].astype(np.float32), refl[..., 1].astype(np.float32)
    rl = cv2.remap(layer, mx, my, cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)
    ra = cv2.remap(cow_soft, mx, my, cv2.INTER_LINEAR, borderValue=0)
    # свет: низкие частоты от исходной шкуры
    lo = lowpass(layer, cow_noear, SIGMA_LIGHT)
    lw = lowpass(rl, ra, SIGMA_LIGHT)
    rl = np.clip(rl + (lo - lw) * np.clip(ra, 0, 1)[..., None], 0, 255)
    # перекрёстное смешение у шеи
    wgt = 1.0 - smoothstep((t - T0) / (T1 - T0))
    wo = cow_soft * (1 - wgt)                              # вес цвета: исходная шея / отражённая
    wr = np.clip((ra - 0.6) / 0.4, 0, 1) * wgt             # только то, что уверенно внутри отражённой шкуры (кромка - исходные пиксели)
    af = np.clip(cow_soft, 0, 1)                           # контур - исходный (ровный, свой у модели): голова отражается внутри него
    den = wo + wr
    cf = np.where(den[..., None] < 1e-3, layer, (layer * wo[..., None] + rl * wr[..., None]) / np.maximum(den, 1e-3)[..., None])
    import obj_derive as od
    core = cv2.erode((cow_noear > 0.5).astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))) > 0
    ext = np.stack([od.spread(cf[..., c].astype(np.float32), core, 6) for c in range(3)], -1)
    cf = np.where(core[..., None], cf, ext)                 # цвет у кромки - от ближайшего внутри (без каймы фона и точек)
    comp = plate * (1 - af[..., None]) + cf * af[..., None]
    z = 1.0 - smoothstep((t - T1) / 30.0)                 # дальше T1 - только исходник
    out = a * (1 - z[..., None]) + comp * z[..., None]
    out = out * (1 - ear[..., None]) + a * ear[..., None]  # уши - теми же пикселями
    return Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=sorted(VARIANTS))
    a = ap.parse_args()
    hd = Image.open(SRC).convert("RGB")
    out = mirror(hd, a.mode)
    os.makedirs(OUT, exist_ok=True)
    dst = os.path.join(OUT, "%d.png" % VARIANTS[a.mode])
    out.save(dst)
    print("готово", dst)
    return 0


if __name__ == "__main__":
    sys.exit(main())
