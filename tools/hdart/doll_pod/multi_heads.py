"""Лист голов набора крупно: окно отличий (windows.json box) классика x4 | HD, по 10 пар в строке. Аргументы: набор вариант выход."""
import json
import os
import re
import sys
from PIL import Image, ImageDraw, ImageFont
sys.stdout.reconfigure(encoding="utf-8")
D = os.environ.get("MULTI_OUT", r"E:\tmp\doll_ingame\multi_all")
s, v, out = sys.argv[1], sys.argv[2], sys.argv[3]
CROPS = json.load(open(os.path.join(D, "crops.json"), encoding="utf-8"))
WINS = json.load(open(os.path.join(D, "windows.json"), encoding="utf-8"))
FONT = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 12)
names = sorted((n for n in CROPS if re.match(r"^%s[MF]\d+\.SPK$" % s, n)), key=lambda n: (n[len(s)] != "F", int(n[len(s) + 1:-4])))
x0, y0, x1, y1 = WINS[s]["box"]
x0, y0, x1, y1 = max(0, x0 - 2), max(0, y0 - 2), min(320, x1 + 2), min(200, y1 + 2)
w, h = (x1 - x0) * 4, (y1 - y0) * 4
per = 10
rows = (len(names) + per - 1) // per
o = Image.new("RGB", (per * (2 * w + 8), rows * (h + 16)), (14, 15, 19))
dr = ImageDraw.Draw(o)
for i, n in enumerate(names):
    cx, cy = (i % per) * (2 * w + 8), (i // per) * (h + 16)
    for j, p in enumerate((os.path.join(D, "classic_%s.png" % n), os.path.join(D, "hd_" + v, n.lower() + ".png"))):
        if not os.path.exists(p):
            continue
        im = Image.open(p).convert("RGBA")
        k = im.width // 320
        im = im.crop((x0 * k, y0 * k, x1 * k, y1 * k)).resize((w, h), Image.NEAREST if k == 1 else Image.LANCZOS)
        bg = Image.new("RGBA", (w, h), (24, 26, 32, 255))
        bg.alpha_composite(im)
        o.paste(bg.convert("RGB"), (cx + j * w, cy + 16))
    dr.text((cx + 2, cy), n[len(s):-4], fill=(255, 220, 90), font=FONT)
o.save(out, quality=88)
print(o.size)
