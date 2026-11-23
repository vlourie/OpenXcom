#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ALIGNED_RECOLOR_V1 - перекраска со сдвигом силуэта на несколько пикселей (специалист 02.10, RELATION_DISCOVERY_V5_PREP).
CPU, чтение. Общий детектор: исключений по наборам нет, пороги R4 не снижены.

R4 (relation_discovery_v4) сравнивает силуэты без сдвига: кадр, перерисованный со сдвигом на пиксель, даёт
IoU ниже R4_NEAR, и перекраска не видна. Здесь силуэт B сдвигается на dx, dy в малом фиксированном диапазоне
(прямо и в отражении), берётся сдвиг с наибольшим IoU, и на выровненной паре проверяется то же, что у R4:

  - сдвиг не нулевой: без сдвига - область R4, AR1 там не срабатывает;
  - силуэт после выравнивания >= AR_IOU (= R4_NEAR);
  - функция цвета max(f_ab, f_ba) >= AR_FUNC (= R4D_FUNC) на общем силуэте - устойчивое соответствие цветов;
  - цветов основы >= MIN_COLORS, границ цветовых областей >= AR_BORDER (= R4D_BORDER);
  - остаток (пиксели объединения силуэтов, не объяснённые функцией цвета) <= AR_RESID (= 1 - R4D_FUNC);
  - силуэт не общий у обоих кадров (кадров с IoU >= GEO не больше R4D_GENERIC).

Уровень - как у R4: STRONG только когда пара наборов - строгая перекраска (SetIndex.pair_stats), иначе
CANDIDATE. Тип всегда TYPE_OPEN (подтип на ревью). Отрицательный контроль - цвета B, перемешанные внутри силуэта.
Параметры записаны в spec.json V5_PREP до диагностического пересчёта.
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import relation_discovery_v2 as v2                # noqa: E402
import relation_discovery_v4 as v4                # noqa: E402

TYPE = "ALIGNED_RECOLOR"
DETECTOR = "AR1"
AR_SHIFT = 2                     # |dx|, |dy| <= 2 базовых пикселя: 6 % ширины 32 и 5 % высоты 40
AR_IOU = v4.R4_NEAR              # 0.92 - как нижняя граница почти того же силуэта R4b
AR_FUNC = v4.R4D_FUNC            # 0.80 - как местная правка R4d
AR_BORDER = v4.R4D_BORDER        # 0.80
AR_RESID = round(1.0 - v4.R4D_FUNC, 6)     # 0.20 - остаток местной правки по объединению силуэтов
AR_GENERIC = v4.R4D_GENERIC      # 30
MIN_COLORS = v4.MIN_COLORS       # 6
PREFILTER = 0.03                 # запас только для отбора кандидатов (у края кадра сдвиг A и сдвиг B режут разное);
                                 # решает scores() по самой паре
PARAMS = {"AR_SHIFT": AR_SHIFT, "AR_IOU": AR_IOU, "AR_FUNC": AR_FUNC, "AR_BORDER": AR_BORDER, "AR_RESID": AR_RESID,
          "AR_GENERIC": AR_GENERIC, "MIN_COLORS": MIN_COLORS, "PREFILTER": PREFILTER,
          "level": "STRONG только при строгой перекраске пары наборов (v4.SetIndex, R4C_COMMON и R4_SET_STRICT), "
                   "иначе CANDIDATE", "type_level": "TYPE_OPEN"}
SHIFTS = [(dx, dy) for dy in range(-AR_SHIFT, AR_SHIFT + 1) for dx in range(-AR_SHIFT, AR_SHIFT + 1)]


def shift(a, dx, dy):
    """Сдвиг массива (h, w[, c]) на dx вправо и dy вниз; освободившееся - нули (прозрачно)."""
    out = np.zeros_like(a)
    h, w = a.shape[:2]
    ys, yd = (slice(0, h - dy), slice(dy, h)) if dy >= 0 else (slice(-dy, h), slice(0, h + dy))
    xs, xd = (slice(0, w - dx), slice(dx, w)) if dx >= 0 else (slice(-dx, w), slice(0, w + dx))
    out[yd, xd] = a[ys, xs]
    return out


def iou(ma, mb):
    u = (ma | mb).sum()
    return float((ma & mb).sum() / u) if u else 0.0


def best_alignment(A, B):
    """Лучший сдвиг B к A прямо и в отражении: (IoU, flip, dx, dy); при равенстве - меньший сдвиг, без отражения."""
    ma = A[..., 3] > 0
    best = None
    for flip in (False, True):
        mb = (B[:, ::-1] if flip else B)[..., 3] > 0
        for dx, dy in SHIFTS:
            v = iou(ma, shift(mb, dx, dy))
            k = (round(v, 6), -(abs(dx) + abs(dy)), not flip)
            if best is None or k > best[0]:
                best = (k, (v, flip, dx, dy))
    return best[1]


def aligned(B, flip, dx, dy):
    BB = np.ascontiguousarray(B[:, ::-1]) if flip else B
    return shift(BB, dx, dy)


def residual(A, BB):
    """Доля объединения силуэтов, не объяснённая лучшей функцией цвета (в любую сторону)."""
    import relation_probe as rp
    ma, ca = rp.codes(A)
    mb, cb = rp.codes(BB)
    u = int((ma | mb).sum())
    if not u:
        return 1.0
    m = ma & mb
    best = 0
    for x, y in ((ca[m], cb[m]), (cb[m], ca[m])):
        f, mp, _na, _nb = rp.func_map(x, y)
        best = max(best, int(round(f * len(x))))
    return 1.0 - best / u


def scores(A, B):
    v, flip, dx, dy = best_alignment(A, B)
    BB = aligned(B, flip, dx, dy)
    f_ab, f_ba, sil, na, nb, biou = v2.funcs(A, BB)
    fmax = max(f_ab, f_ba)
    nbase = max(na, nb) if min(f_ab, f_ba) >= v4.FUNC else (na if f_ab >= f_ba else nb)
    d0 = iou(A[..., 3] > 0, B[..., 3] > 0)
    f0 = iou(A[..., 3] > 0, B[:, ::-1][..., 3] > 0)
    return {"silhouette": round(sil, 4), "shift": [dx, dy], "flip": flip, "unshifted": round(max(d0, f0), 4),
            "topology": round(biou, 3), "f_ab": round(f_ab, 3), "f_ba": round(f_ba, 3), "fmax": round(fmax, 3),
            "base_colors": nbase, "residual": round(residual(A, BB), 4)}


def passes(sc, gen_a, gen_b):
    """Условия AR1 по очкам пары; -> (годно, [почему нет])."""
    no = []
    if sc["shift"] == [0, 0]:
        no.append("сдвиг нулевой - область R4")
    if sc["silhouette"] < AR_IOU:
        no.append("силуэт %.3f < %.2f" % (sc["silhouette"], AR_IOU))
    if sc["fmax"] < AR_FUNC:
        no.append("функция %.3f < %.2f" % (sc["fmax"], AR_FUNC))
    if sc["base_colors"] < MIN_COLORS:
        no.append("цветов основы %d < %d" % (sc["base_colors"], MIN_COLORS))
    if sc["topology"] < AR_BORDER:
        no.append("границ %.2f < %.2f" % (sc["topology"], AR_BORDER))
    if sc["residual"] > AR_RESID:
        no.append("остаток %.3f > %.2f" % (sc["residual"], AR_RESID))
    if gen_a > AR_GENERIC or gen_b > AR_GENERIC:
        no.append("силуэт общий (%d / %d)" % (gen_a, gen_b))
    return not no, no


def pair(ctx, si, a, b, B=None):
    """Довод AR1 на паре (a, b) или []. B - подмена кадра b (перемешанный контроль)."""
    a, b = a.upper(), b.upper()
    if a == b or b in ctx.ix.exact(a) or b in ctx.ix.mirror(a):
        return []
    A, B0 = ctx.rgba(a), ctx.rgba(b)
    if A is None or B0 is None or A.shape != B0.shape:
        return []
    sc = scores(A, B0 if B is None else B)
    ok, _no = passes(sc, si.generic(a), si.generic(b))
    if not ok:
        return []
    (sa, _fa), (sb, _fb) = v2.split(a), v2.split(b)
    st = si.pair_stats(sa, sb) if sa != sb else None
    strict = bool(st and st["common"] >= v4.R4C_COMMON and (st["strict"] or 0) >= v4.R4_SET_STRICT)
    e = v2.edge(TYPE, a, b, "STRONG" if strict else "CANDIDATE", DETECTOR, "AR1" + ("s" if strict else ""),
                "%s, сдвиг %+d,%+d: силуэт %.3f (без сдвига %.3f), границ %.2f, функция %.3f/%.3f, остаток %.3f, "
                "цветов основы %d%s" % ("отражение" if sc["flip"] else "прямо", sc["shift"][0], sc["shift"][1],
                                         sc["silhouette"], sc["unshifted"], sc["topology"], sc["f_ab"], sc["f_ba"],
                                         sc["residual"], sc["base_colors"],
                                         "" if st is None else "; наборы: общих %d, строгая перекраска %.2f" % (
                                             st["common"], st["strict"] or 0)))
    e["scores"] = dict(sc, set=st)
    return [e]


def candidates(ctx, a):
    """Кадры индекса, у которых силуэт после какого-нибудь ненулевого сдвига (прямо или в отражении) >= AR_IOU."""
    A = ctx.rgba(a)
    if A is None:
        return []
    m = A[..., 3] > 0
    if m.shape != ctx.masks.shape:
        return []
    hit = np.zeros(len(ctx.masks.keys), bool)
    for flip in (False, True):
        q0 = m[:, ::-1] if flip else m
        for dx, dy in SHIFTS:
            if (dx, dy) == (0, 0):
                continue
            # сдвиг B на (dx, dy) к A - то же, что сдвиг A на (-dx, -dy) к B; отражение B - отражение A
            hit |= ctx.masks.iou(shift(q0, -dx, -dy)) >= AR_IOU - PREFILTER
    return [ctx.masks.keys[i] for i in np.nonzero(hit)[0] if ctx.masks.keys[i] != a.upper()]


def discover(ctx, si, a):
    out = []
    for b in candidates(ctx, a):
        out += pair(ctx, si, a, b)
    return out
