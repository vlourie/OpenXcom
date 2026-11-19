# -*- coding: utf-8 -*-
"""Шов пола HD без просвета фона (грабли R-439, тикет XP-000211).

Пол (тип 0 в MCD) лежит прямо на фоне, соседние клетки кладутся встык. Если кромка ромба полупрозрачна
с двух сторон шва, сквозь пол виден тёмный фон - по каждой клетке тянется сетка. Судить по кромке одного
кадра нельзя: полупрозрачный выступ за ромбом ложится на непрозрачную середину соседа и сетки не даёт
(CULTAN:25 - альфа 128 по выступу, а сетка 3x3 ровная). Поэтому мера - ПРОСВЕТ ЗАМОЩЕНИЯ: кадр кладётся
сеткой 3x3, как клетки в игре, и внутри ромба средней клетки считаются пиксели, где суммарная альфа
ниже 250, а классика тем же замощением пиксель закрывает.

Предметы (тип 3) и стены лежат поверх пола - их мягкая кромка ложится на пол, а не на фон: не трогаем.

Починка - у шва (мера ромба от BAND), непрозрачно:
  * точный ромб x k с перехлёстом OVERLAP (R-291), но только там, где рядом есть силуэт классики
    (зубцы лесенки базы закрываются, а пустая половина куска пола - треугольника - не дорисовывается);
  * в клине 1/8 x 1/8 у верхней вершины - только силуэт классики (R-247: сквозь угол видны выступы соседей).
Внутренний край куска пола (диагональ треугольника) в полосу шва не входит - его мягкая альфа задумана.
Цвет бывшего полупрозрачного пикселя - он сам поверх ближайшего непрозрачного пикселя кадра (то, что было
бы видно поверх материала соседа): кромка тоном середины, а не чёрной рамкой (rgb прозрачных - мусор).

    py -3.13 tools\\hdart\\rim_alpha.py census                    # перепись -> census/rim_alpha/rim_census.tsv
    py -3.13 tools\\hdart\\rim_alpha.py sheet --cls fix --batch 1  # листы 3x3 до / после
    py -3.13 tools\\hdart\\rim_alpha.py install --cls fix --batch 1
    py -3.13 tools\\hdart\\rim_alpha.py check                     # защита R-439: полов с просветом нет
"""
import argparse
import hashlib
import io
import os
import re
import sys
from collections import Counter
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
os.chdir(ROOT)

import common  # noqa: E402
import extract_pck  # noqa: E402
import xcom_sprites as xs  # noqa: E402

ENC = "utf-8-sig"
OUT = os.path.join("census", "rim_alpha")
CENSUS = os.path.join(OUT, "rim_census.tsv")
REVIEW = os.path.join("art", "_review", "rim_alpha")
SKIP = os.path.join("tools", "hdart", "rim_alpha_skip.txt")
GAME = os.path.join(common.GAME_HD, "hd")
DATA = [os.path.join(common.PIRATEZ, "TERRAIN"), os.path.join(common.INSTALL, "UFO", "TERRAIN")]
VERSION = "rim_alpha.py 22.10 v2"

SOLID = 250         # пиксель непрозрачен с этой альфы
LEAK = 4.0          # просвет у шва больше стольких пикселей классики (k*k пикселей HD) - сетка
BODY = 0.05         # середина ромба полупрозрачна на такую долю - прозрачность задумана (вода, стекло)
FLAT_TOP = 22       # плоский пол: строки силуэта классики не выше этой
BAND = 0.85         # полоса шва: мера ромба от этой (0 центр, 1 граница клетки)
OVERLAP = 0.04      # перехлёст точного ромба за границу клетки (R-291)
WEDGE = 0.125       # клин у верхней вершины, где альфа - только силуэт классики (R-247)
FILL_SIGMA = 2.0    # размытие тона середины для кромки, пикселей HD
VOID = 16          # пустота классики в ромбе больше стольких пикселей - кусок пола, не трогаем
OWN_A = 24          # альфа ниже этой - rgb пикселя мусор, берётся тон середины

COLS = ["набор", "кадр", "класс", "причина", "генератор", "типы", "плоский", "k", "ромб",
        "просвет", "доля", "просвет_после", "пикселей", "середина_lt250", "rgb_мусор", "пустота", "шов", "sha"]


def diamond(k, fw=32, fh=40):
    """-> (мера ромба, u, v) на пиксель кадра x k: 0 центр, 1 граница клетки; u, v - от верхней вершины."""
    ys, xs_ = np.mgrid[0:fh * k, 0:fw * k].astype(np.float32)
    dx = ((xs_ + 0.5) / k - fw / 2.0) / (fw / 2.0)
    dy = ((ys + 0.5) / k - (fh - 16.0)) / 8.0          # 0 - верхняя вершина ромба, 2 - нижняя
    d = np.abs(dx) + np.abs(dy - 1.0)
    d[dy < 0] = np.maximum(d[dy < 0], 99.0)
    return d, (dy + dx) / 2.0, (dy - dx) / 2.0


def silhouette(fr, k):
    return np.kron(fr != 0, np.ones((k, k), bool))


def tiling(alpha, k, fw=32, fh=40):
    """Суммарная альфа (0..1) сетки 3x3 одного кадра на холсте и сдвиг средней клетки."""
    h, w = alpha.shape
    W, H = fw * k, 8 * k                               # шаг клетки: 32k по x, 16k по y (половины)
    cv = np.ones((h + 4 * H, w + 2 * W), np.float32)    # доля фона, пропущенная насквозь
    t = 1.0 - alpha.astype(np.float32) / 255.0
    for r in range(3):
        for c in range(3):
            x0 = W + (c - r) * W // 2
            y0 = (c + r) * H
            cv[y0:y0 + h, x0:x0 + w] *= t
    return 1.0 - cv, (W, 2 * H)


def seam_ratio(rgba, k, fw=32, fh=40):
    """Яркость шва к яркости середины средней клетки сетки 3x3 на чёрном фоне (как в игре): тёмная сетка -
    меньше 1. Шов - мера ромба 0.88-1, середина - 0.45-0.8."""
    h, w = rgba.shape[:2]
    W, H = fw * k, 8 * k
    cv = np.zeros((h + 4 * H, w + 2 * W), np.float32)
    lum = rgba[..., :3].astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)
    a = rgba[..., 3].astype(np.float32) / 255.0
    for r in range(3):
        for c in range(3):
            x0, y0 = W + (c - r) * W // 2, (c + r) * H
            sl = cv[y0:y0 + h, x0:x0 + w]
            sl *= 1 - a
            sl += lum * a
    d, _, _ = diamond(k, fw, fh)
    mid = cv[2 * H:2 * H + h, W:W + w]
    seam, body = (d >= 0.88) & (d < 1.0), (d >= 0.45) & (d < 0.8)
    return float(mid[seam].mean() / max(1.0, mid[body].mean()))


_PAL = []


def classic_rgba(fr, k):
    if not _PAL:
        _PAL.append(np.array(xs.load_palette_file(os.path.join(common.PIRATEZ, "Resources", "Pals",
                                                               "delicious_regular.pal")), np.uint8))
    pal = _PAL[0]
    img = np.zeros(fr.shape + (4,), np.uint8)
    img[..., :3] = pal[fr]
    img[..., 3] = np.where(fr != 0, 255, 0)
    return np.kron(img, np.ones((k, k, 1), np.uint8))


def leak(alpha, op, k, fw=32, fh=40):
    """-> (просвет, закрыто классикой) в ромбе средней клетки сетки 3x3."""
    hd, (x0, y0) = tiling(alpha, k, fw, fh)
    cl, _ = tiling(np.where(silhouette(op, k), 255, 0), k, fw, fh)
    d, _, _ = diamond(k, fw, fh)
    m = np.zeros(hd.shape, bool)
    m[y0:y0 + fh * k, x0:x0 + fw * k] = (d < 1.0) & (d >= BAND)     # у шва: внутренний край куска - не сетка
    cov = m & (cl > 0.99)
    return int((cov & (hd < SOLID / 255.0)).sum()), int(cov.sum())


def seam_mask(op, k, fw=32, fh=40):
    """Пиксели, которые у шва должны быть непрозрачны (см. шапку)."""
    from scipy import ndimage
    d, u, v = diamond(k, fw, fh)
    # зубцы лесенки базы: до 2 пикселей классики вбок от силуэта
    near = ndimage.binary_dilation(op, structure=np.ones((1, 5), bool))
    near = np.kron(near, np.ones((k, k), bool))
    sil = silhouette(op, k)
    band = (d >= BAND) & (d < 99)
    wedge = (u < WEDGE) & (v < WEDGE)
    exact = band & (d <= 1.0 + OVERLAP) & near & ~wedge
    # середина - по силуэту классики (её дыры остаются дырами): мягкая альфа вглубь от шва иначе даёт
    # ступень на границе полосы - пилу по шву (FOREST_WASTE:8, альфа 160-190 уже на мере 0.8)
    # клин нижней вершины: выступ силуэта классики за ромб закрывает верхнюю вершину клетки ниже (у неё
    # там только силуэт - R-247), иначе в каждой вершине четырёх клеток точка фона (R-291)
    # то же - боковые вершины: их выступ (пиксели классики 0 и 31 строки 32) закрывает верхнюю вершину соседа
    hi_u, hi_v = u > 1 - WEDGE, v > 1 - WEDGE
    tip = band & sil & ((hi_u & hi_v) | (hi_u & (v < WEDGE)) | (hi_v & (u < WEDGE)))
    return exact | tip | (band & wedge & sil) | (sil & (d < BAND))


def void(op, fw=32, fh=40):
    """Наибольшая связная пустота классики внутри ромба, пикселей классики: кусок пола (треугольник,
    край у пустоты) - десятки и сотни, дыры решётки или сетки - единицы."""
    from scipy import ndimage
    d = xs.diamond_distance(fw, fh) <= 1.0
    lab, n = ndimage.label(d & ~op)
    return int(np.bincount(lab.ravel())[1:].max()) if n else 0


def fill(cur):
    """Тон середины рядом: размытое среднее непрозрачных пикселей (сигма FILL_SIGMA), дальше - ближайший.
    Не ближайший пиксель: тот копирует одиночные блики и тёмные точки в крапины по шву."""
    from scipy import ndimage
    solid = cur[..., 3] >= SOLID
    rgb = cur[..., :3].astype(np.float32)
    if not solid.any():
        return rgb
    w = ndimage.gaussian_filter(solid.astype(np.float32), FILL_SIGMA)
    out = np.dstack([ndimage.gaussian_filter(rgb[..., c] * solid, FILL_SIGMA) for c in range(3)])
    out /= np.maximum(w, 1e-4)[..., None]
    _, ind = ndimage.distance_transform_edt(~solid, return_indices=True)
    far = w < 0.05
    out[far] = rgb[ind[0], ind[1]][far]
    return out


def fixed(cur, op, k, fw=32, fh=40):
    """-> (новый кадр, сколько пикселей стали непрозрачными)."""
    from scipy import ndimage
    a = cur[..., 3].astype(np.float32) / 255.0
    new = cur.copy()
    todo = seam_mask(op, k, fw, fh) & (cur[..., 3] < 255)
    if not todo.any():
        return new, 0
    own = cur[..., :3].astype(np.float32)
    # свой цвет полупрозрачного пикселя - это и есть его цвет (прямая альфа): затирка и фаска по краю плитки
    # остаются своим цветом. Замена тоном середины рвала такие линии в лесенку (URBAN:78, SEAURBANDIO:78).
    # Тон середины - только почти прозрачным пикселям, у них rgb - мусор генератора
    rgb = np.where((cur[..., 3] >= OWN_A)[..., None], own, fill(cur))
    new[..., :3][todo] = np.clip(np.rint(rgb[todo]), 0, 255).astype(np.uint8)
    new[..., 3][todo] = 255
    return new, int(todo.sum())


_SETS = {}


def classic(s):
    """-> (кадры - массивы индексов, типы MCD на кадр - множество, ш, в); кэш на процесс. Индекс 0 прозрачен."""
    if s in _SETS:
        return _SETS[s]
    res = None
    for d in DATA:
        pck = extract_pck.find_ci(d, s + ".PCK")
        if not pck:
            continue
        stem = os.path.splitext(pck)[0]
        tab = extract_pck.find_ci(d, os.path.basename(stem) + ".TAB") or stem + ".TAB"
        fw, fh = xs.frame_size_for(s + ".PCK")
        frames = xs.read_pck(pck, tab, fw, fh)
        types = [set() for _ in frames]
        mcd = extract_pck.find_ci(d, os.path.basename(stem) + ".MCD")
        if mcd:
            for rec in xs.read_mcd(mcd):
                for fr in rec["frames"]:
                    if fr < len(frames):
                        types[fr].add(rec["type"])
        arr = [None if f is None else np.array(f, dtype=np.uint8) for f in frames]
        res = (arr, types, fw, fh)
        break
    _SETS[s] = res
    return res


def measure(job):
    s, f, rel, gen, sha = job
    row = dict.fromkeys(COLS, "")
    row.update({"набор": s, "кадр": f, "генератор": gen or "", "sha": (sha or "")[:12]})
    cs = classic(s)
    if cs is None:
        row.update(класс="skip", причина="нет классики набора в Пиратках")
        return row
    frames, types, fw, fh = cs
    if f >= len(frames) or frames[f] is None:
        row.update(класс="skip", причина="кадра нет в классике")
        return row
    tp = types[f]
    row["типы"] = ",".join(str(t) for t in sorted(tp)) or "-"
    if not tp:
        row.update(класс="skip", причина="кадр не в MCD")
        return row
    if 0 not in tp:
        row.update(класс="skip", причина="не пол (тип %s): кромка ложится на пол, не на фон" % row["типы"])
        return row
    if (fw, fh) != (32, 40):
        row.update(класс="skip", причина="кадр не 32x40")
        return row
    try:
        cur = np.array(Image.open(os.path.join(GAME, rel)).convert("RGBA"))
    except Exception:
        row.update(класс="skip", причина="нет HD-файла в игре")
        return row
    k = cur.shape[1] // fw
    if k < 1 or cur.shape[1] != fw * k or cur.shape[0] != fh * k:
        row.update(класс="skip", причина="размер HD не кратен классике")
        return row
    row["k"] = k
    op = frames[f] != 0
    if not op.any():
        row.update(класс="skip", причина="пустой кадр")
        return row
    row["плоский"] = int(np.nonzero(op.any(1))[0].min() >= FLAT_TOP)
    n, cov = leak(cur[..., 3], op, k, fw, fh)
    row["ромб"], row["просвет"] = cov, n
    share = n / float(k * k)
    row["доля"] = "%.1f" % share          # просвет в пикселях классики
    d, _, _ = diamond(k, fw, fh)
    from scipy import ndimage
    body = ndimage.binary_erosion(silhouette(op, k), iterations=2 * k) & (d < BAND)   # без мягкого края куска
    body_t = (body & (cur[..., 3] < SOLID)).sum() / max(1, body.sum())
    row["середина_lt250"] = "%.3f" % body_t
    if share <= LEAK:
        row.update(класс="ok", причина="")
        return row
    new, px = fixed(cur, op, k, fw, fh)
    n2, _ = leak(new[..., 3], op, k, fw, fh)
    row["просвет_после"], row["пикселей"] = n2, px
    ch = (new[..., 3] != cur[..., 3])
    if ch.any():
        # доля ставших непрозрачными пикселей, где rgb генератора - мусор (альфа почти 0), взят тон середины
        row["rgb_мусор"] = "%.2f" % (cur[..., 3][ch] < OWN_A).mean()
    row["пустота"] = void(op, fw, fh)
    if row["пустота"] > VOID:
        row.update(класс="except", причина="кусок пола: пустота классики %d пикс. - край у пустоты задуман "
                                            "мягким, альфа по силуэту дала бы лесенку" % row["пустота"])
    elif body_t >= BODY:
        row.update(класс="review", причина="середина полупрозрачна %.0f%% - прозрачность задумана?" % (100 * body_t))
    elif n2 / float(k * k) > LEAK:
        row.update(класс="review", причина="после починки просвет остался: %d" % n2)
    else:
        row.update(класс="fix", причина="")
    # справочно: яркость шва к середине сетки 3x3 на чёрном - классика / до / после. Судить по ней нельзя:
    # текстура HD у шва и в середине своя (DESERTROCKS_RED:15 классика 1.95, HD 1.03 - и сетка уходит)
    rc, rb, ra_ = (seam_ratio(classic_rgba(frames[f], k), k), seam_ratio(cur, k), seam_ratio(new, k))
    row["шов"] = "%.2f/%.2f/%.2f" % (rc, rb, ra_)
    return row


def manifest():
    import build_hd_pack as bp
    return bp, bp.load()


def jobs(man):
    out = []
    for rel, e in man["files"].items():
        m = re.match(r"TERRAIN/([^/]+)\.PCK/(\d+)\.png$", rel)
        if m:
            out.append((m.group(1), int(m.group(2)), rel, e.get("generator"), e.get("sha256")))
    out.sort(key=lambda j: (j[0], j[1]))     # по наборам: классика набора читается одним процессом
    return out


def load_skip():
    """Исключения: строка «НАБОР:кадр<TAB>причина»."""
    res = {}
    if os.path.exists(SKIP):
        for ln in open(SKIP, encoding=ENC):
            ln = ln.strip()
            if ln and not ln.startswith("#"):
                key, _, why = ln.partition("\t")
                res[key.strip()] = why.strip()
    return res


def survey(js, procs):
    with Pool(procs) as pool:
        rows = list(pool.imap(measure, js, chunksize=64))
    skip = load_skip()
    for r in rows:
        key = "%s:%s" % (r["набор"], r["кадр"])
        if key in skip and r["класс"] in ("fix", "review"):
            r["класс"], r["причина"] = "except", skip[key]
    return rows


def write_tsv(rows, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding=ENC, newline="") as f:
        f.write("\t".join(COLS) + "\n")
        for r in rows:
            f.write("\t".join(str(r[c]) for c in COLS) + "\n")


def read_tsv(path=CENSUS):
    with open(path, encoding=ENC) as f:
        head = f.readline().rstrip("\n").split("\t")
        return [dict(zip(head, ln.rstrip("\n").split("\t"))) for ln in f]


def cmd_census(a):
    bp, man = manifest()
    rows = survey(jobs(man), a.procs)
    write_tsv(rows, CENSUS)
    c = Counter(r["класс"] for r in rows)
    print("кадров TERRAIN в манифесте:", len(rows), dict(c))
    print("полов (тип 0):", sum(1 for r in rows if r["k"] != ""))
    gens = Counter(r["генератор"] for r in rows if r["класс"] in ("fix", "review", "except"))
    print("с просветом по генераторам:", gens.most_common(12))
    why = Counter(re.sub(r"[\d%]+", "N", r["причина"]) for r in rows if r["класс"] != "ok")
    print("причины:", why.most_common(12))
    print("->", CENSUS)
    return 0


def pick(rows, cls, batch, size, sets=None):
    rs = [r for r in rows if r["класс"] == cls]
    if sets:
        rs = [r for r in rs if r["набор"] in sets]
    rs.sort(key=lambda r: (r["набор"], int(r["кадр"])))
    if batch:
        rs = rs[(batch - 1) * size: batch * size]
    return rs


def grid(img, k, bg=(20, 20, 20, 255)):
    h, w = img.shape[:2]
    W, H = 32 * k, 16 * k
    cv = Image.new("RGBA", (W * 4, H * 4 + h), bg)
    t = Image.fromarray(img)
    for r in range(3):
        for c in range(3):
            cv.alpha_composite(t, ((c - r) * W // 2 + W * 3 // 2, (c + r) * H // 2))
    return cv.crop((W // 2, h - H * 2, W * 7 // 2, h + H * 3 // 2))


def cmd_sheet(a):
    rows = read_tsv()
    rs = pick(rows, a.cls, a.batch, a.size, a.sets)
    if not rs:
        print("нечего показывать")
        return 0
    os.makedirs(REVIEW, exist_ok=True)
    tiles = []
    for r in rs:
        s, f = r["набор"], int(r["кадр"])
        rel = "TERRAIN/%s.PCK/%d.png" % (s, f)
        cur = np.array(Image.open(os.path.join(GAME, rel)).convert("RGBA"))
        frames, _, fw, fh = classic(s)
        k = cur.shape[1] // fw
        new, n = fixed(cur, frames[f] != 0, k, fw, fh)
        gs = [grid(classic_rgba(frames[f], k), k), grid(cur, k), grid(new, k)]
        if a.crop:
            # середина сетки: вершина четырёх клеток вблизи
            cx, cy = gs[0].width // 2, gs[0].height // 2 + 8 * k
            box = (cx - 24 * k, cy - 12 * k, cx + 24 * k, cy + 12 * k)
            gs = [g.crop(box) for g in gs]
        sc = a.scale / k
        gs = [g.resize((int(g.width * sc), int(g.height * sc)), Image.LANCZOS if sc < 1 else Image.NEAREST)
              for g in gs]
        gw = gs[0].width
        cell = Image.new("RGB", (gw * 3 + 12, gs[0].height + 14), (60, 60, 60))
        for i, g in enumerate(gs):
            cell.paste(g.convert("RGB"), (i * (gw + 6), 14))
        ImageDraw.Draw(cell).text((2, 1), "%s:%d %s leak %s  classic | before | after" % (
            s, f, r["генератор"][:14], r["доля"]), fill=(255, 255, 0))
        tiles.append(cell)
    cols = a.cols
    w, h = tiles[0].size
    sheet = Image.new("RGB", (w * cols, h * ((len(tiles) + cols - 1) // cols)), (30, 30, 30))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * w, (i // cols) * h))
    name = "%s%s_b%d.png" % (a.cls, "_crop" if a.crop else "", a.batch)
    if a.sets:
        name = "%s_%s" % ("_".join(a.sets)[:40], name)
    out = os.path.join(REVIEW, name)
    sheet.save(out, optimize=True)
    print(len(tiles), "кадров ->", out)
    return 0


def cmd_install(a):
    bp, man = manifest()
    rows = read_tsv()
    rs = pick(rows, a.cls, a.batch, a.size, a.sets)
    rels, total = [], 0
    for r in rs:
        s, f = r["набор"], int(r["кадр"])
        rel = "TERRAIN/%s.PCK/%d.png" % (s, f)
        e = man["files"][rel]
        if e["sha256"][:12] != r["sha"]:
            print("пропуск, кадр сменился после переписи:", rel)
            continue
        cur = np.array(Image.open(bp.blob_path(e["sha256"], rel)).convert("RGBA"))
        frames, _, fw, fh = classic(s)
        k = cur.shape[1] // fw
        new, n = fixed(cur, frames[f] != 0, k, fw, fh)
        if not n:
            continue
        buf = io.BytesIO()
        Image.fromarray(new, "RGBA").save(buf, "PNG", optimize=True)
        old = e["sha256"]
        bp.stage(man, rel, buf.getvalue(), generator="rim_alpha", generator_version=VERSION,
                 source_path=None, approved=True,
                 approval="Vitali 21.10: тикеты как считаешь нужным; XP-000211/R-439 шов пола",
                 derived_from=old, source_frame="%s:%d" % (s, f),
                 note="шов пола непрозрачен (точный ромб у силуэта классики): %d пикселей, просвет %s -> %s" % (
                     n, r["просвет"], r["просвет_после"]))
        man["files"][rel]["replaced"] = old
        rels.append(rel)
        total += n
    if not rels:
        print("нечего ставить")
        return 0
    if a.dry:
        print("проба: %d кадров, %d пикселей шва" % (len(rels), total))
        return 0
    bp.save(man, why="rim_alpha: шов пола R-439, %s партия %s" % (a.cls, a.batch))
    print("game:", bp.install(man, "game", only=rels))
    print("repo:", bp.install(man, "repo", only=rels))
    bad = 0
    for rel in rels:
        for root in (bp.TARGETS["game"], bp.TARGETS["repo"]):
            with open(os.path.join(root, rel), "rb") as fo:
                if hashlib.sha256(fo.read()).hexdigest() != man["files"][rel]["sha256"]:
                    print("РАСХОДИТСЯ", root, rel)
                    bad += 1
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "installed.tsv"), "a", encoding=ENC) as f:
        for rel in rels:
            f.write("%s\t%s\t%s\t%s\n" % (rel, man["files"][rel]["replaced"], man["files"][rel]["sha256"], VERSION))
    print("поставлено %d кадров, %d пикселей шва; расхождений sha: %d" % (len(rels), total, bad))
    return 1 if bad else 0


def cmd_check(a):
    """Защита R-439: пол (тип 0) с просветом замощения вне исключений - ошибка (код 1)."""
    bp, man = manifest()
    js = jobs(man)
    if a.sets:
        js = [j for j in js if j[0] in a.sets]
    rows = survey(js, a.procs)
    bad = [r for r in rows if r["класс"] in ("fix", "review")]
    for r in bad[:30]:
        print("R-439 просвет шва пола: %s:%s %s просвет %s %s" % (
            r["набор"], r["кадр"], r["генератор"], r["просвет"], r["причина"]))
    print("полов проверено: %d, исключений: %d, с просветом вне исключений: %d" % (
        sum(1 for r in rows if r["k"] != ""), sum(1 for r in rows if r["класс"] == "except"), len(bad)))
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("census")
    p.add_argument("--procs", type=int, default=12)
    for n in ("sheet", "install"):
        p = sub.add_parser(n)
        p.add_argument("--cls", default="fix")
        p.add_argument("--batch", type=int, default=0)
        p.add_argument("--size", type=int, default=200)
        p.add_argument("--sets", nargs="*")
        if n == "sheet":
            p.add_argument("--cols", type=int, default=6)
            p.add_argument("--scale", type=float, default=1.0, help="пикселей листа на пиксель классики")
            p.add_argument("--crop", action="store_true", help="вблизи: середина сетки, стык четырёх клеток")
        else:
            p.add_argument("--dry", action="store_true")
    p = sub.add_parser("check")
    p.add_argument("--procs", type=int, default=12)
    p.add_argument("--sets", nargs="*")
    a = ap.parse_args(argv)
    return {"census": cmd_census, "sheet": cmd_sheet, "install": cmd_install, "check": cmd_check}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
