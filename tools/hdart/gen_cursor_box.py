#!/usr/bin/env python3
"""
gen_cursor_box.py - рамка курсора боя (CURSOR.PCK, кадры 0-5) по координатам.

Кадры 0/1 (задняя половина рамки, красная и жёлтая) и 3/4 (передняя) рисуются
на ярусе курсора, кадры 2 и 5 - те же рамки пунктиром на каждом ярусе ниже.
Модель нарисовала их порознь, и линии нижних ярусов легли на 2-3 пикселя мимо
красных (белая бахрома у северного угла пола). Здесь все шесть кадров строятся
из ОДНИХ отрезков, снятых с классических кадров, поэтому совпадают по построению:

  - отрезок задаётся в пикселях классики 32x40 (центр пикселя = .5), толщина 1;
  - покрытие считается аналитически с запасом (SS отсчётов на пиксель базы) и
    усредняется при уменьшении: прямая гладкая, угол острый (грабли R-042);
  - цвет каждой точки - цвет ближайшего пикселя классического кадра, так что
    перелив рампы (красная 32-45, жёлтая 144-156) сохраняется;
  - пунктир 2 и 5 - круглые точки ровно в пикселях классики.

    py -3 tools/hdart/gen_cursor_box.py --out user/mods/hd/hd/CURSOR.PCK --sheet art/_review/cursor_box.png
"""
import argparse
import os
import shutil
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xcom_sprites as xs  # noqa: E402

UFO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "bin", "UFO")
SS = 4          # отсчётов на пиксель HD

# отрезки (x0, y0, x1, y1) в пикселях классики, общие для всех ярусов
TOP_L = (3.0, 8.5, 15.0, 2.5)
TOP_R = (29.0, 8.5, 17.0, 2.5)
FLOOR_BACK_L = (3.0, 33.5, 15.0, 27.5)
FLOOR_BACK_R = (29.0, 33.5, 17.0, 27.5)
# передние рёбра выходят из ТЕХ ЖЕ углов ромба, что и задние: в классике угловой пиксель
# принадлежит кадру 0, поэтому кадр 3 начинается на 2 пикселя внутрь - по нему снимать нельзя,
# иначе в сборе 0+3 углы не замыкаются
FRONT_TOP_L = (3.0, 8.5, 15.0, 14.5)
FRONT_TOP_R = (29.0, 8.5, 17.0, 14.5)
FRONT_BOT_L = (3.0, 33.5, 15.0, 39.5)
FRONT_BOT_R = (29.0, 33.5, 17.0, 39.5)
BAR_L = ("rect", 2.0, 8.5, 3.0, 33.5)
BAR_R = ("rect", 29.0, 8.5, 30.0, 33.5)
STEM_BACK = ("rect", 15.0, 2.5, 17.0, 27.5)
STEM_FRONT = ("rect", 15.0, 14.5, 17.0, 39.5)

SHAPES = {
    0: [TOP_L, TOP_R, STEM_BACK, BAR_L, BAR_R, FLOOR_BACK_L, FLOOR_BACK_R],
    3: [FRONT_TOP_L, FRONT_TOP_R, STEM_FRONT, FRONT_BOT_L, FRONT_BOT_R],
}
SHAPES[1] = SHAPES[0]
SHAPES[4] = SHAPES[3]
# пунктир: сплошными остаются только линии пола, как в классике
SOLID_DOTTED = {2: [FLOOR_BACK_L, FLOOR_BACK_R], 5: [FRONT_BOT_L, FRONT_BOT_R]}


def seg_cover(px, py, seg, half):
    """1, где точка (px, py) ближе half к отрезку или внутри прямоугольника."""
    if seg[0] == "rect":
        _, x0, y0, x1, y1 = seg
        return (px >= x0) & (px < x1) & (py >= y0 - 0.5) & (py < y1 + 0.5)
    x0, y0, x1, y1 = seg
    dx, dy = x1 - x0, y1 - y0
    L2 = dx * dx + dy * dy
    t = np.clip(((px - x0) * dx + (py - y0) * dy) / L2, 0.0, 1.0)
    cx, cy = x0 + t * dx, y0 + t * dy
    # толщина меряется по вертикали: у изолинии 2:1 классика кладёт по строке на шаг
    return (np.abs(py - cy) <= half) & (np.abs(px - cx) <= 1.0)


def render(frame_idx, classic, pal, k):
    h, w = 40 * k * SS, 32 * k * SS
    ys, xs_ = np.mgrid[0:h, 0:w].astype(np.float32)
    px = (xs_ + 0.5) / (k * SS)
    py = (ys + 0.5) / (k * SS)
    cover = np.zeros((h, w), bool)
    if frame_idx in SHAPES:
        for seg in SHAPES[frame_idx]:
            cover |= seg_cover(px, py, seg, 0.5)
    else:
        for seg in SOLID_DOTTED[frame_idx]:
            cover |= seg_cover(px, py, seg, 0.5)
        # точки пунктира: круг радиусом 0.55 в каждом пикселе классики, кроме сплошных линий
        solid = np.zeros((40, 32), bool)
        for y in range(40):
            for x in range(32):
                if classic[y, x] and seg_cover(np.float32(x + 0.5), np.float32(y + 0.5), SOLID_DOTTED[frame_idx][0], 0.5) | \
                        seg_cover(np.float32(x + 0.5), np.float32(y + 0.5), SOLID_DOTTED[frame_idx][1], 0.5):
                    solid[y, x] = True
        for y, x in zip(*np.nonzero(classic)):
            if solid[y, x]:
                continue
            cover |= (px - (x + 0.5)) ** 2 + (py - (y + 0.5)) ** 2 <= 0.55 ** 2
    alpha = cover.reshape(40 * k, SS, 32 * k, SS).mean(axis=(1, 3))
    # цвет: ближайший непрозрачный пиксель классики
    opaque = np.argwhere(classic != 0)
    gy, gx = np.mgrid[0:40 * k, 0:32 * k]
    cy = (gy + 0.5) / k
    cx = (gx + 0.5) / k
    d = (cy[..., None] - (opaque[:, 0] + 0.5)) ** 2 + (cx[..., None] - (opaque[:, 1] + 0.5)) ** 2
    near = opaque[np.argmin(d, axis=-1)]
    idx = classic[near[..., 0], near[..., 1]]
    rgb = pal[idx][..., :3].astype(np.float32)
    out = np.zeros((40 * k, 32 * k, 4), np.uint8)
    out[..., :3] = rgb.astype(np.uint8)
    out[..., 3] = np.clip(alpha * 255 + 0.5, 0, 255).astype(np.uint8)
    out[out[..., 3] == 0, :3] = 0
    return out


def main():
    ap = argparse.ArgumentParser(description="рамка курсора по координатам")
    ap.add_argument("--out", required=True, help="папка CURSOR.PCK мода hd")
    ap.add_argument("--scale", type=int, default=4)
    ap.add_argument("--sheet", default="", help="лист: классика x4 | новое | наложение ярусов")
    ap.add_argument("--backup", default="art/_backup/CURSOR.PCK_before_box", help="куда убрать прежние 0-5")
    args = ap.parse_args()
    k = args.scale
    pal = np.array(xs.load_palette(os.path.join(UFO, "GEODATA", "PALETTES.DAT")), np.uint8)
    frames = xs.read_pck(os.path.join(UFO, "UFOGRAPH", "CURSOR.PCK"))
    os.makedirs(args.out, exist_ok=True)
    made = {}
    for i in range(6):
        classic = np.array(frames[i])
        made[i] = render(i, classic, pal, k)
        dst = os.path.join(args.out, "%d.png" % i)
        if os.path.exists(dst) and args.backup:
            os.makedirs(args.backup, exist_ok=True)
            keep = os.path.join(args.backup, "%d.png" % i)
            if not os.path.exists(keep):
                shutil.copy2(dst, keep)
        Image.fromarray(made[i], "RGBA").save(dst)
        print("кадр %d -> %s" % (i, dst))
    if args.sheet:
        # наложение: курсор на ярусе 1, под ним ярус 0 (сдвиг 24 пикселя классики вниз), тёмный пол
        W, H = 32 * k, 40 * k + 24 * k
        sheet = Image.new("RGBA", (W * 4 + 24, H + 8), (24, 24, 28, 255))
        for n, (back, front) in enumerate([(0, 3), (1, 4)]):
            canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            canvas.alpha_composite(Image.fromarray(made[2], "RGBA"), (0, 24 * k))
            canvas.alpha_composite(Image.fromarray(made[back], "RGBA"), (0, 0))
            canvas.alpha_composite(Image.fromarray(made[5], "RGBA"), (0, 24 * k))
            canvas.alpha_composite(Image.fromarray(made[front], "RGBA"), (0, 0))
            sheet.alpha_composite(canvas, (4 + n * (W + 4), 4))
        for n, i in enumerate((2, 5)):
            sheet.alpha_composite(Image.fromarray(made[i], "RGBA"), (4 + (2 + n) * (W + 4), 4))
        os.makedirs(os.path.dirname(os.path.abspath(args.sheet)), exist_ok=True)
        sheet.save(args.sheet)
        print("лист:", args.sheet)
    return 0


if __name__ == "__main__":
    sys.exit(main())
