"""DERIVE_RECOLOR_V3.1 - детерминированный вывод HD-кадра члена семейства: Stage A из V3 без изменений,
новый Stage B INTERPOLATED_MAP_V1.

Решение: специалист 03.10, передал Vitali в чате (DERIVE_RECOLOR_V3.1_PREP). Stage A (геометрия IDENTITY /
MIRROR_X по точному совпадению силуэта, отказ при несовпадении) - derive_recolor_v3.resolve_geometry, не
трогается. EXACT_MAP и SOFT_MAP V3 отвергнуты как общий метод и остаются диагностическими базами
(derive_recolor_v3.derive с mode=...); выбора EXACT/SOFT детектором больше нет.

INTERPOLATED_MAP_V1. Класс - пара (цвет оригинала основы, цвет оригинала члена). Для каждого HD-пикселя:
  1. след художника: четыре места оригинала, между центрами которых лежит центр пикселя (билинейное окно
     2x2), с билинейными весами - априорная доля каждого места. Места за силуэтом - ближайшие внутри
     (derive_recolor_v3._spread_index). Один класс в нескольких местах - одна запись, доли складываются;
  2. SPATIAL_REGION_BOUNDARY: области - группы классов, внутри которых цвет основы переходит в ОДИН цвет
     члена (regions: склейка соседствующих классов от частых соседств к редким, склейка запрещена, если один
     цвет основы ушёл бы в два цвета члена). Это граница, которую показывает член, а в основе её нет. Доля
     каждой области в пикселе - ТОЛЬКО пространственная (сумма долей следа её мест, как у художника на шве);
     по цвету области не смешиваются, как бы близко ни лежали их классы. Рассыпанная соль члена (один цвет
     основы в разные цвета члена вперемешку) - те же разные области, и они смешиваются по следу: средний тон
     без блоков 4x4;
  3. COLOR_INTERPOLATION: внутри одной области - положение цвета пикселя (YCbCr) между опорными цветами
     основы её классов, разложение на смесь: веса w >= 0, сумма 1, минимум нормированной невязки
     |h - sum w B|^2 плюс PRIOR_W * |w - доли следа области|^2 (unmix, перебор активных множеств); веса
     области умножаются на её пространственную долю. Невязка в единицах ожидаемого разброса
     HD: цветность - sig_n (медиана по классам разброса цветности их внутренних HD-пикселей, не меньше
     SIGMA_MIN), яркость - sqrt(sig_n^2 + (sig_g * Y)^2), где sig_g - медиана относительной штриховки классов:
     светотень внутри одного класса не читается как смесь с более светлым или тёмным классом;
  4. те же веса переносятся на пару: цвет основы и цвет члена смешиваются с ними (палитровые координаты), и
     к HD-пикселю применяется прежняя формула переноса (obj_derive.transfer / derive_recolor_v3.transfer):
     яркость умножается на (Yчлена+2)/(Yосновы+2), цветность - сдвиг, а при сильной перекраске цветность
     члена.
Чистая область - вес 1/0, то есть ровно перенос своего места. Размытая граница - плавная смесь. Дизеринг,
нарисованный в HD средним тоном, - средний цвет между классами, без блоков и соли.
Альфа HD-основы не меняется (после преобразования геометрии).

Только numpy, без модели и видеокарты. Вызов: derive(hd, ob, ot, declared, via=None) -> (RGBA uint8 или
None, цепочка). Модуль ничего не пишет на диск.
"""
import numpy as np

import derive_recolor_v3 as D3

VERSION = "derive-recolor-v3.1-interpolated-map-v1-2026-10-03.1"
COLOR_TRANSFORM = "RECOLOR_INTERPOLATED_MAP_V1"
SIGMA_MIN = 2.0          # нижний предел сигмы класса, единицы YCbCr (шаг округления и палитры)
SIGMA_FALLBACK = 8.0     # нет ни одного класса с 4+ своими HD-пикселями
STAT_ALPHA = 128         # HD-пиксель идёт в статистику класса, если альфа не меньше
MIXED_W = 0.95           # пиксель «смешан», если наибольший вес класса меньше (только для отчёта)
SHADE_MIN = 0.02         # нижний предел относительной штриховки HD (доля яркости)
SHADE_FALLBACK = 0.10    # нет ни одного класса с 4+ своими HD-пикселями
PRIOR_W = 1.0            # вес притяжения к следу в единицах нормированной невязки
CHROMA_W0, CHROMA_W1 = D3.CHROMA_W0, D3.CHROMA_W1


def classes(ob_o, ot, m):
    """Номер класса каждой клетки (-1 вне силуэта) и цвета классов: основа и член, YCbCr."""
    pair = (D3.codes(ob_o) << 24) | D3.codes(ot)
    uniq, inv = np.unique(pair[m], return_inverse=True)
    cls = np.full(m.shape, -1, np.int64)
    cls[m] = inv.reshape(-1)
    bcode = uniq >> 24
    tcode = uniq & 0xFFFFFF
    col = lambda c: np.stack([(c >> 16) & 255, (c >> 8) & 255, c & 255], -1).astype(np.float64)
    pb = np.stack(D3.ycc(col(bcode)), -1)
    pt = np.stack(D3.ycc(col(tcode)), -1)
    return cls, bcode, pb, pt


def class_spread(hd, cls, n):
    """Разброс каждого класса по внутренним 2x2 HD-пикселям его клеток: цветность (СКО от медианы по осям
    Cb, Cr) и штриховка (СКО яркости к средней яркости); классы с меньше чем 4 пикселями - nan."""
    h, w = cls.shape
    inner = np.zeros((4, 4), bool)
    inner[1:3, 1:3] = True
    inner = np.tile(inner, (h, w))
    big = np.repeat(np.repeat(cls, 4, 0), 4, 1)
    ok = inner & (hd[..., 3] >= STAT_ALPHA) & (big >= 0)
    hcol = np.stack(D3.ycc(hd[..., :3].astype(np.float64)), -1)
    sn = np.full(n, np.nan)
    sg = np.full(n, np.nan)
    npx = np.zeros(n, np.int64)
    for j in range(n):
        v = hcol[ok & (big == j)]
        npx[j] = len(v)
        if len(v) < 4:
            continue
        med = np.median(v[:, 1:], 0)
        sn[j] = float(np.sqrt(((v[:, 1:] - med) ** 2).mean()))
        sg[j] = float(v[:, 0].std() / max(float(v[:, 0].mean()), 1.0))
    return sn, sg, npx


def regions(cls, bcode, n):
    """SPATIAL_REGION_BOUNDARY: области - группы классов, в каждой из которых цвет основы переходит в ОДИН
    цвет члена. Классы склеиваются по числу соседств клеток (8 соседей), начиная с самых частых; склейка
    запрещена, если в объединённой группе один цвет основы ушёл бы в два цвета члена - это и есть граница,
    которую показывает член. Порядок полный: (-соседств, меньший номер, больший номер)."""
    h, w = cls.shape
    aff = {}
    for dy, dx in ((0, 1), (1, -1), (1, 0), (1, 1)):
        a = cls[max(0, -dy):h - max(0, dy), max(0, -dx):w - max(0, dx)]
        b = cls[max(0, dy):, max(0, dx):][:a.shape[0], :a.shape[1]]
        ok = (a >= 0) & (b >= 0) & (a != b)
        for i, j in zip(np.minimum(a[ok], b[ok]).tolist(), np.maximum(a[ok], b[ok]).tolist()):
            aff[(i, j)] = aff.get((i, j), 0) + 1
    root = list(range(n))
    maps = [{int(bcode[j]): j} for j in range(n)]

    def find(i):
        while root[i] != i:
            root[i] = root[root[i]]
            i = root[i]
        return i
    for (i, j), _c in sorted(aff.items(), key=lambda kv: (-kv[1], kv[0][0], kv[0][1])):
        ri, rj = find(i), find(j)
        if ri == rj:
            continue
        mi, mj = maps[ri], maps[rj]
        if any(b in mi and mi[b] != c for b, c in mj.items()):
            continue
        lo, hi = min(ri, rj), max(ri, rj)
        root[hi] = lo
        maps[lo] = {**mi, **mj}
        maps[hi] = None
    return np.array([find(j) for j in range(n)], np.int64)


SUBSETS = tuple(tuple(i for i in range(4) if s >> i & 1) for s in range(1, 16))


def unmix(h, R, p, valid, lam):
    """Веса w >= 0, сумма 1, на местах valid: минимум |h - sum w_j R_j|^2 + lam * |w - p|^2. Перебор
    активных множеств (15 подмножеств четырёх мест), у каждого - система ККТ; берётся допустимое решение с
    наименьшей целью, при равенстве - первое по порядку SUBSETS."""
    N = h.shape[:-1]
    best = np.full(N, np.inf)
    W = np.zeros(N + (4,))
    for S in SUBSETS:
        ok = valid[..., list(S)].all(-1)
        if not ok.any():
            continue
        k = len(S)
        Rs = R[..., list(S), :]                                   # (..., k, 3)
        ps = p[..., list(S)]
        M = np.einsum("...ic,...jc->...ij", Rs, Rs) + lam * np.eye(k)
        K = np.zeros(N + (k + 1, k + 1))
        K[..., :k, :k] = M
        K[..., :k, k] = 1.0
        K[..., k, :k] = 1.0
        rhs = np.zeros(N + (k + 1,))
        rhs[..., :k] = np.einsum("...ic,...c->...i", Rs, h) + lam * ps
        rhs[..., k] = 1.0
        sol = np.linalg.solve(np.where(ok[..., None, None], K, np.eye(k + 1)), rhs[..., None])[..., 0]
        w = sol[..., :k]
        feas = ok & (w >= -1e-9).all(-1)
        w = np.clip(w, 0.0, None)
        w = w / np.maximum(w.sum(-1, keepdims=True), 1e-300)
        full = np.zeros(N + (4,))
        full[..., list(S)] = w
        res = h - np.einsum("...i,...ic->...c", w, Rs)
        obj = (res ** 2).sum(-1) + lam * (((full - p) ** 2) * valid).sum(-1)
        take = feas & (obj < best - 1e-9)
        best = np.where(take, obj, best)
        W = np.where(take[..., None], full, W)
    return W


def transfer(hd, ob_o, ot):
    """hd - RGBA x4 в ориентации цепочки, ob_o - оригинал основы в ней же, ot - оригинал члена."""
    b = ob_o
    m = (b[..., 3] > 0) & (ot[..., 3] > 0)
    h, w = m.shape
    cls, bcode, pb, pt = classes(ob_o, ot, m)
    n = len(bcode)
    sn, sg, npx = class_spread(hd, cls, n)
    sig_n = max(SIGMA_MIN, float(np.nanmedian(sn))) if np.isfinite(sn).any() else SIGMA_FALLBACK
    sig_g = max(SHADE_MIN, float(np.nanmedian(sg))) if np.isfinite(sg).any() else SHADE_FALLBACK
    idx = D3._spread_index(m)
    cls_flat = cls.reshape(-1)
    H, W = hd.shape[:2]
    Y, X = np.mgrid[0:H, 0:W]
    u, v = (X + 0.5) / 4 - 0.5, (Y + 0.5) / 4 - 0.5
    x0, y0 = np.floor(u).astype(np.int64), np.floor(v).astype(np.int64)
    fx, fy = u - x0, v - y0
    C, PR = [], []
    for dy, dx in ((0, 0), (0, 1), (1, 0), (1, 1)):
        yy, xx = np.clip(y0 + dy, 0, h - 1), np.clip(x0 + dx, 0, w - 1)
        wy = fy if dy else 1 - fy
        wx = fx if dx else 1 - fx
        loc = idx[yy, xx]
        c = np.where(loc >= 0, cls_flat[np.maximum(loc, 0)], -1)
        C.append(c)
        PR.append(np.where(c >= 0, wy * wx, 0.0))
    C, PR = np.stack(C, -1), np.stack(PR, -1)
    slots = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))
    # одинаковый класс в нескольких местах следа - одна запись, доли складываются
    for i, j in slots:
        same = (C[..., i] >= 0) & (C[..., i] == C[..., j])
        PR[..., i] = np.where(same, PR[..., i] + PR[..., j], PR[..., i])
        C[..., j] = np.where(same, -1, C[..., j])
        PR[..., j] = np.where(same, 0.0, PR[..., j])
    valid = C >= 0
    Cc = np.maximum(C, 0)
    hcol = np.stack(D3.ycc(hd[..., :3].astype(np.float64)), -1)
    have = valid.any(-1)
    # невязка в единицах ожидаемого разброса: цветность - шум sig_n, яркость - шум плюс штриховка sig_g * Y
    scale = np.stack([1.0 / np.sqrt(sig_n ** 2 + (sig_g * hcol[..., 0]) ** 2),
                      np.full(hcol.shape[:-1], 1.0 / sig_n), np.full(hcol.shape[:-1], 1.0 / sig_n)], -1)
    hs, Rs = hcol * scale, pb[Cc] * scale[..., None, :]
    # SPATIAL_REGION_BOUNDARY: доля каждой области следа - только пространственная (сумма долей её мест), по
    # цвету области не смешиваются; COLOR_INTERPOLATION - разложение цвета внутри одной области
    grp = regions(cls, bcode, n)
    G = np.where(valid, grp[Cc], -1)
    tot = np.maximum(PR.sum(-1), 1e-300)
    wgt = np.zeros(PR.shape)
    region = np.zeros((H, W), bool)
    for s in range(4):
        first = valid[..., s] & ~((G[..., :s] == G[..., s:s + 1]) & valid[..., :s]).any(-1)
        if not first.any():
            continue
        inr = valid & (G == G[..., s:s + 1]) & first[..., None]
        region |= first & (valid & ~inr).any(-1)
        mass = (PR * inr).sum(-1)
        pri = PR * inr / np.maximum(mass, 1e-300)[..., None]
        w_r = unmix(hs, Rs, pri, inr, PRIOR_W)
        wgt += (mass / tot)[..., None] * w_r
    beff = (wgt[..., None] * pb[Cc]).sum(-2)
    teff = (wgt[..., None] * pt[Cc]).sum(-2)
    yb, cbb, crb = beff[..., 0], beff[..., 1], beff[..., 2]
    yt, cbt, crt = teff[..., 0], teff[..., 1], teff[..., 2]
    yh, cbh, crh = hcol[..., 0], hcol[..., 1], hcol[..., 2]
    k = np.where(have, (yt + 2.0) / (yb + 2.0), 1.0)
    dcb, dcr = np.where(have, cbt - cbb, 0.0), np.where(have, crt - crb, 0.0)
    wch = np.where(have, np.clip((np.hypot(dcb, dcr) - CHROMA_W0) / CHROMA_W1, 0.0, 1.0), 0.0)
    tcb, tcr = np.where(have, cbt, cbh), np.where(have, crt, crh)
    cb2 = (1 - wch) * (cbh + dcb) + wch * tcb
    cr2 = (1 - wch) * (crh + dcr) + wch * tcr
    out = hd.copy()
    out[..., :3] = np.round(np.clip(D3.rgb(yh * k, cb2, cr2), 0, 255)).astype(np.uint8)
    out[out[..., 3] == 0, :3] = 0
    op = hd[..., 3] > 0
    return out, {"classes": int(n), "regions": int(len(np.unique(grp))),
                 "classes_without_hd_px": int((npx == 0).sum()),
                 "hd_px_without_place": int((~have & op).sum()),
                 "region_boundary_px": int((region & op).sum()),
                 "mixed_px": int(((wgt.max(-1) < MIXED_W) & have & op).sum()),
                 "opaque_px": int(op.sum()), "sigma_chroma": round(sig_n, 3), "sigma_shade": round(sig_g, 4)}


def derive(hd, ob, ot, declared="recolor", via=None):
    """hd - RGBA uint8 (h*4, w*4) основы, ob и ot - RGBA uint8 (h, w) оригиналов основы и члена.
    Возвращает (вывод или None, цепочка)."""
    if hd.shape[:2] != (ob.shape[0] * 4, ob.shape[1] * 4) or ob.shape != ot.shape:
        raise ValueError("размеры: hd %s, основа %s, член %s" % (hd.shape, ob.shape, ot.shape))
    g, ev = D3.resolve_geometry(ob, ot, declared)
    chain = {"version": VERSION, "stage_a": D3.VERSION, "source": "base", "via": via, "geometry_transform": g,
             "geometry_resolution": ev, "target": "member", "declared_route": declared}
    if g is None:
        chain.update(status="REFUSED", color_transform=None)
        return None, chain
    chain["declared_overridden"] = (g == "MIRROR_X") != (declared == "mirror")
    out, tinfo = transfer(D3.geo(hd, g), D3.geo(ob, g), ot)
    chain.update(status="DERIVED", color_transform=COLOR_TRANSFORM, transfer=tinfo)
    return out, chain
