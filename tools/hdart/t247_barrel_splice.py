# -*- coding: utf-8 -*-
"""Тикет XP-000247: горящая бочка MADDECOR_WASTE 62-65 - в HD-паке барабан нарисован в каждом кадре заново
и «плавает», а должен меняться только огонь. Склейка без генерации: где классика всех четырёх кадров
совпадает (барабан), берётся барабан HD-кадра 62; где классика меняется (огонь) - свой HD-кадр, с запасом
DILATE пикселей HD вокруг огня (R-123: маска классики не режет огонь пака). Семья - побайтные копии
(ticket_family.py): CATACDECOR_CONC 35-38, METRO1 117-120, URBITS_INDUSLUM 18-21.

    py -3.13 tools/hdart/t247_barrel_splice.py               # кадры и лист в art/tickets/t247/
    py -3.13 tools/hdart/t247_barrel_splice.py --install --yes   # + в мод hd через манифест (обе копии)
"""
import argparse
import hashlib
import os
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import xcom_sprites as xs  # noqa: E402

PCK = os.path.join(ROOT, "Пиратки", "Dioxine_XPiratez", "user", "mods", "Piratez", "TERRAIN", "MADDECOR_WASTE.PCK")
HD = os.path.join(ROOT, "user", "mods", "hd", "hd", "TERRAIN", "MADDECOR_WASTE.PCK")
OUT = os.path.join(ROOT, "art", "tickets", "t247")
FRAMES = [62, 63, 64, 65]
BASE = 62
DILATE = 3
FAMILY = {"MADDECOR_WASTE": 62, "CATACDECOR_CONC": 35, "METRO1": 117, "URBITS_INDUSLUM": 18}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(OUT, exist_ok=True)
    classic = xs.read_pck(PCK)
    cl = [classic[f] for f in FRAMES]
    hd = [Image.open(os.path.join(HD, "%d.png" % f)).convert("RGBA") for f in FRAMES]
    w, h = hd[0].size
    k = w // 32
    # огонь: точки классики, где кадры расходятся
    fire = Image.new("L", (32, 40), 0)
    for y in range(40):
        for x in range(32):
            if len({c[y][x] for c in cl}) > 1:
                fire.putpixel((x, y), 255)
    fire = fire.resize((w, h), Image.NEAREST)
    if DILATE:
        fire = fire.filter(ImageFilter.MaxFilter(DILATE * 2 + 1))
    print("огонь: %d из %d точек HD" % (fire.histogram()[255], w * h))
    base = hd[FRAMES.index(BASE)]
    outs = []
    for f, im in zip(FRAMES, hd):
        out = Image.composite(im, base, fire)
        p = os.path.join(OUT, "%d.png" % f)
        out.save(p)
        outs.append(p)
    # лист: было (4 кадра) / стало (4 кадра), вчетверо крупнее
    s = 3
    sheet = Image.new("RGB", (w * s * 4, h * s * 2 + 40), (40, 40, 40))
    d = ImageDraw.Draw(sheet)
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 16)
    for i, f in enumerate(FRAMES):
        for row, im in enumerate((hd[i], Image.open(outs[i]))):
            bg = Image.new("RGBA", im.size, (90, 90, 90, 255))
            bg.alpha_composite(im)
            sheet.paste(bg.convert("RGB").resize((w * s, h * s), Image.NEAREST), (i * w * s, 20 + row * h * s))
        d.text((i * w * s + 4, 4), "кадр %d" % f, fill=(255, 230, 160), font=font)
    d.text((4, 20 + h * s * 2 + 4), "верх - пак сейчас, низ - барабан кадра 62, огонь свой", fill=(255, 230, 160), font=font)
    sheet.save(os.path.join(OUT, "sheet.png"))
    print("лист:", os.path.join(OUT, "sheet.png"), "k =", k)
    if not a.install:
        return 0
    if not a.yes:
        raise SystemExit("сухой прогон; --yes - записать в мод")
    import build_hd_pack as bp
    man = bp.load()
    rels = []
    for set_name, first in FAMILY.items():
        for i, f in enumerate(FRAMES):
            rel = "TERRAIN/%s.PCK/%d.png" % (set_name, first + i)
            bp.stage(man, rel, outs[i], generator="t247_barrel_splice", generator_version="t247_barrel_splice.py 22.10 dilate %d" % DILATE,
                     source_path="user/mods/hd/hd/TERRAIN/MADDECOR_WASTE.PCK/%d.png" % f, approved=True,
                     approval="Vitali 22.10: 247 бочка - склейка на все 16 кадров семьи",
                     derived_from="TERRAIN/MADDECOR_WASTE.PCK/%d.png" % f)
            rels.append(rel)
    bp.save(man, why="t247: бочка - барабан один, меняется огонь (%d кадров семьи)" % len(rels))
    print("game:", bp.install(man, "game", only=rels))
    print("repo:", bp.install(man, "repo", only=rels))
    for r in rels:
        for root in bp.TARGETS.values():
            with open(os.path.join(root, r), "rb") as fh:
                if hashlib.sha256(fh.read()).hexdigest() != man["files"][r]["sha256"]:
                    raise SystemExit("РАСХОДИТСЯ %s %s" % (root, r))
    print("сверено: %d файлов в обеих копиях" % len(rels))
    return 0


if __name__ == "__main__":
    sys.exit(main())
