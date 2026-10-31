#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Ворота верности ассету: цвет и части внутри силуэта готового HD-кадра против оригинала 32x40.

Зачем (DECISIONS 2026-10-03, путь A): run1 прямого рендера прошёл машину с PASS, хотя у банки URBAN40K:86
потух красный, телевизор OSIRON_FINNIK:41 стал меньше, а у ламп XB3BITZ1:26 пропала тёмная арматура.
Проверки photo_accept смотрят контур, альфу и подложку; что внутри контура - не смотрит ни одна.

Как считается. HD-кадр (k = 4) сводится к сетке оригинала: цвет клетки - среднее непрозрачных пикселей блока 4x4.
- COLOR: насыщенность HD к оригиналу у сигнальных пикселей (C* оригинала от SIGNAL_C) и по всему телу.
- DARK: доля тёмных пикселей оригинала (L* < DARK_L), которые в HD остались тёмными (светлее не больше
  DARK_SLACK). Тёмная арматура, ножки, рамки.
- PARTS: цвета оригинала - кластеры (Lab, слияние ближе MERGE), связный кусок кластера - часть. Крупная часть
  (от BIG доли тела), заметно темнее или светлее кольца вокруг себя, сохранена в клетках, где HD на ту же
  сторону от кольца. Худшая крупная часть. Только REVIEW: на калибровке мера не отделяет уменьшенный
  телевизор от принятых Vitali кадров (restore-v1/calibration.md), FAIL по ней был бы ложной тревогой.
- EDGE_COLOR_HALO: цветная кайма по краю тела (специалист 03.10 по RESTORE_V1: синяя подложка осела на тонкие
  ветки MOUNTSNOW2:16). Край - непрозрачные HD-пиксели в HALO_BAND от прозрачного; пиксель каймы - дальше HALO_D
  от ЛЮБОГО цвета оригинала (оттенок, L* с весом HALO_WL) и насыщеннее HALO_C. Мера - доля каймы в крае.
  Сравнение со всей палитрой оригинала, а не с соседями: своя цветная кромка предмета - не кайма.
Пороги - THRESH; калибровка на вердиктах Vitali photo-struct-accept-v1 и run1 (restore-v1/calibration.md).
Стандарт новый (DECISIONS 2026-10-03, путь A): сигнальный цвет и тёмные детали как в оригинале. Прежняя
приёмка его не требовала, поэтому принятые тогда кадры здесь часто REVIEW.

Библиотека и проверка без модели:
    py -3.13 tools/hdart/asset_fidelity.py <оригинал.png> <hd.png>
"""
import sys

import numpy as np

K = 4
MERGE = 14.0            # ΔE76: цвета оригинала ближе - один кластер (рампа одного материала)
MIN_AREA = 8            # часть меньше - не проверяется частями (одиночные огоньки, блики)
SIGNAL_C = 28.0         # C* оригинала от этого - насыщенный (сигнальный) цвет
COVER = 0.5             # клетка HD считается телом, если непрозрачна хотя бы на половину
RING = 2                # ширина кольца вокруг части, пикселей базы
MIN_CONTRAST = 10.0     # L*: часть темнее или светлее кольца хотя бы на столько - проверяется
KEEP_SHARE = 0.25       # клетка HD сохранена, если перепад с кольцом той же стороны и не меньше этой доли
DARK_L = 30.0           # L* оригинала ниже - тёмная деталь (арматура, ножки, рамки)
DARK_SLACK = 15.0       # тёмная клетка HD сохранена, если светлее оригинала не больше чем на столько
DARK_MIN = 20          # тёмных пикселей меньше - DARK не проверяется
BIG = 0.04              # крупная часть - от этой доли тела
HALO_BAND = 4           # пикселей HD: край тела, где ищется кайма (один пиксель базы)
HALO_WL = 0.35          # вес L* в расстоянии каймы: светотень на краю - не кайма, чужой оттенок - кайма
HALO_D = 25.0           # краевой пиксель дальше этого от любого цвета оригинала ...
HALO_C = 15.0           # ... и сам насыщенный (C*) - пиксель каймы
THRESH = {"signal_fail": 0.40, "signal_review": 0.70,
          "body_fail": 0.40, "body_review": 0.70,
          "dark_fail": 0.30, "dark_review": 0.55,
          "parts_review": 0.10,
          "halo_review": 0.05, "halo_fail": 0.15}
CHECKS = ("COLOR", "DARK", "PARTS", "EDGE_COLOR_HALO")


def lab(rgb):
    """sRGB 0..255 -> CIE Lab (D65)."""
    c = np.asarray(rgb, np.float64) / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    m = np.array([[0.4124564, 0.3575761, 0.1804375],
                  [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    xyz = c @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    L = 116 * f[..., 1] - 16
    a = 500 * (f[..., 0] - f[..., 1])
    b = 200 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], -1)


def chroma(lb):
    return np.hypot(lb[..., 1], lb[..., 2])


def blocks(hd, k=K):
    """HD RGBA (H*k, W*k) -> (средний цвет непрозрачного в блоке (H, W, 3), доля непрозрачного (H, W))."""
    a = np.asarray(hd, np.float64)
    H, W = a.shape[0] // k, a.shape[1] // k
    a = a[:H * k, :W * k].reshape(H, k, W, k, 4).transpose(0, 2, 1, 3, 4).reshape(H, W, k * k, 4)
    op = a[..., 3] > 128
    n = op.sum(-1)
    rgb = (a[..., :3] * op[..., None]).sum(-2) / np.maximum(n, 1)[..., None]
    return rgb, n / float(k * k)


def clusters(lab_o, mask):
    """Кластеры цветов оригинала: жадно по частоте, центр - взвешенное среднее. -> (метки (H, W), центры)."""
    cols, inv, cnt = np.unique(lab_o[mask].round(3), axis=0, return_inverse=True, return_counts=True)
    order = np.argsort(-cnt)
    centers, weights, lab_of = [], [], np.zeros(len(cols), int)
    for i in order:
        if centers:
            d = np.linalg.norm(np.asarray(centers) - cols[i], axis=1)
            j = int(d.argmin())
            if d[j] < MERGE:
                w = weights[j] + cnt[i]
                centers[j] = (np.asarray(centers[j]) * weights[j] + cols[i] * cnt[i]) / w
                weights[j] = w
                lab_of[i] = j
                continue
        centers.append(cols[i].copy())
        weights.append(cnt[i])
        lab_of[i] = len(centers) - 1
    labels = np.full(mask.shape, -1)
    labels[mask] = lab_of[inv.ravel()]
    return labels, np.asarray(centers)


def components(labels):
    """Связные куски (4-соседство) одной метки -> список (метка, маска)."""
    H, W = labels.shape
    seen = np.zeros_like(labels, bool)
    out = []
    for y in range(H):
        for x in range(W):
            if labels[y, x] < 0 or seen[y, x]:
                continue
            c, stack, m = labels[y, x], [(y, x)], np.zeros_like(seen)
            seen[y, x] = True
            while stack:
                cy, cx = stack.pop()
                m[cy, cx] = True
                for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                    if 0 <= ny < H and 0 <= nx < W and not seen[ny, nx] and labels[ny, nx] == c:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            out.append((int(c), m))
    return out


def grade(v, fail, review):
    return "FAIL" if v < fail else "REVIEW" if v < review else "PASS"


def halo(o, h):
    """Доля цветной каймы на краю HD-тела: краевой пиксель (HALO_BAND от прозрачного), чей цвет далёк от ЛЮБОГО
    цвета оригинала (по оттенку; L* с весом HALO_WL) и насыщен. Сравнение со всей палитрой тела, а не с соседями:
    своя красная кромка стола (DECORLUX:7) - цвет предмета, синяя подложка на ветках (MOUNTSNOW2:16) - нет."""
    op = h[..., 3] > 128
    inner = op.copy()
    for _ in range(HALO_BAND):
        g = inner.copy()
        g[1:] &= inner[:-1]
        g[:-1] &= inner[1:]
        g[:, 1:] &= inner[:, :-1]
        g[:, :-1] &= inner[:, 1:]
        inner = g
    edge = op & ~inner
    n = int(edge.sum())
    if n == 0:
        return None, 0, None
    pal = np.unique(lab(o[..., :3])[o[..., 3] > 0].round(2), axis=0)
    le = lab(h[..., :3])[edge]
    d = np.sqrt((le[:, None, 1] - pal[None, :, 1]) ** 2 + (le[:, None, 2] - pal[None, :, 2]) ** 2
                + (HALO_WL * (le[:, None, 0] - pal[None, :, 0])) ** 2).min(1)
    bad = (d > HALO_D) & (chroma(le) > HALO_C)
    rgb = [int(v) for v in h[..., :3][edge][bad].mean(0)] if bad.any() else None
    return float(bad.sum()) / n, n, rgb


def measure(orig, hd):
    """orig RGBA (H, W) 32x40, hd RGBA (H*4, W*4) -> отчёт с вердиктами PARTS и COLOR."""
    o = np.asarray(orig.convert("RGBA") if hasattr(orig, "convert") else orig)
    h = np.asarray(hd.convert("RGBA") if hasattr(hd, "convert") else hd)
    if h.shape[0] != o.shape[0] * K or h.shape[1] != o.shape[1] * K:
        raise ValueError("HD %s не x%d от оригинала %s" % (h.shape[:2], K, o.shape[:2]))
    mask = o[..., 3] > 0
    lo = lab(o[..., :3])
    frgb, cover = blocks(h)
    lf = lab(frgb)
    body = cover >= COVER
    labels, centers = clusters(lo, mask)
    parts = []
    for c, m in components(labels):
        area = int(m.sum())
        if area < MIN_AREA:
            continue
        # кольцо - тело вокруг части шириной RING; часть проверяется, если в оригинале она заметно темнее или
        # светлее кольца. Клетка сохранена, если в HD она на ту же сторону от кольца и с долей перепада не меньше
        # KEEP_SHARE: общий сдвиг тона это не меняет, подмена части соседом (ТВ меньше, арматуры нет) - меняет
        grow = m.copy()
        for _ in range(RING):
            g = grow.copy()
            g[1:] |= grow[:-1]
            g[:-1] |= grow[1:]
            g[:, 1:] |= grow[:, :-1]
            g[:, :-1] |= grow[:, 1:]
            grow = g
        ring = grow & ~m & mask
        ring_b = ring & body
        ys, xs = np.nonzero(m)
        co = float(chroma(lo[m]).mean())
        inb = m & body
        cf = float(chroma(lf[inb]).mean()) if inb.any() else 0.0
        d_o = float(lo[m][:, 0].mean() - np.median(lo[ring][:, 0])) if ring.any() else 0.0
        kept = None
        if abs(d_o) >= MIN_CONTRAST and ring_b.sum() >= 3:
            d_f = lf[..., 0] - np.median(lf[ring_b][:, 0])
            ok = m & body & (np.sign(d_f) == np.sign(d_o)) & (np.abs(d_f) >= KEEP_SHARE * abs(d_o))
            kept = float(ok.sum()) / area
        parts.append({"cluster": c, "area": area, "bbox": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
                      "rgb": [int(v) for v in o[..., :3][m].mean(0)], "L": round(float(lo[m][:, 0].mean()), 1),
                      "C": round(co, 1), "contrast": round(d_o, 1),
                      "kept": round(kept, 3) if kept is not None else None,
                      "chroma_ratio": round(cf / co, 3) if co >= SIGNAL_C else None})
    dark_m = mask & (lo[..., 0] < DARK_L)
    dark_kept = (float((dark_m & body & (lf[..., 0] < lo[..., 0] + DARK_SLACK)).sum()) / dark_m.sum()
                 if dark_m.sum() >= DARK_MIN else None)
    sig_m = mask & (chroma(lo) >= SIGNAL_C)
    sig_b = sig_m & body
    signal = (float(chroma(lf[sig_b]).sum() / chroma(lo[sig_m]).sum()) if sig_m.sum() >= 4 else None)
    bm = mask & body
    body_ratio = float(chroma(lf[bm]).mean() / max(chroma(lo[mask]).mean(), 1e-6)) if bm.any() else 0.0
    t = THRESH
    big = [p for p in parts if p["kept"] is not None and p["area"] >= BIG * mask.sum()]
    worst = min(big, key=lambda p: p["kept"]) if big else None
    pv = ("REVIEW" if worst["kept"] < t["parts_review"] else "PASS") if worst else "N/A"
    cvs = [grade(body_ratio, t["body_fail"], t["body_review"])]
    if signal is not None:
        cvs.append(grade(signal, t["signal_fail"], t["signal_review"]))
    cv = "FAIL" if "FAIL" in cvs else "REVIEW" if "REVIEW" in cvs else "PASS"
    dv = grade(dark_kept, t["dark_fail"], t["dark_review"]) if dark_kept is not None else "N/A"
    why_p = ("часть rgb%s площадь %d сохранена %.2f" % (tuple(worst["rgb"]), worst["area"], worst["kept"])
             if worst else "крупных контрастных частей нет")
    why_c = "насыщенность тела %.2f%s" % (body_ratio, ", сигнальных %.2f" % signal if signal is not None else "")
    why_d = ("тёмных осталось %.2f из %d" % (dark_kept, int(dark_m.sum())) if dark_kept is not None
             else "тёмных меньше %d" % DARK_MIN)
    hs, hn, hrgb = halo(o, h)
    hv = ("N/A" if hs is None else "FAIL" if hs >= t["halo_fail"] else "REVIEW" if hs >= t["halo_review"]
          else "PASS")
    why_h = ("края нет" if hs is None else "кайма %.3f края из %d%s" % (
        hs, hn, ", цвет rgb%s" % (tuple(hrgb),) if hrgb else ""))
    return {"PARTS": [pv, why_p], "COLOR": [cv, why_c], "DARK": [dv, why_d], "EDGE_COLOR_HALO": [hv, why_h],
            "halo": None if hs is None else round(hs, 4), "parts": parts, "signal_ratio": signal,
            "dark_kept": None if dark_kept is None else round(dark_kept, 3), "dark_px": int(dark_m.sum()),
            "body_ratio": round(body_ratio, 3), "clusters": len(centers),
            "mean_dE": round(float(np.linalg.norm(lf[bm] - lo[bm], axis=-1).mean()), 1) if bm.any() else None}


def verdict(rep):
    v = [rep[c][0] for c in CHECKS]
    return "FAIL" if "FAIL" in v else "REVIEW" if "REVIEW" in v else "PASS"


def main():
    from PIL import Image
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    rep = measure(Image.open(sys.argv[1]), Image.open(sys.argv[2]))
    for c in CHECKS:
        print("%-6s %-6s %s" % (c, rep[c][0], rep[c][1]))
    for p in sorted(rep["parts"], key=lambda p: -1 if p["kept"] is None else p["kept"]):
        print("   часть rgb%-16s площадь %3d перепад %5.1f сохранена %s %s" % (
            tuple(p["rgb"]), p["area"], p["contrast"], "-" if p["kept"] is None else "%.2f" % p["kept"],
            "насыщ. %.2f" % p["chroma_ratio"] if p["chroma_ratio"] is not None else ""))
    print("итог", verdict(rep))


if __name__ == "__main__":
    main()
