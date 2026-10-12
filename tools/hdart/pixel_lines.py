"""HD-кадр пола с рисунком из тонких линий (фаски, швы, канавки) - xBRZ по полю классики (R-298).

DREAD_BASE 61 (пол базы, 27 тысяч клеток): восьмиугольные плиты и плитки между ними, разделённые тёмными
канавками, со светлой фаской. Линии рисунка в классике толщиной в пиксель и идут только по горизонтали,
вертикали и изо-наклону 2:1. Прежний пак потерял рисунок и рисовал тёмное поле с шумом.

Почему не отрезками: проба 12.10 - цепочки пикселей классики, спрямлённые Дугласом-Пекером с доворотом к трём
направлениям, на стыках плит дали ложные ветви и галочки (тёмные косые штрихи там, где классика сводит три
канавки в точку). xBRZ x4 спрямляет лесенку 2:1 и держит прямые углы, а рисунок не выдумывает.

Что делается:
  1. Поле 5x5 копий классики (порядок рисования - по x + y), рисунок периодичен по сетке клеток.
  2. Кадр средней копии с полями PAD пикселей базы из поля - xBRZ x4, поля срезаются: соседние клетки
     увеличены по тем же соседям, стык совпадает сам.
  3. Альфа - точный ромб с перехлёстом (R-291).

    py -3.13 tools/hdart/pixel_lines.py --out art/ground/dread-v1/TERRAIN --frames DREAD_BASE:61
"""
import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import water_build as wb          # noqa: E402
import ground_seam as gs          # noqa: E402
import sprite_scale as ss         # noqa: E402

K = 4
OVERLAP = 0.04
N = 5                    # копий поля по каждой оси
PAD = 4                  # поле вокруг кадра для xBRZ, пикселей базы


def build_field(cl):
    f = np.zeros((16 * N + 48, 32 * N + 32), np.int32)
    cells = sorted(((x, y) for x in range(N) for y in range(N)), key=lambda t: (t[0] + t[1], t[0]))
    for x, y in cells:
        px, py = (x - y) * 16 + (N - 1) * 16, (x + y) * 8
        m = cl > 0
        f[py:py + 40, px:px + 32][m] = cl[m]
    c = N // 2
    return f, ((N - 1) * 16, (c + c) * 8)        # начало кадра средней копии


def render(cl, pal):
    fld, (ox, oy) = build_field(cl)
    sub = fld[oy - PAD:oy + 40 + PAD, ox - PAD:ox + 32 + PAD]
    if (sub[PAD:-PAD, PAD:-PAD][cl > 0] == 0).any():
        raise SystemExit("поле не закрывает кадр")
    rgba = np.concatenate([pal[sub], np.full(sub.shape + (1,), 255.0, np.float32)], -1)[None]
    up = ss.xbrz_scale(rgba, K)[0][..., :3]
    return up[PAD * K:-PAD * K, PAD * K:-PAD * K]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--frames", default="DREAD_BASE:61")
    a = ap.parse_args()
    pal = wb.palette().astype(np.float32)
    al = (gs.dmap() <= 1.0 + OVERLAP).astype(np.float32)
    for it in a.frames.split(","):
        s, f = it.split(":")
        cl = wb.read_set(s)[int(f)]
        rgb = render(cl, pal)
        gs.save_rgba(rgb, al, a.out, s, f)
        print("%s %s: средний цвет нового %s, классики %s" % (
            s, f, np.round(rgb[al > 0].mean(axis=0)).astype(int).tolist(),
            np.round(pal[cl[cl > 0]].mean(axis=0)).astype(int).tolist()))


if __name__ == "__main__":
    main()
