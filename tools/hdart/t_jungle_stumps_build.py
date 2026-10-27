#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Мёртвые кадры джунглей JUNGLESTYX 62, 63, 64 - листы, сборка и установка (без видеокарты).
Генерация - t_jungle_stumps.py (Qwen-2.1 strict, только через gpuq); здесь зёрна -> кадры, лист, манифест.

    py -3.13 tools/hdart/t_jungle_stumps_build.py cand                 # лист вариантов art/tickets/jungle_stumps/cand.png
    py -3.13 tools/hdart/t_jungle_stumps_build.py build               # CHOICE -> out/TERRAIN/... и лист sheet.png
    py -3.13 tools/hdart/t_jungle_stumps_build.py build --install --yes   # + в мод hd через манифест (под очередью правок,
                                                                      # обе копии, сверка хэшей; только по слову Vitali)
Кадров на установку: JUNGLESTYX 62-64 и перекраски JUNGLEBITS 62-64 (ticket_family.py, R-457) - 6 файлов.
"""
import argparse
import os
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.join(HERE, "..")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from PIL import Image, ImageDraw, ImageFont         # noqa: E402

from t_jungle_stumps import SET, BASE, GEN, OUT, SEEDS, LIVE   # noqa: E402

CHOICE = {62: 6201, 63: 6301, 64: 6402}   # выбор по листу cand.png (23.10; 63: 6302 -> 6301 27.10 - два пятна рядом читались глазами)
GREY, DARK = (110, 110, 116), (24, 20, 18)
BOX = (0, 80, 128, 160)


def font(n=16):
    try:
        return ImageFont.truetype("C:/Windows/Fonts/arial.ttf", n)
    except OSError:
        return ImageFont.load_default()


def on(im, bg, box, k):
    c = im.crop(box)
    c = c.resize((int(c.width * k), int(c.height * k)), Image.LANCZOS if im.width > 40 else Image.NEAREST)
    out = Image.new("RGBA", c.size, bg + (255,))
    out.alpha_composite(c)
    return out


def cand_path(fr, seed):
    return os.path.join(GEN, "series", SET + ".PCK", "%d_%d.png" % (fr, seed))


def out_path(s, fr):
    return os.path.join(OUT, "TERRAIN", s + ".PCK", "%d.png" % fr)


def grid(rows, path, cw, ch):
    f = font(16)
    ncol = max(len(r) for r in rows)
    out = Image.new("RGB", (ncol * (cw + 8) + 8, len(rows) * (ch + 30) + 8), (12, 12, 14))
    d = ImageDraw.Draw(out)
    for y, r in enumerate(rows):
        for x, (t, im) in enumerate(r):
            ox, oy = 8 + x * (cw + 8), 8 + y * (ch + 30)
            d.text((ox, oy), t, fill=(255, 220, 0), font=f)
            out.paste(im.convert("RGB"), (ox, oy + 24))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    out.save(path)
    print("лист:", path, out.size)


def do_cand():
    import ticket_scene as ts
    sc = ts.Scene()
    rows = []
    for fr in (62, 63, 64):
        cells = [("классика %d" % fr, on(sc.classic(SET, fr), GREY, BOX, 2.5)),
                 ("соседний HD 65", on(sc.hd(SET, 65), GREY, BOX, 2.5))]
        for s in SEEDS[fr]:
            p = cand_path(fr, s)
            if os.path.exists(p):
                cells.append(("зерно %d" % s, on(Image.open(p).convert("RGBA"), GREY, BOX, 2.5)))
        rows.append(cells)
    grid(rows, os.path.join(BASE, "cand.png"), 320, 250)


def lab_shift_family(base_rgba, f):
    """Член семьи JUNGLEBITS (перекраска STYX: красное свечение -> янтарное). Средний Lab всего кадра для этого мал
    (красное - малая часть), поэтому: по пикселям классики, где JUNGLEBITS отличается от JUNGLESTYX, берётся поворот и
    масштаб хромы (a,b) и сдвиг яркости; в HD они применяются с весом по краснотной хроме пикселя. Остальное - как основа."""
    import cv2
    import numpy as np
    import water_build as wb
    pal = wb.palette()

    def lab(a):
        return cv2.cvtColor(np.clip(a, 0, 255).astype(np.float32) / 255, cv2.COLOR_RGB2Lab)

    cs, cb = wb.read_set(SET)[f], wb.read_set("JUNGLEBITS")[f]
    diff = (cs > 0) & (cb > 0) & (cs != cb)
    ls = lab(pal[cs[diff]][..., :3].astype(np.float32).reshape(-1, 1, 3)).reshape(-1, 3).mean(0)
    lb = lab(pal[cb[diff]][..., :3].astype(np.float32).reshape(-1, 1, 3)).reshape(-1, 3).mean(0)
    th = np.arctan2(lb[2], lb[1]) - np.arctan2(ls[2], ls[1])
    sc = float(np.hypot(lb[1], lb[2]) / max(1e-6, np.hypot(ls[1], ls[2])))
    dl = float(lb[0] - ls[0])
    r = base_rgba.astype(np.float32).copy()
    L = lab(r[..., :3])
    a, b = L[..., 1], L[..., 2]
    ch = np.hypot(a, b)
    cosang = (a * ls[1] + b * ls[2]) / np.maximum(ch * np.hypot(ls[1], ls[2]), 1e-6)
    w = np.clip((ch - 12) / 25, 0, 1) * np.clip((cosang - 0.4) / 0.4, 0, 1)
    ca, sa = np.cos(th), np.sin(th)
    na, nb = (a * ca - b * sa) * sc, (a * sa + b * ca) * sc
    L[..., 1] = a * (1 - w) + na * w
    L[..., 2] = b * (1 - w) + nb * w
    L[..., 0] = L[..., 0] + 0.5 * dl * w
    r[..., :3] = np.clip(cv2.cvtColor(L, cv2.COLOR_Lab2RGB) * 255, 0, 255)
    return r, np.array([0.0, np.degrees(th), sc])


def defringe(a):
    """Светлая розовая кромка (подложка просочилась в мягкий край): цвет пикселей с альфой < 235 берётся у ближайшего
    плотного пикселя (альфа >= 235) и чуть темнится; альфа не меняется (она по маске классики, R-089)."""
    import numpy as np
    from scipy import ndimage as ndi
    a = a.copy()
    solid = a[..., 3] >= 235
    idx = ndi.distance_transform_edt(~solid, return_distances=False, return_indices=True)
    ring = (a[..., 3] > 0) & ~solid
    near = a[..., :3][idx[0], idx[1]].astype(np.float32) * 0.92
    a[..., :3][ring] = near[ring].astype(np.uint8)
    return a


def build_all():
    import numpy as np
    res = {}
    for fr, seed in CHOICE.items():
        base = defringe(np.asarray(Image.open(cand_path(fr, seed)).convert("RGBA")).astype(np.uint8))
        res[(SET, fr)] = base
        r, d = lab_shift_family(base, fr)
        print("JUNGLEBITS:%d поворот хромы красного по классике: %.1f градусов, масштаб %.2f" % (fr, d[1], d[2]))
        res[("JUNGLEBITS", fr)] = np.clip(r, 0, 255).round().astype(np.uint8)
    return res


def save_all(res):
    paths = {}
    for (s, f), p in res.items():
        q = out_path(s, f)
        os.makedirs(os.path.dirname(q), exist_ok=True)
        Image.fromarray(p, "RGBA").save(q)
        paths["TERRAIN/%s.PCK/%d.png" % (s, f)] = q
    return paths


def do_sheet():
    import ticket_scene as ts
    sc = ts.Scene()
    rows = []
    for fr in (62, 63, 64):
        new = Image.open(out_path(SET, fr)).convert("RGBA")
        cells = [("классика x4 (%s:%d)" % (SET, fr), on(sc.classic(SET, fr), GREY, BOX, 2.5))]
        for lv in LIVE[fr]:
            cells.append(("живое HD %d" % lv, on(sc.hd(SET, lv), GREY, BOX, 2.5)))
        cells.append(("соседний HD 65", on(sc.hd(SET, 65), GREY, BOX, 2.5)))
        cells.append(("НОВОЕ HD %d" % fr, on(new, GREY, BOX, 2.5)))
        cells.append(("НОВОЕ на тёмном полу", on(new, DARK, BOX, 2.5)))
        a = on(sc.hd("JUNGLEBITS", fr), GREY, BOX, 1.25)
        b = on(Image.open(out_path("JUNGLEBITS", fr)).convert("RGBA"), GREY, BOX, 1.25)
        pair = Image.new("RGBA", (a.width * 2 + 4, a.height), (12, 12, 14, 255))
        pair.paste(a, (0, 0))
        pair.paste(b, (a.width + 4, 0))
        cells.append(("JUNGLEBITS сейчас | новое", pair))
        rows.append(cells)
    grid(rows, os.path.join(BASE, "sheet.png"), 320, 250)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["cand", "build"])
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    if a.cmd == "cand":
        do_cand()
        return 0
    if not CHOICE:
        raise SystemExit("CHOICE пуст: выбери зёрна по cand.png")
    paths = save_all(build_all())
    print("кадров: %d -> %s" % (len(paths), OUT))
    do_sheet()
    if a.install:
        if not a.yes:
            raise SystemExit("сухой прогон; --install --yes - записать в мод (только по слову Vitali)")
        import ticket_scene as ts
        ts.install_files(paths, "t_jungle_stumps", "t_jungle_stumps.py 23.10, Qwen-2.1 strict, зёрна %s" % CHOICE,
                         "Vitali 23.10 «Арт разрешаю» (JUNGLESTYX 62-64, мёртвые кадры джунглей)",
                         "jungle: мёртвые кадры JUNGLESTYX 62-64 и JUNGLEBITS 62-64 - Qwen-2.1 strict")
    return 0


if __name__ == "__main__":
    sys.exit(main())
