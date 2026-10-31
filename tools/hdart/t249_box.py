#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000249: сломанный деревянный ящик URBAN_WASTE 91 (92 - его зеркало) и семья - без видеокарты, из готового кадра.

Vitali 23.10: «зеркальный остов разрушенной деревянной коробки с тенью внутри» - стенки из досок, проломлен, внутри тень.
Текущий HD (sdxl_legacy, без одобрения) - размытая песочная чаша без досок, ступенчатая альфа; g0922 URBAN:91 - доски есть,
но внутри щепа и красное нутро.

Что делается (пробный сбор, решение по листу t249_box2.png за Vitali):
  1. Основа - g0922 URBAN:91 (доски стенок). 92 строится из зеркала той же основы по маске классики 92.
  2. Нутро: тёмная область классики (яркость ниже DARK) x4, мягкая; цвет нутра - глубокая тень с яркостью классики
     (структура остаётся), щепа и красное нутро основы вместо этого не попадают в кадр.
  3. Силуэт: альфа основы, ограниченная сглаженной маской классики x4 (рваный верх классики остаётся мягкими зубцами,
     лесенки 4x4 нет), край мягкий.
  4. Тон: хрома среднего Lab - к классике.
Побайтные копии классики 91/92 в других наборах - см. SKIP/FAMILY: ящиком они являются не везде.

    py -3.13 tools/hdart/t249_box.py                  # кадры в art/tickets/t249/out_box/TERRAIN/...
    py -3.13 tools/hdart/t249_box.py --sheet          # лист art/_review/tickets_2026-10-23/t249_box2.png
    py -3.13 tools/hdart/t249_box.py --install --yes  # + в мод hd через манифест (по слову Vitali, под очередью правок)
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import ticket_scene as ts           # noqa: E402
import water_build as wb            # noqa: E402

DONOR = ROOT / "art" / "_backup" / "hd_TERRAIN_2026-09-22" / "URBAN.PCK" / "91.png"
OUT = ROOT / "art" / "tickets" / "t249" / "out_box"
REVIEW = ROOT / "art" / "_review" / "tickets_2026-10-23"
SET = "URBAN_WASTE"
DARK = 78.0                         # яркость классики: ниже - нутро
SHADOW = np.array([50.0, 37.0, 27.0], np.float32)
SS = 8
LUMA = np.array([0.299, 0.587, 0.114], np.float32)
# семья (ticket_family.py): 91 - COMDECOR:43, CRIBDECOR:44, IDT_SNOWVILBAN:87, URBANLUX:91, URBANWAR:91, URBAN_GOODS:91,
# VILBAN:87, URBAN:91 (перекраска); 92 - COMDECOR:44, CRIBDECOR:45, CULTDECOR:20, IDT_SNOWVILBAN:88, MADDECOR:19,
# MADDECOR_WASTE:18, SEAMADDECOR:19, URBANLUX:92, URBANWAR:92, URBAN_GOODS:92, VILBAN:88, URBAN:92.
FAMILY = {91: [("COMDECOR", 43), ("CRIBDECOR", 44), ("IDT_SNOWVILBAN", 87), ("URBANLUX", 91), ("URBANWAR", 91),
               ("URBAN_GOODS", 91), ("VILBAN", 87), ("URBAN", 91)],
          92: [("COMDECOR", 44), ("CRIBDECOR", 45), ("CULTDECOR", 20), ("IDT_SNOWVILBAN", 88), ("MADDECOR", 19),
               ("MADDECOR_WASTE", 18), ("SEAMADDECOR", 19), ("URBANLUX", 92), ("URBANWAR", 92), ("URBAN_GOODS", 92),
               ("VILBAN", 88), ("URBAN", 92)]}


def lab(rgb):
    return cv2.cvtColor(np.clip(rgb, 0, 255).astype(np.float32) / 255, cv2.COLOR_RGB2Lab)


def unlab(x):
    return np.clip(cv2.cvtColor(x.astype(np.float32), cv2.COLOR_Lab2RGB) * 255, 0, 255)


def up(x, interp=cv2.INTER_CUBIC):
    return cv2.resize(x.astype(np.float32), (128, 160), interpolation=interp)


def soft_classic_mask(a, sig):
    m = (a > 0).astype(np.float32)
    hi = cv2.resize(m, (128 * SS, 160 * SS), interpolation=cv2.INTER_LINEAR)
    g = cv2.GaussianBlur(hi, (0, 0), sig * SS)
    g = np.clip((g - 0.5) * 3.0 + 0.5, 0, 1)
    return cv2.resize(g, (128, 160), interpolation=cv2.INTER_AREA)


def build(f, src):
    pal = wb.palette()
    a = wb.read_set(SET)[f]
    cl = pal[a][..., :3].astype(np.float32)
    lum = cl @ LUMA
    sil = soft_classic_mask(a, 2.2)
    alpha = np.clip(src[..., 3] / 255.0, 0, 1) * sil
    # нутро: тёмное по классике
    dark = ((lum < DARK) & (a > 0)).astype(np.float32)
    dm = cv2.resize(dark, (128 * SS, 160 * SS), interpolation=cv2.INTER_LINEAR)
    dm = cv2.GaussianBlur(dm, (0, 0), 1.6 * SS)
    dm = cv2.resize(dm, (128, 160), interpolation=cv2.INTER_AREA)
    dm = np.clip((dm - 0.15) * 2.2, 0, 1)
    # тень: глубокий тёмный тон, структура - из яркости классики (размытой)
    lb = cv2.GaussianBlur(lum * (a > 0), (0, 0), 1.0) / np.maximum(cv2.GaussianBlur((a > 0).astype(np.float32), (0, 0), 1.0), 1e-3)
    lbu = up(lb)
    shade = SHADOW[None, None, :] * (0.40 + 1.15 * np.clip(lbu / max(DARK, 1.0), 0, 1.3))[..., None]
    rgb = src[..., :3] * (1 - dm[..., None]) + shade * dm[..., None]
    # цвет стенок: хрома среднего Lab к классике (яркость доски - своя)
    wall = (alpha > 0.5) & (dm < 0.2)
    cl_up = np.asarray(Image.fromarray(np.clip(cl, 0, 255).astype(np.uint8)).resize((128, 160), Image.NEAREST)).astype(np.float32)
    wall_cl = ((a > 0) & (lum >= DARK)).astype(np.float32)
    wc = np.asarray(Image.fromarray((wall_cl * 255).astype(np.uint8)).resize((128, 160), Image.NEAREST)) > 127
    if wall.sum() and (wall & wc).sum():
        m_new = lab(rgb)[wall].mean(0)
        m_cls = lab(cl_up)[wall & wc].mean(0)
        d = np.array([0.0, m_cls[1] - m_new[1], m_cls[2] - m_new[2]], np.float32)
        L = lab(rgb) + d * (1 - dm[..., None])
        rgb = unlab(L)
    return np.dstack([np.clip(rgb, 0, 255), alpha * 255])


def mirror(p):
    return p[:, ::-1].copy()


SKIPPED = [("URBAN", 91), ("URBAN", 92)]     # у набора URBAN этот кадр - куча обломков (map_paint, другой предмет): не трогать


def mean_lab(p):
    m = p[..., 3] > 127
    return lab(p[..., :3])[m].mean(0)


def load(path):
    return np.asarray(Image.open(path).convert("RGBA")).astype(np.float32)


def build_all():
    d = load(DONOR)
    base = {91: build(91, d), 92: build(92, mirror(d))}
    res = {(SET, 91): base[91], (SET, 92): base[92]}
    for f in (91, 92):
        ref = mean_lab(load(ts.PACK / (SET + ".PCK") / ("%d.png" % f)))
        for s, ff in FAMILY[f]:
            if (s, ff) in SKIPPED:
                continue
            p = ts.PACK / (s + ".PCK") / ("%d.png" % ff)
            if not p.exists():
                continue
            dl = mean_lab(load(p)) - ref
            dl[0] = 0.0                      # хрома набора (R-457), яркость - как у основы
            r = base[f].copy()
            r[..., :3] = unlab(lab(r[..., :3]) + dl)
            res[(s, ff)] = r
    return res


def save_all(res):
    paths = {}
    keep = {OUT / "TERRAIN" / (s + ".PCK") / ("%d.png" % f) for (s, f) in res}
    if (OUT / "TERRAIN").exists():
        for old in (OUT / "TERRAIN").rglob("*.png"):
            if old not in keep:
                old.unlink()
    for (s, f), p in res.items():
        d = OUT / "TERRAIN" / (s + ".PCK")
        d.mkdir(parents=True, exist_ok=True)
        q = d / ("%d.png" % f)
        Image.fromarray(np.clip(p, 0, 255).round().astype(np.uint8), "RGBA").save(q)
        paths["TERRAIN/%s.PCK/%d.png" % (s, f)] = q
    return paths


def to_img(p):
    return Image.fromarray(np.clip(p, 0, 255).round().astype(np.uint8), "RGBA")


def on_grey(im, k=5, bg=(110, 110, 116)):
    box = (0, 70, 128, 160)
    c = im.crop(box).resize((128 * k, 90 * k), Image.NEAREST)
    out = Image.new("RGBA", c.size, bg + (255,))
    out.alpha_composite(c)
    return out


def scene_overlay(sc, frames, label_block="URBANWASTE49", cells=((7, 8), (9, 8))):
    """Парковка URBANWASTE49 с ящиком 91 и 92 на свободных клетках - как их видит игрок (без блока, где ящик встретился бы сам:
    он остаётся после разрушения ящика в бою)."""
    import map_mockup as mm
    terr = "URBAN_WASTE"
    base = sc.render(terr, label_block, "hd", k=4, maxz=0)[0]
    sx, sy, sz, _ = mm.read_block(sc.w, label_block)
    ox, oy = sy * 16, sz * 24 + 8
    out = base.copy()
    for (x, y), im in zip(cells, frames):
        px, py = ox + (x - y) * 16, oy + (x + y) * 8
        out.alpha_composite(im.resize((128, 160), Image.LANCZOS), (px * 4, py * 4))
    cx = ox + (cells[0][0] - cells[0][1]) * 16 + 16
    cy = oy + (cells[0][0] + cells[0][1]) * 8 + 24
    return out, (int(cx * 4 - 480), int(cy * 4 - 300), int(cx * 4 + 480), int(cy * 4 + 200))


def make_sheet(res):
    sc = ts.Scene()
    panels = []
    for f in (91, 92):
        panels += [("классика x4 %d" % f, on_grey(sc.classic(SET, f))), ("HD сейчас %d" % f, on_grey(sc.hd(SET, f))),
                   ("HD новое %d" % f, on_grey(to_img(res[(SET, f)])))]
    ts.sheet(panels, REVIEW / "t249_box2.png", cols=3)
    s1 = Image.open(REVIEW / "t249_box2.png")
    try:
        frames_now = [sc.hd(SET, 91), sc.hd(SET, 92)]
        frames_new = [to_img(res[(SET, 91)]), to_img(res[(SET, 92)])]
        a, box = scene_overlay(sc, frames_now)
        b, _ = scene_overlay(sc, frames_new)
        cls_fr = [sc.classic(SET, 91).resize((128, 160), Image.NEAREST), sc.classic(SET, 92).resize((128, 160), Image.NEAREST)]
        c, _ = scene_overlay(sc, cls_fr)
        ts.sheet([("сцена: классика", ts.crop_pad(c, box)), ("сейчас", ts.crop_pad(a, box)), ("новое", ts.crop_pad(b, box))],
                 REVIEW / "_t249_box2_scene.png", cols=3)
        s2 = Image.open(REVIEW / "_t249_box2_scene.png")
        W = max(s1.width, s2.width)
        out = Image.new("RGB", (W, s1.height + s2.height), (12, 12, 14))
        out.paste(s1, (0, 0))
        out.paste(s2, (0, s1.height))
        out.save(REVIEW / "t249_box2.png")
        (REVIEW / "_t249_box2_scene.png").unlink()
    except Exception as e:                                     # сцена - довесок, лист кадров уже записан
        print("сцена не собрана:", e)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sheet", action="store_true")
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    res = build_all()
    paths = save_all(res)
    print("кадров: %d -> %s" % (len(res), OUT))
    if a.sheet:
        make_sheet(res)
        print("лист:", REVIEW / "t249_box2.png")
    if a.install:
        if not a.yes:
            raise SystemExit("сухой прогон; --install --yes - записать в мод (только по слову Vitali)")
        ts.install_files(paths, "t249_box", "t249_box.py 23.10 g0922 URBAN:91, нутро - тень",
                         "Vitali 23.10 (XP-000249 ящик); лист art/_review/tickets_2026-10-23/t249_box2.png",
                         "t249: ящик URBAN_WASTE 91/92 - доски и тень")
    return 0


if __name__ == "__main__":
    sys.exit(main())
