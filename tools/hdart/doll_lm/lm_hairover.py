"""Контур маски волос классики (голубой) поверх HD-кадра внешности, рядом классика x8. Аргументы: внешности, выход."""
import os
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"E:\OpenXCom\tools\hdart")
import cv2
import numpy as np
from PIL import Image
import doll_b2_render as db
import doll_photo_pilot as dp
D = r"E:\tmp\doll_ingame\lm"
CROP = (42, 40, 134, 146)
BOX = (64, 40, 114, 80)
F = db.sprite_files()
Z = 8
rows = []
for lk in sys.argv[1].split(","):
    cl = np.asarray(Image.open(os.path.join(D, "classic_%s.png" % lk)).convert("RGB"))
    hd = np.asarray(Image.open(os.path.join(D, "layers", "full_%s.png" % lk)).convert("RGB")).copy()
    hm = dp.layer_mask(F, "LAMIA__13__HAIR_%s" % lk)[CROP[1]:CROP[3], CROP[0]:CROP[2]].astype(np.uint8)
    hm8 = cv2.resize(hm, (hd.shape[1], hd.shape[0]), interpolation=cv2.INTER_NEAREST)
    cnt, _ = cv2.findContours(hm8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cv2.drawContours(hd, cnt, -1, (0, 230, 255), 2)
    b = tuple((v - o) * Z for v, o in zip(BOX, (CROP[0], CROP[1], CROP[0], CROP[1])))
    rows.append(np.hstack([cl[b[1]:b[3], b[0]:b[2]], hd[b[1]:b[3], b[0]:b[2]]]))
Image.fromarray(np.vstack(rows)).save(sys.argv[2], quality=88)
print(sys.argv[2])
