#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Диагностика ответа на HANDOB Томпсона 1642: геометрия целого предмета и зелёная кайма. Без модели.

1. Четыре точки ответа - дуло, конец приклада, основная и передняя рукояти - против целей пробы (plan.json,
   target_zones_rev2.json). Подбирается одно подобие всего предмета: равномерный масштаб, поворот, перенос
   (комплексный МНК z' = a z + b). Остаток каждой точки после подобия отвечает на вопрос: согласуются ли точки
   с целями постановкой целого предмета (остатки малы) или модель изменила пропорции и ракурс (остатки велики).
   Части отдельно не двигаются, по одной оси не тянется ничего, силуэтом оригинала не режется. Наложение -
   только диагностика, не кадр.
   Точки ответа: дуло и приклад - центр полосы глубиной 1 пиксель базы у крайних точек оси (центр крайнего
   пикселя оригинала стоит так же, в 0.5 от края); рукояти - центры деревянных частей под стволом.
   Цели: дуло - центр пикселя muzzle_x4, приклад - butt_base, основная - центр зоны grip, передняя - центр
   зоны support редакции 2.
2. Зелёная кайма: зелень в непрозрачном теле (внутри силуэта на глубине больше 3 пикселей холста) отдельно от
   края. Край раскладывается как смесь C = a F + (1 - a) B (B - фон ответа, F - цвет ближайшего тела): малый
   остаток - это обычная полупрозрачная кромка, и зелень на ней - загрязнение фоном при его снятии (вопрос
   обработки); большой остаток с лишним зелёным - зелень, нарисованная моделью.

    py -3.13 tools/hdart/handob_fit4.py
Выход: art/items/weapons100-v1/grip_pilot/tommy1642/fit4/ (fit4.json, overlay.png, rim.png).
"""
import json
import math
import os
import sys
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

import numpy as np                              # noqa: E402
from PIL import Image, ImageDraw, ImageFont     # noqa: E402

ENC = "utf-8-sig"
PILOT = "art/items/weapons100-v1/grip_pilot"
SRC = os.path.join(PILOT, "tommy1642")
OUT = os.path.join(SRC, "fit4")
REV2 = os.path.join(PILOT, "target_zones_rev2.json")
KEY = "STR_TOMMYGUN.1642"
NAMES = ("muzzle", "butt", "grip", "front")
RU = {"muzzle": "дуло", "butt": "приклад", "grip": "основная", "front": "передняя"}
ERODE = 3                                       # глубина края в пикселях холста 1024


def box_center(b):
    return ((b[0] + b[2] + 1) / 8.0, (b[1] + b[3] + 1) / 8.0)


def targets():
    with open(os.path.join(SRC, "plan.json"), encoding=ENC) as f:
        plan = json.load(f)
    with open(REV2, encoding=ENC) as f:
        rev = json.load(f)["frames"][KEY]
    t = plan["targets_x4"]
    return {"muzzle": ((t["muzzle"][0] // 4) + 0.5, (t["muzzle"][1] // 4) + 0.5),
            "butt": tuple(plan["butt_base"]),
            "grip": box_center(t["grip"]),
            "front": box_center(rev["support"][0])}, plan, {"grip": t["grip"], "front": rev["support"][0]}


def background(rgb):
    e = np.concatenate([rgb[:40].reshape(-1, 3), rgb[-40:].reshape(-1, 3),
                        rgb[:, :40].reshape(-1, 3), rgb[:, -40:].reshape(-1, 3)])
    bg = np.median(e, axis=0)
    return bg, float(np.median(np.abs(e - bg).sum(1)))


def erode(m, r):
    for _ in range(r):
        n = m.copy()
        n[1:] &= m[:-1]
        n[:-1] &= m[1:]
        n[:, 1:] &= m[:, :-1]
        n[:, :-1] &= m[:, 1:]
        n[0] = n[-1] = False
        n[:, 0] = n[:, -1] = False
        m = n
    return m


def components(m):
    """Связные части маски (4-связность) -> список массивов индексов (ys, xs)."""
    lab = np.zeros(m.shape, np.int32)
    out, h, w = [], m.shape[0], m.shape[1]
    for y0, x0 in zip(*np.nonzero(m)):
        if lab[y0, x0]:
            continue
        k = len(out) + 1
        q, ys, xs = deque([(y0, x0)]), [], []
        lab[y0, x0] = k
        while q:
            y, x = q.popleft()
            ys.append(y)
            xs.append(x)
            for yy, xx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= yy < h and 0 <= xx < w and m[yy, xx] and not lab[yy, xx]:
                    lab[yy, xx] = k
                    q.append((yy, xx))
        out.append((np.array(ys), np.array(xs)))
    return out


def answer_points(rgb, bg, s, pad, tg):
    """Точки ответа в пикселях базы. s - пикселей холста на пиксель базы, pad - поле сверху."""
    fg = np.abs(rgb - bg).sum(2) > 60
    ys, xs = np.nonzero(fg)
    bx, by = (xs + 0.5) / s, (ys + 0.5 - pad) / s
    ax = np.array(tg["muzzle"]) - np.array(tg["butt"])
    ax = ax / np.hypot(*ax)
    pr = bx * ax[0] + by * ax[1]
    pts, rep = {}, {}
    for name, sel in (("muzzle", pr >= pr.max() - 1.0), ("butt", pr <= pr.min() + 1.0)):
        pts[name] = (float(bx[sel].mean()), float(by[sel].mean()))
    # дерево: красно-бурое, отдельно от фона; части ищутся на холсте /4
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    wood = fg & (r > g + 30) & (r > b + 40)
    small = wood[::4, ::4]
    comps = [c for c in components(small) if len(c[0]) * 16 > 0.004 * fg.sum()]
    parts = []
    for cy, cx in comps:
        px, py = (cx * 4 + 2) / s, (cy * 4 + 2 - pad) / s
        parts.append({"x": float(px.mean()), "y": float(py.mean()), "n": int(len(cx) * 16),
                      "along": float(((px.mean() - tg["butt"][0]) * ax[0] + (py.mean() - tg["butt"][1]) * ax[1])),
                      "box": [float(px.min()), float(py.min()), float(px.max()), float(py.max())]})
    rep["wood_parts"] = parts
    if len(parts) < 3:
        raise SystemExit("деревянных частей %d, ждал 3 (приклад, основная, передняя)" % len(parts))
    parts = sorted(parts, key=lambda p: -p["n"])[:3]
    stock = min(parts, key=lambda p: p["along"])            # ближе всех к прикладу
    rest = sorted([p for p in parts if p is not stock], key=lambda p: p["along"])
    pts["grip"], pts["front"] = (rest[0]["x"], rest[0]["y"]), (rest[1]["x"], rest[1]["y"])
    rep["stock_part"] = stock
    return pts, rep, fg


def similarity(src, dst, rotate=True):
    z = np.array([complex(*src[n]) for n in NAMES])
    w = np.array([complex(*dst[n]) for n in NAMES])
    mz, mw = z.mean(), w.mean()
    if rotate:
        a = ((w - mw) * np.conj(z - mz)).sum() / (np.abs(z - mz) ** 2).sum()
    else:
        a = complex(((w - mw) * np.conj(z - mz)).sum().real / (np.abs(z - mz) ** 2).sum(), 0)
    b = mw - a * mz
    fit = a * z + b
    res = {n: round(float(abs(fit[i] - w[i])), 2) for i, n in enumerate(NAMES)}
    vec = {n: [round(float((w[i] - fit[i]).real), 2), round(float((w[i] - fit[i]).imag), 2)] for i, n in enumerate(NAMES)}
    return a, b, res, vec, float(np.sqrt(np.mean(np.abs(fit - w) ** 2)))


def along_axis(pts):
    """Положение рукоятей вдоль оси дуло -> приклад (доля длины) и отступ от оси (доля длины)."""
    m, bt = np.array(pts["muzzle"]), np.array(pts["butt"])
    ax = bt - m
    L = float(np.hypot(*ax))
    u = ax / L
    out = {"length": round(L, 2), "angle_deg": round(math.degrees(math.atan2(-ax[1], -ax[0])), 1)}
    for n in ("grip", "front"):
        d = np.array(pts[n]) - m
        out[n] = [round(float(d @ u) / L, 3), round(float(d[0] * u[1] - d[1] * u[0]) / L, 3)]
    return out


def rim_analysis(rgb, bg, fg):
    inner = erode(fg, ERODE)
    rim = fg & ~inner
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    tinted = (g > r + 30) & (g > b + 30)
    # F: цвет ближайшего тела - распространение цветов внутренней части наружу на ERODE + 2 шагов
    F = np.where(inner[..., None], rgb, 0.0)
    known = inner.copy()
    for _ in range(ERODE + 3):
        acc = np.zeros_like(F)
        cnt = np.zeros(known.shape, np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            sk = np.roll(known, (dy, dx), (0, 1))
            acc += np.roll(F, (dy, dx), (0, 1)) * sk[..., None]
            cnt += sk
        new = ~known & (cnt > 0)
        F[new] = acc[new] / cnt[new][:, None]
        known |= new
    sel = rim & known
    C, Fv = rgb[sel], F[sel]
    d = Fv - bg
    a = np.clip(((C - bg) * d).sum(1) / np.maximum((d * d).sum(1), 1.0), 0, 1)
    rec = a[:, None] * Fv + (1 - a[:, None]) * bg
    resid = np.sqrt(((C - rec) ** 2).sum(1))
    extra_g = (C[:, 1] - rec[:, 1]) - 0.5 * ((C[:, 0] - rec[:, 0]) + (C[:, 2] - rec[:, 2]))
    tint_rim = tinted[sel]
    painted = tint_rim & (resid >= 25) & (extra_g > 15)
    blend = tint_rim & ~painted
    dec = (C - (1 - a[:, None]) * bg) / np.maximum(a[:, None], 0.15)
    tint_dec = (dec[:, 1] > dec[:, 0] + 30) & (dec[:, 1] > dec[:, 2] + 30)
    return {"bg": [round(float(v), 1) for v in bg],
            "body_px": int(inner.sum()), "body_green_share": round(float((inner & tinted).sum()) / max(1, int(inner.sum())), 4),
            "rim_px": int(rim.sum()), "rim_green_share": round(float((rim & tinted).sum()) / max(1, int(rim.sum())), 3),
            "rim_green_blend_share": round(float(blend.sum()) / max(1, len(C)), 3),
            "rim_green_painted_share": round(float(painted.sum()) / max(1, len(C)), 4),
            "rim_resid_median": round(float(np.median(resid)), 1),
            "rim_alpha_median": round(float(np.median(a)), 2),
            "rim_green_after_unmix_share": round(float((tint_dec & (a > 0.15)).sum()) / max(1, int((a > 0.15).sum())), 4)}, \
        (sel, a, dec, painted, blend)


def hd_rim(path):
    """Итог 128x160 из check: зелень в непрозрачном и в полупрозрачном (RGB уменьшен вместе с фоном)."""
    h = np.asarray(Image.open(path).convert("RGBA")).astype(float)
    al = h[..., 3] / 255.0
    r, g, b = h[..., 0], h[..., 1], h[..., 2]
    t = (g > r + 30) & (g > b + 30)
    op, semi = al > 0.95, (al > 0.05) & (al <= 0.95)
    return {"opaque_px": int(op.sum()), "opaque_green_share": round(float((op & t).sum()) / max(1, int(op.sum())), 4),
            "semi_px": int(semi.sum()), "semi_green_share": round(float((semi & t).sum()) / max(1, int(semi.sum())), 3)}


def overlay(classic, raw, s, pad, a, pts, tg, title, font):
    """Ответ, поставленный найденным подобием, поверх оригинала x16 (диагностика)."""
    K = 16
    W, H = 32 * K, 40 * K
    base = Image.fromarray(classic).resize((W, H), Image.NEAREST).convert("RGBA")
    # база -> ответ: z = (w - b)/a; пиксель листа (X, Y) -> база (X/K, Y/K) -> холст ответа (s * z, s * z + pad)
    ai = 1 / a[0]
    bb = a[1]
    m = [ai.real * s / K, -ai.imag * s / K, 0, ai.imag * s / K, ai.real * s / K, 0]
    c0 = -ai * bb
    m[2] = (c0.real * s)
    m[5] = (c0.imag * s + pad)
    rgba = raw.convert("RGBA")
    arr = np.asarray(rgba).copy()
    bgc, _ = background(arr[..., :3].astype(float))
    fg = np.abs(arr[..., :3].astype(float) - bgc).sum(2) > 60
    arr[..., 3] = np.where(fg, 150, 0)
    warped = Image.fromarray(arr).transform((W, H), Image.AFFINE, m, Image.BILINEAR)
    out = Image.alpha_composite(base, warped)
    dr = ImageDraw.Draw(out)
    fit = lambda p: a[0] * complex(*p) + a[1]
    for n, col in (("muzzle", (255, 0, 210)), ("butt", (255, 255, 255)), ("grip", (0, 230, 255)), ("front", (255, 230, 0))):
        tx, ty = tg[n][0] * K, tg[n][1] * K
        f = fit(pts[n])
        fx, fy = f.real * K, f.imag * K
        dr.ellipse([tx - 5, ty - 5, tx + 5, ty + 5], outline=col, width=2)
        dr.line([fx - 4, fy - 4, fx + 4, fy + 4], fill=col, width=2)
        dr.line([fx - 4, fy + 4, fx + 4, fy - 4], fill=col, width=2)
        dr.line([tx, ty, fx, fy], fill=col, width=1)
    sheet = Image.new("RGB", (W, H + 22), (20, 22, 28))
    sheet.paste(out.convert("RGB"), (0, 22))
    ImageDraw.Draw(sheet).text((4, 3), title, fill=(235, 235, 235), font=font)
    return sheet


def raw_marks(raw, pts, s, pad, font, title):
    im = raw.convert("RGB").resize((raw.width // 2, raw.height // 2), Image.LANCZOS)
    dr = ImageDraw.Draw(im)
    for n, col in (("muzzle", (255, 0, 210)), ("butt", (255, 255, 255)), ("grip", (0, 230, 255)), ("front", (255, 230, 0))):
        x, y = pts[n][0] * s / 2, (pts[n][1] * s + pad) / 2
        dr.ellipse([x - 7, y - 7, x + 7, y + 7], outline=col, width=3)
    sheet = Image.new("RGB", (im.width, im.height + 22), (20, 22, 28))
    sheet.paste(im, (0, 22))
    ImageDraw.Draw(sheet).text((4, 3), title, fill=(235, 235, 235), font=font)
    return sheet


def rim_sheet(rgb, fg, parts, title, font, crop):
    sel, a, dec, painted, blend = parts
    x0, y0, x1, y1 = crop
    vis = np.zeros(rgb.shape, np.uint8) + 40
    vis[fg] = (rgb[fg] * 0.5).astype(np.uint8)
    ys, xs = np.nonzero(sel)
    col = np.zeros((len(ys), 3), np.uint8) + 90
    col[blend] = (255, 170, 0)
    col[painted] = (255, 0, 0)
    vis[ys, xs] = col
    im = Image.fromarray(vis[y0:y1, x0:x1])
    sheet = Image.new("RGB", (im.width, im.height + 22), (20, 22, 28))
    sheet.paste(im, (0, 22))
    ImageDraw.Draw(sheet).text((4, 3), title, fill=(235, 235, 235), font=font)
    return sheet


def one(name, raw_path, s, pad, hd_path, tg, zones, classic, font):
    raw = Image.open(raw_path)
    rgb = np.asarray(raw.convert("RGB")).astype(float)
    bg, spread = background(rgb)
    pts, rep, fg = answer_points(rgb, bg, s, pad, tg)
    out = {"raw": raw_path.replace("\\", "/"), "raw_size": list(raw.size), "canvas_px_per_base": s, "pad_top": pad,
           "bg": [round(float(v), 1) for v in bg], "bg_spread": spread,
           "points_answer_base": {n: [round(p[0], 2), round(p[1], 2)] for n, p in pts.items()}, "parts": rep}
    for key, rot in (("similarity", True), ("scale_shift_no_rotation", False)):
        a, b, res, vec, rms = similarity(pts, tg, rot)
        out[key] = {"scale": round(abs(a), 4), "rotation_deg": round(math.degrees(math.atan2(a.imag, a.real)), 2),
                    "shift_base": [round(b.real, 2), round(b.imag, 2)], "residual_base": res,
                    "residual_vec_base": vec, "rms_base": round(rms, 2),
                    "max_residual_base": max(res.values())}
        if rot:
            fit_ab = (a, b)
            # попадает ли поставленная точка рукояти в свою зону кисти (зоны - пиксели x4, здесь в базе)
            ins = {}
            for n in ("grip", "front"):
                zb = zones[n]
                f = a * complex(*pts[n]) + b
                ins[n] = bool(zb[0] / 4.0 <= f.real <= (zb[2] + 1) / 4.0 and zb[1] / 4.0 <= f.imag <= (zb[3] + 1) / 4.0)
            out[key]["placed_inside_zone"] = ins
    out["answer_axis"] = along_axis(pts)
    out["target_axis"] = along_axis(tg)
    rim, rparts = rim_analysis(rgb, bg, fg)
    out["rim"] = rim
    out["hd_rim"] = hd_rim(hd_path)
    sim = out["similarity"]
    ov = overlay(classic, raw, s, pad, fit_ab, pts, tg,
                 "%s: подобие x%.3f, поворот %+.1f°, ост. макс %.2f" % (name, sim["scale"], sim["rotation_deg"],
                                                                      sim["max_residual_base"]), font)
    rm = raw_marks(raw, pts, s, pad, font, "%s: найденные точки в сыром ответе" % name)
    ys, xs = np.nonzero(fg)
    crop = (max(0, xs.min() - 20), max(0, ys.min() - 20), min(rgb.shape[1], xs.max() + 20), min(rgb.shape[0], ys.max() + 20))
    rs = rim_sheet(rgb, fg, rparts, "%s: край - оранжевый смесь с фоном, красный зелень модели" % name, font, crop)
    return out, ov, rm, rs


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.chdir(ROOT)
    import grip_matrix as gm
    tg, plan, zones = targets()
    idx = gm.hob(1642)
    classic = gm.hpal[idx].astype(np.uint8)
    classic[idx == 0] = (58, 60, 66)
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 15)
    with open(os.path.join(SRC, "q21", "run.json"), encoding=ENC) as f:
        q21 = json.load(f)
    runs = [r for r in plan["runs"] if r.get("raw")]
    cases = [("Codex", runs[-1]["raw"], 32, 128, os.path.join(SRC, "hd", "1642.png")),
             ("Qwen-2.1", q21["raw"], 26, 104, os.path.join(SRC, "q21", "hd", "1642.png"))]
    os.makedirs(OUT, exist_ok=True)
    rep = {"targets_base": {n: [round(v[0], 2), round(v[1], 2)] for n, v in tg.items()},
           "note": "наложение - диагностика, не кадр; части не двигались, растяжки по оси нет",
           "muzzle_tolerance_base": 0.5}
    ovs, rms, rss = [], [], []
    for name, raw, s, pad, hd in cases:
        r, ov, rm, rs = one(name, raw, s, pad, hd, tg, zones, classic, font)
        rep[name] = r
        ovs.append(ov)
        rms.append(rm)
        rss.append(rs)
        sim = r["similarity"]
        print("%-9s подобие: масштаб %.3f, поворот %+.1f°, остатки %s, rms %.2f" % (
            name, sim["scale"], sim["rotation_deg"], sim["residual_base"], sim["rms_base"]))
        print("          точки рукоятей в своих зонах после подобия: %s" % sim["placed_inside_zone"])
        print("          без поворота: остатки %s" % r["scale_shift_no_rotation"]["residual_base"])
        print("          ось ответа %s | ось цели %s" % (r["answer_axis"], r["target_axis"]))
        print("          кайма %s | итог %s" % (r["rim"], r["hd_rim"]))
    with open(os.path.join(OUT, "fit4.json"), "w", encoding=ENC) as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    gap = 10
    W = sum(i.width for i in rms + ovs) + gap * 5
    H = max(i.height for i in rms + ovs)
    sheet = Image.new("RGB", (W, H + 40), (20, 22, 28))
    x = gap
    for i in (rms[0], ovs[0], rms[1], ovs[1]):
        sheet.paste(i, (x, 0))
        x += i.width + gap
    ImageDraw.Draw(sheet).text((gap, H + 12), "кружок - цель, крест - точка ответа после одного подобия всего предмета; "
                               "лиловый дуло, белый приклад, голубой основная, жёлтый передняя. Диагностика, не кадр",
                               fill=(200, 200, 200), font=font)
    sheet.save(os.path.join(OUT, "overlay.png"))
    W = sum(i.width for i in rss) + gap * 3
    H = max(i.height for i in rss)
    sheet = Image.new("RGB", (W, H), (20, 22, 28))
    x = gap
    for i in rss:
        sheet.paste(i, (x, 0))
        x += i.width + gap
    sheet.save(os.path.join(OUT, "rim.png"))
    print("лист:", os.path.join(OUT, "overlay.png"), os.path.join(OUT, "rim.png"))


if __name__ == "__main__":
    main()
