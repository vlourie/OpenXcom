"""Мерка швов массива кубов (20.10, R-403): стопка 2x2x2 из одного кадра, перепад яркости на стыках блоков к
перепаду внутри граней. Классика - в родном масштабе (при увеличении ближайшим соседом перепад есть на каждом её
пикселе), пак и новое - xk. Бесшовный куб ~1-2.5; шов виден от ~3.5. Кадры - все TERRAIN с данным силуэтом
(census/frames.tsv, по умолчанию полный куб 01a04fe05dc1).

    tools/hdart/.venv/Scripts/python.exe tools/hdart/cube_seam_scan.py <out.tsv> [силуэт] [папка_новых_TERRAIN]
"""
import csv
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import water_build as wb  # noqa: E402

GAME = ROOT / "Пиратки/Dioxine_XPiratez/user/mods/hd/hd/TERRAIN"
POS = [(gx, gy, z) for z in range(2) for gy in range(2) for gx in range(2)]


def scene(rgb, alpha, k):
    """rgb HxWx3, alpha HxW bool -> (картинка стопки, метка блока)"""
    H, W = alpha.shape
    img = np.zeros((H + 40 * k, W * 2, 3), np.float32)
    lab = np.full(img.shape[:2], -1, np.int32)
    for i, (gx, gy, z) in enumerate(POS):
        x0 = (gx - gy) * 16 * k + W // 2
        y0 = (gx + gy) * 8 * k + (1 - z) * 24 * k
        sl = (slice(y0, y0 + H), slice(x0, x0 + W))
        img[sl][alpha] = rgb[alpha]
        lab[sl][alpha] = i
    return img, lab


def ratio(img, lab, k):
    y = img @ np.float32([0.3, 0.59, 0.11])
    gx, gy = np.abs(y[:, 1:] - y[:, :-1]), np.abs(y[1:, :] - y[:-1, :])
    bx = (lab[:, 1:] != lab[:, :-1]) & (lab[:, 1:] >= 0) & (lab[:, :-1] >= 0)
    by = (lab[1:, :] != lab[:-1, :]) & (lab[1:, :] >= 0) & (lab[:-1, :] >= 0)
    bnd = np.zeros(lab.shape, np.uint8)
    bnd[:, 1:][bx] = 1
    bnd[1:, :][by] = 1
    far = cv2.dilate(bnd, np.ones((6 * k + 1, 6 * k + 1), np.uint8)) == 0
    inx = far[:, 1:] & far[:, :-1] & (lab[:, 1:] >= 0) & (lab[:, 1:] == lab[:, :-1])
    iny = far[1:, :] & far[:-1, :] & (lab[1:, :] >= 0) & (lab[1:, :] == lab[:-1, :])
    b = np.concatenate([gx[bx], gy[by]]).mean()
    i = np.concatenate([gx[inx], gy[iny]]).mean()
    return float(b / (i + 1e-3))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    out = Path(sys.argv[1])
    sil = sys.argv[2] if len(sys.argv) > 2 else "01a04fe05dc1"
    nd = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    pal = wb.palette().astype(np.float32)
    items = []
    with open(ROOT / "census/frames.tsv", encoding="utf-8-sig") as fh:
        for r in csv.reader(fh, delimiter="\t"):
            if r[0] == "TERRAIN" and r[8] == sil:
                items.append((r[1], int(r[2]), int(r[11] or 0)))
    rows, cache = [], {}
    for s, f, n in items:
        p = GAME / (s + ".PCK") / ("%d.png" % f)
        if not p.exists():
            continue
        if s not in cache:
            try:
                cache[s] = wb.read_set(s)
            except Exception:
                cache[s] = None
        if cache[s] is None:
            continue
        c = cache[s][f]
        im = np.asarray(Image.open(p).convert("RGBA")).astype(np.float32)
        k = im.shape[1] // 32
        if im.shape[0] != 40 * k:
            continue
        rc = ratio(*scene(pal[c], c > 0, 1), 1)
        rp = ratio(*scene(im[..., :3], im[..., 3] > 127, k), k)
        rn = ""
        if nd is not None and (nd / (s + ".PCK") / ("%d.png" % f)).exists():
            nn = np.asarray(Image.open(nd / (s + ".PCK") / ("%d.png" % f)).convert("RGBA")).astype(np.float32)
            rn = "%.2f" % ratio(*scene(nn[..., :3], nn[..., 3] > 127, k), k)
        rows.append((s, f, n, rc, rp, rn))
    rows.sort(key=lambda r: -r[2] * max(0, r[4] - r[3]))
    with open(out, "w", encoding="utf-8-sig") as o:
        o.write("набор\tкадр\tклеток\tклассика\tпак\tновое\n")
        for r in rows:
            o.write("%s\t%d\t%d\t%.2f\t%.2f\t%s\n" % r)
    print("кубов", len(rows), "->", out)
    for r in rows[:40]:
        print("%-18s %4d %6d классика %.2f пак %.2f %s" % r)


if __name__ == "__main__":
    main()
