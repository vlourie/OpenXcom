"""Наложение готовой HD-куклы расы вместо картинки FLUX там, где классика набора = голая кукла (nude_fast).
same - лок'нар в одежде: кукла ставится только на точки, где классика совпадает с голой куклой точно (одежда остаётся).
pod  - капсула/стекло: кукла сдвинута (dx, dy), подкрашена под жидкость (свой линейный цвет на канал по точкам k=1),
       ставится внутри окна (маска отличий набора с заливкой) и только по телу куклы.
Основа (рамка, костюм, контур, альфа) - готовая HD набора hd_<основа>. Выход hd_N/<имя>.png.
Аргументы: основа набор=ключи|all ... ; набор берёт расу, режим и сдвиг из таблицы SETS."""
import json
import os
import re
import sys
import cv2
import numpy as np
from PIL import Image
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nude_match as nm

L = r"E:\OpenXCom\art\doll\pipe_pilot"
SETS = {   # набор: (раса HD, режим, сдвиг dx dy в точках классики)
    "MAN_802": ("loknar", "same", (0, 0)), "MAN_803": ("loknar", "same", (0, 0)), "MAN_808": ("loknar", "same", (0, 0)),
    "MAN_830": ("loknar", "same", (1, 9)), "MAN_810": ("loknar", "same", (0, 0)), "MAN_811": ("loknar", "pod", (0, 0)),
    "MAN_570": ("fhuman", "pod", (1, 1)), "MAN_590": ("fhuman", "pod", (0, 0)), "MAN_620": ("hybrid", "pod", (1, 0)),
    "MAN_720": ("lamia", "pod", (2, 8)), "MAN_870": ("ogre", "pod", (1, 2)), "MAN_920": ("gnome", "pod", (0, 4)),
}
LAYERS = (("2", "%s_nude"), ("3", "pasties"), ("10", "head_%s"), ("13", "hair_%s"))


def hd_nude(race, key):
    out = np.zeros((800, 1280, 4), np.float32)
    used = []
    for num, pat in LAYERS:
        p = os.path.join(L, race, "heads", "layers", "%s__%s__%s.png" % (race, num, pat % key.lower() if "%s" in pat else pat))
        if not os.path.exists(p):
            continue
        im = np.asarray(Image.open(p).convert("RGBA"), np.float32)
        a = im[..., 3:4] / 255
        out[..., :3] = out[..., :3] * (1 - a) + im[..., :3] * a
        out[..., 3:4] = out[..., 3:4] + a * (1 - out[..., 3:4] / 255) * 255
        used.append(os.path.basename(p))
    return out, used


def shift(x, dx, dy):
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(x, M, (x.shape[1], x.shape[0]), flags=cv2.INTER_NEAREST, borderValue=0)


def soft4(m1, grow=0, feather=1.0):
    m = m1.astype(np.uint8)
    if grow:
        m = (cv2.dilate if grow > 0 else cv2.erode)(m, np.ones((2 * abs(grow) + 1,) * 2, np.uint8))
    m = cv2.GaussianBlur(m.astype(np.float32), (0, 0), feather)
    return np.clip(cv2.resize(m, (1280, 800), interpolation=cv2.INTER_CUBIC), 0, 1)[..., None]


def build(base, s, key, outdir):
    race, mode, (dx, dy) = SETS[s]
    name = "%s%s.SPK" % (s, key)
    cl = np.asarray(Image.open(os.path.join(nm.D, "classic_%s.png" % name)).convert("RGBA"))
    nu1 = nm.nude(nm.pick(nm.RACE[s]), key)[0]
    if nu1 is None:
        return None
    # nude_fast: точка классики (x, y) = точка куклы (x+dx, y+dy) - куклу двигать на (-dx, -dy)
    nu1 = shift(nu1, -dx, -dy)
    hd, used = hd_nude(race, key)
    hd = shift(hd, -dx * 4, -dy * 4)
    diff = np.asarray(Image.open(os.path.join(nm.D, "diff_%s.png" % s))) > 0
    if mode == "same":
        m1 = np.all(cl[..., :3] == nu1[..., :3], -1) & (nu1[..., 3] > 0) & (cl[..., 3] > 0)
        m1 &= cv2.dilate(diff.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
        m = soft4(m1, 0, 0.8)
        col = hd[..., :3]
    else:
        win = cv2.morphologyEx(cv2.dilate(diff.astype(np.uint8), np.ones((3, 3), np.uint8)), cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8)) > 0
        m1 = win & (nu1[..., 3] > 0) & (cl[..., 3] > 0)
        a_c = cl[m1][:, :3].astype(np.float32)
        hd1 = cv2.resize(hd, (320, 200), interpolation=cv2.INTER_AREA)     # цвет подгоняется к самой HD-кукле
        a_n = hd1[m1][:, :3].astype(np.float32)
        # затемнение и цвет жидкости в Lab: светлота умножением (контраст HD цел), оттенок - сдвигом средних к классике
        lc = cv2.cvtColor((a_c / 255)[None].astype(np.float32), cv2.COLOR_RGB2LAB)[0]
        ln = cv2.cvtColor((a_n / 255)[None].astype(np.float32), cv2.COLOR_RGB2LAB)[0]
        lh = cv2.cvtColor(np.ascontiguousarray(hd[..., :3] / 255).astype(np.float32), cv2.COLOR_RGB2LAB)
        lh[..., 0] *= max(lc[:, 0].mean(), 1) / max(ln[:, 0].mean(), 1)
        lh[..., 1:] += (lc[:, 1:].mean(0) - ln[:, 1:].mean(0))[None, None, :]
        col = np.clip(cv2.cvtColor(lh, cv2.COLOR_LAB2RGB), 0, 1) * 255
        wb = cv2.morphologyEx(win.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
        m = soft4(wb > 0, 0, 0.7) * (hd[..., 3:4] / 255)
    bp = os.path.join(nm.D, "hd_" + base, name.lower() + ".png")
    b = np.asarray(Image.open(bp).convert("RGBA"), np.float32)
    res = b.copy()
    res[..., :3] = b[..., :3] * (1 - m) + np.clip(col, 0, 255) * m
    os.makedirs(outdir, exist_ok=True)
    Image.fromarray(np.clip(res + 0.5, 0, 255).astype(np.uint8), "RGBA").save(os.path.join(outdir, name.lower() + ".png"))
    return int(m1.sum()), used


if __name__ == "__main__":
    base = sys.argv[1]
    out = os.path.join(nm.D, "hd_N")
    for arg in sys.argv[2:]:
        s, keys = arg.split("=")
        if keys == "all":
            keys = sorted((n[len(s):-4] for n in nm.CROPS if re.match(r"^%s[MF]\d+\.SPK$" % s, n)), key=lambda k: (k[0] != "F", int(k[1:])))
        else:
            keys = keys.split(",")
        for k in keys:
            r = build(base, s, k, out)
            print(s, k, r, flush=True)
