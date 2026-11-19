"""LAMIA: сборка внешности и нарезка слоёв. Аргументы: <внешность>=<сид головы> через пробел, [--out каталог].
Кадр (рамка x8, 736x848) = основа группы кожи, сверху до плеч - правка головы этой внешности (плавный шов по y).
Кожа (лицо, руки, торс, бока хвоста) сдвигается в Lab к коже классики этой внешности; волосы (маска HAIR),
светлые пластины брюха и чёрные круги не трогаются. Слои: LAMIA__2__<в>_NUDE, LAMIA__10__HEAD_<в>, LAMIA__13__HAIR_<в>.
Выход: <out>/<слой в нижнем регистре>.png (по умолчанию E:/tmp/doll_ingame/lm/layers) и кадр full_<в>.png там же."""
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

D = r"E:\tmp\doll_ingame\lm"
CROP = (42, 40, 134, 146)
Z, K = 8, 4
GROUP = {"orange": ("body_1", "F0 M0 M1 M4 M5"), "green": ("skin_green_body_1_2", "F1 F5"),
         "pink": ("skin_pink_body_1_2", "F2 F4"), "beige": ("skin_beige_body_1_2", "F3 M7"),
         "brown": ("skin_brown_body_1_1", "F6 F7 M2 M3 M6")}
BASE = {lk: b for b, ls in GROUP.values() for lk in ls.split()}
SEAM = (236, 276)                       # шов головы и тела в кадре x8 (подбородок классики y~69 -> 232)
F, PAL = db.sprite_files(), db.game_palette()


def m8(name):
    """Маска слоя классики в кадре x8 (рамка CROP), мягкая 0..1."""
    m = dp.layer_mask(F, name)[CROP[1]:CROP[3], CROP[0]:CROP[2]].astype(np.uint8) * 255
    return cv2.resize(m, ((CROP[2] - CROP[0]) * Z, (CROP[3] - CROP[1]) * Z), interpolation=cv2.INTER_LINEAR) / 255.0


def skin_target(lk):
    rgba = db.to_rgba(db.load_indices(F["LAMIA__2__%s_NUDE" % lk]), PAL).astype(np.uint8)
    reg = np.zeros((db.H, db.W), bool)
    reg[72:96, 60:110] = True
    m = reg & (rgba[..., 3] > 0)
    lab = cv2.cvtColor(np.ascontiguousarray(rgba[..., :3]), cv2.COLOR_RGB2LAB).astype(np.float32)
    m &= lab[..., 0] > np.percentile(lab[..., 0][m], 40)
    return lab[m].mean(0)


def build(lk, seed, out):
    base = np.asarray(Image.open(os.path.join(D, "images", BASE[lk] + ".png")).convert("RGB"), np.float32)
    head = np.asarray(Image.open(os.path.join(D, "images", "head_%s_%s_%d.png" % (lk, BASE[lk], seed))).convert("RGB")
                      .resize((base.shape[1], base.shape[0]), Image.LANCZOS), np.float32)
    y = np.arange(base.shape[0], dtype=np.float32)[:, None, None]
    w = np.clip((SEAM[1] - y) / (SEAM[1] - SEAM[0]), 0, 1)
    img = head * w + base * (1 - w)
    # кожа к классике
    lab = cv2.cvtColor(np.clip(img, 0, 255).astype(np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)
    body, hair = m8("LAMIA__2__%s_NUDE" % lk), m8("LAMIA__13__HAIR_%s" % lk)
    reg = np.zeros(body.shape, bool)
    reg[(72 - CROP[1]) * Z:(96 - CROP[1]) * Z, (60 - CROP[0]) * Z:(110 - CROP[0]) * Z] = True
    reg &= body > 0.5
    L = lab[..., 0]
    reg &= (L > np.percentile(L[reg], 40)) & (L > 60)
    cur = lab[reg].mean(0)
    tgt = skin_target(lk)
    chroma = np.hypot(lab[..., 1] - 128, lab[..., 2] - 128)
    near = np.hypot(lab[..., 1] - cur[1], lab[..., 2] - cur[2])
    skin = (body > 0.5) & (hair < 0.5) & (chroma > 10) & (near < 26) & (L > 25)
    wk = cv2.GaussianBlur(skin.astype(np.float32), (0, 0), 2.0)
    lab[..., 1] += wk * (tgt[1] - cur[1]) * 0.9
    lab[..., 2] += wk * (tgt[2] - cur[2]) * 0.9
    lab[..., 0] += wk * (tgt[0] - cur[0]) * 0.5
    img = cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)
    print(lk, "кожа HD Lab", [int(v) for v in cur], "классика", [int(v) for v in tgt], "точек кожи", int(skin.sum()))
    os.makedirs(out, exist_ok=True)
    Image.fromarray(img).save(os.path.join(out, "full_%s.png" % lk))
    x0, y0, x1, y1 = (v * K for v in CROP)
    full = np.empty((db.H * K, db.W * K, 3), np.float32)
    full[:] = dp.PANEL
    full[y0:y1, x0:x1] = np.asarray(Image.fromarray(img).resize((x1 - x0, y1 - y0), Image.LANCZOS), np.float32)
    for name in ("LAMIA__2__%s_NUDE" % lk, "LAMIA__10__HEAD_%s" % lk, "LAMIA__13__HAIR_%s" % lk):
        P.layer_from(full, dp.layer_mask(F, name), edge=3.0).save(os.path.join(out, name.lower() + ".png"))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if "=" in a]
    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else os.path.join(D, "layers")
    for a in args:
        lk, s = a.split("=")
        build(lk, int(s), out)
