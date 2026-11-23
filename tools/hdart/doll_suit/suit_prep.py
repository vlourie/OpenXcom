"""Костюмы одной картинкой (09.11): классика RGBA палитрой игры, входы FLUX.3 Klein x8 (xBRZ x4 + LANCZOS на подложке
куклы), classic8 крупно, crops.json. Рамка - по кускам больше 6 точек (одиночные лишние точки у MAN_208, MAN_675 не в счёт).
Вход: suit_singles.json (образ -> файл в моде). Выход E:/tmp/doll_ingame/suit/."""
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
import wall_section as ws

OUT = r"E:\tmp\doll_ingame\suit"
S = json.load(open(os.path.join(OUT, "suit_singles.json"), encoding="utf-8"))
PAL = db.game_palette()
Z = 8
if __name__ == "__main__":
    crops = {}
    for name, v in S.items():
        src = Image.open(os.path.join(db.MOD, v["file"]))
        if getattr(src, "n_frames", 1) > 1:
            src.seek(0)
        rgba = db.to_rgba(np.asarray(src.convert("P") if src.mode != "P" else src), PAL)
        Image.fromarray(rgba).save(os.path.join(OUT, "classic_%s.png" % name))
        m = (rgba[..., 3] > 0).astype(np.uint8)
        n, lab, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
        big = np.isin(lab, [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] > 6])
        ys, xs = np.nonzero(big)
        x0, y0, x1, y1 = max(0, xs.min() - 4), max(0, ys.min() - 4), min(320, xs.max() + 5), min(200, ys.max() + 5)
        if (x1 - x0) % 2:
            x1 += 1
        if (y1 - y0) % 2:
            y1 += 1
        crops[name] = (int(x0), int(y0), int(x1), int(y1))
        p = Image.fromarray(rgba).crop(crops[name])
        up = ws.xbrz(p, 4).resize((p.width * Z, p.height * Z), Image.LANCZOS)
        bg = Image.new("RGBA", up.size, dp.PANEL + (255,))
        bg.alpha_composite(up)
        bg.convert("RGB").save(os.path.join(OUT, "init_%s.png" % name))
        cl = Image.new("RGBA", p.size, dp.PANEL + (255,))
        cl.alpha_composite(p)
        cl.resize(up.size, Image.NEAREST).convert("RGB").save(os.path.join(OUT, "classic8_%s.png" % name))
        print(name, crops[name], up.size, "вне рамки точек", int(m.sum() - big.sum()))
    json.dump(crops, open(os.path.join(OUT, "crops.json"), "w", encoding="utf-8"), indent=1)
