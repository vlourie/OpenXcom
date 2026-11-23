#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Партия оружия HD-BIGOBS на просмотр Vitali (03.10: «100 картинок оружия по нашей схеме»): путь пилота
item_photo.py как есть (эскиз struct_guide + оригинал -> Qwen-Image-2.1 по замку, контракт v4: вырезка без
подгонки, альфа из силуэта оригинала, REWORK по размеру и месту модели), а вместо мастеров M-xx - свой список.

Список и кадры готовит отбор (art/items/weapons100-v1/list.tsv, cards/): кадр BIGOBS индексами и палитрой
выгрузки движка (census/items/export/exp_piratez), два кадра, которых в выгрузке нет, - из файла мода.
Описания для модели - what.tsv той же папки (по названию и по кадру, без фото-эталона).
Выход за клетки: у оригинала, который выходит за свои клетки, - правило inherit_overflow, как решено Vitali
для мастеров пилота (HD не дальше контура оригинала x4). Для партии на просмотр это допущение, а не решение:
в моде такой кадр без его слова не появится.

Модель - только через очередь и под render_chunks.py:
    py -3.13 tools/gpuq.py add --name weapons100_v1 --prio 1 --cwd E:/OpenXCom -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/render_chunks.py \
        --out art/items/weapons100-v1 --max-renders 4 -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/weapons_batch.py
Без модели: --dry-run, --recut (как у item_photo.py). Прочие ключи уходят в item_photo.main.
"""
import csv
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                      # noqa: E402

import asset_rev as ar                  # noqa: E402
import item_asset_check as iac          # noqa: E402
import item_photo as ip                 # noqa: E402

ENC = "utf-8-sig"
BATCH = "art/items/weapons100-v1"


def rows(path):
    with open(path, encoding=ENC, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


# --style drawn (Vitali 03.10: «в оружии не нужно описание - нужно просто улучшить качество»; «перерисовать,
# но не фотореалистично, а именно то, что на картинке, сохраняя размер и цвет»): описаний нет, предмет
# называется картинкой <image2>, промпт - перерисовка того же рисунка в высоком разрешении, не фото.
DRAWN_WHAT = "the item drawn in <image2>"
DRAWN_ITEM = ("<image1> is a clean shape sketch of {what}, shown on a flat preview panel of colour RGB({r}, {g}, {b}). "
              "The panel is background, not part of the object. "
              "Redraw <image2> as a clean high-resolution version of exactly the same picture: the same item, "
              "the same drawing and the same view, every part in the same place and of the same size, nothing "
              "added and nothing left out. Keep the colours of <image2> exactly: the same hue, brightness and "
              "saturation of every area, dark parts stay dark. Keep the full width and height and the outline "
              "of <image1>, not slimmer and not smaller. Detailed painted game item art with crisp clean edges "
              "and fine painted detail, no pixels. Output one isolated object on the same flat panel. No hands, "
              "no straps, no other objects, no shadow outside the object, no frame, no text, no letters, no logos.")
DRAWN_NEGATIVE = ("pixel art, pixelated, blocky, jagged stair-stepped edges, dithering, blurry, smudged, blob, "
                  "noise, low detail, photograph, photorealistic, realistic photo, 3d render, different colours, "
                  "faded, desaturated, washed out, thin slim object, smaller object, extra parts, missing parts, "
                  "ground, floor, panel frame, border, drop shadow, text, watermark")


def batch_what(folder, drawn=False):
    """[(мастер, тип, кадр, описание)] по list.tsv и what.tsv; описание обязательно у каждого (R-007).
    drawn: без описаний - предмет называется картинкой <image2>."""
    if drawn:
        return [(r["master"], r["type"], int(r["frame"]), DRAWN_WHAT) for r in rows(os.path.join(folder, "list.tsv"))]
    what = {r["master"]: r["what"].strip() for r in rows(os.path.join(folder, "what.tsv"))}
    out = []
    for r in rows(os.path.join(folder, "list.tsv")):
        if not what.get(r["master"]):
            raise SystemExit("%s %s: нет описания в what.tsv" % (r["master"], r["type"]))
        out.append((r["master"], r["type"], int(r["frame"]),
                    what[r["master"]] + "; exactly the outline and the full width and height of <image1>, not "
                    "slimmer, nothing that <image1> does not show"))
    return out


def gate(jobs):
    """{мастер: (статус, решение)}: оригинал в своих клетках - OK; выходит - inherit_overflow (см. шапку)."""
    out = {}
    for m, t, frame, _w in jobs:
        card = ip.json.load(open(os.path.join(ip.CARDS, t + ".json"), encoding=ENC))
        w, h = int(card["rules"]["invWidth"]["value"]), int(card["rules"]["invHeight"]["value"])
        full, _src = ip.load_frame(t, frame)
        a = np.asarray(full)[..., 3] > 0
        x0, y0, x1, y1 = iac.grid_rect(w, h)
        inside = np.zeros_like(a)
        inside[y0:y1, x0:x1] = True
        out[m] = ("OK", "") if not (a & ~inside).any() else ("BLOCKED_GEOMETRY", "inherit_overflow")
    return out


def main():
    folder = BATCH
    if "--out" in sys.argv:
        folder = sys.argv[sys.argv.index("--out") + 1]
    else:
        sys.argv += ["--out", folder]
    drawn = "--style" in sys.argv and sys.argv[sys.argv.index("--style") + 1] == "drawn"
    if "--style" in sys.argv:
        i = sys.argv.index("--style")
        del sys.argv[i:i + 2]
    os.chdir(ip.ROOT)
    ip.CARDS = os.path.join(folder, "cards")
    ip.WHAT = batch_what(folder, drawn)
    if drawn:
        ip.ITEM = DRAWN_ITEM
        import obj_photo                # item_photo.main берёт негатив из obj_photo.NEGATIVE
        obj_photo.NEGATIVE = DRAWN_NEGATIVE
        print("weapons_batch: стиль drawn - без описаний, перерисовка рисунка, не фото", flush=True)
    g = gate(ip.WHAT)
    ip.geometry_gate = lambda: g
    over = sum(1 for s, _d in g.values() if s != "OK")
    print("weapons_batch: %d предметов, выходят за клетки %d (inherit_overflow)" % (len(ip.WHAT), over), flush=True)
    h = hashlib.sha256()
    for p in ((os.path.join(folder, "list.tsv"), os.path.abspath(__file__)) if drawn else
              (os.path.join(folder, "what.tsv"), os.path.join(folder, "list.tsv"), os.path.abspath(__file__))):
        with open(p, "rb") as f:
            h.update(f.read())
    base_rev = ip.generator_rev
    ip.generator_rev = lambda lock, engine="qwen21": ar.h12({"item_photo": base_rev(lock, engine),
                                                             "batch": h.hexdigest()})
    ip.main()


if __name__ == "__main__":
    main()
