"""Костюмы (копия veh_build): картинка k=4 (1280x800 RGBA) из ответа x8 - на место рамки crops.json, альфа - силуэт классики x4 (ровный
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

D = r"E:\tmp\doll_ingame\suit"
K = 4
KEY_LO, KEY_HI = 8.0, 36.0      # удаление от подложки (макс. по каналу): ниже - прозрачно, выше - деталь
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
    # подложка внутри силуэта у края (модель нарисовала тоньше классики: ротор, хвосты) - серая кайма на тёмном экране
    # (R-089). В полосе 16 px от края серое, связанное с подложкой снаружи, срезаем по контуру самой модели: альфа по
    # удалению цвета от подложки, у полупрозрачных пикселей серое вычитаем (заливка inpaint размазывала деталь).
    sil = (P.ws.sil4(mask) > 0).astype(np.uint8)       # та же плавная маска, что у альфы layer_from (иначе лесенка)
    dist = np.abs(full - np.float32(dp.PANEL)).max(axis=2)
    loose = dist < KEY_HI
    _, lab2 = cv2.connectedComponents(loose.astype(np.uint8), connectivity=8)
    outside = np.unique(lab2[loose & (sil == 0)])
    d = cv2.distanceTransform(sil, cv2.DIST_L2, 5)
    # только где классика сама не серая: серые тени белого скафандра (MAN_105) иначе стали бы дырами
    # плавно: срез тем сильнее, чем модель дальше от размытой классики (резкая маска по классике давала лесенку, R-121)
    c4 = cv2.resize(cl[..., :3], (db.W * K, db.H * K), interpolation=cv2.INTER_NEAREST).astype(np.float32)
    w4 = cv2.GaussianBlur(sil.astype(np.float32), (0, 0), 3.0)       # размытие только по силуэту: фон не темнит край
    c4 = cv2.GaussianBlur(c4 * sil[..., None], (0, 0), 3.0) / np.maximum(w4, 1e-3)[..., None]
    g = np.clip((np.abs(full - c4).max(axis=2) - 30) / 30, 0, 1)
    reg = np.isin(lab2, outside[outside > 0]) & (sil > 0) & (d <= 16)
    key = np.ones(sil.shape, np.float32)
    raw = np.clip((dist[reg] - KEY_LO) / (KEY_HI - KEY_LO), 0, 1)
    key[reg] = 1 - g[reg] * (1 - raw)
    key = cv2.medianBlur((key * 255).astype(np.uint8), 5).astype(np.float32) / 255   # без точек-крошек по краю
    key = np.minimum(key, cv2.GaussianBlur(key, (0, 0), 0.7))
    os.makedirs(out, exist_ok=True)
    p = os.path.join(out, name.lower() + ".png")
    lay = np.asarray(P.layer_from(full, mask, edge=3.0), np.float32)
    part = (key > 0.02) & (key < 1)
    a = key[part][:, None]
    lay[..., :3][part] = np.clip((lay[..., :3][part] - (1 - a) * np.float32(dp.PANEL)) / a, 0, 255)
    lay[..., 3] *= key
    Image.fromarray(np.clip(lay + 0.5, 0, 255).astype(np.uint8), "RGBA").save(p)
    if reg.any():
        print(name, "срезано серого px", int(((key < 0.5) & (sil > 0)).sum()))
    return p


if __name__ == "__main__":
    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else os.path.join(D, "hd")
    for a in sys.argv[1:]:
        if "=" in a:
            n, s = a.rsplit("=", 1)
            print(build(n, int(s), out))
