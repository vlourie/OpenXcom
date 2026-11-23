"""Оттенок вещи к классике: средние a/b (Lab) зелёных точек слоя сдвигаются к средним классики того же слоя,
яркость и фактура остаются. Точки не того цвета (шерсть, уши под капюшоном) не трогаются.
Аргументы: слой HD (пишется рядом с суффиксом _tint, или --inplace), имя слоя классики."""
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"E:\OpenXCom\tools\hdart")
import cv2
import numpy as np
from PIL import Image
import doll_b2_render as db

p, name = sys.argv[1], sys.argv[2]
F, PAL = db.sprite_files(), db.game_palette()
cl = db.to_rgba(db.load_indices(F[name]), PAL).astype(np.uint8)
clab = cv2.cvtColor(np.ascontiguousarray(cl[..., :3]), cv2.COLOR_RGB2LAB).astype(np.float32)
cm = cl[..., 3] > 0
cg = cm & (clab[..., 1] < 120)                                   # зелёное в классике (a < 128 - зелень)
ta, tb, tl = clab[cg, 1].mean(), clab[cg, 2].mean(), clab[cg, 0].mean()
im = np.asarray(Image.open(p).convert("RGBA")).copy()
lab = cv2.cvtColor(np.ascontiguousarray(im[..., :3]), cv2.COLOR_RGB2LAB).astype(np.float32)
hsv = cv2.cvtColor(np.ascontiguousarray(im[..., :3]), cv2.COLOR_RGB2HSV).astype(np.float32)
green = (im[..., 3] > 0) & (hsv[..., 0] > 22) & (hsv[..., 0] < 75) & (hsv[..., 1] > 40)
sa, sb, sl = lab[green, 1].mean(), lab[green, 2].mean(), lab[green, 0].mean()
print("классика L a b", round(tl), round(ta), round(tb), "HD", round(sl), round(sa), round(sb), "точек", int(green.sum()))
w = cv2.GaussianBlur(green.astype(np.float32), (0, 0), 1.5)           # мягкий край перехода
k = 0.85                                                              # сдвиг не до конца - классика палитровая и пёстрая
lab[..., 1] += w * (ta - sa) * k
lab[..., 2] += w * (tb - sb) * k
lab[..., 0] += w * (tl - sl) * 0.5
im[..., :3] = cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)
out = p if "--inplace" in sys.argv else p.replace(".png", "_tint.png")
Image.fromarray(im, "RGBA").save(out)
print(out)
