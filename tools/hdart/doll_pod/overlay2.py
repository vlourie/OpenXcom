"""Капсулы, круг 3: HD-кукла расы В ЖИДКОСТИ, а не поверх.
- окно: скруглённый прямоугольник по области отличий набора, ровный край (сглаживание x16), чуть внутрь рамки;
- жидкость: фон окна из классики (точки окна без куклы), дорисован inpaint, увеличен и размыт;
- кукла: цвет как сама игра кладёт тело в жидкость - по каналу c = a*n + b (классика против классической голой куклы),
  к HD-кукле с глубиной t: a' = 1 + (a-1)*t, b' = b*t; t=1 - ровно как игра, t>1 - глубже;
- рамка, стекло вне окна - из FLUX (основа hd_A).
Аргументы: t набор=ключи|all ... ; выход hd_P<t*10>."""
import os
import re
import sys
import json
import cv2
import numpy as np
from PIL import Image
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nude_match as nm
import overlay as ov

SS = 16
INSET = float(os.environ.get("INSET", "1.5"))     # окно внутрь от края области отличий, точек k=1 (тёмный ободок FLUX остаётся)
SHADE = float(os.environ.get("SHADE", "0.4"))     # тень внутри окна у края (глубина)


def window_mask(s):
    """k=1 область отличий -> ограничивающий скруглённый прямоугольник, гладко на 1280x800"""
    diff = (np.asarray(Image.open(os.path.join(nm.D, "diff_%s.png" % s))) > 0).astype(np.uint8)
    win = cv2.morphologyEx(cv2.dilate(diff, np.ones((3, 3), np.uint8)), cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(win)
    i = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    x, y, w, h = st[i, :4]
    big = np.zeros((800 * SS // 4, 1280 * SS // 4), np.uint8)
    q = SS // 4 * 4 // 4  # точек большой картинки на точку k=1 = SS
    r = 3 * SS
    ins = int(SS * INSET)
    x0, y0, x1, y1 = x * SS + ins, y * SS + ins, (x + w) * SS - ins, (y + h) * SS - ins
    cv2.rectangle(big, (x0 + r, y0), (x1 - r, y1), 255, -1)
    cv2.rectangle(big, (x0, y0 + r), (x1, y1 - r), 255, -1)
    for cx, cy in ((x0 + r, y0 + r), (x1 - r, y0 + r), (x0 + r, y1 - r), (x1 - r, y1 - r)):
        cv2.circle(big, (cx, cy), r, 255, -1)
    big = cv2.resize(big, (320 * SS, 200 * SS), interpolation=cv2.INTER_NEAREST) if big.shape != (200 * SS, 320 * SS) else big
    m = cv2.resize(big.astype(np.float32) / 255, (1280, 800), interpolation=cv2.INTER_AREA)
    return m[..., None], (x, y, w, h)


GLASS = ("MAN_590", "MAN_811")


def window_poly(s):
    """шлем: область отличий -> гладкий контур (сглаживание x16), ровный край без лесенки"""
    diff = (np.asarray(Image.open(os.path.join(nm.D, "diff_%s.png" % s))) > 0).astype(np.uint8)
    win = cv2.morphologyEx(cv2.dilate(diff, np.ones((3, 3), np.uint8)), cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(win)
    i = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    big = cv2.resize((lab == i).astype(np.uint8) * 255, (320 * SS, 200 * SS), interpolation=cv2.INTER_NEAREST)
    big = cv2.GaussianBlur(big, (0, 0), SS * 1.2)          # лесенку k=1 в плавную кривую
    big = ((big > 127) * 255).astype(np.uint8)
    big = cv2.erode(big, np.ones((int(SS * INSET * 0.5) * 2 + 1,) * 2, np.uint8))
    m = cv2.resize(big.astype(np.float32) / 255, (1280, 800), interpolation=cv2.INTER_AREA)
    x, y, w, h = st[i, :4]
    return m[..., None], (x, y, w, h), (lab == i)


def build(t, s, key, outdir):
    race, mode, (dx, dy) = ov.SETS[s]
    name = "%s%s.SPK" % (s, key)
    cl = np.asarray(Image.open(os.path.join(nm.D, "classic_%s.png" % name)).convert("RGBA"))
    nu = nm.nude(nm.pick(nm.RACE[s]), key)[0]
    if nu is None:
        return None
    nu = ov.shift(nu, -dx, -dy)
    hd, used = ov.hd_nude(race, key)
    hd = ov.shift(hd, -dx * 4, -dy * 4)
    glass = s in GLASS
    if glass:
        wm, (x, y, w, h), inwin = window_poly(s)
    else:
        wm, (x, y, w, h) = window_mask(s)
        inwin = np.zeros((200, 320), bool)
        inwin[y + 1:y + h - 1, x + 1:x + w - 1] = True
    body = inwin & (nu[..., 3] > 0) & (cl[..., 3] > 0)
    # 1) как игра кладёт тело в жидкость: по каналу c = a*n + b
    A, B = [], []
    for ch in range(3):
        X = np.stack([nu[body][:, ch].astype(np.float32), np.ones(body.sum(), np.float32)], 1)
        a, b = np.linalg.lstsq(X, cl[body][:, ch].astype(np.float32), rcond=None)[0]
        A.append(a); B.append(b)
    A, B = np.array(A, np.float32), np.array(B, np.float32)
    a2, b2 = 1 + (A - 1) * t, B * t
    col = np.clip(hd[..., :3] * a2 + b2, 0, 255)
    # 2) жидкость: классика окна без куклы, дырки дорисованы
    liq = inwin & ~(nu[..., 3] > 0)
    src = cl[..., :3].copy()
    hole = (~liq).astype(np.uint8) * 255                 # всё, что не жидкость (кукла и рамка), дорисовать из жидкости
    src = cv2.inpaint(np.ascontiguousarray(src), hole, 5, cv2.INPAINT_TELEA)
    src = cv2.GaussianBlur(src.astype(np.float32), (0, 0), 1.2)
    bgw = cv2.resize(src, (1280, 800), interpolation=cv2.INTER_CUBIC)
    # 3) сборка: жидкость -> кукла (её альфа) -> тень у края окна -> только внутри окна; снаружи FLUX
    ha = hd[..., 3:4] / 255
    inside = bgw * (1 - ha) + col * ha
    dist = cv2.distanceTransform((wm[..., 0] > 0.5).astype(np.uint8), cv2.DIST_L2, 5)
    inside = inside * (1 - SHADE * np.exp(-dist / 16))[..., None]
    base = np.asarray(Image.open(os.path.join(nm.D, "hd_A", name.lower() + ".png")).convert("RGBA"), np.float32)
    if glass:   # под стеклом: блики стекла FLUX поверх (светлее своего размытия), где куклы нет - FLUX как есть
        bl = cv2.GaussianBlur(base[..., :3], (0, 0), 10)
        hi = np.clip(base[..., :3] - bl, 0, 255).max(-1, keepdims=True)
        inside = base[..., :3] * (1 - ha) + inside * ha
        inside = np.clip(inside + hi * 1.2, 0, 255)
    res = base.copy()
    res[..., :3] = base[..., :3] * (1 - wm) + inside * wm
    os.makedirs(outdir, exist_ok=True)
    Image.fromarray(np.clip(res + 0.5, 0, 255).astype(np.uint8), "RGBA").save(os.path.join(outdir, name.lower() + ".png"))
    return [round(float(v), 2) for v in A], [round(float(v)) for v in B], used


if __name__ == "__main__":
    t = float(sys.argv[1])
    out = os.path.join(nm.D, "hd_P%02d" % round(t * 10))
    for arg in sys.argv[2:]:
        s, keys = arg.split("=")
        if keys == "all":
            keys = sorted((n[len(s):-4] for n in nm.CROPS if re.match(r"^%s[MF]\d+\.SPK$" % s, n)), key=lambda k: (k[0] != "F", int(k[1:])))
        else:
            keys = keys.split(",")
        for k in keys:
            print(s, k, build(t, s, k, out), flush=True)
