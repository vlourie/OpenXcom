#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикеты XP-000515/516/517, заготовки по выбору Vitali 05.11: сборка кандидатов, семей и листов БЕЗ видеокарты.
Входы - основы hb517_gen.py (art/tickets/hb517/gen/<задание>/<зерно>.png). В МОД НИЧЕГО НЕ СТАВИТ.

  cand/<вариант>/<НАБОР>_<кадр>.png   кандидаты: chair39A/B (39 + 40 зеркалом от 39), chair37A/B (37 новая основа),
                                      chair37M (37 = зеркало одобренного 38, ImageOps.mirror), barrelA/B (12 кадров
                                      семьи), rocketsA/B (10, 11 + PLANE2:119, PLANE2R:119)
  sheets/                             листы ширины не больше 2100

    py -3.13 tools\hdart\hb517_build.py build      # кандидаты + проверки (hb517_checks.tsv)
    py -3.13 tools\hdart\hb517_build.py sheets     # листы кадров, семьи, края и сцены на VES_270
"""
import argparse
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (HERE, os.path.join(HERE, "..")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
os.chdir(ROOT)

import numpy as np                                   # noqa: E402
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps   # noqa: E402

import hb517_gen as g                                # noqa: E402

OUT = os.path.join(ROOT, "art", "tickets", "hb517")
CAND = os.path.join(OUT, "cand")
SHEETS = os.path.join(OUT, "sheets")
# выбранные зёрна (лучшее, второе): заполнено по просмотру листа зёрен
SEL = {"chair39": [5391, 5392], "chair37": [5371, 5372], "barrel24": [5241, 5242], "rockets": [5101, 5102]}
BARREL_FAM = [("COMMS", 24), ("THULBASES01", 22), ("WHITEBASES01", 23), ("CULTAREA", 85), ("MILURBAN", 85),
              ("HANGAR2_SCI", 107), ("HANGAR2_SCI", 108), ("XBASE2", 25), ("CARGO1", 65), ("LINERSHIPC", 4),
              ("XBITSUFO", 4)]
ROCKET_FAM = [("PLANE2", 119), ("PLANE2R", 119)]
FONT = "C:/Windows/Fonts/arial.ttf"


def F(n):
    return ImageFont.truetype(FONT, n)


def tg():
    import t405_409_gen
    return t405_409_gen


def pieces(job, seed):
    """Кадры задания {(набор, кадр): RGBA 128x160} из основы-зерна."""
    cut = Image.open(os.path.join(g.GEN, job, "%d.png" % seed)).convert("RGBA")
    J = g.JOBS[job]
    at = J.get("at") or [(0, 0)] * len(J["members"])
    out = {}
    for (s, f), (ax, ay) in zip(J["members"], at):
        out[(s, f)] = cut.crop((ax * 4, ay * 4, ax * 4 + 128, ay * 4 + 160))
    return out


def clip_smooth(im, cls_k1):
    """Альфа не выходит за силуэт классики (R-089), контур - спрямлённый xBRZ, как в cut_out (R-121), не NEAREST x4."""
    import probe_object as po
    sil = cls_k1.split()[3].point(lambda v: 255 if v > 0 else 0).filter(ImageFilter.MaxFilter(5))
    m = np.asarray(po.smooth_silhouette(sil, 4), np.float32) / 255.0
    a = np.asarray(im).copy()
    a[..., 3] = (a[..., 3].astype(np.float32) * m).astype(np.uint8)
    a[a[..., 3] == 0, :3] = 0
    return Image.fromarray(a, "RGBA")


def lum(a):
    return a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114


def paint_marks(im, cls_t, pred, tag):
    """Пробка/метка кодом по классике (перенос цвета размазывает мелочь): маска - пиксели классики цели по условию pred,
    сглажена xBRZ; цвет - средний цвет этих пикселей классики, свет - от HD (яркость HD под маской к средней)."""
    import probe_object as po
    c = np.asarray(cls_t.convert("RGBA"), np.float32)
    m1 = pred(c) & (c[..., 3] > 0)
    if m1.sum() == 0:
        print("  %s: пикселей метки в классике нет" % tag)
        return im
    col = c[m1][:, :3].mean(0)
    mk = Image.fromarray(m1.astype(np.uint8) * 255, "L")
    soft = np.asarray(po.smooth_silhouette(mk, 4), np.float32) / 255.0
    a = np.asarray(im.convert("RGBA"), np.float32).copy()
    L = lum(a)
    big = np.asarray(Image.fromarray(m1.astype(np.uint8) * 255, "L").resize((a.shape[1], a.shape[0]), Image.NEAREST)) > 0
    ref = float(L[big & (a[..., 3] > 0)].mean()) if (big & (a[..., 3] > 0)).any() else 128.0
    k = np.clip(L / max(ref, 1.0), 0.75, 1.25)[..., None]
    paint = np.clip(col[None, None, :] * k, 0, 255)
    w = (soft * (a[..., 3] > 0))[..., None]
    a[..., :3] = a[..., :3] * (1 - w) + paint * w
    print("  %s: метка кодом, %d пикс. классики, цвет %s" % (tag, int(m1.sum()), tuple(int(v) for v in col)))
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")


def is_red(c):
    return (c[..., 0] > 140) & (c[..., 1] < 100) & (c[..., 2] < 110)


def is_yellow(c):
    return (c[..., 0] >= 140) & (c[..., 2] < 100) & (c[..., 0] - c[..., 2] >= 75)


MARKS = {("HANGAR2_SCI", 108): ("пробка", is_red), ("CARGO1", 65): ("метка", is_yellow),
         ("LINERSHIPC", 4): ("метка", is_yellow)}
ROWS = []


def put(variant, s, f, im):
    d = os.path.join(CAND, variant)
    os.makedirs(d, exist_ok=True)
    im.save(os.path.join(d, "%s_%d.png" % (s, f)))


def edge_report(variant, s, f, im):
    """Края: пикселей альфы за классикой, доля полупрозрачных, касание рамки кадра."""
    a = np.asarray(im)[..., 3]
    cls = tg().classic_of(s, f)
    ys, xs = np.where(a > 0)
    ROWS.append([variant, s, f, "%d,%d,%d,%d" % (xs.min(), ys.min(), xs.max(), ys.max()),
                 int((a[:, :2] > 40).sum() + (a[:, -2:] > 40).sum()), int((a[:2] > 40).sum() + (a[-2:] > 40).sum()),
                 "%.3f" % (((a > 0) & (a < 250)).sum() / max(1, (a > 0).sum())), "%.1f" % lum(np.asarray(im, np.float32)[a > 128].reshape(-1, 4)).mean()])


def do_build():
    t = tg()
    import obj_derive as od
    import shutil
    for v in os.listdir(CAND) if os.path.isdir(CAND) else []:
        pass
    # --- кресла
    for ab, (s39, s37) in zip("AB", zip(SEL["chair39"], SEL["chair37"])):
        p39 = pieces("chair39", s39)[("U_WALL_G", 39)]
        p39 = clip_smooth(p39, t.classic_of("U_WALL_G", 39))
        put("chair39" + ab, "U_WALL_G", 39, p39)
        c39, c40 = t.classic_of("U_WALL_G", 39), t.classic_of("U_WALL_G", 40)
        sil_mirror = np.array_equal(np.asarray(c39)[..., 3], np.asarray(c40)[::, ::-1, 3])
        m40 = clip_smooth(od.derive(p39, c39, c40, "зеркало"), c40)
        put("chair39" + ab, "U_WALL_G", 40, m40)
        print("кресло 39%s: зерно %d, 40 = зеркало 39 с возвратом света (силуэт классики зеркален: %s)" % (ab, s39, sil_mirror))
        p37 = pieces("chair37", s37)[("U_WALL_G", 37)]
        p37 = clip_smooth(p37, t.classic_of("U_WALL_G", 37))
        put("chair37" + ab, "U_WALL_G", 37, p37)
        edge_report("chair39" + ab, "U_WALL_G", 39, p39)
        edge_report("chair39" + ab, "U_WALL_G", 40, m40)
        edge_report("chair37" + ab, "U_WALL_G", 37, p37)
    hd38 = g.hd_now("U_WALL_G", 38)
    put("chair37M", "U_WALL_G", 37, ImageOps.mirror(hd38))
    # --- бочка
    for ab, seed in zip("AB", SEL["barrel24"]):
        base = clip_smooth(pieces("barrel24", seed)[("XB2BR", 24)], t.classic_of("XB2BR", 24))
        put("barrel" + ab, "XB2BR", 24, base)
        edge_report("barrel" + ab, "XB2BR", 24, base)
        for key in BARREL_FAM:
            if key in t.NO_CLASSIC:
                im = base.copy()
                tag = "копия XB2BR:24 (классика набора не читается)"
            else:
                cls = t.classic_of(*key)
                if t.same_px(t.classic_of("XB2BR", 24), cls):
                    im, tag = base.copy(), "копия"
                else:
                    im, tag = t.recolor_to(base, ("XB2BR", 24), key), "перенос цвета"
                    if key in MARKS:
                        im = paint_marks(im, cls, MARKS[key][1], "%s:%d %s" % (key[0], key[1], MARKS[key][0]))
                im = clip_smooth(im, cls)
            put("barrel" + ab, key[0], key[1], im)
            edge_report("barrel" + ab, key[0], key[1], im)
            print("бочка%s %s:%d - %s" % (ab, key[0], key[1], tag))
    # --- ракеты
    for ab, seed in zip("AB", SEL["rockets"]):
        pc = pieces("rockets", seed)
        for key in (("XB2BR", 10), ("XB2BR", 11)):
            im = clip_smooth(pc[key], t.classic_of(*key))
            put("rockets" + ab, key[0], key[1], im)
            edge_report("rockets" + ab, key[0], key[1], im)
        n11 = Image.open(os.path.join(CAND, "rockets" + ab, "XB2BR_11.png")).convert("RGBA")
        for key in ROCKET_FAM:
            cls = t.classic_of(*key)
            im = clip_smooth(t.recolor_to(n11, ("XB2BR", 11), key, layout_free=True), cls)   # по таблице цветов классики: каркас PLANE2 жёлтый, PLANE2R бежевый
            put("rockets" + ab, key[0], key[1], im)
            edge_report("rockets" + ab, key[0], key[1], im)
            print("ракеты%s %s:%d - перенос цвета от XB2BR:11, IoU %.2f" % (ab, key[0], key[1], t.iou(t.classic_of("XB2BR", 11), cls)))
    with open(os.path.join(OUT, "hb517_checks.tsv"), "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["вариант", "набор", "кадр", "габарит x0,y0,x1,y1", "альфа у левого/правого края (2 столбца)",
                    "альфа у верхнего/нижнего края кадра", "доля полупрозрачных", "яркость"])
        w.writerows(ROWS)
    for r in ROWS:
        print("  ", r)


# --- листы -----------------------------------------------------------------------------------------------
BG = (26, 26, 30)


def cropped(im, box, z, near=False):
    im = im.crop(box)
    bg = Image.new("RGBA", im.size, BG + (255,))
    bg.alpha_composite(im.convert("RGBA"))
    return bg.resize((im.width * z, im.height * z), Image.NEAREST if near else Image.LANCZOS).convert("RGB")


def grid(rows, out, title="", gap=10, lab=28):
    W = max(sum(p.width + gap for _, p in r) for r in rows) + gap
    top = 40 if title else 0
    H = top + sum(max(p.height for _, p in r) + lab + gap for r in rows) + gap
    im = Image.new("RGB", (W, H), (12, 12, 14))
    d = ImageDraw.Draw(im)
    if title:
        d.text((gap, 8), title, fill=(255, 220, 0), font=F(22))
    y = top + gap
    for r in rows:
        x = gap
        for t, p in r:
            d.text((x + 2, y + 2), t, fill=(255, 220, 0), font=F(17))
            im.paste(p, (x, y + lab))
            x += p.width + gap
        y += max(p.height for _, p in r) + lab + gap
    os.makedirs(SHEETS, exist_ok=True)
    im.save(os.path.join(SHEETS, out), optimize=True)
    print(out, im.size)
    return im


def cand(variant, s, f):
    p = os.path.join(CAND, variant, "%s_%d.png" % (s, f))
    return Image.open(p).convert("RGBA") if os.path.exists(p) else None


def common_box(sc, keys, pad=6):
    ys, xs = [], []
    for s, f in keys:
        a = np.asarray(sc.classic(s, f))[:, :, 3]
        yy, xx = np.where(a > 0)
        ys += [yy.min(), yy.max()]
        xs += [xx.min(), xx.max()]
    return (max(min(xs) - pad * 4, 0), max(min(ys) - pad * 4, 0), min(max(xs) + pad * 4 + 1, 128), min(max(ys) + pad * 4 + 1, 160))


def frames_sheet(sc, name, title, rows_spec, Z=3):
    """rows_spec: [(набор, кадр, [(подпись, картинка)...])] - классика и сейчас добавляются слева."""
    box = common_box(sc, [(s, f) for s, f, _ in rows_spec])
    rows = []
    for s, f, extra in rows_spec:
        r = [("%s:%d оригинал" % (s, f), cropped(sc.classic(s, f), box, Z, True)), ("сейчас", cropped(sc.hd(s, f), box, Z))]
        r += [(t, cropped(im, box, Z)) for t, im in extra if im is not None]
        rows.append(r)
    return grid(rows, name, title)


def scene_render(sc, override, maxz, win, origin, k=4):
    im, _ = sc.render("VES_270", "VES_270", "hd", k=k, maxz=maxz, override=override)
    im = im.resize((im.width * 2, im.height * 2), Image.LANCZOS)
    ox, oy = origin
    return im if win is None else __import__("ticket_scene").crop_pad(im, (ox + win[0], oy + win[1], ox + win[2], oy + win[3])).convert("RGB")


def scene_sheet(sc, name, title, panels, maxz, win, origin, pw=1030):
    import ticket_scene as ts
    ox, oy = origin
    imgs = []
    for t, ov in panels:
        if ov == "classic":
            im, _ = sc.render("VES_270", "VES_270", "classic", k=8, maxz=maxz)
        else:
            im, _ = sc.render("VES_270", "VES_270", "hd", k=4, maxz=maxz, override=ov)
            im = im.resize((im.width * 2, im.height * 2), Image.LANCZOS)
        c = ts.crop_pad(im, (ox + win[0], oy + win[1], ox + win[2], oy + win[3])).convert("RGB")
        ph = int(c.height * pw / c.width)
        imgs.append((t, c.resize((pw, ph), Image.LANCZOS)))
    rows = [imgs[i:i + 2] for i in range(0, len(imgs), 2)]
    return grid(rows, name, title)


def edge_sheet(variants_keys, name, title, Z=6):
    """Нижняя кромка и верх крупно (NEAREST x6) на тёмном фоне: лесенка x4 была бы видна ступенями."""
    rows = []
    for label, (v, s, f) in variants_keys:
        im = cand(v, s, f)
        if im is None:
            continue
        a = np.asarray(im)[..., 3]
        ys, xs = np.where(a > 40)
        x0, x1 = max(xs.min() - 4, 0), min(xs.max() + 5, 128)
        y1 = min(ys.max() + 5, 160)
        y0 = max(ys.min() - 4, 0)
        bot = cropped(im, (x0, max(y1 - 44, 0), x1, y1), Z, True)
        top = cropped(im, (x0, y0, x1, min(y0 + 40, 160)), Z, True)
        rows.append([(label + " низ", bot), ("верх", top)])
    return grid(rows, name, title)


def do_sheets():
    import ticket_scene as ts
    sc = ts.Scene()
    S = "U_WALL_G"
    # --- кресла
    spec = [
        (S, 37, [("A: новая основа (зерно %d)" % SEL["chair37"][0], cand("chair37A", S, 37)),
                 ("B: новая основа (зерно %d)" % SEL["chair37"][1], cand("chair37B", S, 37)),
                 ("зеркало от одобренного 38", cand("chair37M", S, 37))]),
        (S, 38, [("38 (одобрен, не менять)", sc.hd(S, 38))]),
        (S, 39, [("A (зерно %d)" % SEL["chair39"][0], cand("chair39A", S, 39)),
                 ("B (зерно %d)" % SEL["chair39"][1], cand("chair39B", S, 39))]),
        (S, 40, [("A: зеркало 39A", cand("chair39A", S, 40)), ("B: зеркало 39B", cand("chair39B", S, 40))]),
    ]
    frames_sheet(sc, "chairs_frames.png", "XP-000517 кресла U_WALL_G 37-40: оригинал | сейчас | варианты", spec, Z=2)
    ov = {}
    chair_ov = {
        "A": {(S, 37): cand("chair37A", S, 37), (S, 39): cand("chair39A", S, 39), (S, 40): cand("chair39A", S, 40)},
        "B": {(S, 37): cand("chair37B", S, 37), (S, 39): cand("chair39B", S, 39), (S, 40): cand("chair39B", S, 40)},
        "M": {(S, 37): cand("chair37M", S, 37), (S, 39): cand("chair39A", S, 39), (S, 40): cand("chair39A", S, 40)},
    }
    scene_sheet(sc, "chairs_scene.png", "XP-000517 карта VES_270, 2-й этаж: классика | сейчас | A (37 и 39 новые) | зеркало 37 от 38 + 39/40 A",
                [("классика", "classic"), ("HD сейчас", None), ("вариант A: новые 37, 39, 40", chair_ov["A"]),
                 ("37 зеркало от 38, 39 и 40 как A", chair_ov["M"])],
                2, (1000, 540, 2040, 1240), (3744, 3120))
    scene_sheet(sc, "chairs_scene_B.png", "XP-000517 карта VES_270, 2-й этаж: вариант B (37, 39, 40 вторым зерном)",
                [("вариант B: новые 37, 39, 40", chair_ov["B"]), ("вариант A", chair_ov["A"])],
                2, (1000, 540, 2040, 1240), (3744, 3120))
    edge_sheet([("37A", ("chair37A", S, 37)), ("37B", ("chair37B", S, 37)), ("39A", ("chair39A", S, 39)),
                ("39B", ("chair39B", S, 39)), ("40A", ("chair39A", S, 40)), ("40B", ("chair39B", S, 40))],
               "chairs_edges.png", "края кресел крупно x6 (NEAREST), низ и верх")
    # --- бочка
    X = "XB2BR"
    frames_sheet(sc, "barrel_frames.png", "XP-000515 бочка XB2BR:24: оригинал | сейчас | варианты",
                 [(X, 24, [("A (зерно %d)" % SEL["barrel24"][0], cand("barrelA", X, 24)),
                           ("B (зерно %d)" % SEL["barrel24"][1], cand("barrelB", X, 24))])], Z=4)
    fam = [(X, 24)] + BARREL_FAM
    box = common_box(sc, [k for k in fam if k != ("MILURBAN", 85)])
    rows = []
    for i in range(0, len(fam), 2):
        r = []
        for s, f in fam[i:i + 2]:
            try:
                cl = sc.classic(s, f)
            except TypeError:
                cl = None
            cur = sc.hd(s, f)
            blank = Image.new("RGBA", (128, 160))
            r.append(("%s:%d оригинал" % (s[:11], f), cropped(cl if cl is not None else blank, box, 2, True)))
            r.append(("сейчас", cropped(cur if cur is not None else blank, box, 2)))
            r.append(("A", cropped(cand("barrelA", s, f), box, 2)))
            r.append(("B", cropped(cand("barrelB", s, f), box, 2)))
        rows.append(r)
    grid(rows, "barrel_family.png", "XP-000515 семья бочки, 12 кадров: оригинал | сейчас | A | B", gap=8)
    scene_sheet(sc, "barrel_scene.png", "XP-000515 карта VES_270, 1-й этаж: классика | сейчас | A | B",
                [("классика", "classic"), ("HD сейчас", None),
                 ("вариант A", {(X, 24): cand("barrelA", X, 24)}), ("вариант B", {(X, 24): cand("barrelB", X, 24)})],
                0, (820, 380, 2260, 1040), (1648, 2064))
    edge_sheet([("бочка A", ("barrelA", X, 24)), ("бочка B", ("barrelB", X, 24))], "barrel_edges.png",
               "края бочки крупно x6 (NEAREST), низ и верх")
    # --- ракеты
    P = "PLANE2"
    frames_sheet(sc, "rockets_frames.png", "XP-000516 ракеты XB2BR:10, 11: оригинал | сейчас | варианты",
                 [(X, 10, [("A (зерно %d)" % SEL["rockets"][0], cand("rocketsA", X, 10)),
                           ("B (зерно %d)" % SEL["rockets"][1], cand("rocketsB", X, 10))]),
                  (X, 11, [("A", cand("rocketsA", X, 11)), ("B", cand("rocketsB", X, 11))]),
                  (P, 119, [("A (от 11)", cand("rocketsA", P, 119)), ("B (от 11)", cand("rocketsB", P, 119))]),
                  ("PLANE2R", 119, [("A (от 11)", cand("rocketsA", "PLANE2R", 119)), ("B (от 11)", cand("rocketsB", "PLANE2R", 119))])], Z=3)
    scene_sheet(sc, "rockets_scene.png", "XP-000516 карта VES_270, 1-й этаж: классика | сейчас | A | B",
                [("классика", "classic"), ("HD сейчас", None),
                 ("вариант A", {(X, 10): cand("rocketsA", X, 10), (X, 11): cand("rocketsA", X, 11)}),
                 ("вариант B", {(X, 10): cand("rocketsB", X, 10), (X, 11): cand("rocketsB", X, 11)})],
                0, (130, 380, 1700, 1040), (2742, 2056))
    edge_sheet([("10A", ("rocketsA", X, 10)), ("11A", ("rocketsA", X, 11)), ("10B", ("rocketsB", X, 10)),
                ("11B", ("rocketsB", X, 11))], "rockets_edges.png", "края ракет крупно x6 (NEAREST), низ и верх")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["build", "sheets", "seeds"])
    a = ap.parse_args()
    if a.cmd == "build":
        do_build()
    elif a.cmd == "sheets":
        do_sheets()
    else:
        do_seeds()
    return 0


def do_seeds():
    """Лист всех зёрен без выбора: вход | зёрна, на тёмном - чтобы выбрать лучшие."""
    import ticket_scene as ts
    sc = ts.Scene()
    rows = []
    for job in g.ORDER:
        J = g.JOBS[job]
        full, _ = g.comp_of(job)
        bb = full.split()[3].getbbox()
        box4 = (max(bb[0] - 2, 0) * 4, max(bb[1] - 2, 0) * 4, min(bb[2] + 2, full.width) * 4, min(bb[3] + 2, 40) * 4)
        r = [("%s классика" % job, cropped(full.resize((full.width * 4, 160), Image.NEAREST), box4, 2, True))]
        for seed in J["seeds"]:
            p = os.path.join(g.GEN, job, "%d.png" % seed)
            if os.path.exists(p):
                r.append(("зерно %d" % seed, cropped(Image.open(p).convert("RGBA"), box4, 2)))
        rows.append(r)
    grid(rows, "seeds.png", "зёрна основ")


if __name__ == "__main__":
    sys.exit(main())
