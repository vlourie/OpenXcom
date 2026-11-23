"""Слой жидкости по месту: в каждой меняющейся точке по всем внешностям pod = a*doll + b (по каналу).
a - сколько куклы видно сквозь жидкость (прозрачность), b - цвет жидкости/стекла. Ошибка подгонки против ошибки палитры."""
import os
import sys
import glob
import numpy as np
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"E:\OpenXCom\tools\hdart")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import doll_b2_render as db
import pod_theory as pt
import pod_blend as pb

pal = db.game_palette().astype(np.float32)
for s in (sys.argv[1:] or ["570", "620", "870"]):
    race, (dx, dy) = pt.SETS[s]
    paths = sorted(glob.glob(os.path.join(pt.ARM, "Body_%s" % s, "body%s_*.*" % s)))
    keys = [os.path.splitext(os.path.basename(p))[0].split("_")[1] for p in paths]
    P = np.stack([pt.idx(p) for p in paths])
    Dl = np.stack([pb.doll_of(race, k, dx, dy) for k in keys])
    V = ~np.all(P == P[0], 0) & np.all(Dl > 0, 0)
    X = pal[Dl[:, V]]           # looks x n x 3
    Y = pal[P[:, V]]
    xm, ym = X.mean(0), Y.mean(0)
    cov = ((X - xm) * (Y - ym)).sum(0)
    var = ((X - xm) ** 2).sum(0)
    a = np.where(var > 1, cov / np.maximum(var, 1e-6), 0)
    b = ym - a * xm
    err = np.abs(a[None] * X + b[None] - Y).mean()
    err0 = np.abs(Y - ym[None]).mean()
    print("MAN_%s: точек %d, внешностей %d | прозрачность a: медиана %.2f (10%% %.2f, 90%% %.2f) | ошибка подгонки %.1f против %.1f без куклы" % (
        s, V.sum(), len(keys), np.median(a), np.percentile(a, 10), np.percentile(a, 90), err, err0))
