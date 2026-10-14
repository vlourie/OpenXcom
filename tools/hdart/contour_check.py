"""Потеря исходного контура HD-кадра пола (R-326): какие детали силуэта классики HD-кадр сделал прозрачным.

Мера не про площадь за ромбом. Эталон - силуэт своей классики, сглаженный xBRZ x4 (pixel_lines.own_render): так
его рисует сам рецепт, лесенка базы спрямлена, угол не считается потерей. Потерян пиксель базы, если по эталону
он непрозрачен (доля блока 4x4 от половины), а в HD-кадре его блок прозрачен больше чем наполовину. Узкая полоса
в один пиксель базы вдоль края крыши - 30-40 потерянных пикселей базы, её мера видит; сглаживание края - нет.

    py -3.13 tools/hdart/contour_check.py --src <папка TERRAIN> --frames URBAN:52,U_BITS_G:3
    py -3.13 tools/hdart/contour_check.py --queue installed     (все установленные группы очереди, копия игры)
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import water_build as wb          # noqa: E402
import pixel_lines as pl          # noqa: E402

GAME = ROOT / "Пиратки" / "Dioxine_XPiratez" / "user" / "mods" / "hd" / "hd" / "TERRAIN"
K = 4


def blocks(a):
    """среднее по блокам 4x4: x4 -> база"""
    h, w = a.shape
    return a.reshape(h // K, K, w // K, K).mean(axis=(1, 3))


def loss(cl, alpha, pal=None):
    """cl - индексы классики 40x32, alpha - альфа HD-кадра 160x128 (0..1). Возвращает потерянные пиксели базы
    (маска 40x32) и число строк и столбцов базы, где они есть."""
    if pal is None:
        pal = wb.palette().astype(np.float32)
    # только непрозрачное классики: одиночная дыра решётки (XB3BITZ3 23) у xBRZ своей копии наполовину закрыта,
    # но это дыра, а не деталь
    ref = (cl > 0) & (blocks((pl.own_render(cl, pal)[1] > 0.5).astype(np.float32)) >= 0.5)
    got = blocks((alpha > 0.5).astype(np.float32)) >= 0.5
    lost = ref & ~got
    return lost, int(lost.any(axis=1).sum()), int(lost.any(axis=0).sum())


def verdict(cl, alpha, pal=None):
    lost, rows, cols = loss(cl, alpha, pal)
    n = int(lost.sum())
    if not n:
        return "ok", "контур цел"
    ys, xs = np.nonzero(lost)
    return "lost", "потеряно %d пикс базы контура (строк %d, столбцов %d, рамка x %d-%d y %d-%d)" % (
        n, rows, cols, xs.min(), xs.max(), ys.min(), ys.max())


def read_alpha(path):
    return np.asarray(Image.open(path).convert("RGBA"))[..., 3] / 255.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(GAME), help="папка TERRAIN с <набор>.PCK/<кадр>.png")
    ap.add_argument("--frames", default="")
    ap.add_argument("--queue", default="", help="статус очереди: проверить все её группы (например installed)")
    a = ap.parse_args()
    pal = wb.palette().astype(np.float32)
    frames = [g for g in a.frames.split(",") if g]
    if a.queue:
        import floor_batch as fb
        frames += [r["группа"] for r in fb.load_queue().values() if r["статус"] == a.queue]
    sets = {}
    bad = 0
    for g in frames:
        s, f = g.split(":")
        p = Path(a.src) / (s + ".PCK") / (f + ".png")
        if not p.exists():
            print("%-24s нет файла" % g)
            continue
        if s not in sets:
            sets[s] = wb.read_set(s)
        v, why = verdict(sets[s][int(f)], read_alpha(p), pal)
        bad += v != "ok"
        if v != "ok" or not a.queue:
            print("%-24s %s  %s" % (g, v, why))
    print("проверено %d, с потерей контура %d" % (len(frames), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
