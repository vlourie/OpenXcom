"""Крупно кусок сырой картинки: имя_сид, бокс x0,y0,x1,y1 (в кадре x8), выход; x2 без сглаживания."""
import os
import sys
from PIL import Image
D = r"E:\tmp\doll_ingame\veh\images"
b = tuple(int(v) for v in sys.argv[2].split(","))
im = Image.open(os.path.join(D, sys.argv[1] + ".png")).convert("RGB").crop(b)
im.resize((im.width * 2, im.height * 2), Image.NEAREST).save(sys.argv[3], quality=90)
print(sys.argv[3])
