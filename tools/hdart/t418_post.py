#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""XP-000418, после генерации (без видеокарты): зёрна -> кандидат основы PORTROADS:34, тон корпуса, силуэт линиями, стекло B2,
семья переносом цвета классики, листы и сцены. Зовётся из t418_booth.py (seeds / build / scene). В мод ничего не ставит."""
import csv
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

import t405_409_gen as tg
import probe_object as po
import glass_alpha as ga

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
GEN = os.path.join(ROOT, "art", "tickets", "t418", "gen")
CAND = os.path.join(ROOT, "art", "tickets", "t418", "cand")
REV = os.path.join(ROOT, "art", "_review", "tickets_2026-10-30")
BASE = ("PORTROADS", 34)
FAMILY = [("MILURBITSEXT", 18), ("MILWARE", 45), ("MILWAREGHOUL", 44), ("XBITSUFO", 44)]
# зёрна листа: (круг, зерно); BEST - то, из которого выводится семья (после просмотра листа)
SHEET = [("boothq", 4195), ("boothq", 4196), ("boothq", 4197)]
BEST = ("boothq", int(os.environ.get("T418_BEST", "4197")))     # зерно основы и семьи; T418_BEST=4195 - другое
TONE = 0.7                    # доля подгонки тона корпуса к классике
ALPHA_BACK = 0.34             # непрозрачность заднего стекла: 0,28-0,4
ALPHA_HL = 0.55               # блик на заднем стекле плотнее
ZONE_GROW = 8                 # допуск зоны окон классики, пикселей HD (HD-окно не повторяет классику, R-406)
SCENES = [("PORTUFO21", "PORTTFTD5", "PORTUFO21"), ("INDUSTRIALSLUM05", "INDUSTRIALSLUM", "INDUSTRIALSLUM05")]
LUMW = np.array([0.299, 0.587, 0.114], np.float32)


def cls1():
    """Классика основы, k=1, RGBA 32x40."""
    return tg.classic_of(*BASE)


def cool_cls(a):
    r, g, b, al = (a[..., i].astype(np.int32) for i in range(4))
    cool = (al > 0) & (b >= r + 30) & (g + b >= 2 * r + 30)
    green = (al > 0) & (g >= r + 20) & (g >= b) & (r < 100)          # водоросли классики
    return cool | green


def glass_zone(grow=ZONE_GROW):
    """Зона окон классики x4 (bool 160x128), с допуском grow: холодные индексы классики, спрямлено линиями."""
    a = np.asarray(cls1())
    m = Image.fromarray(cool_cls(a).astype(np.uint8) * 255, "L")
    z = po.smooth_silhouette(m, 4)
    if grow:
        z = z.filter(ImageFilter.MaxFilter(2 * grow + 1))
    return np.asarray(z) > 100


def two_tone(rgb, mask):
    """Два якоря корпуса: средние цвета светлой и тёмной половин (по яркости, порог - среднее) под маской. -> (тёмный, светлый, яркость
    порога); так подгоняются отдельно освещённая левая грань и тень правой, а не одно среднее на весь кадр."""
    px = rgb[mask]
    lum = px @ LUMW
    thr = float(lum.mean())
    lo, hi = px[lum < thr].mean(0), px[lum >= thr].mean(0)
    return lo, hi, float(lo @ LUMW), float(hi @ LUMW)


def hull_tone(cut, amount=TONE):
    """Тон корпуса - к классике: два якоря (освещённая грань и тень), сдвиг цвета интерполируется по яркости пикселя. Окна
    (зона классики) не трогаются: стекло классики синее и тянуло бы тень в зелёный, интерьер должен остаться тёмным."""
    a = np.asarray(cut, np.float32).copy()
    cl = np.asarray(cls1()).astype(np.float32)
    hull_c = (cl[..., 3] > 0) & ~cool_cls(cl)
    zone0 = glass_zone(0)
    body = (a[..., 3] > 128) & ~glass_zone()
    # якоря модели - по корпусу без окон; классика - по корпусу без стекла
    lo_m, hi_m, ld_m, lh_m = two_tone(a[..., :3], body)
    lo_c, hi_c, ld_c, lh_c = two_tone(cl[..., :3], hull_c)
    rgb = a[..., :3]
    t = np.clip(((rgb @ LUMW) - ld_m) / max(lh_m - ld_m, 1.0), 0.0, 1.0)[..., None]
    shift = (lo_c - lo_m) * (1 - t) + (hi_c - hi_m) * t
    w = 1.0 - np.asarray(Image.fromarray(zone0.astype(np.uint8) * 255, "L").filter(ImageFilter.GaussianBlur(2.0)), np.float32) / 255.0
    a[..., :3] = np.clip(rgb + shift * amount * w[..., None], 0, 255)
    return Image.fromarray(np.rint(a).astype(np.uint8), "RGBA")


def edge_ramp(cut):
    """Альфа: внутри силуэта 255 (R-439), снаружи 0, кромка - ровная линия шириной около одного пикселя HD (сглаживание
    smooth_silhouette растягивает её на 3-4 пикселя - полупрозрачный ободок на тёмном полу)."""
    a = np.asarray(cut).copy()
    al = a[..., 3].astype(np.float32) / 255.0
    al = np.clip((al - 0.20) / 0.60, 0.0, 1.0)
    a[..., 3] = np.rint(al * 255).astype(np.uint8)
    a[a[..., 3] == 0, :3] = 0
    return Image.fromarray(a, "RGBA")


def glass_mask(cut):
    """Заднее стекло в самом HD-кадре (R-406: цвет кадра, а не форма классики): светлый нейтральный/холодный пиксель в зоне
    окон классики; тёплый (рама, корпус, стол) и тёмный (монитор, кресло) - не стекло; куски меньше 60 пикселей - прочь."""
    a = np.asarray(cut).astype(np.int32)
    r, g, b, al = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    neutral = (al > 0) & (lum >= 130) & (b >= r - 8) & (np.abs(g - (r + b) / 2.0) <= 14)
    m = neutral & glass_zone()
    # на кромку рамы не заходить: сжать на 2 пикселя
    m = ga.erode(m, 2)
    return ga.big_parts(m, 60), lum


def stage_glass(cut, alpha=ALPHA_BACK, hl=ALPHA_HL):
    """B2: альфа заднего стекла; мягкий переход по краю маски (размытие 1 пиксель), интерьер и рама непрозрачны."""
    a = np.asarray(cut).astype(np.float32).copy()
    m, lum = glass_mask(cut)
    if not m.any():
        return cut, 0
    med = np.median(lum[m])
    mul = np.where(lum > med + 45, hl, alpha)                      # блик плотнее
    soft = np.asarray(Image.fromarray(m.astype(np.uint8) * 255, "L").filter(ImageFilter.GaussianBlur(1.0)), np.float32) / 255.0
    f = 1.0 - soft * (1.0 - mul)                                   # 1 вне маски, mul внутри
    a[..., 3] = np.clip(np.rint(a[..., 3] * f), 0, 255)
    out = Image.fromarray(a.astype(np.uint8), "RGBA")
    return out, int(m.sum())


def process(job, seed, glass=True):
    """Зерно -> кадр: дыры внутри залиты, тон корпуса, кромка линией; glass - стекло B2. Возвращает (кадр, пикселей стекла)."""
    cut = Image.open(os.path.join(GEN, job, "%d.png" % seed)).convert("RGBA")
    cut = hull_tone(cut)
    cut = edge_ramp(cut)
    if not glass:
        return cut, 0
    return stage_glass(cut)


def over(im, bg):
    b = Image.new("RGBA", im.size, tuple(bg) + (255,))
    b.alpha_composite(im.convert("RGBA"))
    return b.convert("RGB")


def checker(w, h, cell=16):
    y, x = np.mgrid[0:h, 0:w]
    c = (((x + y) // cell) % 2).astype(bool)
    im = np.zeros((h, w, 3), np.uint8)
    im[c] = (235, 200, 40)
    im[~c] = (50, 40, 30)
    return Image.fromarray(im)


def on_checker(im):
    b = checker(im.width, im.height).convert("RGBA")
    b.alpha_composite(im.convert("RGBA"))
    return b.convert("RGB")


def cl4():
    return cls1().resize((128, 160), Image.NEAREST)


def note(job, seed):
    return "зерно %d" % seed


def do_seeds():
    import ticket_scene as ts
    panels = [("классика x4", tg.on_dark(cl4())), ("HD сейчас", tg.on_dark(tg.hd_now(*BASE)))]
    for job, s in SHEET:
        if os.path.exists(os.path.join(GEN, job, "%d.png" % s)):
            im, n = process(job, s)
            panels.append(("зерно %d (стекло %d пикс.)" % (s, n), tg.on_dark(im)))
    big = [(t, i.resize((i.width * 2, i.height * 2), Image.LANCZOS)) for t, i in panels]
    out = os.path.join(REV, "t418_seeds.png")
    ts.sheet(big, out, cols=len(big))
    print("лист:", out)


def metrics(im):
    """Проверки кадра: альфа внутри силуэта, ширина полутона по кромке, выход за классику x1 (пикселей HD)."""
    a = np.asarray(im)[..., 3]
    cm = np.asarray(po.smooth_silhouette(Image.fromarray(((np.asarray(cls1())[..., 3] > 0) * 255).astype(np.uint8), "L"), 4))
    semi = int(((a > 0) & (a < 250)).sum())
    inside = a[cm > 200]
    out_px = int(((a > 0) & (cm < 30)).sum())
    return dict(semi=semi, inner_min=int(inside.min()) if inside.size else -1, inner_lt250=int((inside < 250).sum()),
                outside_classic=out_px, opaque=int((a == 255).sum()))


def build_all(job_seed):
    """Основа из зерна + семья. -> {(набор, кадр): RGBA}, число пикселей заднего стекла."""
    job, seed = job_seed
    base_final, n = process(job, seed)
    base_plain, _ = process(job, seed, glass=False)
    ob = tg.classic_of(*BASE)
    zone = glass_zone(4)      # окна целиком (стекло, интерьер): перенос цвета классики их не красит, иначе стол и монитор синеют
    soft = np.asarray(Image.fromarray(zone.astype(np.uint8) * 255, "L").filter(ImageFilter.GaussianBlur(2.0)), np.float32) / 255.0
    out = {BASE: base_final}
    plain = np.asarray(base_plain, np.float32)
    for key in FAMILY:
        ot = tg.classic_of(*key)
        tr = np.asarray(tg.colormap_transfer(base_plain, ob, ot), np.float32)
        rgb = plain[..., :3] * soft[..., None] + tr[..., :3] * (1 - soft[..., None])      # окна - как нарисованы, без переноса
        res = np.zeros_like(plain)
        res[..., :3] = rgb
        res[..., 3] = np.asarray(base_final)[..., 3]
        res[res[..., 3] == 0, :3] = 0
        out[key] = Image.fromarray(np.rint(res).astype(np.uint8), "RGBA")
    return out, n


def stack(paths, out, bg=(12, 12, 14)):
    ims = [Image.open(p) for p in paths]
    W = max(i.width for i in ims)
    sh = Image.new("RGB", (W, sum(i.height for i in ims)), bg)
    y = 0
    for i in ims:
        sh.paste(i, (0, y))
        y += i.height
    sh.save(out)
    for p in paths:
        os.remove(p)


def do_build():
    import ticket_scene as ts
    os.makedirs(os.path.join(CAND, "B", "_seeds"), exist_ok=True)
    rows = []
    per_seed = {}
    for job, s in SHEET:
        if not os.path.exists(os.path.join(GEN, job, "%d.png" % s)):
            continue
        fam, n = build_all((job, s))
        per_seed[(job, s)] = fam
        fam[BASE].save(os.path.join(CAND, "B", "_seeds", "PORTROADS_34_s%d.png" % s))
        met = metrics(fam[BASE])
        rows.append([s, n] + [met[k] for k in ("semi", "inner_lt250", "inner_min", "outside_classic", "opaque")])
    best = per_seed[BEST] if BEST in per_seed else per_seed[next(iter(per_seed))]
    for key, im in best.items():
        im.save(os.path.join(CAND, "B", "%s_%d.png" % key))
    os.makedirs(REV, exist_ok=True)
    with open(os.path.join(REV, "t418_checks.tsv"), "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=chr(9))
        w.writerow(["зерно", "пикс. заднего стекла", "полупрозрачных 1-249 (вся кромка и стекло)", "внутри силуэта классики <250",
                    "мин. альфа внутри силуэта", "за силуэтом классики (пикс. HD)", "альфа 255 (пикс.)"])
        w.writerows(rows)
    for r in rows:
        print("  ", r)
    A = [("классика x4", tg.on_dark(cl4())), ("HD сейчас", tg.on_dark(tg.hd_now(*BASE)))]
    B = [("классика x4 на клетке", on_checker(cl4())), ("HD сейчас на клетке", on_checker(tg.hd_now(*BASE)))]
    for (job, s), fam in per_seed.items():
        A.append(("зерно %d" % s, tg.on_dark(fam[BASE])))
        B.append(("зерно %d: прозрачность B2" % s, on_checker(fam[BASE])))

    def x2(ps):
        return [(t, i.resize((i.width * 2, i.height * 2), Image.LANCZOS)) for t, i in ps]
    ts.sheet(x2(A), os.path.join(REV, "_a.png"), cols=len(A))
    ts.sheet(x2(B), os.path.join(REV, "_b.png"), cols=len(B))
    fam_p = []
    for key in [BASE] + FAMILY:
        c = tg.classic_of(*key).resize((128, 160), Image.NEAREST)
        fam_p.append(("%s:%d классика | HD" % key, tg.hstack([c, best[key]])))
    ts.sheet(fam_p, os.path.join(REV, "_c.png"), cols=5)
    stack([os.path.join(REV, n) for n in ("_a.png", "_b.png", "_c.png")], os.path.join(REV, "t418_cand.png"))
    print("лист:", os.path.join(REV, "t418_cand.png"))
    do_scene(per_seed)


def do_scene(per_seed=None):
    import ticket_scene as ts
    if per_seed is None:
        per_seed = {}
        for job, s in SHEET:
            p = os.path.join(CAND, "B", "_seeds", "PORTROADS_34_s%d.png" % s)
            if os.path.exists(p):
                per_seed[(job, s)] = {BASE: Image.open(p).convert("RGBA")}
    sc = ts.Scene()
    sheets = []
    for name, terrain, block in SCENES:
        found = ts.find_cells(sc, terrain, block, [BASE])
        cell = max(found, key=lambda f: (-f[3], f[2][1]))
        box = ts.window([(cell[0], cell[1], tuple(v * 4 for v in cell[2]))], 88, 64, 4)
        todo = [("классика", "classic", None), ("HD сейчас", "hd", None)]
        todo += [("зерно %d" % s, "hd", {BASE: fam[BASE]}) for (job, s), fam in per_seed.items()]
        panels = []
        for title, mode, ov in todo:
            im, _f = sc.render(terrain, block, mode, override=ov, k=4, maxz=cell[3])
            panels.append(("%s: %s" % (name, title), ts.crop_pad(im, box)))
        out = os.path.join(REV, "_s_%s.png" % name)
        ts.sheet(panels, out, cols=len(panels))
        sheets.append(out)
    stack(sheets, os.path.join(REV, "t418_scenes.png"))
    print("лист:", os.path.join(REV, "t418_scenes.png"))
