"""LAMIA: нарезка 19 вещей из правок arm_<ключ>_<сид>.png. Аргументы: <ключ>=<сид> (выбранный сид каждой правки).
Плащ сзади: из BRONZE, точки, видимые только в гоплите, - из HOPLITE. Проверка покрытия: доля видимых точек маски вещи,
где в HD осталась кукла без вещи (цвет как у full_F0, dE < 12 на k=1) - вещь там не нарисована.
Выход E:/tmp/doll_ingame/lm/layers/<слой>.png."""
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
import wall_section as ws

D = r"E:\tmp\doll_ingame\lm"
CROP = (42, 40, 134, 146)
K = 4
SRC = {"BOSS": "BOSS", "BOSSGOG": "BOSS", "HOPL_CAPE_BACK": "BRONZE", "HORR_VAMBR": "BRONZE", "ROYAL_ARMOR": "BRONZE",
       "SHILD_A1": "NUDE_S", "CHAINM": "CHAIN_MAIL", "GREAT_SHIELD": "CHAIN_MAIL_A", "SCALE": "SCALE_MAIL",
       "CHITIN_SHIELD": "SCALE_MAIL_A", "HOPL_CAPE_FRONT": "HOPLITE", "BARD_SKIRT": "HOPLITE", "HOPL_ARMR": "HOPLITE",
       "HELM_HOPL": "HOPLITE", "SHILD_HOPL": "HOPLITE", "BCKPCK": "STRAPS", "LSTRAPS": "STRAPS", "HSUIT": "TAC_SUIT",
       "HSUIT_HELM": "TAC_SUIT"}
F = db.sprite_files()
A = db.armor_layers()


def full_of(img_path):
    x0, y0, x1, y1 = (v * K for v in CROP)
    full = np.empty((db.H * K, db.W * K, 3), np.float32)
    full[:] = dp.PANEL
    full[y0:y1, x0:x1] = np.asarray(Image.open(img_path).convert("RGB").resize((x1 - x0, y1 - y0), Image.LANCZOS), np.float32)
    return full


def visible(name, arm):
    names = [n for n in A["STR_LAMIA_%s_UC" % arm]["F0"] if n in F] if "F0" in A["STR_LAMIA_%s_UC" % arm] else None
    if names is None:
        key = next(k for k in A["STR_LAMIA_%s_UC" % arm] if "F0" in k.upper())
        names = [n for n in A["STR_LAMIA_%s_UC" % arm][key] if n in F]
    i = names.index(name)
    above = np.zeros((db.H, db.W), bool)
    for h in names[i + 1:]:
        above |= dp.layer_mask(F, h)
    return dp.layer_mask(F, name) & ~above


def orange(lab):
    """Насыщенный оранжевый кожи F0: оттенок 45..80 градусов, насыщенность > 32, светлота > 90 (Lab OpenCV)."""
    a, b = lab[..., 1] - 128, lab[..., 2] - 128
    h = np.degrees(np.arctan2(b, a))
    return (h > 45) & (h < 80) & (np.hypot(a, b) > 32) & (lab[..., 0] > 90)


def warm(lab):
    """Тёплый тон (кожа, её тени, бронза): оттенок 20..95 градусов, насыщенность > 8 (Lab OpenCV)."""
    a, b = lab[..., 1] - 128, lab[..., 2] - 128
    h = np.degrees(np.arctan2(b, a))
    return (h > 20) & (h < 95) & (np.hypot(a, b) > 8)


def k1(rgb4):
    return cv2.resize(rgb4, (db.W, db.H), interpolation=cv2.INTER_AREA)


seeds = dict(a.split("=") for a in sys.argv[1:] if "=" in a)
# <ключ>=<сид>@new - правка нарисована на F0 круга 2 (layers/full_F0.png): основа сравнения - она, лицо не трогается
NEWK = {k for k, s in seeds.items() if s.endswith("@new")}
seeds = {k: s.split("@")[0] for k, s in seeds.items()}
PAL = db.game_palette()
base4f = full_of(os.path.join(D, "full_F0_items_base.png"))   # основа, на которой рисовались правки вещей (круг 1)
base4 = cv2.cvtColor(np.clip(cv2.GaussianBlur(base4f, (0, 0), 2.0), 0, 255).astype(np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)
hz1 = np.zeros((db.H, db.W), bool)
for n in F:
    if n.startswith("LAMIA__10__") or n.startswith("LAMIA__13__"):
        hz1 |= dp.layer_mask(F, n)
headzone = np.clip(ws.sil4(cv2.dilate(hz1.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0), 0, 1).astype(np.float32)
base1 = k1(base4f)
# цвет кожи лица F0 на основе правок: средний Lab точек зоны головы, где основа насыщенно-оранжевая
_face = (headzone > 0.5) & orange(base4) & (ws.sil4(dp.layer_mask(F, "LAMIA__2__F0_NUDE")) > 0.5)
SKIN0 = base4[_face].mean(0)
print("кожа лица F0 Lab", SKIN0.round(1), "точек", int(_face.sum()))
_fc = cv2.morphologyEx(_face.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((11, 11), np.uint8))  # кожа + глаза и рот
FACE0 = cv2.GaussianBlur(cv2.erode(_fc, np.ones((3, 3), np.uint8)).astype(np.float32), (0, 0), 1.5)
FACE0_1 = cv2.resize(FACE0, (db.W, db.H), interpolation=cv2.INTER_AREA) > 0.5      # место лица F0 на k=1
NEW0 = full_of(os.path.join(D, "layers", "full_F0.png"))                               # F0 круга 2 (по педии)
base4n = cv2.cvtColor(np.clip(cv2.GaussianBlur(NEW0, (0, 0), 2.0), 0, 255).astype(np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)
fig = np.zeros((db.H, db.W), bool)
for n in F:
    if n.startswith("LAMIA__"):
        fig |= dp.layer_mask(F, n)
figure1 = cv2.dilate(fig.astype(np.uint8), np.ones((7, 7), np.uint8))
body4 = cv2.erode(ws.sil4(dp.layer_mask(F, "LAMIA__2__F0_NUDE")).astype(np.float32), np.ones((5, 5), np.uint8))
blab = cv2.cvtColor(np.clip(base1, 0, 255).astype(np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)
fulls = {}
for key, s in seeds.items():
    fulls[key] = full_of(os.path.join(D, "images", "arm_%s_%s.png" % (key, s)))
out = os.path.join(D, "layers")
for it, key in SRC.items():
    if key not in fulls:
        continue
    name = next(n for n in F if n.startswith("LAMIA__") and n.split("__")[2] == it)
    full = fulls[key].copy()
    if it == "HOPL_CAPE_BACK" and "HOPLITE" in fulls:
        only = visible(name, "HOPLITE") & ~visible(name, "BRONZE")
        m4 = cv2.resize(only.astype(np.uint8), (db.W * K, db.H * K), interpolation=cv2.INTER_NEAREST).astype(bool)
        full[m4] = fulls["HOPLITE"][m4]
    lay = np.asarray(P.layer_from(full, dp.layer_mask(F, name), edge=3.0).convert("RGBA")).copy()
    # где правка не изменила куклу F0 (подложка, кожа и волосы F0) - вещи нет: прозрачно, видно тело своей внешности;
    # в зоне головы и волос (все внешности) - цвет классики (капюшон под шлемом закрывает волосы, как в классике)
    d = cv2.cvtColor(np.clip(cv2.GaussianBlur(full, (0, 0), 2.0), 0, 255).astype(np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)
    dE = np.sqrt(((d - (base4n if key in NEWK else base4)) ** 2).sum(-1))
    w = np.clip((dE - 7.0) / 8.0, 0, 1)
    # вне силуэта тела F0: точки цвета фона правки (FLUX стёр волосы F0 и нарисовал подложку) - тоже не вещь
    small = cv2.resize(full, (db.W, db.H), interpolation=cv2.INTER_AREA)
    bg = cv2.inpaint(np.clip(small, 0, 255).astype(np.uint8), figure1, 6, cv2.INPAINT_TELEA)
    bg = cv2.GaussianBlur(cv2.resize(bg, (db.W * K, db.H * K), interpolation=cv2.INTER_LINEAR).astype(np.float32), (0, 0), 3.0)
    bl = cv2.cvtColor(np.clip(bg, 0, 255).astype(np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)
    wp = np.clip((np.sqrt(((d - bl) ** 2).sum(-1)) - 10.0) / 6.0, 0, 1)
    wp = cv2.erode(wp.astype(np.float32), np.ones((3, 3), np.uint8))        # светлая кайма FLUX по контуру вещи
    w = np.where(body4 > 0.5, w, w * wp)
    # кожа и чешуя F0 (насыщенный оранжевый), если в классике вещи оранжевого нет (бронза и золото не трогаются)
    clab = cv2.cvtColor(np.ascontiguousarray(db.to_rgba(db.load_indices(F[name]), PAL)[..., :3].astype(np.uint8)),
                        cv2.COLOR_RGB2LAB).astype(np.float32)
    cm = dp.layer_mask(F, name)
    if orange(clab)[cm].mean() < 0.05:
        wo = cv2.GaussianBlur(orange(d).astype(np.float32), (0, 0), 1.5)
        w = w * (1 - wo)
    a0 = lay[..., 3].astype(np.float32)
    # кожа лица F0 круга 1 в слое вещи (только на месте лица F0, не на волосах): доля - близость к цвету кожи
    # (dE < 14 полностью, > 24 нет). Шлем с прорезью (в классике лицо видно своё) - залить цветом классики шлема;
    # глухой шлем (лицо в классике одно на все внешности) - лицо новой F0 круга 2 со змеиными глазами
    sk = np.maximum(np.clip((24.0 - np.sqrt(((d - SKIN0) ** 2).sum(-1))) / 10.0, 0, 1),
                    np.clip((30.0 - dE) / 10.0, 0, 1))          # или почти то же, что основа F0 в этой точке (глаза, тени)
    sk = cv2.GaussianBlur(sk.astype(np.float32), (0, 0), 1.5) * FACE0 * (key not in NEWK)
    hzone = headzone
    if sk.max() > 0.5:
        hole = (FACE0_1 & ~cm).sum()
        if hole >= 20:          # бронзовый шлем ROYAL_ARMOR: 5 точек по краю - глухой
            # ещё тёплый тон кожи (и тени кожи) там, где у классики шлем холодного цвета (зелёный, серый, чёрный)
            cl4 = cv2.resize(clab, (db.W * K, db.H * K), interpolation=cv2.INTER_NEAREST)
            wr = cv2.GaussianBlur((warm(d) & ~warm(cl4)).astype(np.float32), (0, 0), 1.5) * FACE0
            sk = np.maximum(sk, wr)
            w = w * (1 - sk)
            print("    прорезь %d точек: кожа F0 залита цветом шлема" % hole)
        else:
            lay[..., :3] = np.clip(lay[..., :3] * (1 - sk[..., None]) + NEW0 * sk[..., None], 0, 255).astype(np.uint8)
            print("    глухой шлем: лицо новой F0")
    if (hzone * (a0 > 0) * (w < 0.5)).any():
        cl = np.asarray(ws.xbrz(Image.fromarray(db.to_rgba(db.load_indices(F[name]), PAL).astype(np.uint8), "RGBA"), K)
                        .convert("RGBA"), np.float32)
        cl = cv2.GaussianBlur(cl[..., :3], (0, 0), 2.0)
        mix = ((1 - w) * hzone)[..., None]
        lay[..., :3] = np.clip(lay[..., :3] * (1 - mix) + cl * mix, 0, 255).astype(np.uint8)
    lay[..., 3] = np.clip(a0 * np.maximum(w, hzone), 0, 255).astype(np.uint8)
    Image.fromarray(lay, "RGBA").save(os.path.join(out, name.lower() + ".png"))
    m = dp.layer_mask(F, name).sum() * K * K
    print("    залито у головы %.0f%%, снято %.0f%% маски" % (100.0 * ((1 - w) * headzone * (a0 > 0)).sum() / m,
                                                          100.0 * ((1 - np.maximum(w, headzone)) * (a0 > 0)).sum() / m))
    vis = visible(name, key)
    lab = cv2.cvtColor(np.clip(k1(full), 0, 255).astype(np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)
    same = np.sqrt(((lab - blab) ** 2).sum(-1)) < 12
    print("%-16s из %-12s видно %5d  без вещи %4.0f%%" % (it, key + "_" + seeds[key], int(vis.sum()),
                                                        100.0 * (same & vis).sum() / max(1, vis.sum())))
