"""Доводка ответа генератора по частям, без генерации (решение специалиста 05.10): замер и операции над слоями частей.

Ответ - RGBA 1024x1536 со своей альфой (Codex image_gen). Сетка база -> ответ одна на предмет: масштаб по длине
предмета (длинная ось габарита оригинала), оба конца длинной оси совпадают, поперёк - центр к центру. Замер - по
строкам и столбцам базы на полном размере, до маски и уменьшения: края тела ответа (альфа > 0.5) против краёв
оригинала, переведённых той же сеткой.

Операция - смещение точек внутри своей области (многоугольник в координатах ответа): сужение или расширение
поперёк оси по профилю (taper), растяжка вдоль оси от точки крепления (stretch), сгиб части у места крепления
(bend), жёсткий перенос заплатки (move). Картинка внутри области берётся обратным отображением, бикубически по
цвету с умножением на альфу; маской края не подгоняются. Проверки каждой операции: вне её области не изменился
ни один пиксель, на границе области по телу смещение меньше 0.5 пикс (нет шва), защищённые многоугольники
(protect) не изменились вовсе. Журнал - <выход>.ops_log.json.

    py -3.13 tools/hdart/weapon_part_fit.py measure --type STR_REVOLVER --answer <png> [--ops <json>] --out <папка>
    py -3.13 tools/hdart/weapon_part_fit.py apply --type STR_REVOLVER --answer <png> --ops <json> --out <png>
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import item_photo as ip  # noqa: E402
import weapon_fit as wf  # noqa: E402

ROOT = "E:/OpenXCom"
ENC = "utf-8-sig"
FONT = "C:/Windows/Fonts/arial.ttf"


def load_rgba(p):
    return np.asarray(Image.open(p).convert("RGBA")).astype(np.float32)


def body_bbox(a, thr=0.5, crumb=200):
    """Габарит тела по альфе без крошек."""
    lab, n = ip.pb.label(a > thr, 8)
    sizes = np.bincount(lab.ravel())
    keep = np.isin(lab, [i for i in range(1, n + 1) if sizes[i] >= crumb])
    ys, xs = np.nonzero(keep)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


class Grid:
    """База (пиксели кадра 32x48, края пикселей) <-> ответ (пиксели картинки)."""

    def __init__(self, box, ab, axis=None):
        bw, bh = box[2] - box[0], box[3] - box[1]
        aw, ah = ab[2] - ab[0], ab[3] - ab[1]
        self.axis = axis or ("y" if bh >= bw else "x")
        if self.axis == "y":
            self.s = bh / float(ah)                      # база на пиксель ответа
            self.oy = box[1] - ab[1] * self.s
            self.ox = (box[0] + box[2]) / 2.0 - (ab[0] + ab[2]) / 2.0 * self.s
        else:
            self.s = bw / float(aw)
            self.ox = box[0] - ab[0] * self.s
            self.oy = (box[1] + box[3]) / 2.0 - (ab[1] + ab[3]) / 2.0 * self.s
        self.box, self.ab = box, ab

    def to_base(self, u, v):
        return self.ox + u * self.s, self.oy + v * self.s

    def to_ans(self, x, y):
        return (x - self.ox) / self.s, (y - self.oy) / self.s

    def json(self):
        return {"axis": self.axis, "base_per_answer_px": self.s, "ox": self.ox, "oy": self.oy,
                "orig_box": list(self.box), "answer_box": list(self.ab)}


def profiles(a, m_o, g):
    """По строкам и столбцам базы: края оригинала и края тела ответа в той же полосе (средняя половина полосы),
    в пикселях базы."""
    m = a > 0.5
    H, W = m_o.shape
    rows, cols = [], []
    for r in range(H):
        xs = np.nonzero(m_o[r])[0]
        if not len(xs):
            continue
        v0, v1 = g.to_ans(0, r + 0.25)[1], g.to_ans(0, r + 0.75)[1]
        band = m[max(0, int(round(v0))):max(0, int(round(v1)))]
        cc = np.nonzero(band.any(0))[0] if band.size else []
        rows.append({"i": r, "o0": int(xs.min()), "o1": int(xs.max()) + 1,
                     "a0": round(g.to_base(cc.min(), 0)[0], 2) if len(cc) else None,
                     "a1": round(g.to_base(cc.max() + 1, 0)[0], 2) if len(cc) else None})
    for c in range(W):
        ys = np.nonzero(m_o[:, c])[0]
        if not len(ys):
            continue
        u0, u1 = g.to_ans(c + 0.25, 0)[0], g.to_ans(c + 0.75, 0)[0]
        band = m[:, max(0, int(round(u0))):max(0, int(round(u1)))]
        rr = np.nonzero(band.any(1))[0] if band.size else []
        cols.append({"i": c, "o0": int(ys.min()), "o1": int(ys.max()) + 1,
                     "a0": round(g.to_base(0, rr.min())[1], 2) if len(rr) else None,
                     "a1": round(g.to_base(0, rr.max() + 1)[1], 2) if len(rr) else None})
    return rows, cols


def iou_base(a, m_o, g, sub=4):
    """Совпадение силуэтов на сетке базы: альфа ответа, усреднённая по пикселю базы (sub x sub отсчётов)."""
    H, W = m_o.shape
    cov = np.zeros((H, W), np.float32)
    for y in range(H):
        for x in range(W):
            us = [g.to_ans(x + (i + 0.5) / sub, 0)[0] for i in range(sub)]
            vs = [g.to_ans(0, y + (j + 0.5) / sub)[1] for j in range(sub)]
            acc = 0.0
            for v in vs:
                for u in us:
                    iu, iv = int(u), int(v)
                    if 0 <= iv < a.shape[0] and 0 <= iu < a.shape[1]:
                        acc += a[iv, iu]
            cov[y, x] = acc / (sub * sub)
    got = cov > 0.5
    return float((got & m_o).sum() / max(1, (got | m_o).sum())), float((m_o & ~got).sum() / max(1, m_o.sum())), \
        float((got & ~m_o).sum() / max(1, m_o.sum())), got


def overlay(rgba, m_o, g, p, parts=None, ops=None, title=""):
    """Ответ на тёмном полу, поверх - контур пикселей оригинала той же сеткой (жёлтый) и области операций."""
    a = rgba[..., 3:4] / 255.0
    bgc = np.asarray((40, 40, 44), np.float32)
    im = Image.fromarray(np.clip(rgba[..., :3] * a + bgc * (1 - a), 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    H, W = m_o.shape
    for y in range(H):
        for x in range(W):
            if not m_o[y, x]:
                continue
            for dx, dy, seg in ((0, -1, ((0, 0), (1, 0))), (0, 1, ((0, 1), (1, 1))),
                                (-1, 0, ((0, 0), (0, 1))), (1, 0, ((1, 0), (1, 1)))):
                yy, xx = y + dy, x + dx
                if 0 <= yy < H and 0 <= xx < W and m_o[yy, xx]:
                    continue
                (p0, p1) = seg
                d.line([g.to_ans(x + p0[0], y + p0[1]), g.to_ans(x + p1[0], y + p1[1])], fill=(255, 220, 0), width=2)
    for op in ops or []:
        d.polygon([tuple(v) for v in op["region"]], outline=(0, 230, 255), width=2)
    for poly in (parts or {}).values():
        d.polygon([tuple(v) for v in poly], outline=(255, 70, 70), width=2)
    b = g.ab
    pad = 40
    im = im.crop((max(0, b[0] - pad), max(0, b[1] - pad), min(im.width, b[2] + pad), min(im.height, b[3] + pad)))
    if title:
        out = Image.new("RGB", (im.width, im.height + 26), (24, 24, 26))
        out.paste(im, (0, 26))
        ImageDraw.Draw(out).text((6, 5), title, fill=(230, 230, 230), font=ImageFont.truetype(FONT, 15))
        im = out
    im.save(p)


def measure(rgba, m_o, axis=None):
    ab = body_bbox(rgba[..., 3] / 255.0)
    g = Grid(wf.bbox(m_o), ab, axis)
    rows, cols = profiles(rgba[..., 3] / 255.0, m_o, g)
    iou, drop, extra, _ = iou_base(rgba[..., 3] / 255.0, m_o, g)
    return g, {"grid": g.json(), "rows": rows, "cols": cols, "iou": round(iou, 4), "drop": round(drop, 4),
               "extra": round(extra, 4)}


def poly_mask(poly, shape):
    im = Image.new("L", (shape[1], shape[0]), 0)
    ImageDraw.Draw(im).polygon([tuple(v) for v in poly], fill=255)
    return np.asarray(im) > 0


def _unit(p0, p1):
    d = np.asarray(p1, float) - np.asarray(p0, float)
    L = float(np.hypot(*d))
    return d / L, L


def _profile(t, pts):
    """Кусочно-линейный профиль [[t, значение], ...] по t (за краями - крайние значения)."""
    ts = [p[0] for p in pts]
    vs = [p[1] for p in pts]
    return np.interp(t, ts, vs)


def _smooth(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def forward1(op, u, v):
    """Прямое отображение операции: точка (u, v) исходной картинки -> куда она попадает.
    taper   - расстояние от опорной линии (через anchor, параллельно оси from->to) умножается на профиль
              scale по доле t вдоль оси: [[t, s], ...]; t считается от from (0) до to (1).
    stretch - вдоль оси from->to: точки дальше from уходят вдоль оси, t' = t * k (from неподвижна).
    bend    - поворот на angle градусов вокруг pivot и сдвиг shift; сила нарастает от 0 на линии через from
              (по умолчанию pivot) до 1 на расстоянии ramp (по умолчанию до to) вдоль оси from->to - переход
              у места крепления плавный, без разрыва.
    move    - жёсткий перенос на shift (заплатка без масштаба; источник обычно answer - картинка до операций)."""
    t = op["type"]
    if t == "move":
        sx, sy = op["shift"]
        return u + sx, v + sy
    p0 = np.asarray(op.get("from", op.get("pivot")), float)
    d, L = _unit(p0, op["to"])
    n = np.array([-d[1], d[0]])
    tt = (u - p0[0]) * d[0] + (v - p0[1]) * d[1]
    if t == "taper":
        a = np.asarray(op.get("anchor", op["from"]), float)
        w = (u - a[0]) * n[0] + (v - a[1]) * n[1]
        s = _profile(tt / L, op["scale"])
        dw = w * (s - 1)
        return u + n[0] * dw, v + n[1] * dw
    if t == "stretch":
        k = float(op["k"])
        dt = np.where(tt > 0, tt * (k - 1), 0.0)
        return u + d[0] * dt, v + d[1] * dt
    if t == "bend":
        g = _smooth(tt / float(op.get("ramp", L)))
        th = np.deg2rad(op.get("angle", 0.0)) * g
        c = np.asarray(op["pivot"], float)
        x, y = u - c[0], v - c[1]
        sx, sy = op.get("shift", [0.0, 0.0])
        return c[0] + x * np.cos(th) - y * np.sin(th) + sx * g, c[1] + x * np.sin(th) + y * np.cos(th) + sy * g
    raise SystemExit("неизвестная операция %s" % t)


def forward(op, u, v):
    """forward1 и ворота: gate - список {from, to}; смещение умножается на плавную долю 0 у линии через from
    до 1 у to (перпендикулярно оси from->to). Так смещение гаснет у второго места крепления части."""
    fu, fv = forward1(op, u, v)
    if op["type"] == "move" or not op.get("gate"):
        return fu, fv
    k = np.ones_like(u)
    for gt in op["gate"]:
        p0 = np.asarray(gt["from"], float)
        d, L = _unit(p0, gt["to"])
        k = k * _smooth(((u - p0[0]) * d[0] + (v - p0[1]) * d[1]) / L)
    return u + (fu - u) * k, v + (fv - v) * k


def backward(op, qu, qv, it=12):
    """Обратное отображение итерацией p = q - (F(p) - p): смещения малы против своего градиента."""
    if op["type"] == "move":
        sx, sy = op["shift"]
        return qu - sx, qv - sy
    pu, pv = qu.copy(), qv.copy()
    for _ in range(it):
        fu, fv = forward(op, pu, pv)
        pu, pv = qu - (fu - pu), qv - (fv - pv)
    fu, fv = forward(op, pu, pv)
    err = float(np.max(np.hypot(fu - qu, fv - qv))) if qu.size else 0.0
    return pu, pv, err


def _keys(x):
    """Ядро бикубики Keys, a = -0.5."""
    x = np.abs(x)
    return np.where(x <= 1, 1.5 * x ** 3 - 2.5 * x ** 2 + 1,
                    np.where(x < 2, -0.5 * x ** 3 + 2.5 * x ** 2 - 4 * x + 2, 0.0))


def sample(rgba, pu, pv):
    """Бикубическая выборка RGBA с умножением на альфу (фон не втекает в кромку); вне картинки - прозрачно."""
    H, W = rgba.shape[:2]
    al = rgba[..., 3:4] / 255.0
    pre = np.concatenate([rgba[..., :3] * al, rgba[..., 3:4]], 2)
    pre = np.pad(pre, ((2, 3), (2, 3), (0, 0)))
    x0 = np.floor(pu).astype(int)
    y0 = np.floor(pv).astype(int)
    fx, fy = pu - x0, pv - y0
    acc = np.zeros(pu.shape + (4,), np.float64)
    for j in range(-1, 3):
        wy = _keys(fy - j)
        yy = np.clip(y0 + j, -2, H + 2) + 2
        for i in range(-1, 3):
            wx = _keys(fx - i)
            xx = np.clip(x0 + i, -2, W + 2) + 2
            acc += (wx * wy)[..., None] * pre[yy, xx]
    A = np.clip(acc[..., 3], 0, 255)
    an = A / 255.0
    rgb = np.where(an[..., None] > 1e-3, np.clip(acc[..., :3] / np.maximum(an, 1e-3)[..., None], 0, 255), 0)
    return np.concatenate([rgb, A[..., None]], -1)


def soft_mask(poly, shape, feather):
    """Вес операции: 1 внутри многоугольника, к его границе спадает до 0 за feather пикселей (только внутрь)."""
    m = poly_mask(poly, shape)
    if feather <= 0:
        return m.astype(np.float32), m
    from PIL import ImageFilter
    b = np.asarray(Image.fromarray((m * 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(feather / 2.0)),
                   np.float32) / 255.0
    return np.where(m, np.clip((b - 0.5) * 2.0, 0, 1), 0).astype(np.float32), m


def boundary(m):
    """Пиксели многоугольника на его границе (сосед снаружи)."""
    e = m.copy()
    e[1:] &= m[:-1]
    e[:-1] &= m[1:]
    e[:, 1:] &= m[:, :-1]
    e[:, :-1] &= m[:, 1:]
    return m & ~e


def visible_diff(a, b):
    """Пиксели, которые выглядят иначе: альфа или цвет с умножением на альфу отличаются больше чем на 0.5.
    Цвет под нулевой альфой не виден и не считается (у ответа там бывает что угодно)."""
    da = np.abs(a[..., 3] - b[..., 3])
    dc = np.abs(a[..., :3] * a[..., 3:4] - b[..., :3] * b[..., 3:4]).max(2) / 255.0
    return (da > 0.5) | (dc > 0.5)


def apply_ops(rgba, ops, protect=None):
    """Операции по порядку. Внутри своего многоугольника region операция ставит картинку, взятую обратным
    отображением (из текущей или, при source=answer, из исходной); вне region ничего не меняется - проверяется.
    На границе region, где есть тело, смещение обязано быть меньше 0.5 пикс (иначе шов) - кроме move, у которого
    граница - растушёвка заплатки. protect - именованные многоугольники, в которых не должен измениться ни один
    пиксель. -> (итог, журнал)."""
    orig = rgba.copy()
    cur = rgba.copy()
    H, W = cur.shape[:2]
    log = []
    union = np.zeros((H, W), bool)
    for k, op in enumerate(ops):
        w, m = soft_mask(op["region"], (H, W), float(op.get("feather", 0)))
        ys, xs = np.nonzero(m)
        qu, qv = xs.astype(np.float64), ys.astype(np.float64)
        r = backward(op, qu, qv)
        pu, pv = r[0], r[1]
        inv_err = r[2] if len(r) > 2 else 0.0
        src = orig if op.get("source") == "answer" else cur
        got = sample(src, pu, pv)
        new = cur.copy()
        ww = w[ys, xs][:, None]
        # смешение по весу: premultiplied, чтобы прозрачное не красило кромку
        ca, ga = cur[ys, xs, 3:4] / 255.0, got[:, 3:4] / 255.0
        a_out = ga * ww + ca * (1 - ww)
        rgb_out = (got[:, :3] * ga * ww + cur[ys, xs, :3] * ca * (1 - ww)) / np.maximum(a_out, 1e-3)
        new[ys, xs, :3] = np.where(a_out > 1e-3, rgb_out, 0)
        new[ys, xs, 3] = a_out[:, 0] * 255.0
        new = np.clip(np.rint(new), 0, 255)
        cur_q = np.clip(np.rint(cur), 0, 255)
        changed = visible_diff(new, cur_q)
        outside = int((changed & ~m).sum())
        # шов: смещение на границе region там, где тело есть до или после
        bd = boundary(m)
        by_, bx_ = np.nonzero(bd)
        sel = (cur[by_, bx_, 3] > 12)
        idx = {(yy, xx): i for i, (yy, xx) in enumerate(zip(ys, xs))}
        bi = [idx[(yy, xx)] for yy, xx in zip(by_[sel], bx_[sel])]
        seam = float(np.max(np.hypot(pu[bi] - qu[bi], pv[bi] - qv[bi]))) if bi else 0.0
        disp = np.hypot(pu - qu, pv - qv)
        cy, cx = np.nonzero(changed)
        e = {"op": k, "name": op.get("name", ""), "type": op["type"], "params": {kk: vv for kk, vv in op.items()
                                                                               if kk not in ("region", "name")},
             "region_px": int(m.sum()), "changed_px": int(changed.sum()),
             "changed_bbox": [int(cx.min()), int(cy.min()), int(cx.max()) + 1, int(cy.max()) + 1] if len(cx) else None,
             "max_displacement_px": round(float(disp.max()) if disp.size else 0.0, 2),
             "seam_displacement_px": round(seam, 3), "inverse_error_px": round(inv_err, 4),
             "changed_outside_region": outside}
        log.append(e)
        assert outside == 0, "операция %d изменила %d пикс вне своей области" % (k, outside)
        if op["type"] != "move":
            assert seam < 0.5, "операция %d: шов %.2f пикс на границе области по телу" % (k, seam)
        union |= m
        cur = new.astype(np.float32)
    total = visible_diff(np.clip(np.rint(cur), 0, 255), np.clip(np.rint(orig), 0, 255))
    raw = np.abs(np.clip(np.rint(cur), 0, 255) - np.clip(np.rint(orig), 0, 255)).max(2) > 0
    summary = {"changed_px": int(total.sum()), "changed_outside_all_regions": int((total & ~union).sum()),
               "bytes_changed_outside_all_regions": int((raw & ~union).sum()), "protect": {}}
    assert summary["changed_outside_all_regions"] == 0 and summary["bytes_changed_outside_all_regions"] == 0
    for nm, poly in (protect or {}).items():
        pm = poly_mask(poly, (H, W))
        summary["protect"][nm] = int((total & pm).sum())
        assert summary["protect"][nm] == 0, "защищённое «%s» изменено: %d пикс" % (nm, summary["protect"][nm])
    return cur, log, summary


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["measure", "apply"])
    ap.add_argument("--type", required=True)
    ap.add_argument("--answer", required=True)
    ap.add_argument("--ops", default="")
    ap.add_argument("--axis", default="", help="длинная ось сетки: x или y (по умолчанию по габариту оригинала)")
    ap.add_argument("--grid", default="", help="measure_<ТИП>.json прежнего замера: та же сетка, а не по новому габариту")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.chdir(ROOT)
    _rgb_o, m_o = wf.original(a.type)
    rgba = load_rgba(a.answer)
    spec = json.load(open(a.ops, encoding=ENC)) if a.ops else {}
    ops, protect = spec.get("ops", []), spec.get("protect", {})
    if a.cmd == "measure":
        os.makedirs(a.out, exist_ok=True)
        g, rep = measure(rgba, m_o, a.axis or None)
        if a.grid:
            gj = json.load(open(a.grid, encoding=ENC))["grid"]
            g.s, g.ox, g.oy, g.axis = gj["base_per_answer_px"], gj["ox"], gj["oy"], gj["axis"]
            rows, cols = profiles(rgba[..., 3] / 255.0, m_o, g)
            iou, drop, extra, _ = iou_base(rgba[..., 3] / 255.0, m_o, g)
            rep.update({"grid": g.json(), "grid_from": a.grid, "rows": rows, "cols": cols, "iou": round(iou, 4),
                        "drop": round(drop, 4), "extra": round(extra, 4)})
        overlay(rgba, m_o, g, os.path.join(a.out, "overlay_%s.png" % a.type), parts=protect, ops=ops,
                title="%s: жёлтый - контур оригинала, IoU %.3f, выпало %.3f, лишнее %.3f" % (
                    a.type, rep["iou"], rep["drop"], rep["extra"]))
        json.dump(rep, open(os.path.join(a.out, "measure_%s.json" % a.type), "w", encoding=ENC), ensure_ascii=False,
                  indent=1)
        print("%s: сетка %s, база на пикс ответа %.5f; IoU %.3f, выпало %.3f, лишнее %.3f" % (
            a.type, g.axis, g.s, rep["iou"], rep["drop"], rep["extra"]))
        for kind, lst in (("строка", rep["rows"]), ("столбец", rep["cols"])):
            for r in lst:
                if r["a0"] is None:
                    print("  %s %2d: оригинал %d..%d, ответа нет" % (kind, r["i"], r["o0"], r["o1"]))
                    continue
                d0, d1 = r["a0"] - r["o0"], r["a1"] - r["o1"]
                flag = "  <<" if max(abs(d0), abs(d1)) >= 0.75 else ""
                print("  %s %2d: оригинал %2d..%2d, ответ %6.2f..%6.2f  (%+.2f, %+.2f)%s" % (
                    kind, r["i"], r["o0"], r["o1"], r["a0"], r["a1"], d0, d1, flag))
        return
    out, log, summary = apply_ops(rgba, ops, protect)
    Image.fromarray(out.astype(np.uint8), "RGBA").save(a.out)
    jl = os.path.splitext(a.out)[0] + ".ops_log.json"
    json.dump({"answer": a.answer, "ops_file": a.ops, "ops": ops, "protect": protect, "log": log,
               "summary": summary}, open(jl, "w", encoding=ENC), ensure_ascii=False, indent=1)
    for e in log:
        print("операция %d %s (%s): область %d пикс, изменено %d, вне области %d, смещение до %.2f, шов %.3f" % (
            e["op"], e["name"], e["type"], e["region_px"], e["changed_px"], e["changed_outside_region"],
            e["max_displacement_px"], e["seam_displacement_px"]))
    print("итого изменено %d пикс, вне всех областей %d; защищено: %s" % (
        summary["changed_px"], summary["changed_outside_all_regions"],
        ", ".join("%s %d" % kv for kv in summary["protect"].items()) or "-"))
    print("записано", a.out, "журнал", jl)


if __name__ == "__main__":
    main()
