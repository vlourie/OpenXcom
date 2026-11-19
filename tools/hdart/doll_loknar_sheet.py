"""Лист показа LOKNAR: по паре на внешность - лицо классики и новое крупно, окно планки 26x23 в размере игры k=4.
Читает heads/layers, мод не трогает. Выход art/doll/pipe_pilot/loknar/faces.png.

  E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe E:/OpenXCom/tools/hdart/doll_loknar_sheet.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from PIL import Image, ImageDraw, ImageFont
import doll_b2_render as db

K = 4
OUT = os.path.join(db.ROOT, "art", "doll", "pipe_pilot", "loknar")
LOOKS = ["F%d" % i for i in range(8)] + ["M%d" % i for i in range(8)]
CLOSE = (58, 44, 100, 90)
PLANK = (66, 53, 92, 76)                            # avatarOffset 66, 53 у STR_SOLDIER_LOKNAR, окно 26x23
BG = (40, 42, 50, 255)
PER = 4
Z = 2


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 20)
    files, pal = db.sprite_files(), db.game_palette()
    cw, ch = (CLOSE[2] - CLOSE[0]) * K * Z // 2, (CLOSE[3] - CLOSE[1]) * K * Z // 2
    pw, ph = (PLANK[2] - PLANK[0]) * K, (PLANK[3] - PLANK[1]) * K
    tw, th = 2 * cw + pw + 12, ch + 28
    rows = (len(LOOKS) + PER - 1) // PER
    sheet = Image.new("RGB", (PER * tw, rows * th), (15, 15, 18))
    d = ImageDraw.Draw(sheet)
    for i, n in enumerate(LOOKS):
        x, y = (i % PER) * tw, (i // PER) * th
        cl = Image.new("RGBA", (db.W, db.H), BG)
        cl.alpha_composite(Image.fromarray(db.to_rgba(db.load_indices(files["LOKNAR__2__%s_NUDE" % n]), pal), "RGBA"))
        cl = cl.resize((db.W * K, db.H * K), Image.NEAREST)
        new = Image.new("RGBA", (db.W * K, db.H * K), BG)
        new.alpha_composite(Image.open(os.path.join(OUT, "heads", "layers", "loknar__2__%s_nude.png" % n.lower())).convert("RGBA"))
        box = tuple(v * K for v in CLOSE)
        pl = tuple(v * K for v in PLANK)
        sheet.paste(cl.crop(box).resize((cw, ch), Image.NEAREST).convert("RGB"), (x, y + 28))
        sheet.paste(new.crop(box).resize((cw, ch), Image.LANCZOS).convert("RGB"), (x + cw, y + 28))
        sheet.paste(new.crop(pl).convert("RGB"), (x + 2 * cw + 4, y + 28))
        sheet.paste(cl.crop(pl).convert("RGB"), (x + 2 * cw + 4, y + 28 + ph + 8))
        d.text((x + 4, y + 4), "%s: классика | новое | планка новое и классика" % n, fill=(255, 230, 0), font=font)
    fn = os.path.join(OUT, "faces.png")
    sheet.save(fn)
    print(fn, sheet.size)


if __name__ == "__main__":
    main()
