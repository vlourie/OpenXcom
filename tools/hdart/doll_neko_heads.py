"""Головы NEKOMIMI: кадр на внешность (doll_race_heads.py), он же кладётся на тела обеих поз; волосы слоя 15 вырезаны из него же.
Описания doll_looks_nekomimi.json, необязательные поля: skin - кожа словами вместо замера, neg - что запретить. Лицо взрослое (R-693).
Выход art/doll/pipe_pilot/nekomimi/heads/, layers/ под настоящими именами слоёв. В мод не ставит.

  py -3.13 tools/gpuq.py add --name doll_neko_heads -- E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe E:/OpenXCom/tools/hdart/doll_neko_heads.py [--looks F0,M5] [--dry-run]
"""
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import doll_neko_bodies as M                        # до numpy: пилот ставит окружение модели
import build_pack as bp
import cv2
import doll_neko_classic as NC
import doll_race_heads as H
import numpy as np
from PIL import Image

P = M.P
HAIR_FROM, HAIR_SOFT = 14, 12                       # расстояние цвета от кожи щёк: дальше - прядь
OLD_FACE = ("A pretty young woman's face with smooth unlined skin and soft feminine features: clear eyes with irises and highlights, "
            "neat brows, a small nose, soft lips.")
NEW_FACE = ("A grown woman's face with defined adult features and smooth skin: clear eyes with irises and highlights, neat brows, "
            "a straight nose, soft lips. The cat ears are covered in short fur and stay exactly where the input has them; she has no human ears.")
NO_EXTRA = ", human ears, text, letters, smile, grin, open mouth, teeth, big eyes, anime eyes"
SKIN_L, SKIN_LIT, LIT_PCT = 8, 12, 65               # как у MHUMAN: лицо только светлеет, иначе лицо темнее тела (R-790)
neck_text = P.neck_text
base_setup = H.setup
base_passport = P.passport
base_skin_match = P.skin_match
base_negative = P.negative_for
base_compose = H.compose


def passport(files, pal, look):
    """Случайные слова лица звали круглое лицо и курносый нос, глаза у кошек свои."""
    pz = base_passport(files, pal, look)
    d = P.LOOKS[look]
    rnd = random.Random("face:" + NC.RACE + look)
    pz["face"] = ", ".join((rnd.choice(["an oval face", "a heart-shaped face", "a face with high cheekbones"]), d["eyes"], "a calm confident look"))
    pz["skin"] = d.get("skin", pz["skin"])
    pz["neg"] = d.get("neg", "")
    return pz


def negative_for(pz):
    return base_negative(pz) + NO_EXTRA + (", " + pz["neg"] if pz["neg"] else "")


def lit_gap(rgb, look, region, sample):
    dp = P.dp
    cov1 = P.skin_cover(look) & region
    cov = P.ws.sil4(cov1 if sample is None else cov1 & sample) > 0.5
    cov = cv2.erode(cov.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=2) > 0
    names = [n for n in ("%s__%d__%s_NUDE" % (dp.RACE, dp.BODY, look), "%s__%d__HEAD_%s" % (dp.RACE, dp.HEAD, look)) if n in P.FILES]
    cl = np.asarray(dp.classic(P.FILES, P.PAL, names).resize((P.db.W * dp.K, P.db.H * dp.K), P.Image.NEAREST).convert("RGB"), np.float32)
    Lc = cv2.GaussianBlur(bp._rgb_to_lab(cl / 255.0)[..., 0], (0, 0), dp.K)
    Ld = bp._rgb_to_lab(rgb / 255.0)[..., 0]
    sel = cov & (Ld > 22)
    if sel.sum() < 100:
        return 0.0
    return np.percentile(Lc[cov], LIT_PCT) - np.percentile(Ld[sel], LIT_PCT)


def skin_match(rgb, look, region, sample=None, near=None):
    if near is None:
        return base_skin_match(rgb, look, region, sample)
    _o, d = base_skin_match(rgb, look, region, sample)
    if d is None:
        return base_skin_match(rgb, look, region, sample, near)
    lift = float(np.clip(lit_gap(rgb, look, region, sample), 0, SKIN_LIT))
    return base_skin_match(rgb, look, region, sample, (SKIN_L + lift, near[1], near[2]))


def hair_zone(look, box):
    """Голова, волосы и шея: пятна на теле (полосы, когти, бельё) кадру головы не нужны."""
    bm, hm, _i, _r = H.classic_parts(look)
    x0, _y0, x1, y1 = H.FACE_BOX
    zone = hm.copy()
    zone[:y1 + 3, x0 - 2:x1 + 4] |= bm[:y1 + 3, x0 - 2:x1 + 4]
    keep = np.zeros_like(zone)
    keep[box[1]:box[3], box[0]:box[2]] = True
    return zone & keep


def skin_part(lay):
    """Доля кожи кадра по цвету щёк, ниже шеи: 1 - кожа, 0 - прядь."""
    k = P.dp.K
    x0, y0, x1, y1 = H.FACE_BOX
    lab = bp._rgb_to_lab(lay[..., :3] / 255.0)
    d = lab - np.median(lab[(y0 + 4) * k:(y1 + 1) * k, x0 * k:(x1 + 1) * k].reshape(-1, 3), axis=0)
    hairish = np.clip((np.sqrt((d[..., 0] * 0.5) ** 2 + d[..., 1] ** 2 + d[..., 2] ** 2) - HAIR_FROM) / HAIR_SOFT, 0, 1).astype(np.float32)
    ramp = np.clip((np.arange(lay.shape[0], dtype=np.float32) - NC.NECK_ROW * k) / (2 * k), 0, 1)[:, None]
    return (1 - cv2.GaussianBlur(hairish, (0, 0), 1.5)) * ramp


def strands_only(body, hair, look):
    """Ниже шеи от кадра головы нужны только пряди: его кожа лежала на теле окном с прямым краем зоны (F18, M14)."""
    lay = np.asarray(body, np.float32).copy()
    base = np.asarray(Image.open(os.path.join(H.BODIES, look.lower() + ".png")).convert("RGBA"), np.float32)
    t = skin_part(lay) * (base[..., 3] > 128)
    lay[..., :3] += (base[..., :3] - lay[..., :3]) * t[..., None]
    out = Image.fromarray(np.clip(lay + 0.5, 0, 255).astype(np.uint8), "RGBA")
    if hair is None:
        return out, None
    h = np.asarray(hair, np.float32).copy()
    h[..., 3] *= 1 - skin_part(h)                   # слой 15 лежит поверх брони: кожа кадра в нём легла бы на одежду
    return out, Image.fromarray(np.clip(h + 0.5, 0, 255).astype(np.uint8), "RGBA")


def compose(j, rgb):
    """Тот же кадр на тело второй позы: голова и шея у них совпадают точка в точку (мерка 07.11)."""
    body, _head, hair, info = base_compose(j, rgb)
    body, hair = strands_only(body, hair, j["look"])
    look = "A" + j["look"]
    alt = dict(j, look=look, names=[n.replace("__%s_NUDE" % j["look"], "__%s_NUDE" % look) for n in j["names"]])
    body2, _h, _r, _i = base_compose(alt, rgb)
    body2, _r = strands_only(body2, None, look)
    body2.save(os.path.join(H.HEADS, "layers", NC.real_body(look).lower() + ".png"))
    return body, None, hair, info


def setup(looks_file):
    base_setup(looks_file)
    M.setup()
    P.neck_text = neck_text
    assert OLD_FACE in P.HEAD
    P.HEAD = P.HEAD.replace(OLD_FACE, NEW_FACE).replace("an X-COM-style strategy game", "a strategy game")   # R-781
    assert "X-COM" not in P.HEAD
    P.passport = passport
    P.negative_for = negative_for
    P.skin_match = skin_match
    P.hair_zone = hair_zone


H.RACE = NC.RACE
H.OUT = NC.OUT
H.BODIES = os.path.join(H.OUT, "assembled")
H.HEADS = os.path.join(H.OUT, "heads")
H.FACE_BOX = NC.FACE_BOX
H.NECK_ROW = NC.NECK_ROW
H.SHEET_CLOSE = (58, 38, 106, 90)
H.SHEET_FULL = (56, 38, 106, 148)
H.saved_names = lambda look: [NC.real_body(look), "", NC.real_hair(look)]
H.compose = compose
H.setup = setup

if __name__ == "__main__":
    H.main()
