#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000404: радар защиты базы XB2BR 0-9 (4x3 клетки) - заготовки 404A+ (цельный радар по построению).
В мод НИЧЕГО не ставит: кадры - art/tickets/t402_409/cand/404A/<НАБОР>_<кадр>.png (RGBA 128x160), их берёт
t402_409_install.py по слову Vitali.

Рецепт (вариант 404A+, задание командира 30.10):
  1. основа - холст радара целиком на слоте 0: classic x4 как вход Qwen-Image-2.1 strict (путь t276_gen/t300_gen
     do_render, ракурс и свет - battle_view.prompt_block("object")), альфа по объединённому силуэту классики x4
     (R-089), 3 зерна, лучшее выбирает глаз по листу (art/tickets/t404/gen);
  2. анимация - остальные 7 слотов НЕ рисуются (R-071, R-341): HD слота = HD основы + МЯГКАЯ разница классики слота и
     слота 0 (бикубика x4, гаусс SIG_D = 1.75 базы) с весом anim_flicker.weight по маске изменений (запас 1 пикс),
     вне маски - байты основы. Пиксели и прямые края классики не копируются (R-542): по рисунку основы
     переливается свет классики слота;
  3. нарезка - клетка берёт свою часть холста по маске своей классики (NEAREST x4) по смещениям движка
     (x-y)*16, (x+y)*8 (как t364_build.slice_frame); у соседей одни и те же пиксели - шва нет по построению;
  4. перекраски THULBASES02/03, WHITEBASES02/03 - перенос цвета классики своего набора на новые кадры (obj_derive.transfer);
  5. запасной вариант A (если генерация не держит форму) - процедурно по маске классики, один холст на слот
     (t364_build: заливка, бикубика, край-сохраняющее сглаживание), без видеокарты.

    py -3.13 tools\hdart\t404_radar_gen.py preview                 # вход модели и классика холста, без видеокарты
    py -3 tools\gpuq.py add --name t404-radar --prio 1 -- tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\t404_radar_gen.py render
    py -3.13 tools\hdart\t404_radar_gen.py build [--seed N | --procedural]   # кадры -> cand/404A, проверки (BEST = 4041)
    py -3.13 tools\hdart\t404_radar_gen.py sheet                   # лист art/_review/tickets_2026-10-30/t404_cand.png
"""
import argparse
import os
import sys
import time
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (HERE, os.path.join(HERE, "..")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np                                  # noqa: E402
from PIL import Image                               # noqa: E402

STEPS, CFG, MP, ZOOM, GROW, SOFT, PAD, TONE = 40, 4.0, 1.0, 16, 2, 40, 3, 0.7
K = 4
SET = "XB2BR"
GEN = os.path.join(ROOT, "art", "tickets", "t404", "gen")
CAND = os.path.join(ROOT, "art", "tickets", "t402_409", "cand", "404A")
SEEDS = [4041, 4042, 4043]
BEST = 4041                                         # выбор по листу зёрен (art/_review/.../t404_seeds.png)

# раскладка радара по сейву игрока (x30..33, y50..52): локально x 0..3, y 0..2 -> запись MCD
GRID = {(0, 0): 3, (1, 0): 2, (2, 0): 6, (3, 0): 9,
        (1, 1): 1, (2, 1): 5, (3, 1): 8,
        (1, 2): 0, (2, 2): 4, (3, 2): 7}
ALT = {0: 55, 1: 62, 2: 69, 3: 76, 4: 83, 5: 90, 6: 97}     # запись b: слот 0 - кадр b, слот s>0 - ALT[b]+s-1
ORDER = sorted(GRID, key=lambda c: (c[1], c[0]))            # порядок рисования движка: y, потом x

WHAT = ("a sci-fi radar unit: one big round glass cylinder tank filled with glowing green liquid, dark green at "
        "the sides and lighter green swirling wave patterns in the middle of its front, an orange-brown metal rim "
        "ring around the top opening with a dark green inside, an orange diagonal support strut at its lower left, "
        "a small green screen box with an orange frame at the left, an orange copper dome at the right, black "
        "pipes and cables with green and yellow wires at the base, and a flat grey metal grating plate under "
        "everything")
NEG = ", ground, grass, extra objects, text, labels, people, circuit board, flat map"


def frame_of(b, slot):
    return ALT[b] + slot - 1 if (slot > 0 and b in ALT) else b


class Canvas:
    """Холст радара k=1: положение клеток как в движке, PAD вокруг."""

    def __init__(self, grid=GRID, pad=PAD):
        self.cells = [c for c in sorted(grid, key=lambda c: (c[1], c[0]))]
        self.grid = grid
        self.pad = pad
        xs = [(x - y) * 16 for x, y in self.cells]
        ys = [(x + y) * 8 for x, y in self.cells]
        self.x0, self.y0 = min(xs) - pad, min(ys) - pad
        self.cw = max(xs) - self.x0 + 32 + pad
        self.ch = max(ys) - self.y0 + 40 + pad

    def pos(self, c):
        return (c[0] - c[1]) * 16 - self.x0, (c[0] + c[1]) * 8 - self.y0


def classic_k1(sc, setname, f):
    return np.asarray(sc.classic(setname, f))[::4, ::4].copy()          # 40x32x4 uint8


def classic_canvas(sc, cv, slot, setname=SET, recs=None):
    """Классика холста слота k=1: RGBA uint8 (ch, cw, 4)."""
    out = np.zeros((cv.ch, cv.cw, 4), np.uint8)
    for c in cv.cells:
        b = cv.grid[c]
        fr = classic_k1(sc, setname, frame_of(b, slot))
        ox, oy = cv.pos(c)
        reg = out[oy:oy + 40, ox:ox + 32]
        m = fr[..., 3] > 0
        reg[m] = fr[m]
    return out


def model_input(sc):
    """Вход модели: классика слота 0 по габариту с запасом, bicubic x16 на подложке pick_background."""
    import probe_object as po
    cv = Canvas()
    cl = Image.fromarray(classic_canvas(sc, cv, 0), "RGBA")
    bb = cl.split()[3].getbbox()
    box = (max(0, bb[0] - PAD), max(0, bb[1] - PAD), min(cl.width, bb[2] + PAD), min(cl.height, bb[3] + PAD))
    crop = cl.crop(box)
    panel = po.pick_background(crop)
    src = crop.resize((crop.width * ZOOM, crop.height * ZOOM), Image.BICUBIC)
    flat = Image.new("RGBA", src.size, tuple(panel) + (255,))
    flat.alpha_composite(src)
    return cv, cl, box, crop, flat


def do_preview():
    import ticket_scene as ts
    sc = ts.Scene()
    cv, cl, box, crop, flat = model_input(sc)
    os.makedirs(GEN, exist_ok=True)
    flat.convert("RGB").save(os.path.join(GEN, "input.png"))
    big = cl.resize((cl.width * 4, cl.height * 4), Image.NEAREST)
    bg = Image.new("RGBA", big.size, (30, 30, 34, 255))
    bg.alpha_composite(big)
    bg.convert("RGB").save(os.path.join(GEN, "classic_x4.png"))
    print("холст %dx%d, габарит %s, вход %s" % (cv.cw, cv.ch, box, flat.size))


def do_render():
    import argparse as ap_
    import ticket_scene as ts
    import probe_object as po
    import battle_view as bv
    sc = ts.Scene()
    cv, cl, box, crop, flat = model_input(sc)
    os.makedirs(os.path.join(GEN, "raw"), exist_ok=True)
    ns = ap_.Namespace(models=po.gen_hd.DEFAULT_MODELS_DIR, qwen21_model="", qwen21_steps=STEPS,
                       qwen21_cfg=CFG, qwen21_mp=MP, qwen21_strength=0.0, qwen21_offload="model",
                       qwen21_thrifty=False, qwen21_ref="", qwen21_ref_mp=1.0, qwen21_prompt="strict",
                       qwen21_hint="off", qwen21_ref_order="ref-first")
    painter = po.gen_hd.Qwen21Painter(ns, {"ground": ("", "")})
    blk = bv.prompt_block("object")
    po.gen_fire.NEGATIVE = po.NEGATIVE + ", " + blk["negative"] + NEG
    args = ap_.Namespace(steps=STEPS, cfg=CFG, mp=MP)
    prompt = po.STYLE["strict"].replace("{what}", WHAT) + " " + blk["positive"]
    t0 = time.time()
    for n, seed in enumerate(SEEDS, 1):
        dst = os.path.join(GEN, "%d.png" % seed)
        if os.path.exists(dst):
            print("[%d/%d] зерно %d уже есть" % (n, len(SEEDS), seed), flush=True)
            continue
        hd = po.gen_fire.run_pass(painter, args, prompt, flat.convert("RGB"), seed)
        po.gen_hd.save_png(hd, os.path.join(GEN, "raw", "%d.png" % seed))
        part = po.match_tone(po.cut_out(hd, crop, GROW, SOFT), crop, TONE)
        cut = Image.new("RGBA", (cv.cw * 4, cv.ch * 4), (0, 0, 0, 0))
        cut.paste(part, (box[0] * 4, box[1] * 4))
        po.gen_hd.save_png(cut, dst)
        print("[%d/%d] зерно %d готово, %.0f с" % (n, len(SEEDS), seed, time.time() - t0), flush=True)


# ---------------------------------------------------------------------------------------------------------
# сборка: основа -> 8 слотов -> нарезка -> перекраски -> проверки
# ---------------------------------------------------------------------------------------------------------
MARGIN = 1
LUM = np.array([0.299, 0.587, 0.114], np.float32)

# перекраски: набор -> {запись MCD набора: запись XB2BR}; в записи 8 слотов (кадры Frame[0..7])
RECOLOR = {
    "THULBASES02": {33: 0, 35: 1, 37: 2, 39: 3},
    "WHITEBASES02": {33: 0, 35: 1, 37: 2, 39: 3},
    "THULBASES03": {0: 5, 2: 6, 4: 7, 6: 8, 8: 9},
    "WHITEBASES03": {0: 5, 2: 6, 4: 7, 6: 8, 8: 9},
}


def idx_canvas(frames, cv, slot):
    out = np.zeros((cv.ch, cv.cw), np.uint8)
    for c in cv.cells:
        fr = frames[frame_of(cv.grid[c], slot)]
        ox, oy = cv.pos(c)
        reg = out[oy:oy + 40, ox:ox + 32]
        m = fr > 0
        reg[m] = fr[m]
    return out


def up_mask(m):
    return np.repeat(np.repeat(m, K, 0), K, 1)


SIG_D = 1.75           # размытие разницы классики слотов, база: узор классики резкими прямоугольниками не копируется,
                       # разница несёт только перелив света по рисунку основы


def classic_rgb(idx, pal):
    rgb = np.zeros(idx.shape + (3,), np.float32)
    rgb[idx > 0] = pal[idx[idx > 0]][:, :3]
    return rgb


def soft_delta(d):
    """Разница классики слота и слота 0 (k=1, RGB) -> гладкое поле x4: бикубика и гаусс SIG_D базы."""
    import cv2
    big = cv2.resize(d, (d.shape[1] * K, d.shape[0] * K), interpolation=cv2.INTER_CUBIC)
    return cv2.GaussianBlur(big, (0, 0), SIG_D * K)


def build_slots(seed, procedural):
    """-> (cv, {слот: float32 RGB холста x4}, маска x4, индексы классики по слотам)."""
    import water_build as wb
    import t364_build as tb
    import anim_flicker as af
    cv = Canvas()
    frames = wb.read_set(SET)
    pal = wb.palette()
    idx = {s: idx_canvas(frames, cv, s) for s in range(8)}
    m1 = np.zeros(idx[0].shape, bool)
    for s in range(8):
        m1 |= idx[s] > 0
    mk = up_mask(m1)
    lows = {}
    for s in range(8):
        rgb = np.zeros(idx[s].shape + (3,), np.float32)
        rgb[idx[s] > 0] = pal[idx[s][idx[s] > 0]][:, :3]
        lows[s] = tb.low_field(cv, rgb, m1)
    if procedural:
        out = {s: lows[s] for s in range(8)}
    else:
        cut = np.asarray(Image.open(os.path.join(GEN, "%d.png" % seed)).convert("RGBA"), np.float32)
        al = cut[..., 3] / 255.0
        wg = np.clip((al - 0.4) / 0.3, 0, 1)[..., None]
        base = cut[..., :3] * wg + lows[0] * (1 - wg)
        out = {0: base}
        rgb0 = classic_rgb(idx[0], pal)
        for s in range(1, 8):
            w = af.weight(idx[0], idx[s], K, MARGIN)
            out[s] = base + w * soft_delta(classic_rgb(idx[s], pal) - rgb0)
    for s in out:
        out[s] = np.clip(out[s], 0, 255)
        out[s][~mk] = 0
    return cv, out, mk, idx


def cell_frame(sc, cv, canvas, c, f, setname=SET):
    """Кадр клетки c из холста x4: маска - классика кадра f (NEAREST x4)."""
    ox, oy = cv.pos(c)
    sub = canvas[oy * K:(oy + 40) * K, ox * K:(ox + 32) * K]
    cm = np.asarray(sc.classic(setname, f))[..., 3] > 0           # 160x128 - NEAREST x4 классики
    a = np.zeros((40 * K, 32 * K, 4), np.uint8)
    a[..., :3] = np.where(cm[..., None], np.rint(sub), 0).astype(np.uint8)
    a[..., 3] = np.where(cm, 255, 0)
    return Image.fromarray(a, "RGBA")


def slice_all(sc, cv, slots):
    """{(НАБОР, кадр): PIL RGBA 128x160} - все 59 кадров XB2BR."""
    out = {}
    for c in cv.cells:
        b = cv.grid[c]
        for s in range(8 if b in ALT else 1):
            f = frame_of(b, s)
            out[(SET, f)] = cell_frame(sc, cv, slots[s], c, f)
    return out


def luma_corr(a, b, m):
    x, y = a[m], b[m]
    x = x - x.mean()
    y = y - y.mean()
    d = float(np.sqrt((x * x).sum() * (y * y).sum()))
    return float((x * y).sum() / d) if d > 0 else 0.0


def luma(a):
    return a[..., :3].astype(np.float32) @ LUM


def recolors(sc, new):
    """Перекраски: перенос цвета классики своего набора на новые кадры XB2BR. Источник кадра - тот же слот записи XB2BR. -> ({(набор, кадр): PIL}, строки отчёта)."""
    import map_mockup as mm
    import obj_derive as od
    w = mm.World()
    out, rows = {}, []
    for s, recs in RECOLOR.items():
        mcd = w.records(s)
        for rec, xb in recs.items():
            seen = set()
            for slot, f in enumerate(mcd[rec]["frames"]):
                if f in seen:
                    continue
                seen.add(f)
                t = classic_k1(sc, s, f)
                tm = t[..., 3] > 0
                # слот записи набора - тот же слот записи XB2BR (общий лист кадров, порядок петли тот же)
                sl = slot if xb in ALT else 0
                fx = frame_of(xb, sl)
                ob = classic_k1(sc, SET, fx)
                m = (ob[..., 3] > 0) & tm
                cr = luma_corr(luma(ob), luma(t), m) if m.any() else 0.0
                iou = float(((ob[..., 3] > 0) & tm).sum() / max(((ob[..., 3] > 0) | tm).sum(), 1))
                im = od.transfer(new[(SET, fx)], Image.fromarray(ob, "RGBA"), Image.fromarray(t, "RGBA"))
                cm = np.asarray(sc.classic(s, f))[..., 3] > 0
                a = np.asarray(im).copy()
                a[..., 3] = np.where(cm, 255, 0)
                a[~cm, :3] = 0
                out[(s, f)] = Image.fromarray(a, "RGBA")
                rows.append((s, f, xb, (sl, fx), cr, iou))
    return out, rows


def assemble(get, slot, cv=None, bg=(0, 0, 0), k=K):
    """Радар из кадров по смещениям движка: get(кадр) -> PIL RGBA (32k x 40k)."""
    cv = cv or Canvas()
    im = Image.new("RGBA", (cv.cw * k, cv.ch * k), bg + (255,))
    for c in cv.cells:
        spr = get(frame_of(cv.grid[c], slot))
        if spr.width != 32 * k:
            spr = spr.resize((32 * k, 40 * k), Image.NEAREST)
        ox, oy = cv.pos(c)
        im.alpha_composite(spr, (ox * k, oy * k))
    return im


def line_cols(a, valid):
    """Доля строк с одинарной линией (на 12 ярче или темнее обоих соседей) по столбцам."""
    l = a[..., :3].mean(-1)
    p, q, r = l[:, :-2], l[:, 1:-1], l[:, 2:]
    ok = valid[:, :-2] & valid[:, 1:-1] & valid[:, 2:]
    ln = (((q - p > 12) & (q - r > 12)) | ((p - q > 12) & (r - q > 12))) & ok
    cnt, tot = ln.sum(0), ok.sum(0)
    return np.where(tot > 60, cnt / np.maximum(tot, 1), np.nan)


def seam_report(new, sc, slot):
    """Тонкая вертикальная линия по стыкам клеток (столбцы через 16 базы от края клетки) против остальных столбцов."""
    cv = Canvas()
    res = {}
    cands = {
        "классика": lambda f: sc.classic(SET, f),
        "HD сейчас": lambda f: sc.hd(SET, f) or sc.classic(SET, f),
        "новое": lambda f: new[(SET, f)],
    }
    seam_cols = sorted({(cv.pos(c)[0] + 16 * j) * K for c in cv.cells for j in range(0, 3)})
    for name, g in cands.items():
        im = np.asarray(assemble(g, slot, cv)).astype(np.float32)
        valid = im[..., :3].sum(-1) > 0
        fr = line_cols(im, valid)
        sc_ = [v for i in seam_cols for v in fr[max(i - 2, 0):i + 1] if not np.isnan(v)]      # столбцы вокруг разреза
        other = [fr[i] for i in range(len(fr)) if not np.isnan(fr[i]) and all(abs(i + 1 - s) > 3 for s in seam_cols)]
        res[name] = (max(sc_) if sc_ else float("nan"), float(np.percentile(other, 95)) if other else float("nan"),
                     max(other) if other else float("nan"))
    return res


def anim_report(sc, new):
    """Доля изменённых пикселей между слотами: классика против нового HD (разница больше 8 по каналу)."""
    rows = []
    for b in sorted(ALT):
        base = np.asarray(new[(SET, b)])
        cb = np.asarray(sc.classic(SET, b))
        op = cb[..., 3] > 0
        cl, nw = [], []
        for s in range(1, 8):
            f = frame_of(b, s)
            cf = np.asarray(sc.classic(SET, f))
            cl.append(float((np.abs(cf[..., :3].astype(int) - cb[..., :3].astype(int)).max(-1) > 0)[op].mean()))
            hf = np.asarray(new[(SET, f)])
            nw.append(float((np.abs(hf[..., :3].astype(int) - base[..., :3].astype(int)).max(-1) > 8)[op].mean()))
        rows.append((b, float(np.mean(cl)), float(np.mean(nw))))
    return rows


def construction_check(new, sc, cv, slots, mk):
    """Радар из кадров == холст на видимых пикселях (шва по построению нет); силуэт вне классики x4."""
    worst = 0.0
    for s in (0, 3):
        im = np.asarray(assemble(lambda f: new[(SET, f)], s, cv)).astype(np.float32)
        vis = im[..., :3].sum(-1) > 0
        worst = max(worst, float(np.abs(im[..., :3] - np.rint(slots[s]))[vis & mk].max()))
    outside = 0
    for (s_, f), im in new.items():
        a = np.asarray(im)[..., 3] > 0
        cm = np.asarray(sc.classic(SET, f))[..., 3] > 0
        outside += int((a & ~cm).sum())
    return worst, outside


def substrate_report(new, sc):
    """Подложки нет: у кромки (2 пикс x4 внутри силуэта) светлого серого без цвета не больше, чем в классике;
    прозрачные пиксели чистые (RGB 0); непрозрачных вне классики нет."""
    res = {}
    for name, get in (("классика", lambda f: sc.classic(SET, f)), ("новое", lambda f: new[(SET, f)])):
        ring = tot = grey = 0
        dirty = 0
        for b in range(10):
            a = np.asarray(get(b)).astype(int)
            al = a[..., 3] > 0
            er = al.copy()
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    er &= np.roll(np.roll(al, dy, 0), dx, 1)
            edge = al & ~er
            c = a[..., :3]
            lum = c.mean(-1)
            g = (np.abs(c[..., 0] - c[..., 1]) < 8) & (np.abs(c[..., 1] - c[..., 2]) < 10) & (lum > 150)
            ring += int(edge.sum())
            grey += int((g & edge).sum())
            dirty += int((c[~al] != 0).sum())
        res[name] = (grey / max(ring, 1), dirty)
    return res


def do_build(seed, procedural):
    import ticket_scene as ts
    sc = ts.Scene()
    cv, slots, mk, idx = build_slots(seed, procedural)
    new = slice_all(sc, cv, slots)
    rec, rows = recolors(sc, new)
    return sc, cv, slots, mk, new, rec, rows


def save_cands(new, rec):
    os.makedirs(CAND, exist_ok=True)
    for f in os.listdir(CAND):
        if f.endswith(".png"):
            os.remove(os.path.join(CAND, f))
    for (s, f), im in list(new.items()) + list(rec.items()):
        im.save(os.path.join(CAND, "%s_%d.png" % (s, f)))
    return len(new) + len(rec)


def do_build_cmd(a):
    sc, cv, slots, mk, new, rec, rows = do_build(a.seed or BEST, a.procedural)
    n = save_cands(new, rec)
    print("кадров XB2BR %d, перекрасок %d, файлов %d -> %s" % (len(new), len(rec), n, CAND))
    worst, outside = construction_check(new, sc, cv, slots, mk)
    print("радар из кадров против холста: макс. разница %.1f; пикселей вне классики x4: %d" % (worst, outside))
    for slot in (0, 3):
        r = seam_report(new, sc, slot)
        print("слот %d, доля строк с тонкой линией (макс. по стыкам / 95-й процентиль и макс. прочих столбцов):" % slot,
              {k: tuple(round(float(x), 3) for x in v) for k, v in r.items()})
    sub = substrate_report(new, sc)
    print("подложка: доля светло-серого без цвета на кромке, ненулевой RGB под прозрачным:",
          {k: (round(v[0], 4), v[1]) for k, v in sub.items()})
    print("анимация: запись, доля изменений между слотами - классика / новое")
    for b, c, n_ in anim_report(sc, new):
        print("   %d  %.3f  %.3f" % (b, c, n_))
    print("перекраски: набор кадр <- XB2BR (слот, кадр), корреляция яркости, IoU маски")
    for r in rows:
        print("   ", r[0], r[1], "<-", r[2], r[3], "%.2f %.2f" % (r[4], r[5]))


# ---------------------------------------------------------------------------------------------------------
# лист для Vitali
# ---------------------------------------------------------------------------------------------------------
SHEET = os.path.join(ROOT, "art", "_review", "tickets_2026-10-30", "t404_cand.png")
GIF = os.path.join(ROOT, "art", "_review", "tickets_2026-10-30", "t404_cand_anim.gif")
STRIP = os.path.join(ROOT, "art", "_review", "tickets_2026-10-30", "t404_cand_slots.png")
BGC = (30, 30, 34)
# вырезы стыков (база): граница клеток по цилиндру и по основанию
CROPS = [("стыки цилиндра x10", (42, 28, 76, 52)), ("стыки основания x10", (44, 56, 80, 80))]


def stack(rows, gap=8):
    W = max(sum(p.width for p in r) + gap * (len(r) + 1) for r in rows)
    H = sum(max(p.height for p in r) for r in rows) + gap * (len(rows) + 1)
    out = Image.new("RGB", (W, H), (12, 12, 14))
    y = gap
    for r in rows:
        x = gap
        for p in r:
            out.paste(p, (x, y))
            x += p.width + gap
        y += max(p.height for p in r) + gap
    return out


def lab(im, text, n=20):
    import ticket_scene as ts
    im = im.convert("RGB").copy()
    return ts.label(im, text, n)


def part_radar(sc, new, rec, setname, slot, k=K):
    """Радар из перекрашенных кадров по раскладке блока базы (XB 0-3 из набора 02, 5-9 из набора 03; XB 4 в базе нет)."""
    import map_mockup as mm
    w = mm.World()
    s2, s3 = setname + "02", setname + "03"
    src = {0: (s2, 33), 1: (s2, 35), 2: (s2, 37), 3: (s2, 39), 5: (s3, 0), 6: (s3, 2), 7: (s3, 4), 8: (s3, 6), 9: (s3, 8)}
    cv = Canvas()
    im = Image.new("RGBA", (cv.cw * k, cv.ch * k), BGC + (255,))
    imc = im.copy()
    for c in cv.cells:
        b = cv.grid[c]
        if b not in src:
            continue
        st, r = src[b]
        frs = w.records(st)[r]["frames"]
        f = frs[slot] if b in ALT else frs[0]
        ox, oy = cv.pos(c)
        if (st, f) in rec:
            im.alpha_composite(rec[(st, f)], (ox * k, oy * k))
        imc.alpha_composite(sc.classic(st, f), (ox * k, oy * k))
    return imc, im


def do_sheet(a):
    import ticket_scene as ts
    sc, cv, slots, mk, new, rec, rows = do_build(a.seed or BEST, a.procedural)
    k = K
    cls = lambda s: assemble(lambda f: sc.classic(SET, f), s, cv, BGC)                        # noqa: E731
    old = lambda s: assemble(lambda f: sc.hd(SET, f) or sc.classic(SET, f), s, cv, BGC)      # noqa: E731
    nw = lambda s: assemble(lambda f: new[(SET, f)], s, cv, BGC)                              # noqa: E731
    bb = np.asarray(cls(0))[..., :3].astype(int)
    ys, xs = np.where(np.abs(bb - np.array(BGC)).sum(-1) > 10)
    box = (max(xs.min() - 8, 0), max(ys.min() - 8, 0), xs.max() + 8, ys.max() + 8)
    rowsimg = []
    for s in (0, 3):
        rowsimg.append([lab(x(s).crop(box), "%s, слот %d" % (n, s)) for n, x in
                        (("классика x4", cls), ("HD сейчас", old), ("новое 404A+", nw))])
    # стыки вблизи
    z = 10
    zs = []
    for title, (x0, y0, x1, y1) in CROPS:
        for n, x in (("классика", cls), ("HD сейчас", old), ("новое", nw)):
            im = x(3).crop((x0 * k, y0 * k, x1 * k, y1 * k))
            im = im.resize((im.width * z // k, im.height * z // k), Image.NEAREST if n == "классика" else Image.LANCZOS)
            zs.append(lab(im, "%s: %s" % (title, n), 16))
    rowsimg.append(zs[:3])
    rowsimg.append(zs[3:])
    # перекраски: Thul и White, слоты 0 и 3, классика | новое
    rr = []
    for fam in ("THULBASES", "WHITEBASES"):
        for s in (0, 3):
            c_, n_ = part_radar(sc, new, rec, fam, s)
            rr += [lab(c_.crop(box), "%s классика, слот %d" % (fam, s), 16), lab(n_.crop(box), "%s новое, слот %d" % (fam, s), 16)]
    rowsimg.append(rr[:4])
    rowsimg.append(rr[4:])
    img = stack(rowsimg)
    os.makedirs(os.path.dirname(SHEET), exist_ok=True)
    img.save(SHEET)
    print("лист", SHEET, img.size)
    # полоса 8 слотов и GIF
    st = []
    for s in range(8):
        st.append(lab(nw(s).crop(box).resize(((box[2] - box[0]) // 2, (box[3] - box[1]) // 2), Image.LANCZOS), "слот %d" % s, 14))
    stack([st[:4], st[4:]]).save(STRIP)
    frames = [nw(s).crop(box).convert("P", palette=Image.ADAPTIVE) for s in range(8)]
    frames[0].save(GIF, save_all=True, append_images=frames[1:], duration=100, loop=0)
    print("полоса", STRIP, "GIF", GIF)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["preview", "render", "build", "sheet"])
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--procedural", action="store_true")
    a = ap.parse_args()
    if a.cmd == "preview":
        do_preview()
    elif a.cmd == "render":
        do_render()
    elif a.cmd == "build":
        do_build_cmd(a)
    elif a.cmd == "sheet":
        do_sheet(a)
    else:
        raise SystemExit("команда ещё не написана")
    return 0


if __name__ == "__main__":
    sys.exit(main())
