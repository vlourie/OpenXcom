"""DEMONESS и DOGE (09.11): ответ FLUX (рамка x8 из dd_init) -> слой k=4 1280x800, альфа - силуэт классики x4 (ws.sil4),
кайма у края берёт цвет изнутри (P.layer_from, R-089). Аргументы: картинка ответа, имя слоя, рамка (dem или dog), [выход].
Выход по умолчанию E:/tmp/doll_ingame/dd/layers/<ответ>/<слой>.png."""
import os
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"E:\OpenXCom\tools\hdart")
import numpy as np
from PIL import Image
import doll_b2_render as db
import doll_photo_pilot as dp
import doll_pipe_pilot as P

CROPS = {"dem": (36, 10, 120, 176), "dog": (44, 50, 108, 150)}
K = 4


def cut(src, layer, crop, out=None):
    F = db.sprite_files()
    x0, y0, x1, y1 = (v * K for v in CROPS[crop])
    full = np.empty((db.H * K, db.W * K, 3), np.float32)
    full[:] = dp.PANEL
    full[y0:y1, x0:x1] = np.asarray(Image.open(src).convert("RGB").resize((x1 - x0, y1 - y0), Image.LANCZOS), np.float32)
    lay = P.layer_from(full, dp.layer_mask(F, layer), edge=3.0)
    out = out or os.path.join(r"E:\tmp\doll_ingame\dd\layers", os.path.splitext(os.path.basename(src))[0], layer.lower() + ".png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    lay.save(out)
    return out


if __name__ == "__main__":
    print(cut(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None))
