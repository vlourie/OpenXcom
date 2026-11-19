# -*- coding: utf-8 -*-
r"""Лица шести героинь (M1-M6, кастинг интро 18.10) для опор генерации фонов экранов.

Из портретов кастинга (F:\AIStudio\EscapeScene\output\M<N>_portrait.png, 1536x2048) вырезается только голова
и шея - тело кастинга в бельё в опору не идёт, одежду задаёт промпт. Итог - art/cast/M<N>_face.png
(квадрат 768) и лист проверки art/cast/faces_sheet.jpg. Кто есть кто - F:\AIStudio\EscapeScene\CHARACTERS_AND_SCENE.md.

    tools\hdart\.venv\Scripts\python.exe tools\hdart\cast_faces.py
"""
import os

from PIL import Image, ImageDraw

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = r"F:\AIStudio\EscapeScene\output"
OUT = os.path.join(ROOT, "art", "cast")
# голова и шея на портрете, (x0, y0, x1, y1) в пикселях 1536x2048: ниже ключиц не заходить
BOX = {
    1: (500, 20, 1090, 610),
    2: (580, 40, 1200, 660),
    3: (420, 30, 1120, 730),
    4: (580, 0, 990, 410),
    5: (220, 40, 1320, 1140),
    6: (580, 0, 940, 360),
}
# внешность словами (CHARACTERS_AND_SCENE.md) - тем же текстом её зовёт промпт фонов
LOOK = {
    1: "Sever, 21, tall, pale skin, straight silver-white chin-length bob with thick bangs, grey eyes, strong "
       "cheekbones and jaw",
    2: "Iskra, 20, warm fair skin, golden-blonde high ponytail, blue eyes, straight strong eyebrows, "
       "square-oval face",
    3: "Shpilka, 20, light olive skin, shoulder-length chestnut hair held by a plain metal bobby pin, brown eyes, "
       "oval face, slightly asymmetric nose",
    4: "Bazalt, 21, very tall and the strongest, deep dark-brown skin, long thick dreadlocks, dark-brown eyes, "
       "broad face and nose",
    5: "Rys, 19, warm freckled skin, short copper-red curls, green eyes, narrow angular face",
    6: "Tikhaya, 20, East Asian facial features, broad cheekbones, dark almond-shaped eyes, straight black hair "
       "in one practical braid",
}


def main():
    os.makedirs(OUT, exist_ok=True)
    tiles = []
    for m, box in BOX.items():
        im = Image.open(os.path.join(SRC, "M%d_portrait.png" % m)).convert("RGB").crop(box)
        im = im.resize((768, 768), Image.LANCZOS)
        im.save(os.path.join(OUT, "M%d_face.png" % m))
        t = im.resize((256, 256), Image.LANCZOS)
        ImageDraw.Draw(t).text((6, 6), "M%d" % m, fill=(255, 220, 0))
        tiles.append(t)
    board = Image.new("RGB", (256 * len(tiles), 256))
    for i, t in enumerate(tiles):
        board.paste(t, (i * 256, 0))
    board.save(os.path.join(OUT, "faces_sheet.jpg"), quality=88)
    print("%d лиц в %s" % (len(tiles), OUT))


if __name__ == "__main__":
    main()
