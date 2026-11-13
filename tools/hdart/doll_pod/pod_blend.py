"""Капсула = кукла, смешанная с жидкостью и сведённая к палитре? Для меняющихся точек на кукле:
1) по каналу pod = a*doll + b (МНК), ошибка в цвете;
2) предсказанный цвет -> ближайший цвет из палитры, которой нарисовано окно капсулы; доля точь-в-точь по индексу;
3) то же, если куклу сперва чуть размыть (3x3) - вдруг смешивали с размытием.
Контроль: те же расчёты на кукле ЧУЖОЙ внешности."""
import os
import sys
import glob
import numpy as np
import cv2
from PIL import Image
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"E:\OpenXCom\tools\hdart")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import doll_b2_render as db
import pod_theory as pt

pal = db.game_palette().astype(np.float32)


def doll_of(race, key, dx, dy):
    doll = np.zeros((200, 320), np.uint8)
    for nm in ("%s__2__%s_NUDE", "%s__10__HEAD_%s", "%s__13__HAIR_%s"):
        a = pt.layer(nm % (race, key))
        if a is None:
            continue
        ys, xs = np.nonzero(a)
        y2, x2 = ys - dy, xs - dx
        ok = (y2 >= 0) & (y2 < 200) & (x2 >= 0) & (x2 < 320)
        doll[y2[ok], x2[ok]] = a[ys[ok], xs[ok]]
    return doll


def test(pod, doll, V, blur):
    on = V & (doll > 0)
    d = pal[doll]
    if blur:
        d = cv2.blur(d, (3, 3))
    X = d[on]
    Y = pal[pod][on]
    pred = np.zeros_like(Y)
    for ch in range(3):
        A = np.stack([X[:, ch], np.ones(len(X))], 1)
        k = np.linalg.lstsq(A, Y[:, ch], rcond=None)[0]
        pred[:, ch] = A @ k
    err = np.abs(pred - Y).mean()
    used = np.unique(pod[V])
    pp = pal[used]
    near = used[np.argmin(((pred[:, None, :] - pp[None]) ** 2).sum(-1), 1)]
    return err, (near == pod[on]).mean(), on.sum()


for item in ((sys.argv[1:] or ["570:F0", "620:F0", "870:F0", "870:M3"]) if __name__ == "__main__" else []):
    s, key = item.split(":")
    race, (dx, dy) = pt.SETS[s]
    allp = sorted(glob.glob(os.path.join(pt.ARM, "Body_%s" % s, "body%s_*.*" % s)))
    stack = np.stack([pt.idx(p) for p in allp])
    V = ~np.all(stack == stack[0], 0)
    pod = pt.idx(glob.glob(os.path.join(pt.ARM, "Body_%s" % s, "body%s_%s.*" % (s, key)))[0])
    other = "F3" if key != "F3" else "F1"
    for lab, k in (("своя", key), ("чужая " + other, other)):
        doll = doll_of(race, k, dx, dy)
        for blur in (False, True):
            e, m, n = test(pod, doll, V, blur)
            print("MAN_%s%s кукла %-9s размытие %-3s: ошибка цвета %5.1f, индекс точь-в-точь %.2f (%d точек)" % (
                s, key, lab, "да" if blur else "нет", e, m, n))
