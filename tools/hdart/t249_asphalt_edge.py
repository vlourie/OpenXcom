#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000249: края асфальта ROADS_WASTE 1-8 - формы классики назад, без генерации.

Классика: у кадров 1-8 чёрные языки асфальта (индексы 244-251) по песку (85-91) - чёткая рваная кромка. HD пака
(sdxl_legacy 21.09, прежний пак, ни одного одобрения) - пёстрая каменистая фактура на весь кадр, формы асфальта
потеряны, у 8 золотистый тон. Лечение - маска классики, как у плоских плиток (flat_tile.py, R-296):

  1. Маска асфальта = пиксели классики не из рампы песка (85-91); за силуэтом классики класс ближайшего пикселя.
     Мягкое x4 (water_build.soft_mask): рваный зубец в 1-2 пикселя базы остаётся зубцом, лесенки 8x4 нет.
  2. Асфальт - HD ROADS_WASTE 9 (чистый асфальт того же набора, 109 клеток в блоке URBANWASTE49), песок - HD
     URBITS_WASTE 16 (чистый песок, классика та же рампа 85-88). Кадры сидят каждый в своих координатах клетки,
     поэтому сосед 9 или 16 продолжается без шва (R-249). Вне их альфы цвет дотянут от края.
  3. У кромки песок темнеет так же, как в классике (индексы 90/91 - тень языка): множитель = размытая яркость
     классики песка к средней яркости чистого песка, только в полосе EDGE от кромки (R-265: клетку целиком по
     низким частотам не переносить).
  4. Альфа - силуэт классики x4 плюс точный ромб (ground_seam.classic_alpha, R-247).
Копии: у кадров 1-8 побайтных копий классики в других наборах нет (ticket_family.py: 5 и 6 - зеркало с перекраской
друг друга, оба в этой же правке и каждый строится по СВОЕЙ маске классики). Вариантов .vN у них нет.

    py -3.13 tools/hdart/t249_asphalt_edge.py                  # кадры в art/tickets/t249/out/TERRAIN/ROADS_WASTE.PCK
    py -3.13 tools/hdart/t249_asphalt_edge.py --sheet          # лист art/_review/tickets_2026-10-23/t249_after.png
    py -3.13 tools/hdart/t249_asphalt_edge.py --install --yes  # + в мод hd через манифест (по слову Vitali, под очередью правок)
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import ground_seam as gs            # noqa: E402
import ticket_scene as ts           # noqa: E402
import water_build as wb            # noqa: E402

SET = "ROADS_WASTE"
FRAMES = list(range(1, 9))
OUT = ROOT / "art" / "tickets" / "t249" / "out"
REVIEW = ROOT / "art" / "_review" / "tickets_2026-10-23"
ASPH_SRC = ("ROADS_WASTE", 9)
SAND_SRC = ("URBITS_WASTE", 16)
SAND = (85, 91)                    # рампа песка классики
BLUR = 1.3                         # мягкость маски, пикс HD
EDGE = 14.0                        # полоса затенения песка у кромки, пикс HD
SHADE_MIN, SHADE_MAX = 0.62, 1.08


def load_hd(s, f):
    p = ts.PACK / (s + ".PCK") / ("%d.png" % f)
    return np.asarray(Image.open(p).convert("RGBA")).astype(np.float32)


def extend(rgba):
    """RGB кадра дотянут за его альфу ближайшим цветом (чтобы силуэт классики за ромбом не был дырой)."""
    a = rgba[..., 3] > 127
    idx = ndi.distance_transform_edt(~a, return_distances=False, return_indices=True)
    return rgba[..., :3][idx[0], idx[1]]


def class_mask(a):
    """Асфальт = 1, песок = 0, по классике; за силуэтом - класс ближайшего пикселя."""
    sand = (a >= SAND[0]) & (a <= SAND[1])
    asph = ((a > 0) & ~sand).astype(np.float32)
    known = a > 0
    idx = ndi.distance_transform_edt(~known, return_distances=False, return_indices=True)
    return asph[idx[0], idx[1]]


def sand_ref_luma(pal):
    a = wb.read_set(SAND_SRC[0])[SAND_SRC[1]]
    m = a > 0
    return float((pal[a[m]][:, :3] @ gs.LUMA).mean())


def build(f, tex, ref):
    pal = wb.palette()
    a = wb.read_set(SET)[f]
    mask = wb.soft_mask(class_mask(a), BLUR)                  # 1 - асфальт
    t_asph, t_sand = tex
    # затенение песка у кромки: яркость классики песка, размытая только по песку
    sand = ((a >= SAND[0]) & (a <= SAND[1])).astype(np.float32)
    luma = (pal[a][..., :3].astype(np.float32) @ gs.LUMA) * sand
    num = wb.gauss(luma, 1.2)
    den = np.maximum(wb.gauss(sand, 1.2), 1e-3)
    shade = np.clip(num / den / ref, SHADE_MIN, SHADE_MAX)
    shade = np.where(wb.gauss(sand, 1.2) > 0.05, shade, 1.0)
    shade = np.asarray(Image.fromarray(shade.astype(np.float32), "F").resize((128, 160), Image.BICUBIC))
    # полоса у кромки: расстояние до асфальта по маске x4
    dist = ndi.distance_transform_edt(mask < 0.5)
    w_edge = np.clip(1.0 - dist / EDGE, 0, 1)
    s_mod = 1.0 + (shade - 1.0) * w_edge
    sand_rgb = t_sand * s_mod[..., None]
    rgb = mask[..., None] * t_asph + (1 - mask[..., None]) * sand_rgb
    al = gs.classic_alpha(a)
    out = np.dstack([np.clip(rgb, 0, 255), al * 255]).round().astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def build_all():
    pal = wb.palette()
    ref = sand_ref_luma(pal)
    tex = (extend(load_hd(*ASPH_SRC)), extend(load_hd(*SAND_SRC)))
    res = {}
    for f in FRAMES:
        res[f] = build(f, tex, ref)
        p = OUT / "TERRAIN" / (SET + ".PCK") / ("%d.png" % f)
        p.parent.mkdir(parents=True, exist_ok=True)
        res[f].save(p)
    return res


def make_sheet(res):
    from PIL import ImageDraw
    sc = ts.Scene()
    over = {(SET, f): im for f, im in res.items()}
    terr, block = "URBAN_WASTE", "URBANWASTE49"
    cls, _ = sc.render(terr, block, "classic", k=4, maxz=0)
    now, _ = sc.render(terr, block, "hd", k=4, maxz=0)
    new, _ = sc.render(terr, block, "hd", override=over, k=4, maxz=0)
    shot = Image.open(ROOT / "census" / "tickets" / "XP-000249" / "files" / "01_shot.png").convert("RGBA")
    # окна: участок парковки у бочки и у края (в px сцены x4)
    boxes = [(1000, 900, 2000, 1500), (1500, 1100, 2500, 1700)]
    rows = []
    for i, box in enumerate(boxes):
        ims = [("классика", cls), ("HD сейчас", now), ("HD новое", new)]
        rows += [("%s, окно %d" % (t, i + 1), ts.crop_pad(im, box)) for t, im in ims]
    # скриншот игрока: посадочная площадка, 1600x1000 вокруг машины
    sh = shot.crop((780, 440, 1820, 1040)).resize((1000, 577), Image.LANCZOS)
    panels = [("скриншот игрока (XP-249), площадка и край асфальта", sh)] + rows
    ts.sheet(panels, REVIEW / "t249_after.png", cols=3, width=900)
    # кадры 1-8: классика / сейчас / новое, x4
    fr = []
    for f in FRAMES:
        c = sc.classic(SET, f)
        h = sc.hd(SET, f)
        n = res[f]
        col = Image.new("RGBA", (128, 3 * 160 + 8), (26, 26, 30, 255))
        for j, im in enumerate((c, h, n)):
            col.alpha_composite(im, (0, j * 164))
        fr.append(("ROADS_WASTE %d" % f, col))
    ts.sheet(fr, REVIEW / "t249_frames.png", cols=8)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sheet", action="store_true")
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    res = build_all()
    print("кадров: %d -> %s" % (len(res), OUT))
    if a.sheet:
        make_sheet(res)
        print("лист:", REVIEW / "t249_after.png")
    if a.install:
        if not a.yes:
            raise SystemExit("сухой прогон; --install --yes - записать в мод (только по слову Vitali)")
        files = {"TERRAIN/%s.PCK/%d.png" % (SET, f): OUT / "TERRAIN" / (SET + ".PCK") / ("%d.png" % f) for f in FRAMES}
        ts.install_files(files, "t249_asphalt_edge", "t249_asphalt_edge.py 23.10 маска классики x4",
                         "Vitali 23.10 «чини все» (XP-000249); лист art/_review/tickets_2026-10-23/t249_after.png",
                         "t249: ROADS_WASTE 1-8 - края асфальта по маске классики")
    return 0


if __name__ == "__main__":
    sys.exit(main())
