"""Кожа 16 внешностей LAMIA по классике: средний Lab освещённого торса (строки 72..95, без головы), группы по близости."""
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"E:\OpenXCom\tools\hdart")
import cv2
import numpy as np
import doll_b2_render as db
F, PAL = db.sprite_files(), db.game_palette()
LOOKS = ["F%d" % i for i in range(8)] + ["M%d" % i for i in range(8)]
res = {}
for k in LOOKS:
    rgba = db.to_rgba(db.load_indices(F["LAMIA__2__%s_NUDE" % k]), PAL).astype(np.uint8)
    reg = np.zeros((db.H, db.W), bool)
    reg[72:96, 60:110] = True
    m = reg & (rgba[..., 3] > 0)
    lab = cv2.cvtColor(np.ascontiguousarray(rgba[..., :3]), cv2.COLOR_RGB2LAB).astype(np.float32)
    L = lab[..., 0]
    m &= L > np.percentile(L[m], 40)
    res[k] = lab[m].mean(0)
    print(k, "L a b", [int(v) for v in res[k]], "rgb", [int(v) for v in rgba[..., :3][m].mean(0)])
groups = []
for k in LOOKS:
    for g in groups:
        if np.linalg.norm(res[k] - res[g[0]]) < 12:
            g.append(k)
            break
    else:
        groups.append([k])
print("групп", len(groups), groups)
