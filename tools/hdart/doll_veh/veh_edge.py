"""Края: классика x4 | HD k=4 на тёмном фоне, кусок по контуру x2. Аргументы: имя, вариант (1|2), бокс x0,y0,x1,y1 в k=1, выход."""
import os
import sys
from PIL import Image
D = r"E:\tmp\doll_ingame\veh"
n, v = sys.argv[1], sys.argv[2]
b = [int(x) for x in sys.argv[3].split(",")]
b4 = tuple(x * 4 for x in b)
cl = Image.open(os.path.join(D, "classic_%s.png" % n)).convert("RGBA").resize((1280, 800), Image.NEAREST)
hd = Image.open(os.path.join(D, "hd_v%s" % v, n.lower() + ".png")).convert("RGBA")
tiles = []
for im in (cl, hd):
    bg = Image.new("RGBA", im.size, (24, 26, 32, 255))
    bg.alpha_composite(im)
    t = bg.crop(b4)
    tiles.append(t.resize((t.width * 2, t.height * 2), Image.NEAREST).convert("RGB"))
out = Image.new("RGB", (tiles[0].width * 2, tiles[0].height))
out.paste(tiles[0], (0, 0))
out.paste(tiles[1], (tiles[0].width, 0))
out.save(sys.argv[4], quality=90)
print(sys.argv[4], out.size)
