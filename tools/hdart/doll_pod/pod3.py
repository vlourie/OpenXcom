"""Капсулы, проба 4: как сделаны в моде - вся кукла под одним слоем жидкости на набор.
Слой снимается из самой игры: в каждой точке окна по всем внешностям набора pod = a*doll + b (по каналу),
где куклы нет ни у кого - жидкость L = медиана капсул. Карты a, b, L сглажены (палитра и пузырьки - шум),
увеличены до HD; HD-кукла расы целиком: out = L + alpha*(a*hd + b - L). Окно - ровный скруглённый прямоугольник,
снаружи рамка и стекло FLUX (hd_A). Аргументы: набор=ключи|all ... ; выход hd_Q."""
import os
import re
import sys
import glob
import cv2
import numpy as np
from PIL import Image
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"E:\OpenXCom\tools\hdart")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import doll_b2_render as db
import nude_match as nm
import overlay as ov
import overlay2 as o2
import pod_theory as pt
import pod_blend as pb

pal = db.game_palette().astype(np.float32)
SIG = float(os.environ.get("SIG", "3"))        # сглаживание карт, точек k=1
RIM = float(os.environ.get("RIM", "1.0"))      # ширина тёмного ободка окна, точек k=1
RACE = {"MAN_570": "FHUMAN", "MAN_620": "HYBRID", "MAN_870": "OGRE", "MAN_720": "LAMIA", "MAN_920": "GNOME"}
_maps = {}


def nsmooth(v, w, sig):
    """нормированное размытие: только по точкам с весом; дыры без данных - из широкого размытия"""
    num = cv2.GaussianBlur(v * w[..., None], (0, 0), sig)
    den = cv2.GaussianBlur(w, (0, 0), sig)[..., None]
    num2 = cv2.GaussianBlur(v * w[..., None], (0, 0), sig * 6)
    den2 = cv2.GaussianBlur(w, (0, 0), sig * 6)[..., None]
    k = np.clip(den / 0.3, 0, 1)
    out = (num / np.maximum(den, 1e-6)) * k + (num2 / np.maximum(den2, 1e-6)) * (1 - k)
    return out, den[..., 0]


def maps(s):
    if s in _maps:
        return _maps[s]
    race, (dx, dy) = RACE[s], ov.SETS[s][2]
    n = s[4:]
    paths = sorted(glob.glob(os.path.join(pt.ARM, "Body_%s" % n, "body%s_*.*" % n)))
    keys = [os.path.splitext(os.path.basename(p))[0].split("_")[1] for p in paths]
    P = pal[np.stack([pt.idx(p) for p in paths])]                       # looks x 200 x 320 x 3
    Di = np.stack([pb.doll_of(race, k, dx, dy) for k in keys])
    D = pal[Di]
    on = (Di > 0)[..., None].astype(np.float32)
    cnt = on.sum(0)[..., 0]
    xm = (D * on).sum(0) / np.maximum(on.sum(0), 1)
    ym = (P * on).sum(0) / np.maximum(on.sum(0), 1)
    cov = (((D - xm) * (P - ym)) * on).sum(0)
    var = (((D - xm) ** 2) * on).sum(0)
    a = np.clip(np.where(var > 50, cov / np.maximum(var, 1e-6), 0.3), 0, 1)
    b = ym - a * xm
    off = (Di == 0)[..., None].astype(np.float32)
    Lr = (P * off).sum(0) / np.maximum(off.sum(0), 1)                     # жидкость там, где куклы нет
    V = ~np.all(np.all(P == P[0], -1), 0)                               # окно: где меняется сама капсула
    V = cv2.morphologyEx(V.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)) > 0
    wL = ((off.sum(0)[..., 0] > 0) & V).astype(np.float32)               # рамку снаружи окна в жидкость не тянуть
    wab = ((cnt >= 3) & V).astype(np.float32)
    a_s, _ = nsmooth(a, wab, SIG)
    b_s, _ = nsmooth(b, wab, SIG)
    # жидкость: где есть пустые точки - из них, иначе b/(1-a)
    L0 = np.where(wL[..., None] > 0, Lr, b / np.maximum(1 - a, 0.2))
    wLL = np.where(wL > 0, 1.0, np.where(wab > 0, 0.15, 0.0)).astype(np.float32)   # пустые точки надёжнее b/(1-a)
    L_s, _ = nsmooth(np.clip(L0, 0, 255), wLL, SIG * 1.5)
    up = lambda m: cv2.resize(m.astype(np.float32), (1280, 800), interpolation=cv2.INTER_CUBIC)
    _maps[s] = (up(a_s), up(b_s), up(L_s), len(keys), float(np.median(a[wab > 0])))
    return _maps[s]


def window_rect(s):
    """окно по рамке классики: связная область «не голубой рамки» вокруг меняющихся точек -> скруглённый прямоугольник"""
    n = s[4:]
    paths = sorted(glob.glob(os.path.join(pt.ARM, "Body_%s" % n, "body%s_*.*" % n)))
    I = np.stack([pt.idx(p) for p in paths[:8]])
    c = pal[I[0]]
    cyan = (c[..., 1] > c[..., 0] + 40) & (c[..., 2] > c[..., 0] + 40)
    V = ~np.all(I == I[0], 0)
    reg = (~cyan & (I[0] > 0)).astype(np.uint8)
    k, lab, st, _ = cv2.connectedComponentsWithStats(reg, connectivity=4)
    ids, cnt = np.unique(lab[V & (reg > 0)], return_counts=True)
    i = int(ids[np.argmax(cnt)])
    x, y, w, h = st[i, :4]
    m = lab == i
    ring = m & ~(cv2.erode(m.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)
    rc = c[ring]
    lum = rc @ np.array([0.299, 0.587, 0.114], np.float32)
    rim = np.median(rc[lum <= np.percentile(lum, 40)], 0)          # цвет тёмного ободка окна классики (тело у края не брать)

    def rr(ins):
        big = np.zeros((200 * o2.SS, 320 * o2.SS), np.uint8)
        SS, r = o2.SS, 3 * o2.SS
        ins = int(SS * ins)
        x0, y0, x1, y1 = x * SS + ins, y * SS + ins, (x + w) * SS - ins, (y + h) * SS - ins
        rad = max(SS, r - ins)
        cv2.rectangle(big, (x0 + rad, y0), (x1 - rad, y1), 255, -1)
        cv2.rectangle(big, (x0, y0 + rad), (x1, y1 - rad), 255, -1)
        for cx, cy in ((x0 + rad, y0 + rad), (x1 - rad, y0 + rad), (x0 + rad, y1 - rad), (x1 - rad, y1 - rad)):
            cv2.circle(big, (cx, cy), rad, 255, -1)
        return cv2.resize(big.astype(np.float32) / 255, (1280, 800), interpolation=cv2.INTER_AREA)[..., None]
    outer, inner = rr(0.0), rr(RIM)
    return outer, inner, rim, (x, y, w, h)


def build(s, key, outdir):
    race, mode, (dx, dy) = ov.SETS[s]
    name = "%s%s.SPK" % (s, key)
    a, b, L, nlooks, amed = maps(s)
    hd, used = ov.hd_nude(ov.SETS[s][0], key)
    hd = ov.shift(hd, -dx * 4, -dy * 4)
    al = hd[..., 3:4] / 255
    inside = L + al * (a * hd[..., :3] + b - L)
    outer, inner, rim, wr = window_rect(s)
    base = np.asarray(Image.open(os.path.join(nm.D, "hd_A", name.lower() + ".png")).convert("RGBA"), np.float32)
    res = base.copy()
    # окно целиком по рамке классики: снаружи FLUX, по краю тёмный ободок цвета классики, внутри жидкость с куклой
    win = base[..., :3] * (1 - outer) + rim[None, None, :] * outer
    res[..., :3] = win * (1 - inner) + np.clip(inside, 0, 255) * inner
    os.makedirs(outdir, exist_ok=True)
    Image.fromarray(np.clip(res + 0.5, 0, 255).astype(np.uint8), "RGBA").save(os.path.join(outdir, name.lower() + ".png"))
    return nlooks, round(amed, 2), used


if __name__ == "__main__":
    out = os.path.join(nm.D, os.environ.get("OUT", "hd_Q"))
    for arg in sys.argv[1:]:
        s, keys = arg.split("=")
        if keys == "all":
            keys = sorted((n[len(s):-4] for n in nm.CROPS if re.match(r"^%s[MF]\d+\.SPK$" % s, n)), key=lambda k: (k[0] != "F", int(k[1:])))
        else:
            keys = keys.split(",")
        for k in keys:
            print(s, k, build(s, k, out), flush=True)
