"""HANDOB 1642: проверочный кандидат из ответа Codex одним подобием целого предмета (диагностика, не в мод).

Постановка (специалист 07.10): одно равномерное подобие - масштаб, поворот, перенос - из handob_fit4 (fit4.json,
"similarity"), без деформации частей, без растяжки по оси (R-208) и без обрезки силуэтом оригинала.

Порядок:
  1. альфа по фону ответа на полном холсте 1024x1536: тело (глубже ERODE от края) непрозрачно, край - разложение
     C = a*F + (1-a)*B, F - цвет ближайшего тела, B - фон ответа; тёмная сталь далеко от фона и остаётся телом,
     отверстия, где виден фон, прозрачны (R-089);
  2. очистка цвета края от фона ДО уменьшения: dec = (C - (1-a)*B)/a, при малой a и остаточной зелени - F;
  3. подобие и уменьшение в премультиплицированном виде: билинейная выборка на сетке x64 базы (почти 1:1 к холсту
     ответа), затем среднее по блокам 16x16 -> x4 (128x160), деление на альфу в конце.

Проверки: размер против рамки оригинала (±3%), дуло (блок 4x4 базового пикселя, R-242), обе рукояти (центры
деревянных частей кандидата в зонах), зелень в непрозрачном и полупрозрачном, сохранность деталей (тёмная сталь,
отверстия, площадь). Контроль меры: сам оригинал x32 на фоне ответа с тождественным подобием - размер 0/0, дуло 0,
зелени 0; он же со сдвигом на базовый пиксель - дуло 4.

  py -3.13 tools/hdart/handob_cand1642.py
"""
import json
import math
import os
import sys
from collections import deque

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

ENC = "utf-8-sig"
PILOT = "art/items/weapons100-v1/grip_pilot"
SRC = os.path.join(PILOT, "tommy1642")
OUT = os.path.join(SRC, "cand_sim")
S_ANS, PAD_ANS = 32, 128          # холст Codex: 32 пикселя на пиксель базы, поле 128 сверху
ERODE = 3
FG_DIFF = 60                      # порог отличия от фона, как в check и fit4
BAND = 2                          # пиксели вне порога, которые ещё разлагаются (мягкий край)
K_HI = 64                         # промежуточная сетка: пикселей на пиксель базы
TOL_SIZE = 3.0
TOL_MUZZLE_X4 = 2.0
FLOOR = (58, 60, 66)


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


def dilate(m, r):
    for _ in range(r):
        n = m.copy()
        n[1:] |= m[:-1]
        n[:-1] |= m[1:]
        n[:, 1:] |= m[:, :-1]
        n[:, :-1] |= m[:, 1:]
        m = n
    return m


def components(m):
    """4-связные части маски -> (метки, размеры); метка 0 - фон."""
    lab = np.zeros(m.shape, np.int32)
    sizes = [0]
    h, w = m.shape
    for y0, x0 in zip(*np.nonzero(m)):
        if lab[y0, x0]:
            continue
        k = len(sizes)
        q = deque([(y0, x0)])
        lab[y0, x0] = k
        n = 0
        while q:
            y, x = q.popleft()
            n += 1
            for yy, xx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= yy < h and 0 <= xx < w and m[yy, xx] and not lab[yy, xx]:
                    lab[yy, xx] = k
                    q.append((yy, xx))
        sizes.append(n)
    return lab, np.array(sizes)


def holes(alpha_mask, min_px):
    """Отверстия: связные части прозрачного, не касающиеся края холста, площадью от min_px."""
    lab, sizes = components(~alpha_mask)
    border = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    out = []
    for k in range(1, len(sizes)):
        if k in border or sizes[k] < min_px:
            continue
        ys, xs = np.nonzero(lab == k)
        out.append({"px": int(sizes[k]), "centre": [float(xs.mean()), float(ys.mean())],
                    "box": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]})
    return out


def background(rgb):
    e = np.concatenate([rgb[:40].reshape(-1, 3), rgb[-40:].reshape(-1, 3),
                        rgb[:, :40].reshape(-1, 3), rgb[:, -40:].reshape(-1, 3)])
    return np.median(e, axis=0)


def matte(rgb, bg):
    """Альфа и очищенный цвет на холсте ответа. Возвращает (rgb_clean, alpha, отчёт)."""
    diff = np.abs(rgb - bg).sum(2)
    fg = diff > FG_DIFF
    # шум далеко от предмета: части меньше 0.1% самой большой (на сетке /4, как в fit4_size)
    H4, W4 = fg.shape[0] // 4, fg.shape[1] // 4
    g = fg[:H4 * 4, :W4 * 4].reshape(H4, 4, W4, 4).any((1, 3))
    lab, sizes = components(g)
    big = sizes.max()
    keep_lab = [k for k in range(1, len(sizes)) if sizes[k] >= 0.001 * big]
    keep = np.isin(lab, keep_lab).repeat(4, 0).repeat(4, 1)
    full = np.zeros(fg.shape, bool)
    full[:H4 * 4, :W4 * 4] = keep
    full = dilate(full, 4)
    dropped = int((fg & ~full).sum())
    fg &= full
    inner = erode(fg, ERODE)
    zone = dilate(fg, BAND) & full & ~inner
    # F: цвет ближайшего тела - распространение изнутри наружу
    F = np.where(inner[..., None], rgb, 0.0)
    known = inner.copy()
    for _ in range(ERODE + BAND + 4):
        acc = np.zeros_like(F)
        cnt = np.zeros(known.shape, np.float64)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            sk = np.roll(known, (dy, dx), (0, 1))
            acc += np.roll(F, (dy, dx), (0, 1)) * sk[..., None]
            cnt += sk
        new = ~known & (cnt > 0)
        F[new] = acc[new] / cnt[new][:, None]
        known |= new
    alpha = inner.astype(np.float64)
    out = np.where(inner[..., None], rgb, 0.0)
    sel = zone & known
    C, Fv = rgb[sel], F[sel]
    d = Fv - bg
    a = np.clip(((C - bg) * d).sum(1) / np.maximum((d * d).sum(1), 1.0), 0.0, 1.0)
    # пиксель ровно цвета фона - прозрачный, даже если проекция дала больше нуля
    a[np.abs(C - bg).sum(1) < 12] = 0.0
    dec = (C - (1 - a[:, None]) * bg) / np.maximum(a[:, None], 1e-3)
    dec = np.clip(dec, 0, 255)
    tint = (dec[:, 1] > dec[:, 0] + 30) & (dec[:, 1] > dec[:, 2] + 30)
    weak = a < 0.25
    use_f = tint | weak
    dec[use_f] = Fv[use_f]
    alpha[sel] = a
    out[sel] = dec
    rep = {"bg": [round(float(v), 1) for v in bg], "fg_px": int(fg.sum()), "body_px": int(inner.sum()),
           "edge_px_unmixed": int(sel.sum()), "edge_alpha_median": round(float(np.median(a[a > 0])), 2) if (a > 0).any() else None,
           "edge_colour_from_body_share": round(float(use_f[a > 0].mean()), 3) if (a > 0).any() else None,
           "edge_green_after_unmix_replaced": int((tint & (a > 0)).sum()),
           "stray_px_dropped": dropped}
    return out, alpha, rep


def place(rgb_clean, alpha, a, b, s, pad, out_k=4):
    """Подобие w = a*z + b (z - база ответа, w - база кадра) в премультиплицированном виде -> RGBA float
    (32*out_k)x(40*out_k); out_k=4 - кадр 128x160."""
    W, H = 32 * K_HI, 40 * K_HI
    # пиксель (X, Y) сетки x64 -> база w = ((X+0.5) + i(Y+0.5))/K -> z = (w - b)/a -> холст (s*z.re, s*z.im + pad)
    ai = 1 / a
    c0 = -ai * b
    # координаты холста (центр пикселя на +0.5): u = s*Re(ai*w + c0); PIL AFFINE берёт (x, y) выхода без +0.5
    # и сам сдвигает на центр пикселя, поэтому коэффициенты для центров совпадают с коэффициентами для углов
    m = [ai.real * s / K_HI, -ai.imag * s / K_HI, c0.real * s,
         ai.imag * s / K_HI, ai.real * s / K_HI, c0.imag * s + pad]
    chans = []
    pm = rgb_clean * alpha[..., None]
    for c in range(3):
        chans.append(np.asarray(Image.fromarray(pm[..., c].astype(np.float32), "F").transform(
            (W, H), Image.AFFINE, m, Image.BILINEAR), np.float64))
    al = np.asarray(Image.fromarray(alpha.astype(np.float32), "F").transform((W, H), Image.AFFINE, m, Image.BILINEAR),
                    np.float64)
    f = K_HI // out_k

    def box(x):
        return x.reshape(40 * out_k, f, 32 * out_k, f).mean((1, 3))

    A = box(al)
    P = np.dstack([box(c) for c in chans])
    rgb = np.where(A[..., None] > 1e-4, P / np.maximum(A[..., None], 1e-4), 0)
    return np.dstack([np.clip(rgb, 0, 255), np.clip(A * 255, 0, 255)])


def measures(img, t, butt_base, zones):
    """Размер, дуло, рукояти, зелень итога 128x160 RGBA float."""
    al = img[..., 3] / 255.0
    opq = al > 0.5
    ys, xs = np.nonzero(opq)
    tb = t["bbox"]
    bb = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
    rep = {"bbox_x4": bb, "target_bbox_x4": tb,
           "size_pct": [round(100.0 * ((bb[2] - bb[0] + 1) / (tb[2] - tb[0] + 1) - 1), 1),
                        round(100.0 * ((bb[3] - bb[1] + 1) / (tb[3] - tb[1] + 1) - 1), 1)]}
    rep["size_ok"] = all(abs(v) <= TOL_SIZE for v in rep["size_pct"])
    # дуло: дальний пиксель по оси приклад -> дуло, расстояние до блока 4x4 базового пикселя дула (R-242)
    mx, my = t["muzzle"]
    bx, by = butt_base[0] * 4.0, butt_base[1] * 4.0
    ax, ay = mx + 0.5 - bx, my + 0.5 - by
    k = np.argmax((xs + 0.5) * ax + (ys + 0.5) * ay)
    fx, fy = int(xs[k]), int(ys[k])
    b0x, b0y = (mx // 4) * 4, (my // 4) * 4
    dx = max(b0x - fx, 0, fx - (b0x + 3))
    dy = max(b0y - fy, 0, fy - (b0y + 3))
    rep["far_end_x4"] = [fx, fy]
    rep["muzzle_err_x4"] = round(float(np.hypot(dx, dy)), 2)
    rep["muzzle_ok"] = rep["muzzle_err_x4"] <= TOL_MUZZLE_X4
    # рукояти: деревянные части кандидата (красно-бурое), две ближе к дулу из трёх крупных - основная и передняя
    r, g, b_ = img[..., 0], img[..., 1], img[..., 2]
    wood = opq & (r > g + 30) & (r > b_ + 40)
    lab, sizes = components(wood)
    parts = []
    for i in range(1, len(sizes)):
        if sizes[i] < 6:
            continue
        py, px = np.nonzero(lab == i)
        cx, cy = px.mean() + 0.5, py.mean() + 0.5
        along = (cx - bx) * ax + (cy - by) * ay
        parts.append({"n": int(sizes[i]), "centre_x4": [round(float(cx), 1), round(float(cy), 1)], "along": float(along)})
    parts = sorted(parts, key=lambda p: -p["n"])[:3]
    rep["wood_parts"] = [{k2: v for k2, v in p.items() if k2 != "along"} for p in parts]
    if len(parts) == 3:
        stock = min(parts, key=lambda p: p["along"])
        rest = sorted([p for p in parts if p is not stock], key=lambda p: p["along"])
        for name, p in (("grip", rest[0]), ("front", rest[1])):
            z = zones[name]
            cx, cy = p["centre_x4"]
            inside = z[0] <= cx <= z[2] + 1 and z[1] <= cy <= z[3] + 1
            ddx = max(z[0] - cx, 0, cx - (z[2] + 1))
            ddy = max(z[1] - cy, 0, cy - (z[3] + 1))
            rep["%s_centre_x4" % name] = p["centre_x4"]
            rep["%s_in_zone" % name] = bool(inside)
            rep["%s_out_of_zone_x4" % name] = round(float(np.hypot(ddx, ddy)), 2)
            rep["%s_zone_fill" % name] = round(float(opq[z[1]:z[3] + 1, z[0]:z[2] + 1].mean()), 2)
    else:
        rep["grip_in_zone"] = rep["front_in_zone"] = False
        rep["wood_note"] = "деревянных частей %d, ждал 3" % len(parts)
    # зелень: непрозрачное и полупрозрачное
    tint = (g > r + 30) & (g > b_ + 30)
    semi = (al > 0.05) & (al <= 0.95)
    op = al > 0.95
    rep["opaque_px"] = int(op.sum())
    rep["opaque_green_share"] = round(float((op & tint).sum()) / max(1, int(op.sum())), 4)
    rep["semi_px"] = int(semi.sum())
    rep["semi_green_share"] = round(float((semi & tint).sum()) / max(1, int(semi.sum())), 4)
    # зелень, видимая на полу: сдвиг цвета края к фону после наложения на пол боя
    return rep


def lum(x):
    return 0.299 * x[..., 0] + 0.587 * x[..., 1] + 0.114 * x[..., 2]


def details(raw_rgb, alpha_ans, rgb_clean, img, a, b, classic_idx):
    """Сохранность деталей: площадь, тёмная сталь, отверстия - ответ (в пересчёте на x4) против кандидата.
    Тёмная сталь: доля тёмного ответа (яркость < 60), уменьшенная тем же подобием, - сколько её в каждом пикселе x4;
    пиксели, где тёмного больше половины, обязаны остаться тёмными (порог по яркости после усреднения сравнивал бы
    разные величины: тонкая тёмная линия при 16:1 честно становится серее)."""
    sc = abs(a) * 4.0 / S_ANS                  # длина: пиксель холста ответа -> пиксель x4
    al = img[..., 3] / 255.0
    dark = alpha_ans * (lum(rgb_clean) < 60)
    D = place(np.zeros_like(rgb_clean), dark, a, b, S_ANS, PAD_ANS)[..., 3] / 255.0
    major = (al > 0.5) & (D > 0.5 * np.maximum(al, 1e-3))
    area_ans = float(alpha_ans.sum()) * sc * sc
    area_cand = float(al.sum())
    lw_ans = float((alpha_ans * lum(rgb_clean)).sum() / alpha_ans.sum())
    lw_cand = float((al * lum(img)).sum() / al.sum())
    h_ans = holes(alpha_ans > 0.5, int(round(0.25 / (sc * sc))))
    h_cand = holes(al > 0.5, 1)
    h_cls = holes((classic_idx > 0).repeat(4, 0).repeat(4, 1), 1)
    return {"area_x4_expected": round(area_ans, 1), "area_x4_candidate": round(area_cand, 1),
            "area_ratio": round(area_cand / area_ans, 4),
            "mean_luma_answer": round(lw_ans, 1), "mean_luma_candidate": round(lw_cand, 1),
            "dark_steel_share_answer": round(float(dark.sum() / alpha_ans.sum()), 4),
            "dark_steel_share_candidate_coverage": round(float(D.sum() / al.sum()), 4),
            "dark_majority_px": int(major.sum()),
            "dark_majority_luma_median": round(float(np.median(lum(img)[major])), 1) if major.any() else None,
            "dark_majority_still_dark_share": round(float((lum(img)[major] < 70).mean()), 3) if major.any() else None,
            "holes_answer_x4_px": sorted([round(h["px"] * sc * sc, 2) for h in h_ans], reverse=True),
            "holes_candidate_x4_px": sorted([h["px"] for h in h_cand], reverse=True),
            "holes_classic_x4_px": sorted([h["px"] for h in h_cls], reverse=True),
            "holes_answer": h_ans, "holes_candidate": h_cand}


# ракурс: элементы, у которых в боевом виде (ортографическая камера 30° сверху, battle_view) рёбра вертикальны -
# магазин и торец приклада; на холсте ответа коробки по сетке /16 (handob_cand1642 view_probe)
VIEW_BOXES = {"magazine_left": ((530, 800, 640, 878), "left"), "magazine_right": ((530, 800, 640, 878), "right"),
              "butt_end": ((60, 975, 140, 1100), "left")}
VIEW_CLASSIC = {"magazine_left": ((17, 19, 20, 22), "left"), "magazine_right": ((17, 19, 20, 22), "right"),
                "butt_end": ((10, 21, 13, 24), "left")}


def edge_angle(mask, box, side):
    """Наклон кромки от вертикали в градусах (плюс - низ правее): по строкам коробки крайний пиксель, прямая x(y)."""
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    yy, xx = [], []
    for y in range(max(0, y0), min(mask.shape[0], y1)):
        r = np.nonzero(mask[y, max(0, x0):min(mask.shape[1], x1)])[0]
        if len(r):
            yy.append(y + 0.5)
            xx.append(max(0, x0) + (r[0] if side == "left" else r[-1] + 1))
    if len(yy) < 3:
        return None, 0
    m, _c = np.polyfit(yy, xx, 1)
    return round(math.degrees(math.atan(m)), 1), len(yy)


def view_check(alpha_ans, a, b, classic_idx):
    """Углы вертикальных кромок: классика, ответ, кандидат (ответ, поставленный тем же подобием, x16 до уменьшения)."""
    K = 16
    hi = place(np.zeros(alpha_ans.shape + (3,)), alpha_ans, a, b, S_ANS, PAD_ANS, out_k=K)[..., 3] > 127
    cm = (classic_idx > 0).repeat(K, 0).repeat(K, 1)
    rot = math.degrees(math.atan2(a.imag, a.real))
    out = {}
    for name, (box, side) in VIEW_BOXES.items():
        ang_raw, n_raw = edge_angle(alpha_ans > 0.5, box, side)
        corners = [a * complex(u / S_ANS, (v - PAD_ANS) / S_ANS) + b for u in (box[0], box[2]) for v in (box[1], box[3])]
        cb = (min(c.real for c in corners) * K, min(c.imag for c in corners) * K,
              max(c.real for c in corners) * K, max(c.imag for c in corners) * K)
        ang_c, n_c = edge_angle(hi, cb, side)
        cbx = VIEW_CLASSIC[name][0]
        ang_cls, n_cls = edge_angle(cm, [v * K for v in cbx], side)
        out[name] = {"classic_deg": ang_cls, "answer_deg": ang_raw, "candidate_deg": ang_c,
                     "expected_candidate_deg": None if ang_raw is None else round(ang_raw - rot, 1),
                     "rows": [n_cls, n_raw, n_c], "candidate_box_x16": [round(v, 1) for v in cb]}
    return out, hi


def control(classic_idx, pal, bg, t, butt, zones, shift):
    """Мера на себе: оригинал x32 на фоне ответа, тождественное подобие (+сдвиг на базовый пиксель)."""
    H, W = 1536, 1024
    can = np.zeros((H, W, 3)) + bg
    up = pal[classic_idx].astype(np.float64).repeat(S_ANS, 0).repeat(S_ANS, 1)
    m = (classic_idx > 0).repeat(S_ANS, 0).repeat(S_ANS, 1)
    lay = np.zeros((1280, 1024, 3)) + bg
    lay[m] = up[m]
    if shift:
        x0 = S_ANS * shift
        lay[:, x0:] = lay[:, :-x0].copy()
        lay[:, :x0] = bg
    can[PAD_ANS:PAD_ANS + 1280] = lay
    clean, al, mrep = matte(can, bg)
    img = place(clean, al, complex(1, 0), complex(0, 0), S_ANS, PAD_ANS)
    rep = measures(img, t, butt, zones)
    return {"shift_base": shift, "size_pct": rep["size_pct"], "muzzle_err_x4": rep["muzzle_err_x4"],
            "opaque_green_share": rep["opaque_green_share"], "semi_green_share": rep["semi_green_share"],
            "max_abs_vs_classic_x4": None if shift else float(np.abs(
                img[..., :3] * (img[..., 3:] / 255) - (pal[classic_idx].repeat(4, 0).repeat(4, 1) *
                                                     (classic_idx > 0).repeat(4, 0).repeat(4, 1)[..., None])).max()),
            "matte": mrep}, img


# ---------------------------------------------------------------- листы
def on_floor(img, scale, floor=FLOOR, checker=True):
    h, w = img.shape[:2]
    if checker:
        fl = (np.indices((h, w)).sum(0) // 8 % 2)[..., None] * 8 + np.array(floor, float)
    else:
        fl = np.zeros((h, w, 3)) + np.array(floor, float)
    a = img[..., 3:4] / 255.0
    im = Image.fromarray(np.clip(img[..., :3] * a + fl * (1 - a), 0, 255).astype(np.uint8))
    return im.resize((w * scale, h * scale), Image.NEAREST if scale >= 1 else Image.LANCZOS)


def up_idx(idx, pal, k=4):
    a = (idx > 0).astype(np.float64)
    return np.dstack([pal[idx].astype(np.float64).repeat(k, 0).repeat(k, 1), (a * 255).repeat(k, 0).repeat(k, 1)])


def hands_visible(item, gm, zones):
    """Видимость кистей после сборки TWO_STAND dir 2: la рисуется ДО предмета (предмет её закрывает), ra - после.
    Доля пикселей слоя руки в зоне рукояти, которые остались видны (R-240: закрытая кисть - не довод)."""
    out = {}
    cover = item[..., 3] > 127
    for arm, fr, zname in (("la", 242, "front"), ("ra", 250, "grip")):
        m = (gm.gov(fr) > 0).repeat(4, 0).repeat(4, 1)
        z = zones[zname]
        zm = np.zeros(m.shape, bool)
        zm[z[1]:z[3] + 1, z[0]:z[2] + 1] = True
        arm_px = m & zm
        hidden = arm_px & cover if arm == "la" else np.zeros_like(arm_px)
        out["%s_in_%s_zone_px" % (arm, zname)] = int(arm_px.sum())
        out["%s_visible_share" % arm] = round(1 - float(hidden.sum()) / max(1, int(arm_px.sum())), 3)
        out["%s_hand_whole_visible_share" % arm] = round(1 - float((m & cover).sum()) / max(1, int(m.sum())), 3) \
            if arm == "la" else 1.0
    return out


def compose_unit(item, gm):
    L = {"la": 242, "lg": 18, "to": 34, "ra": 250}
    out = np.zeros((160, 128, 4))
    for n in "la lg to iR ra".split():
        lay = item if n == "iR" else up_idx(gm.gov(L[n]), gm.gpal)
        a = lay[..., 3:4] / 255.0
        out[..., :3] = lay[..., :3] * a + out[..., :3] * (1 - a)
        out[..., 3:4] = np.maximum(out[..., 3:4], lay[..., 3:4])
    return out


def marks(im, t, S):
    dr = ImageDraw.Draw(im)
    for k, c in (("bbox", (255, 255, 255)), ("grip", (0, 230, 255)), ("front", (255, 230, 0))):
        b = t[k]
        dr.rectangle([b[0] * S, b[1] * S, (b[2] + 1) * S - 1, (b[3] + 1) * S - 1], outline=c, width=1)
    mx, my = t["muzzle"]
    b0x, b0y = (mx // 4) * 4, (my // 4) * 4
    dr.rectangle([b0x * S, b0y * S, (b0x + 4) * S - 1, (b0y + 4) * S - 1], outline=(255, 0, 210), width=1)
    return im


def titled(im, title, font, sub=None):
    hh = 22 + (20 if sub else 0)
    sh = Image.new("RGB", (im.width, im.height + hh), (20, 22, 28))
    sh.paste(im, (0, hh))
    d = ImageDraw.Draw(sh)
    d.text((4, 3), title, fill=(235, 235, 235), font=font)
    if sub:
        d.text((4, 22), sub, fill=(255, 190, 120), font=font)
    return sh


def row(ims, gap=10, bg=(20, 22, 28)):
    W = sum(i.width for i in ims) + gap * (len(ims) + 1)
    H = max(i.height for i in ims) + 2 * gap
    sh = Image.new("RGB", (W, H), bg)
    x = gap
    for i in ims:
        sh.paste(i, (x, gap))
        x += i.width + gap
    return sh


def col(ims, gap=6, bg=(20, 22, 28)):
    W = max(i.width for i in ims)
    H = sum(i.height for i in ims) + gap * (len(ims) - 1)
    sh = Image.new("RGB", (W, H), bg)
    y = 0
    for i in ims:
        sh.paste(i, (0, y))
        y += i.height + gap
    return sh


def load_rgba(p):
    return np.asarray(Image.open(p).convert("RGBA")).astype(np.float64)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.chdir(ROOT)
    import grip_matrix as gm
    with open(os.path.join(SRC, "plan.json"), encoding=ENC) as f:
        plan = json.load(f)
    with open(os.path.join(SRC, "fit4", "fit4.json"), encoding=ENC) as f:
        fit = json.load(f)
    with open(os.path.join(PILOT, "target_zones_rev2.json"), encoding=ENC) as f:
        rev = json.load(f)["frames"]["STR_TOMMYGUN.1642"]
    t = dict(plan["targets_x4"])
    t["front"] = rev["support"][0]
    zones = {"grip": t["grip"], "front": t["front"]}
    butt = plan["butt_base"]
    sim = fit["Codex"]["similarity"]
    raw_path = fit["Codex"]["raw"]
    a = sim["scale"] * complex(math.cos(math.radians(sim["rotation_deg"])), math.sin(math.radians(sim["rotation_deg"])))
    b = complex(*sim["shift_base"])
    os.makedirs(OUT, exist_ok=True)
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 15)

    raw = Image.open(raw_path)
    rgb = np.asarray(raw.convert("RGB")).astype(np.float64)
    bg = background(rgb)
    clean, alpha, mrep = matte(rgb, bg)
    img = place(clean, alpha, a, b, S_ANS, PAD_ANS)
    out8 = np.clip(np.round(img), 0, 255).astype(np.uint8)
    cand_path = os.path.join(OUT, "1642.png")
    Image.fromarray(out8, "RGBA").save(cand_path)
    img = out8.astype(np.float64)               # меры - по тому, что лежит в файле
    rep = {"raw": raw_path, "note": "проверочный кандидат, не в мод: одно подобие целого предмета из fit4.json",
           "similarity": {"scale": sim["scale"], "rotation_deg": sim["rotation_deg"], "shift_base": sim["shift_base"]},
           "matte": mrep, "candidate": cand_path.replace("\\", "/")}
    rep["measures"] = measures(img, t, butt, zones)
    idx = gm.hob(1642)
    rep["details"] = details(rgb, alpha, clean, img, a, b, idx)
    rep["view"], _hi = view_check(alpha, a, b, idx)
    rep["hands"] = {"classic": hands_visible(up_idx(idx, gm.hpal), gm, zones), "candidate": hands_visible(img, gm, zones),
                    "note": "TWO_STAND dir 2, порядок la lg to iL iR ra (grip_matrix.order): левая кисть на передней "
                            "рукояти под предметом, правая на основной - над ним"}
    rep["view_note"] = ("боевой вид - ортографическая камера 30° сверху (battle_view): вертикальные рёбра магазина и "
                        "торца приклада на экране вертикальны; поворот целого предмета наклоняет их на угол поворота")
    old = load_rgba(os.path.join(SRC, "hd", "1642.png"))
    rep["old_check_hd"] = {k: v for k, v in measures(old, t, butt, zones).items()
                           if k in ("size_pct", "muzzle_err_x4", "opaque_green_share", "semi_green_share", "semi_px",
                                    "grip_in_zone", "front_in_zone")}
    # контроль меры
    c0, cimg = control(idx, gm.hpal, bg, t, butt, zones, 0)
    c1, _ = control(idx, gm.hpal, bg, t, butt, zones, 1)
    c0["pass"] = c0["size_pct"] == [0.0, 0.0] and c0["muzzle_err_x4"] == 0.0 and c0["opaque_green_share"] == 0 \
        and c0["semi_green_share"] == 0 and c0["max_abs_vs_classic_x4"] < 8.0
    c1["pass"] = c1["size_pct"] == [0.0, 0.0] and c1["muzzle_err_x4"] == 4.0
    rep["control"] = {"identity": c0, "shift_right_1": c1}
    if not (c0["pass"] and c1["pass"]):
        print(json.dumps(rep["control"], ensure_ascii=False, indent=1))
        raise SystemExit("контроль меры НЕ прошёл - числа кандидата не довод")
    with open(os.path.join(OUT, "cand.json"), "w", encoding=ENC) as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    m = rep["measures"]
    print("кандидат:", cand_path)
    print("размер %s (ok %s), дуло %.2f x4 (ok %s), основная в зоне %s (%.2f), передняя %s (%.2f)" % (
        m["size_pct"], m["size_ok"], m["muzzle_err_x4"], m["muzzle_ok"], m.get("grip_in_zone"),
        m.get("grip_out_of_zone_x4", -1), m.get("front_in_zone"), m.get("front_out_of_zone_x4", -1)))
    print("зелень: непрозрачное %.4f, полупрозрачное %.4f (%d пикс); прежний check: %s" % (
        m["opaque_green_share"], m["semi_green_share"], m["semi_px"], rep["old_check_hd"]))
    d = rep["details"]
    print("детали: площадь %.4f, яркость %.1f/%.1f, тёмное %.4f/%.4f, тёмных по большинству %d - остались тёмными %s "
          "(медиана %s); отверстия ответа %s, кандидата %s, классики %s" % (
              d["area_ratio"], d["mean_luma_answer"], d["mean_luma_candidate"], d["dark_steel_share_answer"],
              d["dark_steel_share_candidate_coverage"], d["dark_majority_px"], d["dark_majority_still_dark_share"],
              d["dark_majority_luma_median"], d["holes_answer_x4_px"], d["holes_candidate_x4_px"],
              d["holes_classic_x4_px"]))
    for k, v in rep["view"].items():
        print("ракурс %-15s классика %s°, ответ %s°, кандидат %s° (ждал %s°), строк %s" % (
            k, v["classic_deg"], v["answer_deg"], v["candidate_deg"], v["expected_candidate_deg"], v["rows"]))
    print("кисти:", rep["hands"]["classic"], "->", rep["hands"]["candidate"])
    print("контроль: тождество %s, сдвиг %s" % (c0["pass"], c1["pass"]))
    print("край:", mrep)

    # ---- лист 1: исходный ответ | кандидат крупно | 1:1 и x2 рядом с классикой и прежним check
    cls = up_idx(idx, gm.hpal)
    S = 5
    rawv = raw.convert("RGB").resize((512, 768), Image.LANCZOS)
    big = marks(on_floor(img, S), t, S)
    big_plain = on_floor(img, S)
    small = []
    for name, im in (("классика", cls), ("кандидат", img), ("прежний check", old)):
        small.append(titled(row([on_floor(im, 1, checker=False), on_floor(im, 2, checker=False)], gap=6), name, font))
    s1 = row([titled(rawv, "исходный ответ Codex 1024x1536 (уменьшен)", font),
              titled(big_plain, "кандидат 128x160 x5 на полу", font,
                     "размер %+.1f%% / %+.1f%%, дуло %.1f x4" % (m["size_pct"][0], m["size_pct"][1], m["muzzle_err_x4"])),
              titled(big, "то же с местами (только на листе)", font,
                     "белая рамка, голубая основная, жёлтая передняя, лиловый блок дула"),
              col(small)])
    s1.save(os.path.join(OUT, "sheet_candidate.png"))
    # ---- лист 2: сборка с бойцом TWO_STAND dir 2: классика | кандидат | прежний check, крупно и 1:1
    units = []
    for name, im in (("классика", cls), ("кандидат", img), ("прежний check", old)):
        u = compose_unit(im, gm)
        units.append(titled(row([on_floor(u, 4), col([on_floor(u, 1, checker=False), on_floor(u, 2, checker=False)])],
                                gap=8), name, font))
    s2 = titled(row(units), "сборка с бойцом TWO_STAND, dir 2 (la lg to iR ra): x4, справа 1:1 и x2", font)
    zoom = []
    for name, im in (("классика", cls), ("кандидат", img)):
        u = compose_unit(im, gm)[12 * 4:26 * 4, 8 * 4:28 * 4]
        p = on_floor(u, 8, checker=False)
        dr = ImageDraw.Draw(p)
        for k, c in (("grip", (0, 230, 255)), ("front", (255, 230, 0))):
            z = t[k]
            dr.rectangle([(z[0] - 32) * 8, (z[1] - 48) * 8, (z[2] + 1 - 32) * 8 - 1, (z[3] + 1 - 48) * 8 - 1],
                         outline=c, width=2)
        zoom.append(titled(p, name + ": хват x8 (голубая - зона основной рукояти, жёлтая - передней)", font))
    col([s2, row(zoom)]).save(os.path.join(OUT, "sheet_unit.png"))
    # ---- лист 3: край вблизи на тёмном и светлом полу: прежний check против кандидата
    edges = []
    for name, im in (("прежний check", old), ("кандидат", img)):
        cr = im[50:100, 40:108]
        edges.append(titled(col([on_floor(cr, 8, (24, 26, 30), False), on_floor(cr, 8, (200, 200, 205), False)]),
                            name + ": край x8, тёмный и светлый пол", font))
    row(edges).save(os.path.join(OUT, "sheet_edge.png"))
    # ---- лист 4: ракурс x16 - классика | кандидат (файл 128x160) | ответ тем же подобием до уменьшения
    K = 16
    hi_col = place(clean, alpha, a, b, S_ANS, PAD_ANS, out_k=K)
    no_rot = complex(fit["Codex"]["scale_shift_no_rotation"]["scale"], 0)
    b_nr = complex(*fit["Codex"]["scale_shift_no_rotation"]["shift_base"])
    hi_nr = place(clean, alpha, no_rot, b_nr, S_ANS, PAD_ANS, out_k=K)
    cls16 = up_idx(idx, gm.hpal, K)
    cand16 = img.repeat(4, 0).repeat(4, 1)
    panels = []
    for title, reg in (("коробка, магазин, рукояти", (14, 14, 26, 23)), ("приклад", (9, 19, 17, 25))):
        x0, y0, x1, y1 = [v * K for v in reg]
        cells = []
        for name, im in (("классика x16", cls16), ("кандидат 128x160 x4", cand16),
                         ("ответ подобием, x16 до уменьшения", hi_col), ("ответ без поворота (для сравнения)", hi_nr)):
            p = on_floor(im[y0:y1, x0:x1], 2, checker=False)
            dr = ImageDraw.Draw(p)
            for gx in range(0, p.width, K * 4):         # вертикали через 2 пикселя базы - отсчёт для рёбер
                dr.line([gx, 0, gx, p.height], fill=(90, 160, 255), width=1)
            cells.append(titled(p, name, font))
        panels.append(titled(row(cells, gap=8), title, font))
    v = rep["view"]
    cap = ("наклон от вертикали, плюс - низ правее; ответ -> ждали после поворота -> мерено на кандидате x16: "
           "магазин слева %s -> %s -> %s°, справа %s -> %s -> %s°, торец приклада %s -> %s -> %s°" % tuple(
               v[k][f] for k in ("magazine_left", "magazine_right", "butt_end")
               for f in ("answer_deg", "expected_candidate_deg", "candidate_deg")))
    titled(col(panels), "ракурс: в бою вертикальные рёбра вертикальны (синие линии - вертикали); классика 2-3 пикселя, "
           "угол по ней не мерится", font, cap).save(os.path.join(OUT, "sheet_view.png"))
    with open(os.path.join(OUT, "cand.json"), "w", encoding=ENC) as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    print("листы:", OUT)


if __name__ == "__main__":
    main()
