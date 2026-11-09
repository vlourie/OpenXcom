"""Техника: картинка k=4 (1280x800 RGBA) из ответа x8 - на место рамки crops.json, альфа - силуэт классики x4 (ровный
контур, R-121), кайма по краю цветом изнутри (R-089). Аргументы: имя=сид через пробел, [--out каталог].
Выход <out>/<имя в нижнем регистре>.png - так движок ищет hd/UI/<имя>.png (Mod.cpp, HdUiArt::addLazy)."""
import json
import os
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"E:\OpenXCom\tools\hdart")
import cv2
import numpy as np
from PIL import Image
import doll_b2_render as db
import doll_photo_pilot as dp
import doll_pipe_pilot as P

D = r"E:\tmp\doll_ingame\veh"
K = 4
CROPS = json.load(open(os.path.join(D, "crops.json"), encoding="utf-8"))


def build(name, seed, out):
    x0, y0, x1, y1 = (v * K for v in CROPS[name])
    raw = Image.open(os.path.join(D, "images", "%s_%d.png" % (name, seed))).convert("RGB")
    full = np.empty((db.H * K, db.W * K, 3), np.float32)
    full[:] = dp.PANEL
    full[y0:y1, x0:x1] = np.asarray(raw.resize((x1 - x0, y1 - y0), Image.LANCZOS), np.float32)
    cl = np.asarray(Image.open(os.path.join(D, "classic_%s.png" % name)).convert("RGBA"))
    mask = cl[..., 3] > 0
    # мелкие отдельные кусочки (капли под ховертанком, 1-3 точки k=1): у модели они в кайме подложки - цвет классики
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    small = np.isin(lab, [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] <= 6])
    if small.any():
        sm4 = cv2.resize(small.astype(np.uint8), (db.W * K, db.H * K), interpolation=cv2.INTER_NEAREST).astype(bool)
        sm4 = cv2.dilate(sm4.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
        c4 = cv2.resize(cl[..., :3], (db.W * K, db.H * K), interpolation=cv2.INTER_NEAREST).astype(np.float32)
        full[sm4] = c4[sm4]
        print(name, "мелких кусочков", int(small.sum()))
    os.makedirs(out, exist_ok=True)
    p = os.path.join(out, name.lower() + ".png")
    P.layer_from(full, mask, edge=3.0).save(p)
    return p


if __name__ == "__main__":
    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else os.path.join(D, "hd")
    for a in sys.argv[1:]:
        if "=" in a:
            n, s = a.rsplit("=", 1)
            print(build(n, int(s), out))
