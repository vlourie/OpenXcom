#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000395, переделка 31.10 (Vitali: «Переделать: без сердечка, кочан крупнее, до края ромба»).

Семья кадров: CULTIVAT_UBER:7 (основа, цвет генерации), CULTIVAT:7 (серая серединка), CULTIVAT_PP:7 (пурпур),
VILFRNITURE:104 (копия CULTIVAT:7). Генерация - t394_395_gen.py, задания cab7b / cab7c (без слова heart, размер оригинала не
требуется), зёрна 3961-3966 и 3971-3976. Этот скрипт - сборка кадров из зёрен и листы, видеокарта не нужна.

Что исправлено против кандидата 31.10 (t394_395_gen.cab_frame):
  - сердцевина: области - не по цвету пикселя, а по связной бледной области вокруг центра головки (бледные жилки внешних листьев
    больше не получают серый цвет сердцевины); у основы UBER цвет сердцевины - как у генерации, розовое проверяется числом;
  - земля: пиксели вне головки - всегда земля, а не «лист» (зелёные и пурпурные точки на верхнем углу ромба были землёй
    потемнее, которую цвет принял за лист);
  - край: альфа - точный ромб, под ним земля залита до краёв; пунктирная кромка (светлые точки вдоль края) гасится;
  - размер: кочан можно растянуть до заданной доли ширины ромба (--fill).

    py -3.13 tools\hdart\t395_v2.py seeds
    py -3.13 tools\hdart\t395_v2.py build --seed cab7b:3961 [--fill 0.9]
    py -3.13 tools\hdart\t395_v2.py sheets
В МОД НИЧЕГО НЕ СТАВИТ: кадры - art/tickets/t395/v2/<вариант>/<НАБОР>_<кадр>.png.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (HERE, os.path.join(HERE, "..")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np                                   # noqa: E402
from PIL import Image                                # noqa: E402
from scipy import ndimage                            # noqa: E402

import t394_395_gen as t                             # noqa: E402

g = t.g
REV = t.REVD
V2 = os.path.join(ROOT, "art", "tickets", "t395", "v2")
FAM = t.CAB_FAM
COPY = t.CAB_COPY
BASE = t.CAB_BASE
RIM_KEEP = 0.93          # доля полуширины ромба: глубже края 5 пикселей цвет из ответа, ближе - заливка изнутри


def hsv(rgb):
    import cv2
    x = np.clip(rgb, 0, 255).astype(np.float32).reshape(-1, 1, 3) / 255.0
    return cv2.cvtColor(x, cv2.COLOR_RGB2HSV).reshape(-1, 3)          # H 0..360, S, V 0..1


def classify(rgb, alive, center=None):
    """Области грядки: 0 земля, 1 лист, 2 сердцевина. rgb HxWx3, alive - bool.
    Лист: зелёный оттенок (55..175) или тёмный/насыщенный не-бурый; сердцевина: бледная (низкая насыщенность, светло) область,
    связная с центром головки (внутренние листья), закрытая и очищенная от одиночных пикселей; всё остальное - земля."""
    h, w = alive.shape
    hs = hsv(rgb.reshape(-1, 3)).reshape(h, w, 3)
    hue, sat, val = hs[..., 0], hs[..., 1], hs[..., 2]
    green = (hue >= 55) & (hue <= 175) & (sat > 0.12)
    brown = (hue >= 5) & (hue <= 45) & (sat > 0.35) & (val < 0.6) & ~green
    pale = (sat < 0.62) & (val > 0.55) & ~brown
    lab = np.zeros((h, w), np.int8)
    leaf = alive & green
    # головка: связная область зелени и бледных пикселей вокруг центра; одиночные зелёные пятнышки у края - не головка
    head = ndimage.binary_opening(leaf | (alive & pale), iterations=2)
    head = ndimage.binary_closing(head, iterations=3)
    cc, n = ndimage.label(head)
    if n:
        cy, cx = center if center else (h * 0.78, w / 2)
        sizes = ndimage.sum(head, cc, range(1, n + 1))
        k = int(np.argmax(sizes)) + 1
        head = cc == k
    lab[alive & head] = 1
    # сердцевина - бледное, связное с центром головки
    cand = alive & pale & head
    cand = ndimage.binary_opening(cand, iterations=1)
    cc, n = ndimage.label(cand)
    core = np.zeros_like(cand)
    if n:
        ys, xs = np.nonzero(head)
        cy, cx = ys.mean(), xs.mean()
        best, bd = 0, 1e9
        for i in range(1, n + 1):
            yy, xx = np.nonzero(cc == i)
            if len(yy) < 40:
                continue
            d = (yy.mean() - cy) ** 2 + ((xx.mean() - cx) * 0.5) ** 2
            if d < bd:
                best, bd = i, d
        if best:
            core = cc == best
            core = ndimage.binary_closing(core, iterations=3)
    lab[alive & core] = 2
    lab[~alive] = -1
    return lab


def classic_regions(key):
    """Области классики цели: 0 земля, 1 лист, 2 сердцевина (по палитре классики, как _seg_cab, но с областью-ядром)."""
    ct = np.asarray(t.g_classic(*key), np.float32)
    live = ct[..., 3] > 0
    lab = np.full(ct.shape[:2], -1, np.int8)
    lab[live] = t._seg_cab(ct[..., :3][live])
    return ct, lab


def pink_fraction(rgb, mask):
    """Доля розовых пикселей (оттенок 320..360 или 0..14, насыщенность 0.1..0.65, светло) в области mask."""
    if mask.sum() == 0:
        return 0.0
    hs = hsv(rgb[mask])
    hue, sat, val = hs[:, 0], hs[:, 1], hs[:, 2]
    pk = ((hue >= 320) | (hue <= 14)) & (sat >= 0.10) & (sat <= 0.65) & (val > 0.55)
    return float(pk.mean())


def head_stats(img):
    """Доля ширины ромба, которую занимает головка (по ряду её наибольшей ширины), и доля площади ромба под головкой."""
    a = np.asarray(img.convert("RGBA"))
    alive = a[..., 3] > 128
    lab = classify(a[..., :3].astype(np.float32), alive)
    head = lab >= 1
    if not head.any():
        return 0.0, 0.0
    ys, xs = np.nonzero(head)
    w = xs.max() - xs.min() + 1
    return float(w / 128.0), float(head.sum() / max(1, alive.sum()))


def classic_head_stats(key):
    ct, lab = classic_regions(key)
    head = lab >= 1
    ys, xs = np.nonzero(head)
    return float((xs.max() - xs.min() + 1) / 32.0), float(head.sum() / max(1, (ct[..., 3] > 0).sum()))


def enlarge_head(a, lab, fill, anchor=(64.0, 128.0)):
    """Головка (области 1 и 2) растянута вокруг центра ромба так, чтобы её ширина стала долей fill ширины кадра; поверх земли
    кадра. Земля под старой головкой перекрыта новой (масштаб > 1 от центра, головка выпуклая вокруг центра)."""
    head = lab >= 1
    ys, xs = np.nonzero(head)
    w0 = xs.max() - xs.min() + 1
    s = fill * 128.0 / w0
    if s <= 1.02:
        return a, 1.0
    soft = ndimage.gaussian_filter(head.astype(np.float32), 0.9)
    pm = np.dstack([a[..., :3] * soft[..., None], soft * 255.0]).astype(np.float32)
    im = Image.fromarray(np.clip(pm, 0, 255).astype(np.uint8), "RGBA")
    ax, ay = anchor
    coef = (1 / s, 0, ax - ax / s, 0, 1 / s, ay - ay / s)
    big = np.asarray(im.transform(im.size, Image.AFFINE, coef, Image.BICUBIC), np.float32)
    al = big[..., 3:4] / 255.0
    rgb = big[..., :3] / np.maximum(al, 1e-3)
    out = a.copy()
    out[..., :3] = rgb * al + out[..., :3] * (1 - al)
    return out, s


def recolor(a, lab, ob_key, key):
    """Цвет классики цели по областям (земля, лист, сердцевина): яркость - статистика области цели, цвет - по яркости из той же
    области (t._colorize). Области цели - по раскладке классики ОСНОВЫ."""
    cb, lb = classic_regions(ob_key)
    ct = np.asarray(t.g_classic(*key), np.float32)
    out = a.copy()
    for r in (0, 1, 2):
        src = lab == r
        tm = (lb == r) & (ct[..., 3] > 0)
        if src.sum() < 50 or tm.sum() < 5:
            continue
        ls, lt = t._lab(a[..., :3][src]), t._lab(ct[..., :3][tm])
        if r == 2:
            out[..., :3][src] = t._rgb(colorize_keep(ls, lt))
        else:
            out[..., :3][src] = t._rgb(t._colorize(ls, lt))
    return out


def colorize_keep(lab_src, lab_tgt, keep=0.85):
    """Сердцевина: рисунок яркости генерации сохраняется (складки внутренних листьев), среднее - к классике цели; цвет (a, b) - по
    яркости из классики цели. У классики цели сердцевина - горстка пикселей, её разброс яркости рисунок не передаёт."""
    ms = lab_src[:, 0].mean()
    mt = lab_tgt[:, 0].mean()
    Lt = lab_tgt[:, 0]
    out = np.empty_like(lab_src)
    out[:, 0] = np.clip((lab_src[:, 0] - ms) * keep + mt, Lt.min() - 6, Lt.max() + 14)
    for c in (1, 2):
        co = np.polyfit(Lt, lab_tgt[:, c], 1 if Lt.std() > 1.0 else 0)
        out[:, c] = np.polyval(co, np.clip(out[:, 0], Lt.min(), Lt.max()))
    return out


def cab2_frame(cut, key, fill=None, fixed_lab=None):
    """Кадр грядки из зерна: (при fill) головка до доли fill ширины, цвет классики цели по областям, альфа - точный ромб.
    Области берутся у ОСНОВЫ (до перекраски) и переносятся на цель без изменений; пустоты залиты землёй."""
    import rim_alpha as ra
    a = np.asarray(cut.convert("RGBA"), np.float32)
    alive = a[..., 3] >= 200
    lab = classify(a[..., :3], alive)
    s = 1.0
    if fill:
        a, s = enlarge_head(a, lab, fill)
        alive = np.ones_like(alive)
        alive = (a[..., 3] >= 200) | (np.asarray(cut.convert("RGBA"))[..., 3] >= 200)
        lab = classify(a[..., :3], alive)
    if key != BASE:
        a = recolor(a, lab, BASE, key)
    # кромка: полоса около 5 пикселей вдоль края ромба берётся не из ответа (там светлая каёмка ключа: пунктир светлых точек
    # вдоль края), а заливается изнутри ромба
    dd, _u, _v = ra.diamond(4)
    alive = alive & (dd < RIM_KEEP)
    if fill and fill >= 0.9:
        # головка почти во весь ромб: остатки земли у углов (оранжевые точки на левом и правом углу) - не земля, а листья
        alive = alive & (lab >= 1)
    cur = a.copy()
    cur[..., 3] = np.where(alive, 255, 0)
    rgb = ra.fill(cur.astype(np.uint8))
    d = t.diamond_alpha()
    out = np.zeros(a.shape, np.uint8)
    out[..., :3] = np.where(alive[..., None], np.clip(np.rint(a[..., :3]), 0, 255), np.clip(np.rint(rgb), 0, 255)).astype(np.uint8)
    out[..., 3] = np.rint(d * 255).astype(np.uint8)
    out[..., :3][out[..., 3] == 0] = 0
    return Image.fromarray(out, "RGBA"), s


def cut_of(job, seed):
    """Кадр зерна 128x160 RGBA (как pieces_of, но без вывода)."""
    pcs = g.pieces_of(job, seed)
    return pcs[BASE]


def frame_checks(img, key):
    a = np.asarray(img.convert("RGBA"))
    alive = a[..., 3] > 128
    lab = classify(a[..., :3].astype(np.float32), alive)
    wf, af = head_stats(img)
    core = lab == 2
    head = lab >= 1
    return dict(width=wf, area=af, pink_core=pink_fraction(a[..., :3].astype(np.float32), core),
                pink_head=pink_fraction(a[..., :3].astype(np.float32), head))


def build_variant(name, job, seed, fill=None):
    """5 кадров варианта в art/tickets/t395/v2/<name>/. Возвращает {(набор, кадр): Image} и числа."""
    d = os.path.join(V2, name)
    os.makedirs(d, exist_ok=True)
    cut = cut_of(job, seed)
    out, rows = {}, []
    for key in FAM:
        im, s = cab2_frame(cut, key, fill)
        im.save(os.path.join(d, "%s_%d.png" % key))
        out[key] = im
        rows.append((key, s, frame_checks(im, key)))
        if key in COPY:
            c = COPY[key]
            im.save(os.path.join(d, "%s_%d.png" % c))
            out[c] = im
    return out, rows


def load_variant(name):
    d = os.path.join(V2, name)
    ov = {}
    for fn in sorted(os.listdir(d)):
        if fn.endswith(".png"):
            s, f = fn[:-4].rsplit("_", 1)
            ov[(s, int(f))] = Image.open(os.path.join(d, fn)).convert("RGBA")
    return ov


def do_seeds(jobs):
    import ticket_scene as ts
    panels = []
    for job in jobs:
        for seed in g.all_seeds(job):
            if not os.path.exists(os.path.join(g.GEN, job, "%d.png" % seed)):
                continue
            im = cut_of(job, seed)
            c = frame_checks(im, BASE)
            sc = g.on_dark(im).crop((0, 88, 128, 160)).resize((384, 216), Image.NEAREST)
            panels.append(("%s %d  ширина %.0f%%  розовое %.1f%%" % (job, seed, c["width"] * 100, c["pink_head"] * 100), sc))
    ts.sheet(panels, os.path.join(REV, "t395_v2_seeds.png"), cols=3)
    print("лист:", os.path.join(REV, "t395_v2_seeds.png"))


def crop_bottom(im, k=4):
    c = g.on_dark(im).crop((0, 88, 128, 160))
    return c.resize((c.width * k, c.height * k), Image.LANCZOS)


def do_sheets(names):
    """t395_v2_cand.png: по строке на кадр - классика | сейчас | кандидат 31.10 | варианты names."""
    import ticket_scene as ts
    old = t.load_cand()
    var = {n: load_variant(n) for n in names}
    rows = []
    keys = FAM + [("VILFRNITURE", 104)]
    for key in keys:
        cls = g.classic_of(*key).resize((128, 160), Image.NEAREST)
        now = g.hd_now(*key)
        ims = [crop_bottom(cls, 4), crop_bottom(now, 4), crop_bottom(old[key], 4)] + [crop_bottom(var[n][key], 4) for n in names]
        W = sum(i.width for i in ims) + 6 * (len(ims) - 1)
        strip = Image.new("RGB", (W, ims[0].height), (12, 12, 14))
        x = 0
        for im in ims:
            strip.paste(im.convert("RGB"), (x, 0))
            x += im.width + 6
        rows.append(("%s:%d   [классика | сейчас | кандидат 31.10 | %s]" % (key[0], key[1], " | ".join(names)), strip))
    ts.sheet(rows, os.path.join(REV, "t395_v2_cand.png"), cols=1)
    print("лист:", os.path.join(REV, "t395_v2_cand.png"))


def do_scene(names):
    """t395_v2_scene.png: поле CULTAFARM11 (CULTA_UBER) - классика | сейчас | кандидат 31.10 | варианты."""
    import ticket_scene as ts
    sc = ts.Scene()
    found = ts.find_cells(sc, "CULTA_UBER", "CULTAFARM11", [("CULTIVAT_UBER", 7)])
    cell = max(found, key=lambda f: (-f[3], f[2][1]))
    box = ts.window([(cell[0], cell[1], tuple(v * 4 for v in cell[2]))], 150, 110, 4)
    panels = []
    sets = [("классика", "classic", None), ("HD сейчас", "hd", None), ("кандидат 31.10", "hd", t.load_cand())]
    sets += [(n, "hd", var) for n, var in ((n, load_variant(n)) for n in names)]
    for title, mode, o in sets:
        im, _f = sc.render("CULTA_UBER", "CULTAFARM11", mode, override=o, k=4, maxz=cell[3])
        panels.append((title, ts.crop_pad(im, box)))
    ts.sheet(panels, os.path.join(REV, "t395_v2_scene.png"), cols=1)
    print("лист:", os.path.join(REV, "t395_v2_scene.png"), "клеток", len(found))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["probe", "seeds", "build", "sheets", "scene"])
    ap.add_argument("--jobs", nargs="*", default=["cab7b", "cab7c"])
    ap.add_argument("--pick", nargs="*", default=[], help="вариант: job:seed[:fill], например cab7b:3961:0.9")
    a = ap.parse_args()
    if a.cmd == "seeds":
        do_seeds(a.jobs)
    elif a.cmd == "sheets":
        do_sheets(a.pick)
    elif a.cmd == "scene":
        do_scene(a.pick)
    elif a.cmd == "build":
        for p in a.pick:
            parts = p.split(":")
            job, seed = parts[0], int(parts[1])
            fill = float(parts[2]) if len(parts) > 2 else None
            name = "%s_%d%s" % (job, seed, "" if not fill else "_f%02d" % round(fill * 100))
            out, rows = build_variant(name, job, seed, fill)
            print(name)
            for key, s, c in rows:
                print("   %s:%d  масштаб %.2f  ширина %.2f  площадь %.2f  розовое в сердцевине %.3f  в головке %.3f" % (
                    key[0], key[1], s, c["width"], c["area"], c["pink_core"], c["pink_head"]))
    elif a.cmd == "probe":
        for key in FAM:
            print(key, "классика: ширина %.2f площадь %.2f" % classic_head_stats(key))
        old = Image.open(os.path.join(ROOT, "art", "tickets", "t394", "cand", "CULTIVAT_UBER_7.png"))
        print("кандидат 31.10 UBER:7: ширина %.2f площадь %.2f" % head_stats(old))
        now = Image.open(os.path.join(ROOT, "user", "mods", "hd", "hd", "TERRAIN", "CULTIVAT_UBER.PCK", "7.png"))
        print("сейчас UBER:7: ширина %.2f площадь %.2f" % head_stats(now))
    return 0


if __name__ == "__main__":
    sys.exit(main())
