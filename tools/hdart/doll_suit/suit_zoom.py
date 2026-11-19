"""Крупно край: имя, вариант, x0 y0 x1 y1 в k=4, выход. На тёмном фоне, x2."""
import os
import sys
from PIL import Image
D = r"E:\tmp\doll_ingame\suit"
n, v = sys.argv[1], sys.argv[2]
box = tuple(int(a) for a in sys.argv[3:7])
im = Image.open(os.path.join(D, "hd_v%s" % v, n.lower() + ".png")).convert("RGBA")
bg = Image.new("RGBA", im.size, (24, 26, 32, 255))
bg.alpha_composite(im)
c = bg.crop(box)
c.resize((c.width * 2, c.height * 2), Image.NEAREST).convert("RGB").save(sys.argv[7], quality=92)
