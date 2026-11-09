"""Сколько точек вещи классики (по маске, с цветом вещи) в HD того же цвета: покрытие капюшона и жилета.
Аргументы: слой HD, имя слоя классики. Печатает долю по полосам y (база)."""
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"E:\OpenXCom\tools\hdart")
import cv2
import numpy as np
from PIL import Image
import doll_b2_render as db

F, PAL = db.sprite_files(), db.game_palette()
cl = db.to_rgba(db.load_indices(F[sys.argv[2]]), PAL).astype(np.uint8)
hsv_c = cv2.cvtColor(np.ascontiguousarray(cl[..., :3]), cv2.COLOR_RGB2HSV)
cg = (cl[..., 3] > 0) & (hsv_c[..., 0] > 30) & (hsv_c[..., 0] < 90) & (hsv_c[..., 1] > 60)
im = np.asarray(Image.open(sys.argv[1]).convert("RGBA"))
hsv = cv2.cvtColor(np.ascontiguousarray(im[..., :3]), cv2.COLOR_RGB2HSV)
g4 = (im[..., 3] > 128) & (hsv[..., 0] > 30) & (hsv[..., 0] < 90) & (hsv[..., 1] > 50)
g = g4.reshape(200, 4, 320, 4).mean((1, 3)) > 0.5
ys, xs = np.nonzero(cg)
for y0 in range(ys.min(), ys.max() + 1, 6):
    m = cg[y0:y0 + 6]
    print("y %d-%d классика %d HD %d%%" % (y0, y0 + 5, m.sum(), 100 * (g[y0:y0 + 6] & m).sum() // max(1, m.sum())))
print("всего %d%%" % (100 * (g & cg).sum() // cg.sum()))
