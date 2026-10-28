# -*- coding: utf-8 -*-
r"""XP-000352: лист «оригинал / HD сейчас / кандидат» по шоссе ROADS_WASTE и серому полу. Только чтение: в мод
ничего не пишет, кандидаты кадров 0-8 строятся в памяти (t249_asphalt_edge.build, процедурно, без видеокарты).
    py -3.13 tools\hdart\t352_sheet.py"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import t249_asphalt_edge as t249      # noqa: E402
import t351_build as t351             # noqa: E402
import ticket_scene as ts             # noqa: E402

ROOT = HERE.parent.parent
OUT = ROOT / "art" / "_review" / "tickets_2026-10-28" / "t352_sheet.png"
SHOT = ROOT / "census" / "tickets" / "XP-000352" / "files" / "01_shot.png"
BG = (30, 30, 34)


def bright(im, k):
    a = np.asarray(im.convert("RGB")).astype(np.float32) * k
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def label_h(im, text, n=20):
    return ts.label(im.convert("RGB"), text, n)


def tile(sc, s, f, var=0, cand=None, z=2.0):
    """столбец: классика / HD сейчас / (кандидат), обрезан по габариту ромба."""
    hd = sc.hd(s, f, var)
    cl = sc.classic(s, f)
    ims = [("кл", cl), ("HD", hd)]
    if cand is not None:
        ims.append(("нов", cand))
    box = hd.getchannel("A").getbbox() or (0, 0, 128, 160)
    w, h = box[2] - box[0], box[3] - box[1]
    col = Image.new("RGB", (int(w * z), int((h + 4) * len(ims) * z)), BG)
    for j, (_n, im) in enumerate(ims):
        c = Image.new("RGBA", (128, 160), BG + (255,))
        c.alpha_composite(im.convert("RGBA").resize((128, 160), Image.NEAREST if j == 0 else Image.LANCZOS) if im.size != (128, 160) else im.convert("RGBA"))
        c = c.crop(box).resize((int(w * z), int(h * z)), Image.NEAREST if j == 0 else Image.LANCZOS)
        col.paste(c.convert("RGB"), (0, int(j * (h + 4) * z)))
    name = "%s:%d%s" % (s, f, (".v%d" % var) if var else "")
    return label_h(col, name, 16)


def hstack(ims, gap=8):
    W = sum(i.width for i in ims) + gap * (len(ims) + 1)
    H = max(i.height for i in ims) + gap * 2
    out = Image.new("RGB", (W, H), (12, 12, 14))
    x = gap
    for i in ims:
        out.paste(i, (x, gap))
        x += i.width + gap
    return out


def vstack(ims, gap=10):
    W = max(i.width for i in ims)
    H = sum(i.height for i in ims) + gap * (len(ims) + 1)
    out = Image.new("RGB", (W, H), (12, 12, 14))
    y = gap
    for i in ims:
        out.paste(i, (0, y))
        y += i.height + gap
    return out


def main():
    sc = ts.Scene()
    shot = Image.open(SHOT).convert("RGB")
    pal = t249.wb.palette()
    ref = t249.sand_ref_luma(pal)
    tex = (t249.extend(t249.load_hd(*t249.ASPH_SRC)), t249.extend(t249.load_hd(*t249.SAND_SRC)))
    cand = {f: t249.build(f, tex, ref) for f in range(0, 9)}

    # 1. скриншот игрока
    p1 = label_h(shot.crop((300, 100, 1100, 640)), "скрин: шоссе ROADS_WASTE 9, штрих 11, кромка 0-8, яма 14, трещины 18/19", 18)
    p2 = label_h(shot.crop((0, 560, 700, 1150)), "скрин: песок URBITS_WASTE:16 + плитки :17 (сиреневый - свет)", 18)
    row1 = hstack([p1, p2])

    # 2. вблизи скрина: где «слой на слое»
    z1 = shot.crop((560, 120, 1060, 420)).resize((900, 540), Image.LANCZOS)
    z2 = shot.crop((330, 300, 830, 600)).resize((900, 540), Image.LANCZOS)
    row2 = hstack([label_h(z1, "скрин x1.8: кромка 0-8 - глянцевый камень с рваным краем, не щебень классики", 18),
                   label_h(z2, "скрин x1.8: трещины 18/19 и яма 14 - тёмные ромбы с резкой кромкой поверх асфальта 9", 18)])

    # 3. кадры шоссе
    cols = [tile(sc, "ROADS_WASTE", 9, 0), tile(sc, "ROADS_WASTE", 9, 1), tile(sc, "ROADS_WASTE", 9, 2), tile(sc, "ROADS_WASTE", 9, 3),
            tile(sc, "ROADS_WASTE", 11, 0), tile(sc, "ROADS_WASTE", 14, 0), tile(sc, "ROADS_WASTE", 18, 0), tile(sc, "ROADS_WASTE", 19, 0),
            tile(sc, "URBITS_WASTE", 16, 0), tile(sc, "URBITS_WASTE", 17, 0)]
    row3 = hstack(cols)

    # 4. края 0-8
    cols = [tile(sc, "ROADS_WASTE", f, 0, cand[f], z=1.6) for f in range(9)]
    row4 = hstack(cols)

    # 5. сцена URBANWASTEROAD_NS08 (шоссе с краями)
    over = {(t249.SET, f): im for f, im in cand.items()}
    blk = "URBANWASTEROAD_NS08"
    ims = {}
    for tag, mode, ov in (("классика", "classic", None), ("HD сейчас", "hd", None), ("кандидат 0-8 (не одобрен)", "hd", over)):
        im, _ = sc.render("URBAN_WASTE", blk, mode, override=ov, k=3, maxz=0)
        ims[tag] = im.convert("RGB").crop((40, 380, 1010, 870))
    row5 = hstack([label_h(bright(im, 1.8 if "классика" not in tag else 1.8), "%s, %s, x1.8" % (tag, blk[-4:])) for tag, im in ims.items()])

    W = max(r.width for r in (row1, row2, row3, row4, row5))
    sheet = vstack([row1, row2, label_h(row3, "кадры шоссе: сверху классика, снизу HD сейчас (x2). ROADS_WASTE 9/v1-v3/11 - ground_seam 07.10 одобрен; 14 - tile_edge 08.10; 18/19 - sdxl_legacy без одобрения; URBITS 16 tile_edge, 17 - HD"),
                    label_h(row4, "края ROADS_WASTE 0-8: классика / HD сейчас (sdxl_legacy 21.09, не одобрен) / кандидат (маска классики, t249 23.10 для 1-8; 0 - слабый, нужна своя доработка)"), row5])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(OUT)
    print(OUT, sheet.size)


if __name__ == "__main__":
    main()
