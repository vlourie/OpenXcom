"""DEMONESS: круг наклейки слоем DEMONESS__3__PASTIES, один на светлую и тёмную внешность варианта.
Центры - по чёрным кружкам, которые FLUX нарисовал мелко (сетка dd_grid.py, база 320x200). За контур тела не выходит."""
import os
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"E:\OpenXCom\tools\hdart")
import numpy as np
from PIL import Image
import doll_ubergal_pasties as U

L = r"E:\tmp\doll_ingame\dd\layers"
R = 1.45                                            # радиус в точках базы; у SYN 1.25, грудь здесь крупнее
VAR = {"a": ("dem_light_1", "dem_dark_dem_light_1_2", [(55.8, 58.6), (77.1, 61.6)]),
       "b": ("dem_light_3", "dem_dark_dem_light_3_1", [(57.1, 58.5), (77.5, 60.8)])}
for v, (light, dark, spots) in VAR.items():
    al = np.asarray(Image.open(os.path.join(L, light, "demoness__2__light_nude.png")))[..., 3].astype(np.float32)
    ad = np.asarray(Image.open(os.path.join(L, dark, "demoness__2__dark_nude.png")))[..., 3].astype(np.float32)
    px = U.circles([(x * 4, y * 4) for x, y in spots], R * 4).astype(np.float32)
    px[..., 3] *= np.minimum(al, ad) / 255.0
    out = os.path.join(L, "pasties_" + v, "demoness__3__pasties.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    Image.fromarray(np.clip(px + 0.5, 0, 255).astype(np.uint8), "RGBA").save(out)
    print(out)
