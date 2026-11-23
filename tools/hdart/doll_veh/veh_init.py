"""Техника (09.11): входы FLUX.3 Klein - классика в рамке (контур + 4 точки поля, стороны чётные), xBRZ x4 и LANCZOS
до x8 на подложке куклы. init_<имя>.png, classic8_<имя>.png (крупно без сглаживания), crops.json - рамки."""
import json
import os
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"E:\OpenXCom\tools\hdart")
import numpy as np
from PIL import Image
import doll_photo_pilot as dp
import wall_section as ws
from veh_classic import PICS, OUT

Z = 8
crops = {}
for name in PICS:
    part = Image.open(os.path.join(OUT, "classic_%s.png" % name)).convert("RGBA")
    a = np.asarray(part)[..., 3]
    ys, xs = np.nonzero(a)
    x0, y0, x1, y1 = max(0, xs.min() - 4), max(0, ys.min() - 4), min(320, xs.max() + 5), min(200, ys.max() + 5)
    if (x1 - x0) % 2:
        x1 += 1
    if (y1 - y0) % 2:
        y1 += 1
    crops[name] = (int(x0), int(y0), int(x1), int(y1))
    p = part.crop(crops[name])
    up = ws.xbrz(p, 4).resize((p.width * Z, p.height * Z), Image.LANCZOS)
    bg = Image.new("RGBA", up.size, dp.PANEL + (255,))
    bg.alpha_composite(up)
    bg.convert("RGB").save(os.path.join(OUT, "init_%s.png" % name))
    cl = Image.new("RGBA", p.size, dp.PANEL + (255,))
    cl.alpha_composite(p)
    cl.resize(up.size, Image.NEAREST).convert("RGB").save(os.path.join(OUT, "classic8_%s.png" % name))
    print(name, crops[name], up.size)
json.dump(crops, open(os.path.join(OUT, "crops.json"), "w", encoding="utf-8"), indent=1)
