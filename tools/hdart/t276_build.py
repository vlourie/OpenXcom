#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикеты XP-000276 (сухая трава), XP-000278 (колючий куст), XP-000279 (ель) - листы, сборка семей, установка.
Генерация - t276_gen.py (Qwen-2.1 strict, только через gpuq); здесь зёрна -> кадры семьи, листы (без видеокарты).

    .venv\Scripts\python.exe tools\hdart\t276_build.py cand                  # листы зёрен art/tickets/t276_278_279/cand_*.png
    .venv\Scripts\python.exe tools\hdart\t276_build.py build                 # CHOICE -> after/<тикет>/<вариант>/TERRAIN/... и листы after/
    .venv\Scripts\python.exe tools\hdart\t276_build.py install t278 v2 --yes # вариант в мод hd (манифест, обе копии; ТОЛЬКО по слову Vitali,
                                                                              под очередью правок - обернуть в editq)

Семья каждого кадра - tools/hdart/ticket_family.py (R-457): копии классики (индексы равны) получают тот же файл,
перекраски - перенос цвета по классике: для каждого цвета основы в классике берётся средний сдвиг Lab к цвету члена
(по общим пикселям), HD-пиксель сдвигается на сглаженный по близости цветов сдвиг - рисунок и свет HD остаются.
Альфа члена - по его маске классики (R-089). Ель: одно дерево на холсте 128x256 режется по маскам классики на 64 и 65.
"""
import argparse
import os
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (HERE, os.path.join(HERE, ".."), os.path.join(ROOT, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import cv2                                          # noqa: E402
import numpy as np                                  # noqa: E402
from PIL import Image, ImageDraw, ImageFont, ImageFilter   # noqa: E402

BASE = os.path.join(ROOT, "art", "tickets", "t276_278_279")
GEN = os.path.join(BASE, "gen")
AFTER = os.path.join(ROOT, "art", "_review", "tickets_2026-10-23", "after")
GREY, DARK = (110, 110, 116), (24, 20, 18)

# выбор по листам cand_*.png: вариант -> зерно по заданию
CHOICE = {
    "t276": {"v1": {"grass8": 8101, "grass11": 1101, "flowers9": 9101},
             "v2": {"grass8": 8102, "grass11": 1103, "flowers9": 9102},
             "v3": {"grass8": 8103, "grass11": 1106, "flowers9": 9103}},
    "t278": {"v1": {"bush15": 1501}, "v2": {"bush15": 1504}, "v3": {"bush15": 1503}},
    "t279": {"v1": {"spruce": 6401}, "v2": {"spruce": 6403}, "v3": {"spruce": 6405}},
}

# семья по ticket_family.py + проверка индексов классики (probe 23.10): (набор, кадр), опора - кадр основы
FAM = {
    "grass8": dict(bases=[("MOUNTGRASS", 8)], members=[]),
    "grass11": dict(bases=[("CULTIVAT", 11)], members=[("CULTIVAT_UBER", 11, 0), ("GOTHIC", 21, 0), ("VILROADS", 2, 0),
                                                       ("SGR_CAVE", 62, 0)]),
    "flowers9": dict(bases=[("MOUNTGRASS", 9)], members=[("GOTHIC", 9, 0)]),
    "bush15": dict(bases=[("MOUNTGRASS", 15)], members=[("ABUNKER", 7, 0), ("BLACKFOREST", 17, 0), ("FOREST", 17, 0),
                                                        ("FORESTRED", 17, 0), ("FOREST_WASTE", 17, 0), ("MOUNTMUD", 14, 0),
                                                        ("MOUNTROCK", 16, 0)]),
    "spruce": dict(bases=[("MOUNTGRASS", 64), ("MOUNTGRASS", 65)],
                   members=[("FOREST", 21, 0), ("FOREST", 22, 1), ("FORESTRED", 21, 0), ("FORESTRED", 22, 1),
                            ("MOUNTROCK", 64, 0), ("MOUNTROCK", 65, 1), ("FOREST_SNOW", 21, 0), ("FOREST_SNOW", 22, 1)]),
}
TICKET_JOB = {"t276": ["grass8", "grass11", "flowers9"], "t278": ["bush15"], "t279": ["spruce"]}
JOB_TICKET = {j: t for t, js in TICKET_JOB.items() for j in js}
# CULTIVAT_UBER:11 - копия CULTIVAT:11 с отличием в 6 пикселях края (ticket_family: IoU 0.98, рисунок 1.00, цвет 1.00):
# маска по краю даёт полупрозрачные хвосты, берётся тот же кадр, что и у основы
COPY_FORCE = {("CULTIVAT_UBER", 11)}
SIGMA = 14.0
GROW = 2


def font(n=16):
    try:
        return ImageFont.truetype("C:/Windows/Fonts/arial.ttf", n)
    except OSError:
        return ImageFont.load_default()


_SC = None


def scene():
    global _SC
    if _SC is None:
        import ticket_scene as ts
        _SC = ts.Scene()
    return _SC


def classic1(s, f):
    """Классика k=1 RGBA 32x40 (палитра Пираток)."""
    return scene().classic(s, f).resize((32, 40), Image.NEAREST)


def hd_now(s, f):
    return scene().hd(s, f)


def gen_path(job, seed):
    return os.path.join(GEN, job, "%d.png" % seed)


# ------------------------------------------------------------------ цвет

def to_lab(rgb):
    return cv2.cvtColor(np.clip(rgb, 0, 255).astype(np.float32).reshape(-1, 1, 3) / 255.0, cv2.COLOR_RGB2Lab).reshape(-1, 3)


def from_lab(lab):
    return np.clip(cv2.cvtColor(lab.reshape(-1, 1, 3).astype(np.float32), cv2.COLOR_Lab2RGB).reshape(-1, 3) * 255.0, 0, 255)


def color_shift(pairs):
    """pairs: [(RGBA k=1 основы, RGBA k=1 члена)] -> (Lab цветов основы, средний сдвиг Lab к члену, вес)."""
    cb, cm = [], []
    for b, m in pairs:
        ab, am = np.asarray(b), np.asarray(m)
        ok = (ab[..., 3] > 0) & (am[..., 3] > 0)
        cb.append(ab[..., :3][ok])
        cm.append(am[..., :3][ok])
    cb, cm = np.concatenate(cb), np.concatenate(cm)
    key = cb[:, 0].astype(np.int64) * 65536 + cb[:, 1].astype(np.int64) * 256 + cb[:, 2]
    uk, inv = np.unique(key, return_inverse=True)
    n = len(uk)
    lb, lm = to_lab(cb.astype(np.float32)), to_lab(cm.astype(np.float32))
    d = lm - lb
    cnt = np.bincount(inv, minlength=n).astype(np.float32)
    dm = np.stack([np.bincount(inv, weights=d[:, c], minlength=n) for c in range(3)], 1) / cnt[:, None]
    bl = np.stack([np.bincount(inv, weights=lb[:, c], minlength=n) for c in range(3)], 1) / cnt[:, None]
    return bl, dm, cnt


def recolor(hd, pairs):
    """hd: uint8 RGBA (H,W,4) основы; pairs - классика основы и члена на общей раскладке. Возвращает uint8 RGBA."""
    bl, dm, cnt = color_shift(pairs)
    h, w = hd.shape[:2]
    op = hd[..., 3] > 0
    px = hd[..., :3][op].astype(np.float32)
    lab = to_lab(px)
    d2 = ((lab[:, None, :] - bl[None, :, :]) ** 2).sum(-1)
    d2 -= d2.min(1, keepdims=True)
    wgt = np.exp(-d2 / (2 * SIGMA * SIGMA)) * np.sqrt(cnt)[None, :]
    delta = (wgt[:, :, None] * dm[None, :, :]).sum(1) / wgt.sum(1, keepdims=True)
    out = hd.copy()
    out[..., :3][op] = from_lab(lab + delta).round().astype(np.uint8)
    return out


def fill_out(rgba, valid):
    """Цвет за пределами valid (альфа члена шире основы) - от ближайшего пикселя valid."""
    a = rgba.copy()
    inv = (~valid).astype(np.uint8)
    if not inv.any():
        return a
    dist, labels = cv2.distanceTransformWithLabels(inv, cv2.DIST_L2, 3, labelType=cv2.DIST_LABEL_PIXEL)
    ys, xs = np.nonzero(~inv.astype(bool))
    # метка пикселя нуля = порядковый номер среди нулей в порядке обхода строк (1..N)
    sel = labels[inv.astype(bool)] - 1
    a[..., :3][inv.astype(bool)] = a[..., :3][ys[sel], xs[sel]]
    return a


def defringe(a):
    """Светлая кромка (подложка просочилась в мягкий край): цвет пикселей с альфой < 235 берётся у ближайшего плотного
    пикселя и чуть темнится; альфа не меняется (она по маске классики, R-089)."""
    a = a.copy()
    solid = a[..., 3] >= 235
    if not solid.any():
        return a
    ring = (a[..., 3] > 0) & ~solid
    b = fill_out(a, solid)
    a[..., :3][ring] = (b[..., :3][ring].astype(np.float32) * 0.94).astype(np.uint8)
    return a


# ------------------------------------------------------------------ маски

def sil_x4(sil_img, grow=GROW):
    """Силуэт k=1 (L 0/255) -> x4 гладкий, как po.cut_out (grow на k=1, xBRZ-маска)."""
    import probe_object as po
    s = sil_img.point(lambda v: 255 if v > 0 else 0)
    if grow > 0:
        s = s.filter(ImageFilter.MaxFilter(2 * grow + 1))
    return np.asarray(po.smooth_silhouette(s, 4), np.float32) / 255.0


def frame_alpha(rgba_k1):
    return sil_x4(rgba_k1.split()[3])


def stack_classic(parts):
    """Классика стопки k=1 по кадрам parts [(S, f, dy)] -> холст; и маски по кадрам."""
    H = 40 + max(dy for _s, _f, dy in parts)
    cv = Image.new("RGBA", (32, H), (0, 0, 0, 0))
    for s, f, dy in sorted(parts, key=lambda p: -p[2]):
        cv.alpha_composite(classic1(s, f), (0, dy))
    return cv


# ------------------------------------------------------------------ сборка семьи

def build_family(job, seed):
    """Кадры всей семьи задания: {(НАБОР, кадр): uint8 RGBA 160x128}. Ничего не пишет."""
    F = FAM[job]
    whole = np.asarray(Image.open(gen_path(job, seed)).convert("RGBA")).copy()
    whole = defringe(whole)
    out = {}
    if job == "spruce":
        dys = (24, 0)                       # 64 на 24 ниже 65 (z0, z1)
        base_hd = []
        for i, (s, f) in enumerate(F["bases"]):
            cl = classic1(s, f)
            al = frame_alpha(cl)            # 160x128
            y0 = dys[i] * 4
            part = whole[y0:y0 + 160].copy()
            part[..., 3] = (part[..., 3].astype(np.float32) * al).astype(np.uint8)
            base_hd.append(part)
            out[(s, f)] = part
    else:
        base_hd = [whole]
        out[F["bases"][0]] = whole
    for (s, f, bi) in F["members"]:
        bs, bf = F["bases"][bi]
        bc, mc = classic1(bs, bf), classic1(s, f)
        a_b, a_m = np.asarray(bc)[..., :4], np.asarray(mc)[..., :4]
        mb, mm_ = a_b[..., 3] > 0, a_m[..., 3] > 0
        same_mask = (mb == mm_).all()
        close = (mb & mm_).sum() / max(1, (mb | mm_).sum()) >= 0.97     # отличие в единицах пикселей - альфа основы как есть
        same_pix = same_mask and (a_b == a_m).all()
        if same_pix or (s, f) in COPY_FORCE:
            out[(s, f)] = base_hd[bi].copy()
            continue
        # перенос цвета: все пары (основа, член) задания
        pairs = [(classic1(*F["bases"][bi2]), classic1(s2, f2)) for (s2, f2, bi2) in F["members"] if s2 == s]
        rc = recolor(base_hd[bi], pairs)
        if not close:
            # альфа основы под растущим силуэтом члена + плотный силуэт члена там, где основа прозрачна (R-089)
            grown, tight = frame_alpha(mc), sil_x4(mc.split()[3], 0)
            a0 = base_hd[bi][..., 3].astype(np.float32) / 255.0
            valid = a0 > 0.5
            rc = fill_out(rc, valid)
            rc[..., 3] = (np.maximum(a0 * grown, tight) * 255).round().astype(np.uint8)
        out[(s, f)] = rc
    return out


# ------------------------------------------------------------------ листы

def on(im, bg, k=1.0):
    im = im.convert("RGBA")
    c = im.resize((int(im.width * k), int(im.height * k)), Image.LANCZOS if im.width > 40 else Image.NEAREST)
    out = Image.new("RGBA", c.size, bg + (255,))
    out.alpha_composite(c)
    return out


def grid(rows, path, cw, ch, title=None):
    f = font(16)
    ncol = max(len(r) for r in rows)
    top = 30 if title else 0
    out = Image.new("RGB", (ncol * (cw + 8) + 8, len(rows) * (ch + 30) + 8 + top), (12, 12, 14))
    d = ImageDraw.Draw(out)
    if title:
        d.text((8, 6), title, fill=(140, 200, 255), font=font(18))
    for y, r in enumerate(rows):
        for x, (t, im) in enumerate(r):
            ox, oy = 8 + x * (cw + 8), 8 + y * (ch + 30) + top
            d.text((ox, oy), t, fill=(255, 220, 0), font=f)
            out.paste(im.convert("RGB"), (ox, oy + 24))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    out.save(path)
    print("лист:", path, out.size)


def stack_img(frames, parts):
    """Кадры 160x128 (PIL RGBA) этажей -> один холст 256x128 (z1 выше на 96)."""
    cv = Image.new("RGBA", (128, 256), (0, 0, 0, 0))
    for im, (_s, _f, dy) in sorted(zip(frames, parts), key=lambda p: -p[1][2]):
        cv.alpha_composite(im, (0, dy * 4))
    return cv


def do_cand():
    for job in FAM:
        cells_rows = []
        parts = SPRUCE_PARTS if job == "spruce" else None
        if job == "spruce":
            cl = stack_img([scene().classic(s, f) for s, f in FAM[job]["bases"]], parts)
            now = stack_img([hd_now(s, f) for s, f in FAM[job]["bases"]], parts)
            crop = (0, 0, 128, 256)
            k = 1.6
        else:
            s, f = FAM[job]["bases"][0]
            cl, now = scene().classic(s, f), hd_now(s, f)
            bb = cl.split()[3].getbbox()
            crop = (0, max(0, bb[1] - 8), 128, min(160, bb[3] + 8))
            k = 2.0
        row = [("классика", on(cl.crop(crop), GREY, k)), ("сейчас", on(now.crop(crop), GREY, k))]
        seeds = sorted(int(p[:-4]) for p in os.listdir(os.path.join(GEN, job)) if p.endswith(".png")) \
            if os.path.isdir(os.path.join(GEN, job)) else []
        for sd in seeds:
            im = Image.open(gen_path(job, sd)).convert("RGBA")
            if job == "spruce":
                row.append(("зерно %d" % sd, on(im.crop(crop), GREY, k)))
            else:
                row.append(("зерно %d" % sd, on(im.crop(crop), GREY, k)))
        # переносим на несколько строк по 4 ячейки
        for i in range(0, len(row), 4):
            cells_rows.append(row[i:i + 4])
        cw = int(128 * k)
        ch = int((crop[3] - crop[1]) * k)
        grid(cells_rows, os.path.join(BASE, "cand_%s.png" % job), cw, ch, "кандидаты %s" % job)


SPRUCE_PARTS = [("MOUNTGRASS", 64, 24), ("MOUNTGRASS", 65, 0)]


def save_variant(ticket, var):
    """CHOICE -> after/<тикет>/<вариант>/TERRAIN/<НАБОР>.PCK/<кадр>.png; вернёт {относительный путь пака: файл} и кадры."""
    files, frames = {}, {}
    for job, seed in CHOICE[ticket][var].items():
        if not os.path.exists(gen_path(job, seed)):
            print('нет зерна', job, seed, '- пропуск')
            continue
        fam = build_family(job, seed)
        for (s, f), arr in fam.items():
            p = os.path.join(AFTER, ticket, var, "TERRAIN", s + ".PCK", "%d.png" % f)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            Image.fromarray(arr, "RGBA").save(p)
            files["TERRAIN/%s.PCK/%d.png" % (s, f)] = p
            frames[(s, f)] = Image.fromarray(arr, "RGBA")
    return files, frames


def sheet_t276():
    # --- t276: две основы травы, отдельно цветы
    rows = []
    for job in ("grass8", "grass11"):
        s, f = FAM[job]["bases"][0]
        crop = (0, 40, 128, 160)
        row = [("классика %s:%d" % (s, f), on(scene().classic(s, f).crop(crop), GREY, 2.2)),
               ("сейчас", on(hd_now(s, f).crop(crop), GREY, 2.2))]
        for var in CHOICE["t276"]:
            fp = os.path.join(AFTER, "t276", var, "TERRAIN", s + ".PCK", "%d.png" % f)
            if not os.path.exists(fp):
                continue
            fr = Image.open(fp).convert("RGBA")
            row.append(("НОВОЕ %s" % var, on(fr.crop(crop), GREY, 2.2)))
            row.append(("%s на тёмном" % var, on(fr.crop(crop), DARK, 2.2)))
        rows.append(row)
    grid(rows, os.path.join(AFTER, "t276_grass_after.png"), int(128 * 2.2), int(120 * 2.2),
         "XP-000276: сухая трава MOUNTGRASS:8 и CULTIVAT:11 - классика / сейчас / новое")
    if os.path.exists(gen_path("flowers9", CHOICE["t276"]["v1"].get("flowers9", 0))):
        rows = []
        s, f = FAM["flowers9"]["bases"][0]
        crop = (0, 20, 128, 160)
        row = [("классика %s:%d" % (s, f), on(scene().classic(s, f).crop(crop), GREY, 2.2)),
               ("сейчас", on(hd_now(s, f).crop(crop), GREY, 2.2)),
               ("FLORASET:19 сейчас (отклонено)", on(hd_now("FLORASET", 19).crop(crop), GREY, 2.2))]
        rows.append(row)
        row = []
        for var in CHOICE["t276"]:
            fp = os.path.join(AFTER, "t276", var, "TERRAIN", s + ".PCK", "%d.png" % f)
            if not os.path.exists(fp):
                continue
            fr = Image.open(fp).convert("RGBA")
            row.append(("НОВОЕ %s" % var, on(fr.crop(crop), GREY, 2.2)))
            row.append(("%s на тёмном" % var, on(fr.crop(crop), DARK, 2.2)))
        rows.append(row[:3]) if len(row) > 3 else rows.append(row)
        for i in range(3, len(row), 3):
            rows.append(row[i:i + 3])
        grid(rows, os.path.join(AFTER, "t276_flowers_after.png"), int(128 * 2.2), int(140 * 2.2),
             "XP-000276: цветы MOUNTGRASS:9 (и копия GOTHIC:9) - классика / сейчас / новое")


def sheet_t278():
    # --- t278: куст и семья
    rows = []
    s, f = FAM["bush15"]["bases"][0]
    crop = (0, 20, 128, 160)
    row = [("классика %s:%d" % (s, f), on(scene().classic(s, f).crop(crop), GREY, 2.2)),
           ("сейчас", on(hd_now(s, f).crop(crop), GREY, 2.2))]
    for var in CHOICE["t278"]:
        fr = Image.open(os.path.join(AFTER, "t278", var, "TERRAIN", s + ".PCK", "%d.png" % f)).convert("RGBA")
        row.append(("НОВОЕ %s" % var, on(fr.crop(crop), GREY, 2.2)))
        row.append(("%s на тёмном" % var, on(fr.crop(crop), DARK, 2.2)))
    rows.append(row)
    var = sorted(CHOICE["t278"])[0]
    mem = FAM["bush15"]["members"]
    cells = []
    for (ms, mf, _b) in mem:
        fr = Image.open(os.path.join(AFTER, "t278", var, "TERRAIN", ms + ".PCK", "%d.png" % mf)).convert("RGBA")
        cells.append(("%s:%d  классика | сейчас | новое" % (ms, mf),
                      hcat([on(scene().classic(ms, mf).crop(crop), GREY, 1.3), on(hd_now(ms, mf).crop(crop), GREY, 1.3),
                            on(fr.crop(crop), GREY, 1.3)])))
    grid(rows, os.path.join(AFTER, "t278_after.png"), int(128 * 2.2), int(140 * 2.2),
         "XP-000278: колючий куст MOUNTGRASS:15 - классика / сейчас / новое, три варианта")
    fam_rows = [cells[i:i + 3] for i in range(0, len(cells), 3)]
    grid(fam_rows, os.path.join(AFTER, "t278_family_after.png"), 3 * 166 + 8, 184,
         "XP-000278: семья 7 кадров, перекраска основы (вариант %s): классика | сейчас | новое" % var)


def sheet_t279():
    # --- t279: ель
    rows = []
    parts = SPRUCE_PARTS
    cl = stack_img([scene().classic(s, f) for s, f in FAM["spruce"]["bases"]], parts)
    now = stack_img([hd_now(s, f) for s, f in FAM["spruce"]["bases"]], parts)
    row = [("классика 64+65", on(cl, GREY, 1.6)), ("сейчас", on(now, GREY, 1.6))]
    for var in CHOICE["t279"]:
        frs = [Image.open(os.path.join(AFTER, "t279", var, "TERRAIN", s + ".PCK", "%d.png" % f)).convert("RGBA")
               for s, f in FAM["spruce"]["bases"]]
        st = stack_img(frs, parts)
        row.append(("НОВОЕ %s" % var, on(st, GREY, 1.6)))
        row.append(("%s стык x2.5" % var, on(st.crop((0, 70, 128, 190)), GREY, 2.5)))
    rows.append(row)
    var = sorted(CHOICE["t279"])[0]
    cells = []
    for mset, mf64, mf65 in (("FOREST", 21, 22), ("FORESTRED", 21, 22), ("MOUNTROCK", 64, 65), ("FOREST_SNOW", 21, 22)):
        a = stack_img([Image.open(os.path.join(AFTER, "t279", var, "TERRAIN", mset + ".PCK", "%d.png" % q)).convert("RGBA")
                       for q in (mf64, mf65)], parts)
        b = stack_img([hd_now(mset, mf64) or Image.new("RGBA", (128, 160)), hd_now(mset, mf65) or Image.new("RGBA", (128, 160))], parts)
        c = stack_img([scene().classic(mset, mf64), scene().classic(mset, mf65)], parts)
        cells.append(("%s:%d+%d  классика | сейчас | новое" % (mset, mf64, mf65),
                      hcat([on(c, GREY, 1.0), on(b, GREY, 1.0), on(a, GREY, 1.0)])))
    rows.append(cells)
    grid(rows, os.path.join(AFTER, "t279_after.png"), 400, 420,
         "XP-000279: ель MOUNTGRASS:64+65 одним деревом и семья (вариант %s)" % var)


def sheets(only=None):
    for t, fn in (("t276", sheet_t276), ("t278", sheet_t278), ("t279", sheet_t279)):
        if only in (None, t):
            fn()


def hcat(ims, gap=4):
    w = sum(i.width for i in ims) + gap * (len(ims) - 1)
    out = Image.new("RGBA", (w, max(i.height for i in ims)), (12, 12, 14, 255))
    x = 0
    for i in ims:
        out.paste(i, (x, 0))
        x += i.width + gap
    return out


def do_build(only=None):
    for ticket, vs in CHOICE.items():
        if only not in (None, ticket):
            continue
        for var in vs:
            files, _ = save_variant(ticket, var)
            print(ticket, var, "кадров:", len(files))
    sheets(only)


SCENES = {   # (террейн, блок, центр окна в пикселях базы, ширина, высота) - блок PLAINS12 WESTOWN_GRASS, где стоят все три
    "t276": ("WESTOWN_GRASS", "PLAINS12", (256, 228), 150, 110),
    "t278": ("WESTOWN_GRASS", "PLAINS12", (440, 262), 170, 120),
    "t279": ("WESTOWN_GRASS", "PLAINS12", (124, 290), 230, 190),
}


def do_scene(ticket, var):
    """Лист сцены блока: классика | HD сейчас | HD новое (вариант var) - ticket_scene.Scene.render."""
    terrain, block, (cx, cy), w, h = SCENES[ticket]
    sc = scene()
    ov = {}
    base = os.path.join(AFTER, ticket, var, "TERRAIN")
    for pck in os.listdir(base):
        for fn in os.listdir(os.path.join(base, pck)):
            if fn.endswith(".png"):
                ov[(pck[:-4].upper(), int(fn[:-4]))] = Image.open(os.path.join(base, pck, fn)).convert("RGBA")
    k = 4
    box = ((cx - w // 2) * k, (cy - h // 2) * k, (cx + w // 2) * k, (cy + h // 2) * k)
    panels = []
    for title, mode, o in (("классика", "classic", None), ("HD сейчас", "hd", None), ("HD новое, вариант %s" % var, "hd", ov)):
        im, _ = sc.render(terrain, block, mode, override=o, k=k)
        c = im.crop(box).convert("RGB")
        panels.append((title, c.resize((c.width * 3 // 4, c.height * 3 // 4), Image.LANCZOS)))
    pw, ph = panels[0][1].size
    out = Image.new("RGB", (pw * 3 + 32, ph + 60), (12, 12, 14))
    d = ImageDraw.Draw(out)
    d.text((8, 6), "%s: %s %s - классика / сейчас / новое" % (ticket, terrain, block), fill=(140, 200, 255), font=font(18))
    for i, (t, c) in enumerate(panels):
        d.text((8 + i * (pw + 8), 32), t, fill=(255, 220, 0), font=font(16))
        out.paste(c, (8 + i * (pw + 8), 54))
    path = os.path.join(AFTER, "%s_scene_%s.png" % (ticket, var))
    out.save(path)
    print("лист сцены:", path, out.size)


def do_install(ticket, var, yes, jobs=None):
    files = {}
    base = os.path.join(AFTER, ticket, var)
    for job in (jobs or list(CHOICE[ticket][var])):
        F = FAM[job]
        for (s, f) in list(F["bases"]) + [(m[0], m[1]) for m in F["members"]]:
            rel = "TERRAIN/%s.PCK/%d.png" % (s, f)
            files[rel] = os.path.join(base, rel)
    print("кадров: %d" % len(files))
    if not yes:
        raise SystemExit("сухой прогон; --yes - записать в мод (только по слову Vitali, под очередью правок)")
    import ticket_scene as ts
    ts.install_files(files, "t276_gen", "t276_gen.py 23.10, Qwen-2.1 strict, %s %s %s" % (ticket, var, CHOICE[ticket][var]),
                     "Vitali: выбор варианта %s %s по листу art/_review/tickets_2026-10-23/after/" % (ticket, var),
                     "%s: арт тикета, вариант %s - Qwen-2.1 strict, семья" % (ticket, var))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["cand", "build", "install", "scene"])
    ap.add_argument("ticket", nargs="?")
    ap.add_argument("var", nargs="?")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--jobs", default="", help="через запятую: grass8,grass11,flowers9 (по умолчанию все задания варианта)")
    a = ap.parse_args()
    os.chdir(ROOT)
    if a.cmd == "cand":
        do_cand()
    elif a.cmd == "build":
        do_build(a.ticket)
    elif a.cmd == "scene":
        do_scene(a.ticket, a.var)
    else:
        do_install(a.ticket, a.var, a.yes, [j for j in a.jobs.split(',') if j] or None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
