"""DERIVE_RECOLOR_V3 - детерминированный вывод HD-кадра члена семейства из HD-кадра основы.

Решение: специалист 03.10, передал Vitali в чате (DERIVE_RECOLOR_ACCEPTANCE_V3_PREP). Две независимые стадии:

Stage A - геометрия. Цепочка source -> ноль или больше преобразований геометрии -> преобразование цвета ->
target. Поддержано IDENTITY и MIRROR_X (поворот и другой бок - нет). Преобразование выбирается по ТОЧНОМУ
совпадению силуэта оригинала основы после преобразования с силуэтом оригинала члена, а не по тому, как связь
записана в семействе (R-194: FRNITURE:9 -> ABUNKER:11 записан перекраской, а член - перекраска ОТРАЖЁННОЙ
основы). Ни одно не совпало - вывод отказывается (REFUSED), а не рисует криво. Совпали оба (симметричный
силуэт) - решает функция цвета (relation_probe.func_map), при равенстве - заявленный маршрут.

Stage B - цвет. Параметры переноса считаются по месту на сетке оригинала: для каждого пикселя основы своя
пара (цвет основы, цвет члена) -> множитель яркости k, сдвиг цветности, цветность члена (формула та же, что
в obj_derive.transfer). Отличие от V2 - как HD-пиксель выбирает своё место:
  EXACT_MAP (по умолчанию) - HD-пиксель берёт параметры ОДНОГО места из окна 3x3 оригинала вокруг своей
    клетки: ближайшего по цвету к самому HD-пикселю, со штрафом за расстояние. Без усреднения: граница двух
    цветов идёт по краю, который нарисован в HD, и цвета не смешиваются.
  SOFT_MAP - только если детектор доказал дизеринг (скопление шахматных пикселей у основы или у члена):
    в области дизеринга параметры места заменены средним по окну 3x3 внутри силуэта (как obj_derive.soft),
    вне её - EXACT. «soft потому, что эта перекраска требует интерполяции»: HD-художник нарисовал шахматку
    ровным средним тоном, и выбор одного из двух мест дал бы рябь 4x4.
Альфа HD-основы не меняется (после преобразования геометрии).

Только numpy и PIL, без модели и без видеокарты. Вызов: derive(hd, ob, ot, declared, mode=None, via=None)
-> (RGBA uint8 или None, цепочка). Модуль ничего не пишет на диск.
"""
import numpy as np

VERSION = "derive-recolor-v3-2026-10-03.1"
GEOMETRIES = ("IDENTITY", "MIRROR_X")
MODES = ("EXACT_MAP", "SOFT_MAP")
DITHER_NB = 3          # шахматный пиксель - дизеринг, если среди 8 соседей шахматных не меньше
DITHER_MIN_PX = 8      # SOFT_MAP: пикселей дизеринга у основы или члена не меньше
DITHER_MIN_FRAC = 0.01  # и доля от силуэта не меньше
DITHER_GROW = 1        # область дизеринга расширяется на столько пикселей оригинала
PICK_LAMBDA = 8.0      # штраф выбора места: единиц YCbCr на пиксель оригинала расстояния до центра места
SPREAD_N = 8           # места за силуэтом - от ближайших внутри, до стольких шагов
CHROMA_W0, CHROMA_W1 = 8.0, 16.0   # смешение сдвига цветности и цветности члена (как obj_derive.transfer)
# порядок кандидатов: своя клетка первой - при равной цене побеждает она
OFFSETS = ((0, 0), (0, -1), (0, 1), (-1, 0), (1, 0), (-1, -1), (-1, 1), (1, -1), (1, 1))


def ycc(a):
    """Как obj_derive.ycc."""
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    y = 0.299 * r + 0.587 * g + 0.114 * b
    return y, 0.564 * (b - y), 0.713 * (r - y)


def rgb(y, cb, cr):
    """Как obj_derive.rgb."""
    r = y + 1.403 * cr
    b = y + 1.773 * cb
    g = (y - 0.299 * r - 0.114 * b) / 0.587
    return np.stack([r, g, b], -1)


def soft(v, m):
    """Как obj_derive.soft: среднее по окну 3x3 внутри силуэта, центр с весом 1, соседи 0.5."""
    acc, cnt = np.zeros_like(v), np.zeros_like(v)
    mf = m.astype(np.float64)
    P = np.pad(v * mf, 1)
    M = np.pad(mf, 1)
    h, w = v.shape
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            wgt = 1.0 if dy == 0 and dx == 0 else 0.5
            acc += wgt * P[1 + dy:1 + dy + h, 1 + dx:1 + dx + w]
            cnt += wgt * M[1 + dy:1 + dy + h, 1 + dx:1 + dx + w]
    return np.where(cnt > 0, acc / np.maximum(cnt, 1e-9), v)


def geo(a, g):
    if g == "IDENTITY":
        return a
    if g == "MIRROR_X":
        return a[:, ::-1].copy()
    raise ValueError("геометрия %s не поддержана" % g)


def codes(a):
    return (a[..., 0].astype(np.int64) << 16) | (a[..., 1].astype(np.int64) << 8) | a[..., 2].astype(np.int64)


def func_fit(ca, cb):
    """Доля пикселей, объяснённых лучшей функцией цвет A -> цвет B (как relation_probe.func_map)."""
    if not len(ca):
        return 0.0
    best = {}
    pairs, n = np.unique(np.stack([ca, cb], 1), axis=0, return_counts=True)
    for (x, _y), k in zip(pairs.tolist(), n.tolist()):
        best[x] = max(best.get(x, 0), k)
    return sum(best.values()) / len(ca)


# ---------- Stage A ----------

def resolve_geometry(ob, ot, declared):
    sb, st = ob[..., 3] > 0, ot[..., 3] > 0
    mism = {g: int((geo(sb, g) != st).sum()) for g in GEOMETRIES}
    ok = [g for g in GEOMETRIES if mism[g] == 0]
    ev = {"support_mismatch": mism, "declared": declared}
    if not ok:
        return None, dict(ev, reason="no supported geometry transform matches the member support exactly")
    if len(ok) == 1:
        return ok[0], dict(ev, reason="unique exact support match")
    ct = codes(ot)[st]
    fits = {g: round(func_fit(codes(geo(ob, g))[st], ct), 6) for g in ok}
    ev["color_function_fit"] = fits
    best = max(fits.values())
    top = [g for g in ok if fits[g] == best]
    if len(top) == 1:
        return top[0], dict(ev, reason="symmetric support; best colour function")
    dg = "MIRROR_X" if declared == "mirror" else "IDENTITY"
    return (dg if dg in top else top[0]), dict(ev, reason="symmetric support, equal colour function; declared route")


# ---------- детектор дизеринга ----------

def _sh(P, dy, dx):
    return P[1 + dy:P.shape[0] - 1 + dy, 1 + dx:P.shape[1] - 1 + dx]


def dither_mask(a):
    """Шахматный пиксель: слева и справа один цвет, сверху и снизу один цвет, оба не его; дизеринг -
    шахматный пиксель, у которого среди 8 соседей шахматных не меньше DITHER_NB (одиночные - деталь рисунка)."""
    m = a[..., 3] > 0
    c = np.where(m, codes(a), -1)
    P = np.pad(c, 1, constant_values=-1)
    L, R, U, D = _sh(P, 0, -1), _sh(P, 0, 1), _sh(P, -1, 0), _sh(P, 1, 0)
    ok = m & (L >= 0) & (R >= 0) & (U >= 0) & (D >= 0)
    k = ok & (L == R) & (L != c) & (U == D) & (U != c)
    K = np.pad(k, 1)
    nb = sum(_sh(K, dy, dx).astype(np.int32) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx)
    return k & (nb >= DITHER_NB)


def grow(m, n):
    for _ in range(n):
        P = np.pad(m, 1)
        m = m | _sh(P, 0, 1) | _sh(P, 0, -1) | _sh(P, 1, 0) | _sh(P, -1, 0) | _sh(P, 1, 1) | _sh(P, -1, -1) \
            | _sh(P, 1, -1) | _sh(P, -1, 1)
    return m


def detect(ob_o, ot):
    """Решение о режиме: SOFT_MAP, только если дизеринг доказан."""
    sup = (ob_o[..., 3] > 0) & (ot[..., 3] > 0)
    db, dt = dither_mask(ob_o) & sup, dither_mask(ot) & sup
    d = db | dt
    n, s = int(d.sum()), int(sup.sum())
    frac = n / s if s else 0.0
    soft_ok = n >= DITHER_MIN_PX and frac >= DITHER_MIN_FRAC
    info = {"dither_px_base": int(db.sum()), "dither_px_member": int(dt.sum()), "dither_px": n, "support_px": s,
            "dither_frac": round(frac, 4), "proven": bool(soft_ok)}
    if soft_ok:
        info["reason"] = ("soft because this recolor requires interpolation: %d dithered pixels (%.1f%% of the "
                          "support) - the HD painter renders them as one mean tone" % (n, 100 * frac))
    else:
        info["reason"] = "exact: dithering not proven (%d px, %.1f%%; need >= %d px and >= %.1f%%)" % (
            n, 100 * frac, DITHER_MIN_PX, 100 * DITHER_MIN_FRAC)
    return d, info


# ---------- Stage B ----------

def _spread_index(m):
    """Номер места (y*w+x) для каждой клетки оригинала: внутри силуэта своё, за ним - ближайшее внутри
    (по шагам 4-связности, первый сосед по порядку), дальше SPREAD_N шагов - -1."""
    h, w = m.shape
    idx = np.where(m, np.arange(h * w).reshape(h, w), -1)
    for _ in range(SPREAD_N):
        P = np.pad(idx, 1, constant_values=-1)
        new = idx.copy()
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            nb = _sh(P, dy, dx)
            take = (new < 0) & (nb >= 0)
            new[take] = nb[take]
        if (new == idx).all():
            break
        idx = new
    return idx


def transfer(hd, ob_o, ot, soft_region):
    """hd - RGBA x4 в ориентации цепочки, ob_o - оригинал основы в ней же, ot - оригинал члена;
    soft_region - маска мест оригинала, где параметры усредняются (пустая - чистый EXACT_MAP)."""
    a = hd.astype(np.float64)
    b, t = ob_o.astype(np.float64), ot.astype(np.float64)
    m = (b[..., 3] > 0) & (t[..., 3] > 0)
    yb, cbb, crb = ycc(b)
    yt, cbt, crt = ycc(t)
    if soft_region.any():
        sr = soft_region & m
        yb, cbb, crb, yt, cbt, crt = (np.where(sr, soft(v, m), v) for v in (yb, cbb, crb, yt, cbt, crt))
    k = (yt + 2.0) / (yb + 2.0)
    dcb, dcr = cbt - cbb, crt - crb
    wch = np.clip((np.hypot(dcb, dcr) - CHROMA_W0) / CHROMA_W1, 0.0, 1.0)
    h, w = m.shape
    idx = _spread_index(m)
    flat = lambda v: v.reshape(-1)
    pb = np.stack([flat(yb), flat(cbb), flat(crb)], -1)            # цвет места основы
    pp = np.stack([flat(k), flat(dcb), flat(dcr), flat(cbt), flat(crt), flat(wch)], -1)
    H, W = a.shape[:2]
    Y, X = np.mgrid[0:H, 0:W]
    cy, cx = Y // 4, X // 4
    yh, cbh, crh = ycc(a)
    hcol = np.stack([yh, cbh, crh], -1)
    best_cost = np.full((H, W), np.inf)
    best_loc = np.full((H, W), -1, np.int64)
    for dy, dx in OFFSETS:
        ny, nx = np.clip(cy + dy, 0, h - 1), np.clip(cx + dx, 0, w - 1)
        loc = idx[ny, nx]
        valid = loc >= 0
        col = pb[np.maximum(loc, 0)]
        dist = np.hypot((Y + 0.5) / 4 - (ny + 0.5), (X + 0.5) / 4 - (nx + 0.5))
        cost = ((hcol - col) ** 2).sum(-1) + (PICK_LAMBDA * dist) ** 2
        cost = np.where(valid, cost, np.inf)
        better = cost < best_cost
        best_cost = np.where(better, cost, best_cost)
        best_loc = np.where(better, loc, best_loc)
    have = best_loc >= 0
    P = pp[np.maximum(best_loc, 0)]
    kk = np.where(have, P[..., 0], 1.0)
    dcb_, dcr_ = np.where(have, P[..., 1], 0.0), np.where(have, P[..., 2], 0.0)
    tcb, tcr = np.where(have, P[..., 3], cbh), np.where(have, P[..., 4], crh)
    ww = np.where(have, P[..., 5], 0.0)
    cb2 = (1 - ww) * (cbh + dcb_) + ww * tcb
    cr2 = (1 - ww) * (crh + dcr_) + ww * tcr
    out = hd.copy()
    out[..., :3] = np.round(np.clip(rgb(yh * kk, cb2, cr2), 0, 255)).astype(np.uint8)
    out[out[..., 3] == 0, :3] = 0
    return out, {"hd_px_without_place": int((~have & (hd[..., 3] > 0)).sum())}


def derive(hd, ob, ot, declared="recolor", mode=None, via=None, soft_scope="detected"):
    """hd - RGBA uint8 (h*4, w*4) основы, ob и ot - RGBA uint8 (h, w) оригиналов основы и члена.
    mode None - выбор детектором; EXACT_MAP или SOFT_MAP - принудительно (для сравнения режимов).
    soft_scope: detected - SOFT_MAP только в области дизеринга; support - во всём силуэте (диагностика:
    «soft там, где дизеринга нет»). Возвращает (вывод или None, цепочка)."""
    if hd.shape[:2] != (ob.shape[0] * 4, ob.shape[1] * 4) or ob.shape != ot.shape:
        raise ValueError("размеры: hd %s, основа %s, член %s" % (hd.shape, ob.shape, ot.shape))
    g, ev = resolve_geometry(ob, ot, declared)
    chain = {"version": VERSION, "source": "base", "via": via, "geometry_transform": g,
             "geometry_resolution": ev, "target": "member", "declared_route": declared}
    if g is None:
        chain.update(status="REFUSED", color_transform=None)
        return None, chain
    chain["declared_overridden"] = (g == "MIRROR_X") != (declared == "mirror")
    hd_o, ob_o = geo(hd, g), geo(ob, g)
    dmask, dinfo = detect(ob_o, ot)
    auto = "SOFT_MAP" if dinfo["proven"] else "EXACT_MAP"
    use = mode or auto
    if use not in MODES:
        raise ValueError("режим %s" % use)
    sup = (ob_o[..., 3] > 0) & (ot[..., 3] > 0)
    if use == "SOFT_MAP":
        region = sup if soft_scope == "support" else grow(dmask, DITHER_GROW) & sup
    else:
        region = np.zeros_like(sup)
    out, tinfo = transfer(hd_o, ob_o, ot, region)
    chain.update(status="DERIVED", color_transform="RECOLOR_" + use, mode_selected_by_detector=auto,
                 mode_forced=mode is not None, soft_scope=soft_scope if use == "SOFT_MAP" else None,
                 soft_region_px=int(region.sum()), dither=dinfo, transfer=tinfo)
    return out, chain
