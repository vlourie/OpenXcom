"""Посадка HD-слоёв брони на HD-тела кукол (экран бойца), без игры и без видеокарты.

Что считает (подробно - docs/research/doll-armor-fit-2026-11-05.md):
  1. перепись: сколько разных слоёв брони, пар внешность-броня, разных собранных кукол;
  2. слой против классики: сдвиг (dx, dy в HD-пикселях, матч маски HD-альфы с маской классики x4),
     вылезло за контур классики, не закрыто, совпадение, копия лесенки классики (правило 12, R-121);
  3. пара внешность-броня на собранной кукле: просвет (голое тело там, где классика закрыта бронёй),
     броня поверх тела там, где классика показывает тело, дыра (классика непрозрачна, HD нет),
     тонкий/разорванный шов броня-тело, ступенька светлоты на шве;
  4. по внешностям и по слоям: где посадка хуже.
Допуск tol (HD-пикселей, по умолчанию 4 = один пиксель классики): всё, что ближе к границе классики, считается
мягким краем, а не браком. Числа - HD-пиксели и проценты площади классического силуэта (x16) / брони.

Кукла = слои по порядку индексов (как HdUiArt::composeLayers). HD-кукла в игре собирается, только если картинка есть
у каждого слоя ("full"); пары, где HD есть у части слоёв, меряются тоже, по тем слоям, где HD есть, против классики
из тех же слоёв ("partial"). Классика читается индексами (R-043): индекс 0 прозрачен.

Запуск (одна команда, файлы пишутся в art/doll/pipe_pilot/armor_fit/):
  E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe E:/OpenXCom/tools/hdart/doll_armor_fit.py
Ключи: --out DIR  --workers N  --tol 4  --thr "{\"pair_bad_pct\": 3}"  --no-sheets  --sheet-pairs 12  --limit N
       --layers DIR  папка слоёв вместо pipe_pilot/layers
       --pairs "STR_AMAZON_ARMOR_UC:M0,M51,F58"  только эти пары (через ; несколько броней), один лист sheet_pairs_probe.png
Пороги брака лежат в report.json -> thresholds; список брака - report.json -> flags.
Ничего в игре и в слоях не меняет; видеокарту не трогает.
"""
import argparse
import collections
import json
import multiprocessing as mp
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import cv2                                              # noqa: E402
import numpy as np                                      # noqa: E402
from PIL import Image, ImageDraw, ImageFont             # noqa: E402

import doll_b2_render as db                             # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:                                       # noqa: BLE001
    pass
ENC = "utf-8-sig"
ROOT = db.ROOT
LAYERS = os.path.join(ROOT, "art", "doll", "pipe_pilot", "layers")
OUT = os.path.join(ROOT, "art", "doll", "pipe_pilot", "armor_fit")
PAL = os.path.join(ROOT, "art", "doll", "b2", "palette.pal.txt")
K = 4
HW, HH = 320 * K, 200 * K
A_ON = 128                      # альфа, с которой пиксель HD считается непрозрачным

THR = {
    "tol": 4,                   # HD-пикселей: мягкий край вокруг границы классики
    "layer_shift_px": 3.0,      # сдвиг слоя, HD-пикселей (по длине вектора)
    "layer_outside_pct": 1.0,   # вылезло за контур классики, % площади классики
    "layer_uncovered_pct": 1.0,  # не закрыто HD, % площади классики
    "layer_stair_pct": 1.0,     # слой с косыми краями, где край HD совпадает с лесенкой классики x4 (<) - копия лесенки
    "layer_gray_blob_px": 60,   # серое малонасыщенное пятно на теле ниже GRAY_Y0, HD-пикселей (проверено глазом: M20, M2, F11)
    "pair_bad_pct": 2.0,       # просвет+вылезло+дыры пары, % площади классического силуэта
    "pair_gap_deep_px": 400,    # просвет тела под броней, HD-пикселей (всё, что глубже допуска)
    "pair_hole_px": 400,        # дыра, HD-пикселей
    "pair_dark_bare_pct": 0.5,  # запечённое бельё тела на месте голой кожи классики, % площади силуэта
    "pair_lum_corr_min": 0.25,  # корреляция светлоты HD (сжатой) с классикой внутри силуэта, ниже - другая картинка
}

GRAY_Y0 = 340                   # HD-строка, с которой ищем серые заплатки (бёдра и ниже; 85 в пикселях классики)
_pal = None
_cache = {}
_files = None
_tol = 4


def _lum(rgb):
    return rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114


def kind_of(name):
    """0 тело, 1 голова, 2 вещь брони."""
    p = name.upper().split("__")
    if len(p) >= 3 and p[1] == "2" and p[2].endswith("_NUDE"):
        return 0
    if len(p) >= 3 and p[1] == "10" and p[2].startswith("HEAD_"):
        return 1
    return 2


def _lru(key, loader, limit=40):
    v = _cache.get(key)
    if v is None:
        if len(_cache) >= limit:
            _cache.pop(next(iter(_cache)))
        v = loader()
        _cache[key] = v
    return v


def hd_rgba(name):
    def ld():
        im = Image.open(os.path.join(LAYERS, name.lower() + ".png")).convert("RGBA")
        if im.size != (HW, HH):
            raise ValueError("%s: размер %s, ждали %dx%d" % (name, im.size, HW, HH))
        return np.asarray(im)
    return _lru(("h", name), ld)


def cls_idx(name):
    def ld():
        return db.load_indices(_files[name.upper()])
    return _lru(("c", name), ld, 400)


def rep4(a):
    return np.repeat(np.repeat(a, K, axis=0), K, axis=1)


def dt(mask):
    """Расстояние (HD-пикселей) от каждого пикселя маски до ближайшего пикселя вне маски."""
    return cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 3)


def init_worker(tol, layers=None):
    global _files, _tol, _pal, LAYERS
    _files = db.sprite_files()
    _tol = tol
    LAYERS = layers or LAYERS
    _pal = np.array([[int(v) for v in l.split()] for l in open(PAL, encoding="ascii") if l.strip()], np.float32)


# ---------------------------------------------------------------- слой против классики

def layer_fit(name):
    try:
        cidx = cls_idx(name)
        rgba = hd_rgba(name)
    except Exception as e:                                  # noqa: BLE001
        return {"name": name, "error": str(e)}
    c4 = rep4(cidx != 0)
    al = rgba[..., 3]
    hd = al >= A_ON
    area_c = int(c4.sum())
    area_h = int(hd.sum())
    r = {"name": name, "kind": kind_of(name), "area_cls": area_c, "area_hd": area_h}
    if area_c == 0 or area_h == 0:
        r["empty"] = "classic" if area_c == 0 else "hd"
        return r
    tol = _tol
    d_in_c, d_out_c = dt(c4), dt(~c4)
    d_in_h, d_out_h = dt(hd), dt(~hd)
    outside = hd & ~c4 & (d_out_c > tol)
    uncovered = c4 & ~hd & (d_out_h > tol)
    r["outside_px"] = int(outside.sum())
    r["uncovered_px"] = int(uncovered.sum())
    r["outside_pct"] = round(100.0 * r["outside_px"] / area_c, 3)
    r["uncovered_pct"] = round(100.0 * r["uncovered_px"] / area_c, 3)
    r["iou"] = round(float((hd & c4).sum()) / float((hd | c4).sum()), 4)
    # сдвиг: минимум суммы квадратов разности масок HD и классики x4 на окне +-S
    S = 24
    ys, xs = np.nonzero(hd)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    tpl = hd[y0:y1, x0:x1].astype(np.float32)
    pad = np.zeros((HH + 2 * S, HW + 2 * S), np.float32)
    pad[S:S + HH, S:S + HW] = c4
    img = pad[y0:y1 + 2 * S, x0:x1 + 2 * S]
    res = cv2.matchTemplate(img, tpl, cv2.TM_SQDIFF)
    j = np.unravel_index(int(np.argmin(res)), res.shape)    # (y, x), нулевой сдвиг = (S, S)
    dy, dx = float(j[0] - S), float(j[1] - S)
    # параболическое уточнение
    def sub(v, m, p):
        den = v - 2 * m + p
        return 0.0 if abs(den) < 1e-9 else 0.5 * (v - p) / den
    if 0 < j[1] < res.shape[1] - 1:
        dx += sub(res[j[0], j[1] - 1], res[j[0], j[1]], res[j[0], j[1] + 1])
    if 0 < j[0] < res.shape[0] - 1:
        dy += sub(res[j[0] - 1, j[1]], res[j[0], j[1]], res[j[0] + 1, j[1]])
    r["shift_dx"], r["shift_dy"] = round(dx, 2), round(dy, 2)
    r["shift_px"] = round(float(np.hypot(dx, dy)), 2)
    r["shift_at_edge"] = bool(abs(j[0] - S) >= S - 1 or abs(j[1] - S) >= S - 1)
    r["mismatch0_px"] = int(np.count_nonzero(hd != c4))
    r["mismatch_best_px"] = int(round(float(res.min())))
    # копия лесенки: у слоя с косыми краями поясок +-4 пикселя вокруг границы классики x4 совпадает с ней
    band = (d_in_c <= 4) | (d_out_c <= 4)
    band &= c4 | (d_out_c <= 4)
    nb = int(band.sum())
    if nb:
        r["band_px"] = nb
        r["band_mismatch_pct"] = round(100.0 * float(np.count_nonzero((hd != c4) & band)) / nb, 3)
        # доля краевых пикселей с частичной альфой: у сглаженного края она есть, у копии лесенки нет
        edge = band & ((d_in_h <= 1.5) | (d_out_h <= 1.5))
        ne = int(edge.sum())
        r["edge_partial_pct"] = round(100.0 * float(np.count_nonzero(edge & (al > 8) & (al < 247))) / max(ne, 1), 2)
    # лесенка по контуру (правило 12): прямые отрезки по осям длиной от 3 пикселей, сходящиеся под прямым углом
    sh, sc = stair_corners(hd), stair_corners(c4)
    r["stair_hd"], r["stair_cls"] = sh, sc
    r["stair_ratio"] = round(sh / sc, 3) if sc > 0 else 0.0
    # внутри контура: корреляция светлоты HD (сжатой до классики) с классикой по палитре
    cm = cidx != 0
    al_f = al.astype(np.float32) / 255.0
    w = al_f.reshape(200, K, 320, K).mean((1, 3))
    lum_h = (_lum(rgba[..., :3].astype(np.float32)) * al_f).reshape(200, K, 320, K).sum((1, 3)) / np.maximum(w * K * K, 1e-6)
    lum_c = _lum(_pal[cidx])
    inner = cv2.erode(cm.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool) & (w > 0.97)
    if inner.sum() > 30:
        x, y = lum_h[inner], lum_c[inner]
        r["lum_corr"] = round(float(np.corrcoef(x, y)[0, 1]), 3) if x.std() > 1e-3 and y.std() > 1e-3 else None
    # серые заплатки на теле (нашёл глазом: клин плоского серого между бёдер у M20): непрозрачные малонасыщенные
    # пятна >= 60 пикселей на теле с цветной кожей. Только слой тела; металл/украшения брони не считаем
    if r["kind"] == 0:
        rgbf = rgba[..., :3].astype(np.float32)
        sat = rgbf.max(2) - rgbf.min(2)
        lm = _lum(rgbf)
        gm = ((al >= 200) & (sat < 30) & (lm > 70) & (lm < 235)).astype(np.uint8)
        gm[:GRAY_Y0] = 0        # выше бёдер серое - это волосы, маски, цепи и украшения на самом теле, не заплатка
        gm = cv2.morphologyEx(gm, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        nl, lab, st, cen = cv2.connectedComponentsWithStats(gm, connectivity=8)
        blobs = [(int(st[i, cv2.CC_STAT_AREA]), int(cen[i][0]), int(cen[i][1])) for i in range(1, nl) if st[i, cv2.CC_STAT_AREA] >= 60]
        r["gray_blob_n"] = len(blobs)
        r["gray_blob_max_px"] = max([b[0] for b in blobs], default=0)
        r["gray_blob_at"] = [b[1:] for b in sorted(blobs, reverse=True)[:3]]
    # кайма: у краевых пикселей (частичная альфа) цвет против цвета ближайшей внутренней части слоя
    core = al >= 250
    if core.sum() > 50:
        cf = core.astype(np.float32)
        num = cv2.blur(rgba[..., :3].astype(np.float32) * cf[..., None], (13, 13))
        den = cv2.blur(cf, (13, 13))[..., None]
        near = num / np.maximum(den, 1e-4)
        ed = (al > 8) & (al < 247) & (den[..., 0] > 0.05)
        if ed.sum() > 30:
            dd = rgba[..., :3].astype(np.float32)[ed] - near[ed]
            r["fringe_n"] = int(ed.sum())
            r["fringe_lum"] = round(float(_lum(dd).mean()), 2)          # < 0 тёмная кайма, > 0 светлая
            r["fringe_abs"] = round(float(np.abs(dd).mean()), 2)
    return r


def stair_corners(mask):
    """Углы лесенки на 1000 пикселей периметра: вершины контура, где оба соседних отрезка идут по оси и длиной >= 3."""
    cs, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    corners, per = 0, 0
    for c in cs:
        p = c[:, 0, :].astype(np.int32)
        n = len(p)
        if n < 4:
            continue
        nxt = np.roll(p, -1, axis=0)
        seg = nxt - p
        ln = np.abs(seg).sum(1)
        axis = (seg[:, 0] == 0) | (seg[:, 1] == 0)
        per += int(ln.sum())
        long_ax = axis & (ln >= 3)
        prev_ok = np.roll(long_ax, 1)
        perp = (np.roll(seg[:, 0] == 0, 1) != (seg[:, 0] == 0))
        corners += int((long_ax & prev_ok & perp).sum())
    return round(1000.0 * corners / per, 1) if per else 0.0


# ---------------------------------------------------------------- пара: собранная кукла

def compose(names):
    """-> dict с owner-картами HD и классики, составной альфой и цветом (float32)."""
    n = len(names)
    cidx = [cls_idx(x) for x in names]
    rgba = [hd_rgba(x) for x in names]
    own_c = np.full((200, 320), -1, np.int16)
    for i, c in enumerate(cidx):
        own_c = np.where(c != 0, i, own_c)
    own_h = np.full((HH, HW), -1, np.int16)
    keep = np.zeros((HH, HW), np.float32)       # 1 - совокупная альфа
    col = np.zeros((HH, HW, 3), np.float32)     # цвет, премультипликация
    for i, im in enumerate(rgba):
        a = im[..., 3].astype(np.float32) / 255.0
        own_h = np.where(im[..., 3] >= A_ON, i, own_h)
        col = col * (1 - a)[..., None] + im[..., :3].astype(np.float32) * a[..., None]
        keep = keep * (1 - a) if i else (1 - a)
    A = 1.0 - keep
    # классический цвет по палитре
    ccol = np.zeros((200, 320, 3), np.float32)
    for i, c in enumerate(cidx):
        ccol = np.where((c != 0)[..., None], _pal[c], ccol)
    return {"cidx": cidx, "own_c": rep4(own_c), "own_h": own_h, "A": A, "col": col, "ccol": rep4(ccol)}


def analyze(names, want_masks=False):
    tol = _tol
    cp = compose(names)
    kinds = np.array([kind_of(x) for x in names] + [3], np.int8)     # индекс -1 -> 3 (ничего)
    kc, kh = kinds[cp["own_c"]], kinds[cp["own_h"]]
    c_arm, c_skin, c_any = kc == 2, kc < 2, kc < 3
    h_arm, h_body, h_head, h_any = kh == 2, kh == 0, kh == 1, kh < 3
    h_skin = h_body | h_head
    d_in_arm = dt(c_arm)
    d_to_arm = dt(~c_arm)
    d_in_any = dt(c_any)
    d_to_any = dt(~c_any)
    m = {}
    m["area_cls"] = int(c_any.sum())
    m["area_arm"] = int(c_arm.sum())
    gap_b = h_body & c_arm & (d_in_arm > tol)
    gap_h = h_head & c_arm & (d_in_arm > tol)
    gap_e = h_skin & c_arm & (d_in_arm <= tol)
    spill_s = h_arm & c_skin & (d_to_arm > tol)
    spill_o = h_arm & ~c_any & (d_to_any > tol)
    skin_o = h_skin & ~c_any & (d_to_any > tol)
    deep = c_any & (d_in_any > tol)
    hole = deep & ~h_any
    band = cv2.dilate(c_arm.astype(np.uint8), np.ones((17, 17), np.uint8)).astype(bool) & \
        cv2.dilate(c_skin.astype(np.uint8), np.ones((17, 17), np.uint8)).astype(bool)
    hole_seam = hole & band
    thin_seam = band & deep & h_any & (cp["A"] < 0.95)
    m["gap_body_px"] = int(gap_b.sum())
    m["gap_head_px"] = int(gap_h.sum())
    m["gap_deep_px"] = m["gap_body_px"] + m["gap_head_px"]
    m["gap_edge_px"] = int(gap_e.sum())
    m["spill_skin_px"] = int(spill_s.sum())
    m["spill_out_px"] = int(spill_o.sum())
    m["skin_out_px"] = int(skin_o.sum())
    m["hole_px"] = int(hole.sum())
    m["hole_seam_px"] = int(hole_seam.sum())
    m["thin_seam_px"] = int(thin_seam.sum())
    bad = m["gap_deep_px"] + m["spill_skin_px"] + m["spill_out_px"] + m["skin_out_px"] + m["hole_px"]
    m["bad_px"] = bad
    m["bad_pct"] = round(100.0 * bad / max(m["area_cls"], 1), 3)
    m["gap_pct_arm"] = round(100.0 * m["gap_deep_px"] / max(m["area_arm"], 1), 3)
    # бельё, запечённое в HD-теле (R-588, решение Vitali 03.11): тёмные пиксели тела (светлота < 35 и < 0.35 медианы кожи),
    # видимые там, где классика показывает голую кожу. Не просвет по геометрии, но видно глазом
    bi = [i for i, x in enumerate(names) if kind_of(x) == 0]
    if bi:
        brgba = hd_rgba(names[bi[0]])
        bl = _lum(brgba[..., :3].astype(np.float32))
        bo = brgba[..., 3] >= A_ON
        if bo.sum() > 100:
            med = float(np.median(bl[bo]))
            dark = bo & (bl < np.minimum(0.35 * med, 35.0))
            vis_dark = dark & h_body
            m["dark_body_px"] = int(vis_dark.sum())
            m["dark_bare_px"] = int((vis_dark & c_skin & ~c_arm).sum())
            m["dark_bare_pct"] = round(100.0 * m["dark_bare_px"] / max(m["area_cls"], 1), 3)
    # шов голова-тело: ступенька среднего цвета кожи по обе стороны (пояс 6 пикселей), RGB-расстояние
    hb_n = None
    if h_head.sum() > 100 and h_body.sum() > 100:
        nh = h_head & (dt(~h_body) <= 6)
        nb = h_body & (dt(~h_head) <= 6)
        if nh.sum() > 40 and nb.sum() > 40:
            ch, cb = cp["col"][nh].mean(0) / max(float(cp["A"][nh].mean()), 1e-3), cp["col"][nb].mean(0) / max(float(cp["A"][nb].mean()), 1e-3)
            m["neck_step"] = round(float(np.linalg.norm(ch - cb)), 1)
            m["neck_step_lum"] = round(float(_lum(ch) - _lum(cb)), 1)
    # внутри силуэта: светлота собранной HD-куклы (сжатой до классики) против классики
    w = cp["A"].reshape(200, K, 320, K).mean((1, 3))
    lum_h = _lum(cp["col"]).reshape(200, K, 320, K).mean((1, 3)) / np.maximum(w, 1e-6)
    lum_c = _lum(cp["ccol"][::K, ::K])
    cm = cv2.erode((cp["own_c"][::K, ::K] >= 0).astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool) & (w > 0.97)
    if cm.sum() > 30 and lum_h[cm].std() > 1e-3 and lum_c[cm].std() > 1e-3:
        m["lum_corr"] = round(float(np.corrcoef(lum_h[cm], lum_c[cm])[0, 1]), 3)
    # по слоям: чья классическая зона просвечивает, какая броня вылезла
    byl = {}
    for tag, mask, own in (("gap_under", gap_b | gap_h, cp["own_c"]), ("spill_by", spill_s | spill_o, cp["own_h"])):
        cnt = np.bincount(own[mask].ravel() + 1, minlength=len(names) + 1)
        for i in range(len(names)):
            if cnt[i + 1]:
                byl.setdefault(names[i], {})[tag] = int(cnt[i + 1])
    m["by_layer"] = byl
    # ступенька светлоты на шве броня-тело: по обе стороны шва, в поясе 6 пикселей
    if m["area_arm"] > 0:
        def side(a_mask, s_mask, col, d_a, d_s):
            near_a = a_mask & (d_s <= 6)
            near_s = s_mask & (d_a <= 6)
            if near_a.sum() < 200 or near_s.sum() < 200:
                return None
            return float(abs(_lum(col[near_a]).mean() - _lum(col[near_s]).mean()))
        d_to_skin_h, d_to_arm_h = dt(~h_skin), dt(~h_arm)
        hd_step = side(h_arm, h_skin, cp["col"], d_to_arm_h, d_to_skin_h)
        d_to_skin_c = dt(~c_skin)
        cl_step = side(c_arm, c_skin, cp["ccol"], d_to_arm, d_to_skin_c)
        if hd_step is not None and cl_step is not None:
            m["seam_step_hd"], m["seam_step_cls"] = round(hd_step, 1), round(cl_step, 1)
            m["seam_step_delta"] = round(hd_step - cl_step, 1)
    if want_masks:
        m["_masks"] = {"gap": gap_b | gap_h, "spill": spill_s | spill_o | skin_o, "hole": hole, "gap_e": gap_e}
        m["_cp"] = cp
    return m


def work(item):
    kind, name_or_tuple = item
    t = time.time()
    try:
        if kind == "layer":
            r = layer_fit(name_or_tuple)
        else:
            r = analyze(list(name_or_tuple))
    except Exception as e:                                  # noqa: BLE001
        r = {"error": "%s: %s" % (type(e).__name__, e)}
    r["_kind"], r["_key"] = kind, name_or_tuple
    r["_sec"] = round(time.time() - t, 2)
    return r


# ---------------------------------------------------------------- перепись

def split_key(k):
    return k[0], int(k[1:])


def census(arms, have):
    """pairs: список (броня, внешность, кортеж слоёв с HD, full, кортеж всех слоёв)."""
    pairs = []
    for arm, keys in arms.items():
        for look, names in keys.items():
            hdn = [n for n in names if n.lower() in have]
            if not hdn:
                continue
            body = [n for n in hdn if kind_of(n) == 0]
            if not body:
                continue
            full = len(hdn) == len(names)
            has_armor = any(kind_of(n) == 2 for n in hdn)
            pairs.append((arm, look, tuple(hdn), full, has_armor))
    return pairs


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--workers", type=int, default=max(2, min(20, (os.cpu_count() or 4) - 4)))
    ap.add_argument("--tol", type=int, default=THR["tol"])
    ap.add_argument("--thr", default="", help="JSON с порогами поверх THR")
    ap.add_argument("--no-sheets", action="store_true")
    ap.add_argument("--sheet-pairs", type=int, default=12)
    ap.add_argument("--limit", type=int, default=0, help="только первые N разных кукол (проба)")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--layers", default="", help="папка слоёв вместо pipe_pilot/layers")
    ap.add_argument("--pairs", default="", help='только эти пары: "БРОНЯ:M0,M51,F58;БРОНЯ2:F1"')
    a = ap.parse_args()
    global LAYERS
    LAYERS = a.layers or LAYERS
    thr = dict(THR)
    if a.thr:
        thr.update(json.loads(a.thr))
    thr["tol"] = a.tol
    a.thr_gray = thr["layer_gray_blob_px"]
    os.makedirs(a.out, exist_ok=True)
    t0 = time.time()

    have = {os.path.splitext(f)[0].lower() for f in os.listdir(LAYERS) if f.lower().endswith(".png")}
    arms = db.armor_layers()
    pairs_body = census(arms, have)         # все пары, где есть HD-тело (включая броню без единой HD-вещи)
    pairs = [p for p in pairs_body if p[3] or p[4]]     # меряем: HD-кукла целиком или хоть одна HD-вещь брони
    # перепись
    all_names = {n for keys in arms.values() for names in keys.values() for n in names}
    if a.pairs:
        want = {(arm, look) for part in a.pairs.split(";") for arm, looks in [part.split(":")] for look in looks.split(",")}
        pairs = [p for p in pairs if (p[0], p[1]) in want]
        lost = want - {(p[0], p[1]) for p in pairs}
        if lost:
            sys.exit("нет таких пар или у них нет HD-слоёв: %s" % sorted(lost))
        all_names = {n for p in pairs for n in p[2]}
    hd_names = sorted(n for n in all_names if n.lower() in have)
    armor_hd = [n for n in hd_names if kind_of(n) == 2]
    pair_full = [p for p in pairs if p[3]]
    comp = {}                       # кортеж слоёв -> список (броня, внешность)
    for arm, look, hdn, full, has_armor in pairs:
        comp.setdefault(hdn, []).append((arm, look, full))
    # какие вещи брони общие для всех внешностей брони
    per_armor = {}
    for arm in {p[0] for p in pairs}:
        sets = collections.defaultdict(set)
        for look, names in arms[arm].items():
            for n in names:
                if kind_of(n) == 2 and n.lower() in have:
                    sets[n].add(look)
        nlooks = len(arms[arm])
        per_armor[arm] = {"looks": nlooks,
                          "hd_armor_layers": {n: len(s) for n, s in sorted(sets.items())},
                          "full_looks": sum(1 for p in pairs if p[0] == arm and p[3]),
                          "hd_looks": sum(1 for p in pairs if p[0] == arm)}
    cen = {
        "armors_with_layers_definition": len(arms),
        "armors_with_any_hd_layer": len({p[0] for p in pairs_body}),
        "armors_with_hd_armor_layer": len({p[0] for p in pairs if p[4]}),
        "armors_full_hd_for_some_look": sorted({p[0] for p in pair_full}),
        "hd_layer_files": len(have),
        "hd_layers_used_by_armors": len(hd_names),
        "hd_body_files": sum(1 for n in hd_names if kind_of(n) == 0),
        "hd_head_files": sum(1 for n in hd_names if kind_of(n) == 1),
        "hd_armor_files": armor_hd,
        "pairs_with_hd_body": len(pairs_body),
        "pairs_hd_any": len(pairs),
        "pairs_hd_with_armor_layer": sum(1 for p in pairs if p[4]),
        "pairs_full_hd": len(pair_full),
        "pairs_full_hd_with_armor_layer": sum(1 for p in pair_full if p[4]),
        "distinct_compositions": len(comp),
        "distinct_compositions_full": len({p[2] for p in pair_full}),
        "armor_layer_shared_across_looks": {},
        "per_armor": per_armor,
    }
    # общие слои брони: у скольких внешностей брони тот же файл
    shared_all = {}
    for arm, v in per_armor.items():
        shared_all[arm] = {n: (c == v["looks"]) for n, c in v["hd_armor_layers"].items()}
    cen["armor_layer_shared_across_looks"] = shared_all

    jobs = [("layer", n) for n in hd_names] + [("pair", k) for k in sorted(comp, key=lambda t: t[::-1])]
    if a.limit:
        jobs = [j for j in jobs if j[0] == "layer"][:a.limit] + [j for j in jobs if j[0] == "pair"][:a.limit]
    print("слоёв HD %d, пар %d, разных кукол %d, процессов %d" % (len(hd_names), len(pairs), len(comp), a.workers), flush=True)
    res = {}
    with mp.Pool(a.workers, initializer=init_worker, initargs=(a.tol, LAYERS)) as pool:
        done = 0
        for r in pool.imap_unordered(work, jobs, chunksize=2):
            res[(r["_kind"], r["_key"])] = r
            done += 1
            if done % 100 == 0:
                print("  %d/%d  %.0f c" % (done, len(jobs), time.time() - t0), flush=True)
    errs = {k: v["error"] for k, v in res.items() if "error" in v}
    layers = {k[1]: v for k, v in res.items() if k[0] == "layer" and "error" not in v}
    comps = {k[1]: v for k, v in res.items() if k[0] == "pair" and "error" not in v}

    # ---- брак слоёв
    flags = {"layers": [], "pairs": [], "info_underwear": []}
    for n, r in sorted(layers.items()):
        why = []
        if r.get("empty"):
            why.append("пусто: " + r["empty"])
        else:
            if r["shift_px"] > thr["layer_shift_px"]:
                why.append("сдвиг %.1f px (%.1f, %.1f)" % (r["shift_px"], r["shift_dx"], r["shift_dy"]))
            if r["outside_pct"] > thr["layer_outside_pct"]:
                why.append("вылезло за контур %.2f%%" % r["outside_pct"])
            if r["uncovered_pct"] > thr["layer_uncovered_pct"]:
                why.append("не закрыто %.2f%%" % r["uncovered_pct"])
            if r.get("gray_blob_max_px", 0) >= thr["layer_gray_blob_px"]:
                why.append("серая заплатка на теле %d px в (x,y)=%s" % (r["gray_blob_max_px"], r["gray_blob_at"][0]))
            if r.get("band_mismatch_pct", 99) < thr["layer_stair_pct"]:
                why.append("край = лесенка классики x4 (%.2f%% расхождения в пояске)" % r["band_mismatch_pct"])
        if why:
            flags["layers"].append({"name": n, "kind": r["kind"], "why": why})
    # ---- пары
    rows = []
    for key, r in comps.items():
        for arm, look, full in comp[key]:
            rows.append({"armor": arm, "look": look, "full": full, "layers": list(key), **{k: v for k, v in r.items() if not k.startswith("_")}})
    rows.sort(key=lambda r: (r["armor"], r["look"]))     # порядок armor_layers() от прогона к прогону разный
    for row in rows:
        why = []
        if row["bad_pct"] > thr["pair_bad_pct"]:
            why.append("итого %.2f%% силуэта" % row["bad_pct"])
        if row["gap_deep_px"] > thr["pair_gap_deep_px"]:
            why.append("просвет тела %d px" % row["gap_deep_px"])
        if row["hole_px"] > thr["pair_hole_px"]:
            why.append("дыра %d px" % row["hole_px"])
        if not row["full"]:
            # у неполных кукол классика собрана из тех же слоёв без недостающих вещей: "голое место классики" не определено
            for k in ("dark_body_px", "dark_bare_px", "dark_bare_pct"):
                row.pop(k, None)
        if row.get("dark_bare_pct", 0) > thr["pair_dark_bare_pct"]:
            # не брак геометрии, а расхождение с классикой по решению (R-588, DECISIONS 2026-11-03: бельё запечено в HD-теле)
            flags["info_underwear"].append({"armor": row["armor"], "look": row["look"], "dark_bare_px": row["dark_bare_px"], "dark_bare_pct": row["dark_bare_pct"]})
        if row.get("lum_corr", 1) < thr["pair_lum_corr_min"]:
            why.append("светлота внутри силуэта почти не похожа на классику (корр. %.2f)" % row["lum_corr"])
        row["why"] = why
        if why:
            flags["pairs"].append({"armor": row["armor"], "look": row["look"], "full": row["full"], "bad_pct": row["bad_pct"], "why": why})

    # ---- сводки по внешностям, бронёй и слоям
    def agg(keyf, only_armor=True):
        g = collections.defaultdict(list)
        for row in rows:
            if only_armor and not any(kind_of(n) == 2 for n in row["layers"]):
                continue
            g[keyf(row)].append(row)
        out = {}
        for k, v in g.items():
            out[k] = {"pairs": len(v), "bad_pct_mean": round(float(np.mean([x["bad_pct"] for x in v])), 3),
                      "bad_pct_max": round(float(np.max([x["bad_pct"] for x in v])), 3),
                      "gap_deep_px_mean": round(float(np.mean([x["gap_deep_px"] for x in v])), 1),
                      "hole_px_mean": round(float(np.mean([x["hole_px"] for x in v])), 1),
                      "flagged": sum(1 for x in v if x["why"])}
        return out
    by_look = agg(lambda r: r["look"])
    by_armor = agg(lambda r: r["armor"])
    by_layer = collections.defaultdict(lambda: {"gap_under_px": 0, "spill_by_px": 0, "compositions": 0})
    for key, r in comps.items():
        for n, d in r["by_layer"].items():
            by_layer[n]["gap_under_px"] += d.get("gap_under", 0)
            by_layer[n]["spill_by_px"] += d.get("spill_by", 0)
            by_layer[n]["compositions"] += 1
    # разные тела: как отличаются классические маски и HD-посадка тел
    body_rows = {n: r for n, r in layers.items() if r["kind"] == 0}
    bodies = {}
    if body_rows:
        for g in ("M", "F"):
            ns = sorted(n for n in body_rows if n.split("__")[2][0] == g)
            if not ns:
                continue
            masks = np.stack([cls_idx_main(n) != 0 for n in ns])
            cons = masks.mean(0) >= 0.5
            ious = [float((m & cons).sum()) / float((m | cons).sum()) for m in masks]
            bodies[g] = {"n": len(ns), "classic_iou_to_median_mean": round(float(np.mean(ious)), 4),
                         "classic_iou_to_median_min": round(float(np.min(ious)), 4),
                         "classic_area_min": int(masks.sum((1, 2)).min()), "classic_area_max": int(masks.sum((1, 2)).max()),
                         "hd_outside_pct_mean": round(float(np.mean([body_rows[n]["outside_pct"] for n in ns])), 3),
                         "hd_uncovered_pct_mean": round(float(np.mean([body_rows[n]["uncovered_pct"] for n in ns])), 3),
                         "hd_shift_px_max": round(float(np.max([body_rows[n]["shift_px"] for n in ns])), 2)}

    report = {"made": time.strftime("%Y-%m-%d %H:%M:%S"), "seconds": round(time.time() - t0, 1), "thresholds": thr,
              "census": cen, "errors": errs, "layers": layers, "compositions": len(comps),
              "pairs": rows, "flags": flags,
              "summary": {"by_look": {k: by_look[k] for k in sorted(by_look, key=lambda s: (s[0], int(s[1:])))},
                          "by_armor": by_armor, "by_layer": by_layer, "bodies": bodies,
                          "pairs_flagged": len(flags["pairs"]), "layers_flagged": len(flags["layers"])}}
    with open(os.path.join(a.out, "report.json"), "w", encoding=ENC) as f:
        json.dump(report, f, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print("report.json: слоёв %d (брак %d), кукол %d, пар %d (брак %d), ошибок %d, %.0f c" % (
        len(layers), len(flags["layers"]), len(comps), len(rows), len(flags["pairs"]), len(errs), time.time() - t0), flush=True)

    if not a.no_sheets:
        init_worker(a.tol)
        make_sheets(a, rows, layers, comps, random.Random(a.seed))
    print("готово, %.0f c" % (time.time() - t0))


def a_thr_gray(a):
    return a.thr_gray


def cls_idx_main(name):
    global _files
    if _files is None:
        _files = db.sprite_files()
    return cls_idx(name)


# ---------------------------------------------------------------- листы

def font(sz):
    for p in (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\segoeui.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, sz)
    return ImageFont.load_default()


def classic_rgb(cp):
    return np.clip(cp["ccol"], 0, 255).astype(np.uint8), (cp["own_c"] >= 0)


def pair_block(row, thr_tol):
    m = analyze(row["layers"], want_masks=True)
    cp, mk = m["_cp"], m["_masks"]
    bg = np.array([58, 58, 66], np.uint8)
    c_rgb, c_any = classic_rgb(cp)
    c_img = np.where(c_any[..., None], c_rgb, bg)
    A = cp["A"][..., None]
    h_img = (cp["col"] / np.maximum(A, 1e-3)).clip(0, 255)
    h_img = np.where(A > 0.01, h_img * A + bg * (1 - A), bg).astype(np.uint8)
    ov = (h_img.astype(np.float32) * 0.55 + bg * 0.45)
    for mask, color in ((mk["gap_e"], (90, 90, 90)), (mk["gap"], (255, 40, 40)), (mk["spill"], (255, 60, 255)), (mk["hole"], (255, 240, 0))):
        ov[mask] = color
    ov = ov.astype(np.uint8)
    any_ = c_any | (cp["own_h"] >= 0)
    ys, xs = np.nonzero(any_)
    mg = 20
    y0, y1, x0, x1 = max(ys.min() - mg, 0), min(ys.max() + mg, HH), max(xs.min() - mg, 0), min(xs.max() + mg, HW)
    panels = [c_img[y0:y1, x0:x1], h_img[y0:y1, x0:x1], ov[y0:y1, x0:x1]]
    return panels, m


def make_sheets(a, rows, layers, comps, rnd):
    f1, f2 = font(22), font(18)
    wide = [r for r in rows if any(kind_of(n) == 2 for n in r["layers"])]
    rank = sorted(wide, key=lambda r: -r["bad_pct"])
    # один кадр на одну собранную куклу (разные брони с тем же набором слоёв дают тот же кадр)
    seen, worst = set(), []
    for r in rank:
        k = tuple(r["layers"])
        if k in seen:
            continue
        seen.add(k)
        worst.append(r)

    def sheet(sel, path, cols=2, title=""):
        blocks = []
        for r in sel:
            panels, m = pair_block(r, a.tol)
            ph, pw = panels[0].shape[:2]
            cap = ["%s  %s%s" % (r["armor"], r["look"], "" if r["full"] else "  (часть слоёв HD)"),
                   "итог %.2f%%  просвет %d  вылезло %d  дыра %d  шов-тонкий %d  бельё на голом %d (%.2f%%)  шея %s" % (
                       r["bad_pct"], r["gap_deep_px"], r["spill_skin_px"] + r["spill_out_px"] + r["skin_out_px"], r["hole_px"], r["thin_seam_px"],
                       r.get("dark_bare_px", 0), r.get("dark_bare_pct", 0), r.get("neck_step", "-")),
                   "слева классика x4 | HD | наложение: красный просвет, фиолетовый вылезло, жёлтый дыра"]
            blocks.append((panels, cap))
        bw = max(sum(p.shape[1] for p in b[0]) + 40 for b in blocks)
        bh = max(max(p.shape[0] for p in b[0]) + 100 for b in blocks)
        rws = (len(blocks) + cols - 1) // cols
        im = Image.new("RGB", (bw * cols, bh * rws + 50), (24, 24, 28))
        d = ImageDraw.Draw(im)
        d.text((10, 8), title, fill=(255, 255, 255), font=f1)
        for i, (panels, cap) in enumerate(blocks):
            ox, oy = (i % cols) * bw, 50 + (i // cols) * bh
            for j, line in enumerate(cap):
                d.text((ox + 10, oy + 4 + j * 24), line, fill=(235, 235, 235), font=f2 if j else f1)
            x = ox + 10
            for p in panels:
                im.paste(Image.fromarray(p), (x, oy + 80))
                x += p.shape[1] + 10
        im.save(path)
        print("лист", path, im.size, flush=True)

    n = a.sheet_pairs

    def uniq(rank_rows):
        s, o = set(), []
        for r in rank_rows:
            k = tuple(r["layers"])
            if k not in s:
                s.add(k)
                o.append(r)
        return o
    if a.pairs:
        sheet(uniq(rows), os.path.join(a.out, "sheet_pairs_probe.png"), cols=1, title="Проба посадки: " + a.pairs)
        return
    sheet(worst[:n], os.path.join(a.out, "sheet_pairs_worst_geometry.png"), title="Худшие куклы по геометрии посадки (просвет+вылезло+дыра)")
    sheet(uniq(sorted([r for r in rows if "dark_bare_pct" in r and r["full"]], key=lambda r: -r["dark_bare_pct"]))[:n],
          os.path.join(a.out, "sheet_pairs_worst_underwear.png"), title="Больше всего запечённого белья там, где классика голая (только полностью HD куклы)")
    sheet(uniq(sorted([r for r in rows if "lum_corr" in r and r["full"]], key=lambda r: r["lum_corr"]))[:n],
          os.path.join(a.out, "sheet_pairs_lowest_lumcorr.png"), title="Меньше всего похожая на классику светлота внутри силуэта (полностью HD куклы)")
    nude = [r for r in rows if r["full"] and not any(kind_of(x) == 2 for x in r["layers"])]
    rnd.shuffle(nude)
    sheet(uniq(nude)[:n], os.path.join(a.out, "sheet_pairs_nude_random.png"), title="Голые куклы (тело без вещей брони), случайные")
    good = [r for r in wide if r["bad_pct"] <= np.median([x["bad_pct"] for x in wide])]
    gs, seen2 = [], set()
    rnd.shuffle(good)
    for r in good:
        k = tuple(r["layers"])
        if k not in seen2:
            seen2.add(k)
            gs.append(r)
    sheet(gs[:n], os.path.join(a.out, "sheet_pairs_good_sample.png"), title="Случайная выборка пар лучше медианы")
    full = [r for r in rows if r["full"] and any(kind_of(x) == 2 for x in r["layers"])]
    rnd.shuffle(full)
    sheet(full[:n], os.path.join(a.out, "sheet_pairs_full_random.png"), title="Случайные куклы, у которых HD есть у каждого слоя (в игре они HD)")

    # листы слоёв: все вещи брони и худшие тела
    def layer_cell(name):
        r = layers[name]
        c4 = rep4(cls_idx(name) != 0)
        rgba = hd_rgba(name)
        hd = rgba[..., 3] >= A_ON
        ys, xs = np.nonzero(c4 | hd)
        if not len(xs):
            return None, r
        mg = 16
        y0, y1, x0, x1 = max(ys.min() - mg, 0), min(ys.max() + mg, HH), max(xs.min() - mg, 0), min(xs.max() + mg, HW)
        bg = np.array([58, 58, 66], np.uint8)
        pal = _pal.astype(np.uint8)
        cl = np.where(c4[..., None], rep4(pal[cls_idx(name)]), bg)
        al = rgba[..., 3:4].astype(np.float32) / 255
        hi = (rgba[..., :3] * al + bg * (1 - al)).astype(np.uint8)
        ov = np.full((HH, HW, 3), bg, np.uint8)
        d_c, d_h = dt(c4), dt(hd)
        ov[c4 & hd] = (110, 110, 120)
        ov[c4 & ~hd] = (60, 200, 255)       # классика есть, HD нет
        ov[hd & ~c4] = (255, 60, 255)       # HD вылезло
        ov[c4 & ~hd & (dt(~hd) > a.tol)] = (0, 120, 255)
        ov[hd & ~c4 & (dt(~c4) > a.tol)] = (255, 0, 150)
        return [cl[y0:y1, x0:x1], hi[y0:y1, x0:x1], ov[y0:y1, x0:x1]], r

    def layer_sheet(names, path, title, cols=2):
        blocks = []
        for n in names:
            panels, r = layer_cell(n)
            if panels is None:
                continue
            cap = [n, "сдвиг (%.1f, %.1f) px  вылезло %.2f%%  не закрыто %.2f%%  iou %.3f  пояс-расхождение %.2f%%" % (
                r.get("shift_dx", 0), r.get("shift_dy", 0), r.get("outside_pct", 0), r.get("uncovered_pct", 0), r.get("iou", 0), r.get("band_mismatch_pct", -1)),
                "слева классика x4 | HD | наложение: голубой не закрыто, фиолетовый вылезло"]
            blocks.append((panels, cap))
        if not blocks:
            return
        bw = max(sum(p.shape[1] for p in b[0]) + 40 for b in blocks)
        bh = max(max(p.shape[0] for p in b[0]) + 100 for b in blocks)
        rws = (len(blocks) + cols - 1) // cols
        im = Image.new("RGB", (bw * cols, bh * rws + 50), (24, 24, 28))
        d = ImageDraw.Draw(im)
        d.text((10, 8), title, fill=(255, 255, 255), font=f1)
        for i, (panels, cap) in enumerate(blocks):
            ox, oy = (i % cols) * bw, 50 + (i // cols) * bh
            for j, line in enumerate(cap):
                d.text((ox + 10, oy + 4 + j * 24), line, fill=(235, 235, 235), font=f2 if j else f1)
            x = ox + 10
            for p in panels:
                im.paste(Image.fromarray(p), (x, oy + 80))
                x += p.shape[1] + 10
        im.save(path)
        print("лист", path, im.size, flush=True)

    # серые заплатки на телах: вырезки 200x200 вокруг самого крупного пятна, x2
    gb = sorted(((r["gray_blob_max_px"], n) for n, r in layers.items() if r.get("gray_blob_max_px", 0) >= a_thr_gray(a)), reverse=True)[:30]
    if gb:
        cells = []
        bg = np.array([200, 0, 200], np.uint8)
        for px, n in gb:
            x, y = layers[n]["gray_blob_at"][0]
            im = hd_rgba(n)
            al = im[..., 3:4].astype(np.float32) / 255
            rgb = (im[..., :3] * al + bg * (1 - al)).astype(np.uint8)
            x0, y0 = int(np.clip(x - 100, 0, HW - 200)), int(np.clip(y - 100, 0, HH - 200))
            c = Image.fromarray(rgb[y0:y0 + 200, x0:x0 + 200]).resize((400, 400), Image.NEAREST)
            ImageDraw.Draw(c).text((6, 4), "%s %d px" % (n.split("__")[2], px), fill=(255, 255, 255), font=f2)
            cells.append(c)
        cols = 6
        rws = (len(cells) + cols - 1) // cols
        sh = Image.new("RGB", (cols * 404, rws * 404 + 40), (24, 24, 28))
        ImageDraw.Draw(sh).text((10, 8), "Серые пятна на телах (самое крупное пятно в центре вырезки, x2), всего тел с пятном %d" % len(gb), fill=(255, 255, 255), font=f1)
        for i, c in enumerate(cells):
            sh.paste(c, ((i % cols) * 404, 40 + (i // cols) * 404))
        p = os.path.join(a.out, "sheet_body_gray_blobs.png")
        sh.save(p)
        print("лист", p, sh.size, flush=True)

    arm_names = sorted(n for n, r in layers.items() if r["kind"] == 2)
    layer_sheet(arm_names[:5], os.path.join(a.out, "sheet_layers_armor_1.png"), "Вещи брони против классики (1)", cols=1)
    layer_sheet(arm_names[5:], os.path.join(a.out, "sheet_layers_armor_2.png"), "Вещи брони против классики (2)", cols=1)
    bod = sorted((n for n, r in layers.items() if r["kind"] != 2 and "outside_pct" in r), key=lambda n: -(layers[n]["outside_pct"] + layers[n]["uncovered_pct"] + layers[n]["shift_px"]))
    layer_sheet(bod[:6], os.path.join(a.out, "sheet_layers_body_head_worst.png"), "Худшие тела и головы против классики", cols=2)


if __name__ == "__main__":
    mp.freeze_support()
    main()
