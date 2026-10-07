"""Плоский предмет-пятно поверх пола (горелая яма, куча) с рваным краем: тон классики, фактура пака (08.10, без генерации).

Брак пака у горелых ям INDUSLUM 56-59 (предметы части 3 поверх асфальта и земли трущоб): пак залил ромб
целиком - чёткий ромб на поле, и ярче классики (оранжевый огонь по всему пятну против редких искр по тёмной
лиловой куче). У классики пятно кончается рваным краем внутри ромба, сквозь край виден пол клетки.
ground_seam --other здесь не годится: он заливает край полем своего набора, а предмет лежит на чужих полах.

Что делается:
  1. Цвет - ground_seam.detail_tone: крупный тон классики, мелкая фактура пака.
  2. Альфа - силуэт классики x4, размытый гауссом SIG базы, с периодическим шумом ground_seam.grain_noise
     (амплитуда RAGGED) и мягким порогом: край рваный, как у классики, но без лесенки базы.
Проверка - игровой кадр классика | пак установки | новое (R-249).

    py -3.13 tools/hdart/ragged_obj.py --set INDUSLUM --frames 56,57,58,59 --out <папка>/TERRAIN
"""
import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import ground_seam as gs          # noqa: E402
import water_build as wb          # noqa: E402

SIG = 0.8                         # размытие силуэта, пикс базы
RAGGED = 0.12                     # амплитуда шума края (доля размытой маски)
SOFT = 0.12                       # ширина мягкого порога


def build(s, f, pal):
    fr = wb.read_set(s)[f]
    p = gs.load_pack(s, f)
    c = gs.detail_tone(fr, p, pal)
    m = wb.blk(fr != 0).astype(np.float32)
    mb = wb.gauss(m, SIG * gs.K)
    nz = gs.grain_noise(sig=4.0, seed=23 + f)
    nz = nz / (nz.std() + 1e-6)
    al = np.clip((mb + RAGGED * nz - 0.5) / SOFT + 0.5, 0, 1)
    return c, al, fr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", required=True)
    ap.add_argument("--frames", required=True, help="кадры через запятую")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    pal = wb.palette()
    for f in (int(v) for v in a.frames.split(",")):
        c, al, fr = build(a.set, f, pal)
        m = al > 0.5
        print("%s %d: средний цвет классики %s, нового %s, непрозрачно x4 %d против классики x16 %d" % (
            a.set, f, pal[fr[fr > 0]].mean(0).round().astype(int).tolist(),
            c[m].mean(0).round().astype(int).tolist(), int(m.sum()), int((fr != 0).sum()) * 16))
        gs.save_rgba(c, al, a.out, a.set, "%d" % f)


if __name__ == "__main__":
    main()
