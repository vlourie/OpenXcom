"""Слой поворота постройки живой базы (тикет XP-000236, 22.10): поворачивается только деталь (тарелка
локатора), а не круг картинки с полом и мачтой (R-459). Из одобренной картинки painted/<T>@512.png:
  <T>.spin.png  - деталь одна, по маске (эллипс детали по цвету: без пола и мачты), остальное прозрачно;
  <T>.under.png - картинка без детали: место закрашено cv2.inpaint по соседям.
Оба в размере пака (<T>.png, 128 на клетку); base_scene_pack.py кладёт их рядом с кадром как <N>.under.png и
<N>.spin.png (HdBase::layer), строка spin/swing сцены крутит деталь вокруг своей точки (крепление к мачте).
Одобренная <T>.png не меняется: её же показывает педия.
    py -3.13 tools/hdart/base_spin_layer.py [--sheet PATH]"""
import argparse
import os
import sys

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
ART = os.path.join(ROOT, "art", "base_living", "pilot", "painted")
# деталь: эллипс в пикселях @512 (центр, полуоси, наклон в градусах), граница со стороны мачты (x не меньше),
# где её крепление - ось поворота (base_scene_pack.py SPIN берёт её отсюда) и порог насыщенности пола
PIECES = {
    "STR_SMALL_RADAR_SYSTEM": dict(center=(303, 202), axes=(30, 36), tilt=-12, min_x=279, pivot=(280, 204), sat=0.30),
}


def layers(t, p):
    big = np.asarray(Image.open(os.path.join(ART, t + "@512.png")).convert("RGBA"))
    small = Image.open(os.path.join(ART, t + ".png")).convert("RGBA")
    H, W = big.shape[:2]
    ell = np.zeros((H, W), np.uint8)
    cv2.ellipse(ell, p["center"], p["axes"], p["tilt"], 0, 360, 255, -1)
    ell[:, :p["min_x"]] = 0
    hsv = cv2.cvtColor(np.ascontiguousarray(big[..., :3]), cv2.COLOR_RGB2HSV).astype(np.float32)
    grey = hsv[..., 1] / 255.0 < p["sat"]
    m = (ell > 0) & grey
    # одно целое: самый большой кусок, дырки (тени в чаше) закрыты
    n, lab, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8))
    if n > 1:
        m = lab == 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8)) > 0
    m &= ell > 0
    hole = cv2.dilate(m.astype(np.uint8), np.ones((5, 5), np.uint8))
    # закрашивать полом: белое и серое рядом с дыркой (мачта, основание) в источник не берётся
    near = cv2.dilate(hole, np.ones((25, 25), np.uint8)) > 0
    src = (hole > 0) | (near & grey)
    under = cv2.inpaint(np.ascontiguousarray(big[..., :3]), src.astype(np.uint8), 9, cv2.INPAINT_TELEA)
    under = np.where((hole > 0)[..., None], under, big[..., :3])
    a = cv2.GaussianBlur(m.astype(np.float32), (0, 0), 0.8)
    piece = np.dstack([big[..., :3], np.round(a * big[..., 3]).astype(np.uint8)])
    under = np.dstack([under, big[..., 3]])
    size = small.size

    def down(x):
        # уменьшение с домноженной альфой, чтобы край детали не тянул цвет пола
        f = x.astype(np.float32)
        al = f[..., 3:4] / 255.0
        pm = np.dstack([f[..., :3] * al, f[..., 3]])
        r = cv2.resize(pm, size, interpolation=cv2.INTER_AREA)
        out = r.copy()
        out[..., :3] = np.where(r[..., 3:4] > 0, r[..., :3] / np.maximum(r[..., 3:4] / 255.0, 1e-6), 0)
        return Image.fromarray(np.clip(np.round(out), 0, 255).astype(np.uint8), "RGBA")

    pc, un = down(piece), down(under)
    # вне детали подложка - побайтно одобренная картинка (inpaint трогает только дырку)
    sm = np.asarray(small).copy()
    hole_s = cv2.resize(hole.astype(np.float32), size, interpolation=cv2.INTER_AREA) > 0
    u = np.asarray(un)
    sm[hole_s] = u[hole_s]
    un = Image.fromarray(sm, "RGBA")
    k = size[0] / W
    ys, xs = np.nonzero(m)
    reach = np.sqrt(((xs - p["pivot"][0]) ** 2 + (ys - p["pivot"][1]) ** 2).max()) * k
    return pc, un, (p["pivot"][0] * k, p["pivot"][1] * k), reach


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sheet", default="", help="лист: картинка | подложка | деталь")
    ns = ap.parse_args()
    for t, p in PIECES.items():
        pc, un, pivot, reach = layers(t, p)
        pc.save(os.path.join(ART, t + ".spin.png"), optimize=True)
        un.save(os.path.join(ART, t + ".under.png"), optimize=True)
        print("%s: ось %.1f %.1f, деталь до %.1f px от оси (пак)" % (t, pivot[0], pivot[1], reach))
        if ns.sheet:
            orig = Image.open(os.path.join(ART, t + ".png")).convert("RGBA")
            sheet = Image.new("RGB", (3 * orig.width * 4 + 8, orig.height * 4), (20, 20, 20))
            for i, im in enumerate((orig, un, pc)):
                bg = Image.new("RGBA", orig.size, (60, 60, 60, 255))
                bg.alpha_composite(im)
                sheet.paste(bg.convert("RGB").resize((orig.width * 4, orig.height * 4), Image.NEAREST), (i * (orig.width * 4 + 4), 0))
            sheet.save(ns.sheet)
    return 0


if __name__ == "__main__":
    sys.exit(main())
