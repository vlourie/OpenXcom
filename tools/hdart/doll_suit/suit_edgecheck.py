"""Проверка края: имена=сид через пробел -> ../edge.jpg, каждая картинка целиком k=4 на тёмном фоне по рамке crops, рядом."""
import json
import os
import sys
from PIL import Image
D = r"E:\tmp\doll_ingame\suit"
C = json.load(open(os.path.join(D, "crops.json"), encoding="utf-8"))
tiles = []
for a in sys.argv[1:]:
    n, s = a.rsplit("=", 1)
    im = Image.open(os.path.join(D, "hd_v%s" % s, n.lower() + ".png")).convert("RGBA")
    bg = Image.new("RGBA", im.size, (24, 26, 32, 255))
    bg.alpha_composite(im)
    t = bg.crop(tuple(v * 4 for v in C[n])).convert("RGB")
    k = 700 / t.height
    tiles.append(t.resize((int(t.width * k), 700), Image.LANCZOS))
out = Image.new("RGB", (sum(t.width for t in tiles) + 6 * len(tiles), 700), (60, 60, 60))
x = 0
for t in tiles:
    out.paste(t, (x, 0))
    x += t.width + 6
out.save(os.path.join(D, "edge.jpg"), quality=88)
print(out.size)
