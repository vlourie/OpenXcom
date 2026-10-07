#!/usr/bin/env python3
"""
Cuts the boxing gloves out of a sheet of renders into small RGBA pictures for gen_fx.py
(--melee-style 6 --glove 1..10).

    <venv>\Scripts\python.exe tools\hdart\cut_gloves.py pics\gloves.png tools\hdart\gloves [96]

The sheet is a grid of gloves, two rows of five, one glove per cell on a plain or gradient background.
Every cell is matted with grabCut (the glove is the largest thing in the middle), the holes in the
silhouette are filled, the edge is softened by a pixel and the cut-out is scaled to `height` pixels
(96 by default - gen_fx.py scales it to the frame). Writes 01.png ... 10.png plus gloves.png, a sheet
of all of them to look at. Needs OpenCV, so it runs in the generator's venv, not in py -3.
"""
import os, sys
import numpy as np, cv2
from PIL import Image

src = sys.argv[1]
out_dir = sys.argv[2]
height = int(sys.argv[3]) if len(sys.argv) > 3 else 96
os.makedirs(out_dir, exist_ok=True)
sheet = Image.open(src).convert("RGB")
cols, rows = 5, 2
cw, chh = sheet.width // cols, sheet.height // rows
prev = []
for r in range(rows):
    for c in range(cols):
        n = r * cols + c + 1
        cell = sheet.crop((c * cw, r * chh, (c + 1) * cw, (r + 1) * chh))
        a = np.asarray(cell)
        bgr = a[:, :, ::-1].copy()
        mask = np.zeros(bgr.shape[:2], np.uint8)
        m = int(min(cw, chh) * 0.06)
        rect = (m, m, cw - 2 * m, chh - 2 * m)
        bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
        cv2.grabCut(bgr, mask, rect, bgd, fgd, 6, cv2.GC_INIT_WITH_RECT)
        fg = np.isin(mask, (cv2.GC_FGD, cv2.GC_PR_FGD)).astype(np.uint8)
        fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
        num, lab, stats, _ = cv2.connectedComponentsWithStats(fg, 8)
        if num > 1:
            keep = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
            fg = (lab == keep).astype(np.uint8)
        # fill the holes inside the silhouette
        holes = fg.copy()
        cv2.floodFill(holes, np.zeros((chh + 2, cw + 2), np.uint8), (0, 0), 1)
        fg = np.where(holes == 0, 1, fg).astype(np.uint8)
        alpha = cv2.GaussianBlur(fg * 255.0, (0, 0), 1.2)
        rgba = np.dstack([a, np.clip(alpha, 0, 255)]).astype(np.uint8)
        im = Image.fromarray(rgba, "RGBA")
        box = Image.fromarray((alpha > 40).astype(np.uint8) * 255).getbbox()
        im = im.crop(box)
        small = im.resize((max(1, round(im.width * height / im.height)), height), Image.LANCZOS)
        small.save(os.path.join(out_dir, "%02d.png" % n))
        prev.append(small)
        print(n, "cell", (cw, chh), "-> cut", im.size, "-> small", small.size)
w = max(p.width for p in prev) + 8
sheet_out = Image.new("RGBA", (w * 5, (height + 8) * 2), (40, 40, 44, 255))
for i, p in enumerate(prev):
    sheet_out.alpha_composite(p, ((i % 5) * w + 4, (i // 5) * (height + 8) + 4))
sheet_out.save(os.path.join(out_dir, "gloves.png"))
