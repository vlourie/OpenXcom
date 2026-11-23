"""Крупно кусок слоя k=4 с сеткой в координатах 320x200 (линия на каждую точку базы, подпись каждые 5).
Аргументы: слой, x0,y0,x1,y1 (база), выход, [увеличение к k4, по умолчанию 3]."""
import sys
from PIL import Image, ImageDraw, ImageFont
p, box, out = sys.argv[1], [int(v) for v in sys.argv[2].split(",")], sys.argv[3]
z = int(sys.argv[4]) if len(sys.argv) > 4 else 3
im = Image.open(p).convert("RGBA")
bg = Image.new("RGBA", im.size, (14, 14, 18, 255))
bg.alpha_composite(im)
c = bg.crop(tuple(v * 4 for v in box)).resize(((box[2] - box[0]) * 4 * z, (box[3] - box[1]) * 4 * z), Image.LANCZOS).convert("RGB")
d = ImageDraw.Draw(c)
f = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 14)
s = 4 * z
for x in range(box[0], box[2] + 1):
    X = (x - box[0]) * s
    d.line((X, 0, X, c.height), fill=(0, 255, 255) if x % 5 == 0 else (60, 90, 90), width=1)
    if x % 5 == 0:
        d.text((X + 2, 2), str(x), fill=(255, 255, 0), font=f)
for y in range(box[1], box[3] + 1):
    Y = (y - box[1]) * s
    d.line((0, Y, c.width, Y), fill=(0, 255, 255) if y % 5 == 0 else (60, 90, 90), width=1)
    if y % 5 == 0:
        d.text((2, Y + 2), str(y), fill=(255, 255, 0), font=f)
c.save(out, quality=92)
print(out, c.size)
