"""DERIVE_RECOLOR_V3.2 - детерминированный вывод HD-кадра члена семейства: Stage A из V3 без изменений, Stage B
INTERPOLATED_MAP_V1 (derive_recolor_v31) плюс ADAPTIVE_SHIFT_LIMITED_UNMIX (ASL), c = 0.75.

Решение: специалист 03.10, передал Vitali в чате - DEV3 PASS, выбран ASL c = 0.75 по правилу dev_spec_v3.json
(sha256 2d12803373941b93c31d66b31a68c83cbd31ff0dbc56e05c2fe1cea71c70d6de), V3.2 freeze разрешён. c после
заморозки не меняется ни по регрессии, ни по подтверждению. Отвергнуты: регуляризация соседями, глобальные GN и
TCr; PRIOR и V3.1 - только базы сравнения.

Stage B. Веса unmix INTERPOLATED_MAP_V1 (w_unmix) считаются ровно как в derive_recolor_v31.transfer. Доля -
интерполяционная доля мест следа (билинейные доли, нормированные на сумму внутри следа). Между областями
w_unmix - доля = 0, поэтому ограничение трогает только разложение внутри области. Для каждого HD-пикселя:
  dw = w_unmix - доля;
  S = sum_{i: dw_i > 0, j: dw_j < 0} dw_i |dw_j| ||(B_i - B_j) * scale|| / sum dw_i |dw_j| - расхождение
      классов основы, между которыми unmix переносит вес, в единицах шума unmix (scale: яркость
      1/sqrt(sig_n^2 + (sig_g Y)^2), цветность 1/sig_n - те же, что у unmix);
  D = max(|d ln k| / 0.15, |d (cb, cr)| / 8) - сдвиг переноса (ln((Yt+2)/(Yb+2)), dcb, dcr) при весах unmix
      против доли, в порогах ворот V2 (ART_LN, ART_AB);
  lambda = min(1, c S / D) (D = 0 или пиксель без мест - lambda 1); w = доля + lambda dw.
Дальше прежняя формула переноса V3.1 с весами w. Альфа HD-основы не меняется (после преобразования геометрии).

Только numpy, без модели и видеокарты. Вызов: derive(hd, ob, ot, declared, via=None) -> (RGBA uint8 или
None, цепочка). Модуль ничего не пишет на диск.
"""
import numpy as np

import derive_recolor_v3 as D3
import derive_recolor_v31 as D31

VERSION = "derive-recolor-v3.2-asl-c0.75-2026-10-03.1"
COLOR_TRANSFORM = "RECOLOR_INTERPOLATED_MAP_V1_ASL"
ASL_C = 0.75             # заморожен: dev_spec_v3.json, выбор DEV3
ASL_TLN = 0.15           # порог ворот V2 по ln-отношению яркости (ART_LN)
ASL_TAB = 8.0            # порог ворот V2 по a/b (ART_AB)


def source_divergence(Rs, dw):
    """S: расхождение классов основы (Rs - опорные цвета в единицах шума unmix), между которыми unmix переносит
    вес, взвешенное dw_i+ |dw_j-|."""
    gain, loss = np.clip(dw, 0, None), np.clip(-dw, 0, None)
    num = np.zeros(dw.shape[:-1])
    den = np.zeros(dw.shape[:-1])
    for i in range(4):
        for j in range(4):
            if i == j:
                continue
            p = gain[..., i] * loss[..., j]
            num += p * np.linalg.norm(Rs[..., i, :] - Rs[..., j, :], axis=-1)
            den += p
    return np.where(den > 0, num / np.maximum(den, 1e-300), 0.0)


def shift(pb, pt, Cc, w):
    """Перенос при весах w: ln((Yt+2)/(Yb+2)), dcb, dcr."""
    beff = (w[..., None] * pb[Cc]).sum(-2)
    teff = (w[..., None] * pt[Cc]).sum(-2)
    return np.log((teff[..., 0] + 2.0) / (beff[..., 0] + 2.0)), teff[..., 1] - beff[..., 1], teff[..., 2] - beff[..., 2]


def asl(wgt, PR, valid, Rs, pb, pt, Cc, c=ASL_C):
    """ADAPTIVE_SHIFT_LIMITED_UNMIX: веса и число пикселей с lambda < 1."""
    pri = PR / np.maximum(PR.sum(-1, keepdims=True), 1e-300)
    dw = wgt - pri
    S = source_divergence(Rs, dw)
    l1, b1, c1 = shift(pb, pt, Cc, wgt)
    l0, b0, c0 = shift(pb, pt, Cc, pri)
    D = np.maximum(np.abs(l1 - l0) / ASL_TLN, np.hypot(b1 - b0, c1 - c0) / ASL_TAB)
    with np.errstate(divide="ignore", invalid="ignore"):
        lam = np.where(D > 0, np.minimum(1.0, c * S / D), 1.0)
    lam = np.where(valid.any(-1), lam, 1.0)
    return pri + lam[..., None] * dw, int((lam < 1 - 1e-12).sum())


def transfer(hd, ob_o, ot):
    """hd - RGBA x4 в ориентации цепочки, ob_o - оригинал основы в ней же, ot - оригинал члена. Веса unmix -
    как derive_recolor_v31.transfer (тот же код), затем ASL."""
    b = ob_o
    m = (b[..., 3] > 0) & (ot[..., 3] > 0)
    h, w = m.shape
    cls, bcode, pb, pt = D31.classes(ob_o, ot, m)
    n = len(bcode)
    sn, sg, npx = D31.class_spread(hd, cls, n)
    sig_n = max(D31.SIGMA_MIN, float(np.nanmedian(sn))) if np.isfinite(sn).any() else D31.SIGMA_FALLBACK
    sig_g = max(D31.SHADE_MIN, float(np.nanmedian(sg))) if np.isfinite(sg).any() else D31.SHADE_FALLBACK
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
    for i, j in slots:
        same = (C[..., i] >= 0) & (C[..., i] == C[..., j])
        PR[..., i] = np.where(same, PR[..., i] + PR[..., j], PR[..., i])
        C[..., j] = np.where(same, -1, C[..., j])
        PR[..., j] = np.where(same, 0.0, PR[..., j])
    valid = C >= 0
    Cc = np.maximum(C, 0)
    hcol = np.stack(D3.ycc(hd[..., :3].astype(np.float64)), -1)
    have = valid.any(-1)
    scale = np.stack([1.0 / np.sqrt(sig_n ** 2 + (sig_g * hcol[..., 0]) ** 2),
                      np.full(hcol.shape[:-1], 1.0 / sig_n), np.full(hcol.shape[:-1], 1.0 / sig_n)], -1)
    hs, Rs = hcol * scale, pb[Cc] * scale[..., None, :]
    grp = D31.regions(cls, bcode, n)
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
        w_r = D31.unmix(hs, Rs, pri, inr, D31.PRIOR_W)
        wgt += (mass / tot)[..., None] * w_r
    wgt, clamped = asl(wgt, PR, valid, Rs, pb, pt, Cc)
    beff = (wgt[..., None] * pb[Cc]).sum(-2)
    teff = (wgt[..., None] * pt[Cc]).sum(-2)
    yb, cbb, crb = beff[..., 0], beff[..., 1], beff[..., 2]
    yt, cbt, crt = teff[..., 0], teff[..., 1], teff[..., 2]
    yh, cbh, crh = hcol[..., 0], hcol[..., 1], hcol[..., 2]
    k = np.where(have, (yt + 2.0) / (yb + 2.0), 1.0)
    dcb, dcr = np.where(have, cbt - cbb, 0.0), np.where(have, crt - crb, 0.0)
    wch = np.where(have, np.clip((np.hypot(dcb, dcr) - D31.CHROMA_W0) / D31.CHROMA_W1, 0.0, 1.0), 0.0)
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
                 "mixed_px": int(((wgt.max(-1) < D31.MIXED_W) & have & op).sum()),
                 "asl_limited_px": int(clamped),
                 "opaque_px": int(op.sum()), "sigma_chroma": round(sig_n, 3), "sigma_shade": round(sig_g, 4)}


def derive(hd, ob, ot, declared="recolor", via=None):
    """hd - RGBA uint8 (h*4, w*4) основы, ob и ot - RGBA uint8 (h, w) оригиналов основы и члена.
    Возвращает (вывод или None, цепочка)."""
    if hd.shape[:2] != (ob.shape[0] * 4, ob.shape[1] * 4) or ob.shape != ot.shape:
        raise ValueError("размеры: hd %s, основа %s, член %s" % (hd.shape, ob.shape, ot.shape))
    g, ev = D3.resolve_geometry(ob, ot, declared)
    chain = {"version": VERSION, "stage_a": D3.VERSION, "stage_b_base": D31.VERSION, "source": "base", "via": via,
             "geometry_transform": g, "geometry_resolution": ev, "target": "member", "declared_route": declared}
    if g is None:
        chain.update(status="REFUSED", color_transform=None)
        return None, chain
    chain["declared_overridden"] = (g == "MIRROR_X") != (declared == "mirror")
    out, tinfo = transfer(D3.geo(hd, g), D3.geo(ob, g), ot)
    chain.update(status="DERIVED", color_transform=COLOR_TRANSFORM, asl_c=ASL_C, transfer=tinfo)
    return out, chain
