"""DERIVE_RECOLOR_BASE_V1 - безопасная производная картинка члена семейства: Stage A (derive_recolor_v3) без
изменений плюс чистый INTERPOLATED_MAP - перенос цвета V3.1 с интерполяционными долями мест следа, БЕЗ unmix,
БЕЗ ASL, БЕЗ отбора ID/ST/CY.

Решение: специалист 03.10, передал Vitali в чате - universal unmix, ASL и ID/ST/CY eligibility REJECTED;
перекраска и восстановление фактуры разведены: DERIVE_RECOLOR_BASE отвечает за геометрию, общую семантику
перекраски, альфу и силуэт, отсутствие новых пятен и утечки через границы, детерминизм; фактура - будущий
необязательный TEXTURE_TRANSFER. Новых параметров нет.

Перенос. Для HD-пикселя - четыре места билинейного следа на сетке оригинала (как в V3.1), одинаковые классы
слиты, доли нормированы на сумму: w = PR / sum PR. Эффективные цвета основы и члена - w-среднее YCbCr классов
мест, дальше прежняя формула V3.1: Y * (Yt+2)/(Yb+2), сдвиг цветности с плавным переходом к цветности члена
(CHROMA_W0, CHROMA_W1 из V3). Это ровно вариант PRIOR стендов V3.2_DEV/DEV3 и V3.3_DEV. Альфа HD-основы не
меняется (после преобразования геометрии).

Только numpy, без модели и видеокарты. derive(hd, ob, ot, declared, via=None) -> (RGBA uint8 или None, цепочка).
Модуль ничего не пишет на диск.
"""
import numpy as np

import derive_recolor_v3 as D3
import derive_recolor_v31 as D31

VERSION = "derive-recolor-base-v1-interpolated-prior-2026-10-03.1"
COLOR_TRANSFORM = "RECOLOR_BASE_INTERPOLATED_PRIOR_V1"


def weights(ob_o, ot, H, W):
    """Классы, их цвета и интерполяционные доли мест следа: (Cc, w, valid, pb, pt, n)."""
    m = (ob_o[..., 3] > 0) & (ot[..., 3] > 0)
    h, w = m.shape
    cls, bcode, pb, pt = D31.classes(ob_o, ot, m)
    idx = D3._spread_index(m)
    cls_flat = cls.reshape(-1)
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
    for i, j in ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)):
        same = (C[..., i] >= 0) & (C[..., i] == C[..., j])
        PR[..., i] = np.where(same, PR[..., i] + PR[..., j], PR[..., i])
        C[..., j] = np.where(same, -1, C[..., j])
        PR[..., j] = np.where(same, 0.0, PR[..., j])
    valid = C >= 0
    wgt = PR / np.maximum(PR.sum(-1, keepdims=True), 1e-300)
    return np.maximum(C, 0), wgt, valid, pb, pt, len(bcode)


def transfer(hd, ob_o, ot):
    """hd - RGBA x4 в ориентации цепочки, ob_o - оригинал основы в ней же, ot - оригинал члена."""
    H, W = hd.shape[:2]
    Cc, wgt, valid, pb, pt, n = weights(ob_o, ot, H, W)
    hcol = np.stack(D3.ycc(hd[..., :3].astype(np.float64)), -1)
    have = valid.any(-1)
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
    return out, {"classes": int(n), "hd_px_without_place": int((~have & op).sum()),
                 "mixed_px": int(((wgt.max(-1) < D31.MIXED_W) & have & op).sum()), "opaque_px": int(op.sum())}


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
