"""Сверка правок голов LAMIA с основой: тело ниже шеи должно остаться на месте.
Для каждого images/head_<look>_<base>_<seed>.png: средняя разница с основой ниже шеи (y>=270 в кадре 736x848)
и сдвиг фазовой корреляцией. Годна: разница < 14 и сдвиг < 3 px."""
import glob
import os
import re
import sys
import cv2
import numpy as np
sys.stdout.reconfigure(encoding="utf-8")
D = r"E:\tmp\doll_ingame\lm\images"
Y0 = 270
for p in sorted(glob.glob(os.path.join(D, "head_*.png"))):
    n = os.path.splitext(os.path.basename(p))[0]
    m = re.match(r"head_(\w\d)_(.+)_(\d+)$", n)
    base = os.path.join(D, m.group(2) + ".png")
    a = cv2.imread(p).astype(np.float32)
    b = cv2.imread(base).astype(np.float32)
    if a.shape != b.shape:
        a = cv2.resize(a, (b.shape[1], b.shape[0]), interpolation=cv2.INTER_AREA)
    mad = float(np.abs(a[Y0:] - b[Y0:]).mean())
    ga = cv2.cvtColor(a[Y0:], cv2.COLOR_BGR2GRAY)
    gb = cv2.cvtColor(b[Y0:], cv2.COLOR_BGR2GRAY)
    (dx, dy), _ = cv2.phaseCorrelate(gb, ga)
    ok = mad < 14 and abs(dx) < 3 and abs(dy) < 3
    print("%-34s разница %5.1f  сдвиг %+5.1f %+5.1f  %s" % (n, mad, dx, dy, "ГОДНА" if ok else "брак"))
