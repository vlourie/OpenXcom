"""Слои k=4 на тёмном фоне в рамке: аргументы - рамка (dem/dog), выход, затем группы слоёв через запятую (слои одной куклы),
каждая группа - отдельная плитка. Первая плитка - классика первой группы (по имени слоя из файла)."""
import os
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"E:\OpenXCom\tools\hdart")
import numpy as np
from PIL import Image
import doll_b2_render as db

CROPS = {"dem": (36, 10, 120, 176), "dog": (44, 50, 108, 150)}
BG = (14, 14, 18, 255)
crop = CROPS[sys.argv[1]] if sys.argv[1] in CROPS else tuple(int(v) for v in sys.argv[1].split(":"))
box = tuple(v * 4 for v in crop)
F, PAL = db.sprite_files(), db.game_palette()
tiles = []
first = sys.argv[3].split(",")
cl = Image.new("RGBA", (db.W, db.H), BG)
for p in first:
    n = os.path.splitext(os.path.basename(p))[0].upper()
    if n in F:
        cl.alpha_composite(Image.fromarray(db.to_rgba(db.load_indices(F[n]), PAL).astype(np.uint8), "RGBA"))
tiles.append(cl.crop(crop).resize((box[2] - box[0], box[3] - box[1]), Image.NEAREST))
for g in sys.argv[3:]:
    c = Image.new("RGBA", (db.W * 4, db.H * 4), BG)
    for p in g.split(","):
        c.alpha_composite(Image.open(p).convert("RGBA"))
    tiles.append(c.crop(box))
w, h = tiles[0].size
s = Image.new("RGB", (len(tiles) * (w + 6) - 6, h), (40, 40, 46))
for i, t in enumerate(tiles):
    s.paste(t.convert("RGB"), (i * (w + 6), 0))
s.save(sys.argv[2], quality=92)
print(sys.argv[2], s.size)
