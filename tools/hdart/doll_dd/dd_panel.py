"""Подложка внутри силуэта (R-089): точки слоя с альфой > 200 и цветом у PANEL (Lab dE < 10). Аргументы: слои.
С --fix закрашивает такие куски (и кольцо 2 точки) инпейнтом соседей и пишет слой на место."""
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"E:\OpenXCom\tools\hdart")
import cv2
import numpy as np
from PIL import Image
import doll_photo_pilot as dp

fix = "--fix" in sys.argv
pan = cv2.cvtColor(np.uint8([[dp.PANEL]]), cv2.COLOR_RGB2LAB).astype(np.float32)[0, 0]
for p in [a for a in sys.argv[1:] if a != "--fix"]:
    im = np.asarray(Image.open(p).convert("RGBA")).copy()
    lab = cv2.cvtColor(im[..., :3], cv2.COLOR_RGB2LAB).astype(np.float32)
    d = np.sqrt(((lab - pan) ** 2).sum(-1))
    bad = (im[..., 3] > 200) & (d < 10)
    n, lbl, st, _ = cv2.connectedComponentsWithStats(bad.astype(np.uint8))
    big = [(int(st[i, 4]), int(st[i, 0]) // 4, int(st[i, 1]) // 4) for i in range(1, n) if st[i, 4] >= 6]
    print(p, "точек", int(bad.sum()), "кусков >=6:", sorted(big, reverse=True)[:8])
    keep = np.zeros(n, bool)
    keep[1:] = st[1:, 4] >= 20                       # куски меньше - серая шерсть и блики, не подложка
    bad = keep[lbl]
    if fix and bad.any():
        m = cv2.dilate(bad.astype(np.uint8), np.ones((5, 5), np.uint8))
        im[..., :3] = cv2.inpaint(im[..., :3], m, 6, cv2.INPAINT_TELEA)
        Image.fromarray(im, "RGBA").save(p)
        print("  закрашено", int(m.sum()))
