"""WALL_RESTORE_V1: стены увеличением самого кадра, без генерации (решение специалиста 08.10).

WALL_RENDER_V1 и V2 закрыты: модель внутри стены выдумывает окна, крышки, стёкла, и годность зависит от сида.
Здесь кадр не перерисовывается, а увеличивается x4 так, что геометрия остаётся пиксель в пиксель:

  * альфа и силуэт - ВСЕГДА из маски оригинала (wall_section.sil4_frame, у сквозных - wall_thru.sil4_frame_open:
    проём - ровно проём оригинала). Ни увеличитель, ни модель прозрачность не решают;
  * цвет - из кадра оригинала, края которого продолжены наружу (sprite_scale.fill_outside), чтобы перо альфы
    не тянуло чёрное;
  * одинаковые кадры классики (в любых наборах) - один кадр-канон, зеркальные - переворот канона.

Способы (колонки листа):
  A   xbrz     xBRZ x4 - чистое детерминированное увеличение (то же, чем игра сглаживает без пака);
  B1  sharp    A плюс управляемая резкость: поправка яркости (y - blur) в пределах +-25 %, только внутри силуэта;
  B2  esrgan   A плюс мелкая фактура Real-ESRGAN x4plus поправкой яркости (как upscale_units --method detail);
  B3  anime    цвет Real-ESRGAN x4plus anime_6B целиком, альфа - маска оригинала.
B2 и B3 грузят модель на видеокарту - только через очередь; --no-model даёт A и B1 без модели.

  wall_restore.py --cases <cases.json> --out census/walls/restore [--no-model]

cases.json: [{"id": "B01_VILBAN56", "thru": false, "targets": [["VILBAN", 0], ...]}, ...]
Выход: <out>/<случай>/<способ>/series/<НАБОР>.PCK/<кадр>.png (128x160) и <out>/<случай>/report.json.
В мод ничего не кладётся.
"""
import argparse
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                                  # noqa: E402
import cv2                                          # noqa: E402
from PIL import Image                               # noqa: E402
import map_mockup as mm                             # noqa: E402
import sprite_scale as ss                           # noqa: E402
import wall_section as ws                           # noqa: E402
import wall_thru as wt                              # noqa: E402

ENC = "utf-8-sig"
ROOT = os.path.dirname(os.path.dirname(HERE))
K = 4
MODELS = {"esrgan": "E:/models/RealESRGAN_x4plus.pth", "anime": "E:/models/RealESRGAN_x4plus_anime_6B.pth"}
SHARP = (0.8, 0.25)       # B1: сила, предел поправки яркости
DETAIL = (0.6, 0.30)      # B2: сила, предел (как upscale_units по умолчанию у юнитов)
PAD = 4                   # поле вокруг кадра для увеличителя, пикселей базы
METHODS_CPU = ("xbrz", "sharp")
METHODS_GPU = ("esrgan", "anime")


def filled(frame):
    """RGB кадра k=1, продолженный наружу силуэта, с полем PAD (float, (h+2P, w+2P, 3)) и маска k=1."""
    a = np.asarray(frame, np.float32)
    mask = a[..., 3] > 0
    rgb = np.pad(a[..., :3], ((PAD, PAD), (PAD, PAD), (0, 0)))
    pm = np.pad(mask, PAD)
    return ss.fill_outside(rgb[None], pm[None])[0], mask


def alpha_of(mask, thru):
    s = wt.sil4_frame_open(mask) if thru else ws.sil4_frame(mask)
    return np.clip(s * 255.0, 0, 255)


def xbrz_rgb(src):
    """xBRZ x4 непрозрачного продолженного кадра, поле срезано: (h*4, w*4, 3) float."""
    rgba = np.concatenate([src, np.full(src.shape[:2] + (1,), 255.0, np.float32)], -1)[None]
    up = ss.xbrz_scale(rgba, K)[0][..., :3]
    return up[PAD * K:-PAD * K, PAD * K:-PAD * K]


def model_rgb(up, src):
    """Картинка модели x4 продолженного кадра, поле срезано: (h*4, w*4, 3) float."""
    out = up.run(np.clip(src + 0.5, 0, 255).astype(np.uint8)[None])[0].astype(np.float32)
    if out.shape[0] != src.shape[0] * K:
        out = np.asarray(Image.fromarray(out.astype(np.uint8)).resize((src.shape[1] * K, src.shape[0] * K),
                                                                      Image.LANCZOS), np.float32)
    return out[PAD * K:-PAD * K, PAD * K:-PAD * K]


def detail(base, ref, strength, limit, alpha):
    """Поправка яркости по мелкой фактуре ref (ss.add_detail), только внутри силуэта: альфа не трогается."""
    b4 = np.concatenate([base, alpha[..., None]], -1)[None]
    out = ss.add_detail(b4, ref[None], strength, limit, K)[0][..., :3]
    inside = (alpha > 0)[..., None]
    return np.where(inside, out, base)


def make(frame, thru, ups):
    src, mask = filled(frame)
    alpha = alpha_of(mask, thru)
    base = xbrz_rgb(src)
    res = {"xbrz": base, "sharp": detail(base, base, SHARP[0], SHARP[1], alpha)}
    if ups:
        res["esrgan"] = detail(base, model_rgb(ups["esrgan"], src), DETAIL[0], DETAIL[1], alpha)
        res["anime"] = model_rgb(ups["anime"], src)
    return {m: Image.fromarray(np.clip(np.dstack([rgb, alpha]) + 0.5, 0, 255).astype(np.uint8), "RGBA")
            for m, rgb in res.items()}, mask


def metrics(hd, frame, mask):
    """Против оригинала k=1: альфа (пикселей базы не совпало), строение (ws.struct_fid), сдвиг (фазовая
    корреляция яркости), наибольшее отклонение цвета уменьшенного кадра внутри силуэта."""
    a = np.asarray(hd, np.float32)
    cov = a[..., 3].reshape(40, 4, 32, 4).mean((1, 3)) / 255.0
    alpha_miss = int(((cov > 0.5) != mask).sum())
    # перо наружу на вертикалях (R-289) даёт соседнему пустому пикселю базы покрытие до 0.5 - не геометрия
    feather = int(((cov > 0.05) & ~mask).sum())
    c, e, dc = ws.struct_fid(hd, frame)
    al = a[..., 3:4] / 255.0
    small = (a[..., :3] * al).reshape(40, 4, 32, 4, 3).mean((1, 3)) / np.maximum(al.reshape(40, 4, 32, 4, 1).mean((1, 3)), 1e-3)
    o = np.asarray(frame, np.float32)[..., :3]
    dev = np.abs(small - o).max(-1)
    l1 = np.where(mask, ws.lum(small), 0).astype(np.float32)
    l2 = np.where(mask, ws.lum(o), 0).astype(np.float32)
    (dx, dy), _r = cv2.phaseCorrelate(l2, l1) if mask.sum() >= 12 else ((0.0, 0.0), 0)
    r2 = lambda v: None if v is None else round(v, 3)
    return dict(alpha_miss=alpha_miss, feather=feather, lum_corr=r2(c), edge_corr=r2(e), color_diff=r2(dc),
                max_dev=round(float(dev[mask].max()) if mask.any() else 0.0, 1),
                shift=[round(float(dx), 2), round(float(dy), 2)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    ap.add_argument("--out", default="census/walls/restore")
    ap.add_argument("--no-model", action="store_true", help="только A и B1, модель не грузится")
    a = ap.parse_args()
    os.chdir(ROOT)
    cases = json.load(open(a.cases, encoding=ENC))
    ups = {}
    if not a.no_model:
        import upscale_units as uu
        ups = {m: uu.Upscaler(p) for m, p in MODELS.items()}
    methods = METHODS_CPU + (METHODS_GPU if ups else ())
    world = mm.World()
    canon = {}                       # (хэш RGBA, thru) -> (набор, кадр, картинки)
    stat = dict(frames=0, canon=0, copy=0, mirror=0)
    for case in cases:
        d = os.path.join(a.out, case["id"])
        rep = {"id": case["id"], "thru": bool(case.get("thru")), "methods": list(methods), "frames": {}}
        for s, n in case["targets"]:
            frame = world.sprite(s, n, None)
            if frame is None:
                rep["frames"]["%s:%d" % (s, n)] = {"error": "нет кадра"}
                continue
            stat["frames"] += 1
            arr = np.asarray(frame)
            thru = bool(case.get("thru"))
            h = (hashlib.sha1(arr.tobytes()).hexdigest(), thru)
            hm = (hashlib.sha1(np.ascontiguousarray(arr[:, ::-1]).tobytes()).hexdigest(), thru)
            if h in canon:
                src_s, src_n, imgs = canon[h]
                how = "копия" if (src_s, src_n) != (s.upper(), n) else "канон"
                stat["copy" if how == "копия" else "canon"] += 1
            elif hm in canon:
                src_s, src_n, imgs0 = canon[hm]
                imgs = {m: im.transpose(Image.FLIP_LEFT_RIGHT) for m, im in imgs0.items()}
                how = "зеркало"
                stat["mirror"] += 1
                canon[h] = (s.upper(), n, imgs)
            else:
                imgs, _mask = make(frame, thru, ups)
                src_s, src_n, how = s.upper(), n, "канон"
                canon[h] = (s.upper(), n, imgs)
                stat["canon"] += 1
            mask = arr[..., 3] > 0
            fr = {"source": "%s:%d" % (src_s, src_n), "how": how}
            for m in methods:
                p = os.path.join(d, m, "series", s.upper() + ".PCK", "%d.png" % n)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                imgs[m].save(p)
                fr[m] = metrics(imgs[m], frame, mask)
            rep["frames"]["%s:%d" % (s.upper(), n)] = fr
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "report.json"), "w", encoding=ENC) as f:
            json.dump(rep, f, ensure_ascii=False, indent=1)
        worst = {m: max((v[m]["alpha_miss"] for v in rep["frames"].values() if m in v), default=0) for m in methods}
        print("%s: кадров %d, наибольшее расхождение альфы %s" % (case["id"], len(rep["frames"]), worst), flush=True)
    print("всего кадров %(frames)d: канонов %(canon)d, копий %(copy)d, зеркал %(mirror)d" % stat, flush=True)


if __name__ == "__main__":
    main()
