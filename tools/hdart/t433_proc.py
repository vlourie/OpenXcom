#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000433: лестница лифта XB3BITZ2:25 (1 этаж, старая) и :26 (2 этаж, новая Qwen strict 12.10) - два вида на соседних этажах.

Вариант A (Vitali 30.10), без видеокарты: :25 = одобренная HD :26 (лестница и тонкий контур ромба - те же пиксели) + решётка ПОД ней из классики
:25. Решётка: классический кадр :25, у которого пиксели лестницы заменены соседними (cv2.inpaint), увеличенный x4 (клетка x4 с лёгким размытием 1.1 пикс: прямые края клеток, без киселя бикубики),
обрезанный по внутренности контура :26 (заливка прозрачного ромба внутри контура - край решётки это край контура, прямые 2:1 одобренной :26,
лесенки нет); лестница и контур :26 кладутся сверху как есть.
Семья (ticket_family.py, R-457): :25 = XB3BITZ2:25 + METRO1:67, NINJATECH:69, RUSTSHACKS:49, URBAN_WASTE_WALLS:77 (побайтные копии классики);
:26 = XB3BITZ2:26 (одобрена, не меняется) + копии METRO1:68, RUSTSHACKS:48, URBAN_WASTE:114, URBAN_WASTE_WALLS:79 - им ставится HD :26 копией.

    py -3.13 tools\hdart\t433_proc.py build     кадры -> art/tickets/t433/cand/<НАБОР>_<кадр>.png (9 шт), лист и сцена в art/_review/tickets_2026-10-30/
В мод ничего не ставит (арт - сначала показать Vitali).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
os.chdir(ROOT)

import cv2                                   # noqa: E402
import numpy as np                           # noqa: E402
from PIL import Image                        # noqa: E402
from scipy import ndimage                    # noqa: E402

K = 4
OUT = os.path.join(ROOT, "art", "tickets", "t433", "cand")
REV = os.path.join(ROOT, "art", "_review", "tickets_2026-10-30")
FAM25 = [("XB3BITZ2", 25), ("METRO1", 67), ("NINJATECH", 69), ("RUSTSHACKS", 49), ("URBAN_WASTE_WALLS", 77)]
FAM26 = [("METRO1", 68), ("RUSTSHACKS", 48), ("URBAN_WASTE", 114), ("URBAN_WASTE_WALLS", 79)]   # + XB3BITZ2:26 (не трогаем)


def interior(hd26, thr=40):
    """Прозрачный ромб внутри контура :26: связная область alpha<thr от точки в нижней части ромба. -> bool (160,128)."""
    a = np.asarray(hd26)[..., 3]
    free = a < thr
    lab, n = ndimage.label(free)
    seed = lab[136, 40]
    assert seed > 0, "точка заливки попала на контур"
    return lab == seed


def grate_layer(sc, inner):
    """Решётка классики :25 x4 (RGBA 128x160): лестница вынута inpaint, бикубика, альфа - внутренность контура :26 + 1 пикс x4 под линию."""
    c25 = np.asarray(sc.classic("XB3BITZ2", 25))[::K, ::K].copy()
    c26 = np.asarray(sc.classic("XB3BITZ2", 26))[::K, ::K]
    same = np.all(c25 == c26, axis=2) & (c25[..., 3] > 0)
    # пиксели решётки отличаются от :26 (там прозрачно или контур); совпадающие и непрозрачные внутри ромба - лестница
    inner1 = np.asarray(Image.fromarray((inner * 255).astype(np.uint8)).resize((32, 40), Image.BOX)) > 100
    ladder = same & inner1
    # внутри ромба решётка закрыта лестницей: брать соседние пиксели решётки
    rgb = c25[..., :3].copy()
    hole = ladder.astype(np.uint8)
    rgb = cv2.inpaint(rgb, hole, 3, cv2.INPAINT_TELEA)
    up = cv2.resize(rgb, (32 * K, 40 * K), interpolation=cv2.INTER_NEAREST)
    up = cv2.GaussianBlur(up, (0, 0), 1.1)           # клетки решётки: прямые края, мягкая кромка (не ступенька x4 и не кисель бикубики)
    # растянуть цвет решётки за границу внутренности (на 3 пикс), чтобы под линией контура не было просвета
    m = ndimage.binary_dilation(inner, iterations=2)
    out = np.dstack([up, (m * 255).astype(np.uint8)])
    return Image.fromarray(out, "RGBA")


def build_frames(sc):
    hd26 = sc.hd("XB3BITZ2", 26)
    inner = interior(hd26)
    g = grate_layer(sc, inner)
    new25 = g.copy()
    new25.alpha_composite(hd26)
    return hd26, new25, g, inner


def build():
    import ticket_scene as ts
    sc = ts.Scene()
    hd26, new25, g, inner = build_frames(sc)
    os.makedirs(OUT, exist_ok=True)
    files = []
    for s, f in FAM25:
        p = os.path.join(OUT, "%s_%d.png" % (s, f))
        new25.save(p)
        files.append(p)
    for s, f in FAM26:
        p = os.path.join(OUT, "%s_%d.png" % (s, f))
        hd26.save(p)
        files.append(p)
    print("кадров: %d -> %s" % (len(files), OUT))
    return sc, hd26, new25, g, inner


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "build":
        build()
    else:
        print(__doc__)


def sheet():
    sc, hd26, new25, g, inner = build()
    from PIL import ImageDraw
    cand = {("XB3BITZ2", 25): new25}
    bg = (50, 60, 52, 255)

    def on_bg(im, z=2):
        p = Image.new("RGBA", im.size, bg)
        p.alpha_composite(im)
        return p.resize((im.width * z // 1, im.height * z // 1), Image.NEAREST if im.width == 128 and False else Image.LANCZOS)

    def classic_up(s, f):
        return sc.classic(s, f)      # уже x4 NEAREST

    frames = [(s, f, 25) for s, f in FAM25] + [("XB3BITZ2", 26, 26)] + [(s, f, 26) for s, f in FAM26]
    z = 2
    cols = []
    for s, f, kind in frames:
        now = sc.hd(s, f)
        new = new25 if kind == 25 else hd26
        if s == "XB3BITZ2" and f == 26:
            new = hd26
        cols.append((s, f, sc.classic(s, f), now, new))
    cw, ch = 128 * z, 160 * z
    W = len(cols) * (cw + 6) + 6
    img = Image.new("RGB", (W, 3 * (ch + 6) + 6 + 70), (12, 12, 14))
    for i, (s, f, c, n, nw) in enumerate(cols):
        x = 6 + i * (cw + 6)
        for r, im in enumerate((c, n, nw)):
            p = Image.new("RGBA", (128, 160), bg)
            p.alpha_composite(im)
            img.paste(p.resize((cw, ch), Image.LANCZOS if r else Image.NEAREST).convert("RGB"), (x, 6 + r * (ch + 6) + 70))
        d = ImageDraw.Draw(img)
        d.text((x + 4, 6), "%s:%d" % (s, f), fill=(255, 220, 0), font=ts_font())
        d.text((x + 4, 28), "(= :%d)" % (25 if i < 5 else 26), fill=(200, 200, 200), font=ts_font(16))
    img.save(os.path.join(REV, "t433_cand.png"))
    print("лист", os.path.join(REV, "t433_cand.png"))
    return sc, cand


def ts_font(n=20):
    import ticket_scene as ts
    return ts.font(n)


def scene(sc, cand):
    """Блоки базы XBASE с лифтом на двух этажах подряд: :25 (низ) и :26 (верх) - классика | HD сейчас | кандидат.
    XBR_06 (4,0) z3-z4 и XBR_08 (7,2) z0-z1 (вид до верхнего из двух этажей)."""
    import ticket_scene as ts
    ovr = {("XB3BITZ2", 25): cand[("XB3BITZ2", 25)]}
    panels = []
    for blk, xy, z25, z26, w, h in (("XBR_06", (4, 0), 3, 4, 110, 120), ("XBR_08", (7, 2), 0, 1, 110, 120)):
        found = ts.find_cells(sc, "XBASE", blk, [("XB3BITZ2", 25), ("XB3BITZ2", 26)])
        f0 = [(a, b, tuple(v * 4 for v in r), z_, c_) for a, b, r, z_, c_ in found if c_ == xy and z_ in (z25, z26)]
        box = ts.window(f0, w, h, k=4)
        for title, mode, o in (("классика", "classic", None), ("HD сейчас", "hd", None), ("кандидат", "hd", ovr)):
            im, _f = sc.render("XBASE", blk, mode, override=o, k=4, maxz=z26)
            panels.append(("%s, этажи z%d (:25) и z%d (:26): %s" % (blk, z25, z26, title), ts.crop_pad(im, box)))
    ts.sheet(panels, os.path.join(REV, "t433_cand_scene.png"), cols=3)
    print("сцена", os.path.join(REV, "t433_cand_scene.png"))


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "sheet":
    _sc, _cand = sheet()
    scene(_sc, _cand)
