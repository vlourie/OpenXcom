"""Лист: классика x8 | сиды. Аргументы: имена через запятую (all), сиды, выход."""
import os
import sys
sys.stdout.reconfigure(encoding="utf-8")
from PIL import Image, ImageDraw
from suit_flux import WHAT, OUT
names = list(WHAT) if sys.argv[1] == "all" else sys.argv[1].split(",")
seeds = sys.argv[2].split(",")
H = 300
rows = []
for n in names:
    ims = [Image.open(os.path.join(OUT, "classic8_%s.png" % n)).convert("RGB")]
    for s in seeds:
        p = os.path.join(OUT, "images", "%s_%s.png" % (n, s))
        if os.path.exists(p):
            ims.append(Image.open(p).convert("RGB"))
    ims = [i.resize((int(i.width * H / i.height), H), Image.LANCZOS) for i in ims]
    r = Image.new("RGB", (sum(i.width for i in ims), H))
    x = 0
    for i in ims:
        r.paste(i, (x, 0))
        x += i.width
    ImageDraw.Draw(r).text((4, 4), n, fill=(255, 220, 90))
    rows.append(r)
W = max(r.width for r in rows)
out = Image.new("RGB", (W, H * len(rows)))
for k, r in enumerate(rows):
    out.paste(r, (0, k * H))
out.save(sys.argv[3], quality=86)
print(sys.argv[3], out.size)
