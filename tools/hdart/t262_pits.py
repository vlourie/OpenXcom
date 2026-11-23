#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000262: ямы из 4 клеток (2x2) в HD нарисованы клетка за клеткой - форма рваная, круглая впадина стала
квадратной плитой. Здесь яма собирается ЦЕЛИКОМ на холсте 2x2 и режется обратно на кадры. Без видеокарты.

Рецепт (вариант 1 разбора, Vitali 23.10 «чини все»):
  1. классика кадров склеивается на холсте 2x2 (64x56 базы);
  2. маска ямы: у MOUNTGRASS - не-трава (G - R <= 12), у остальных - цвета, которых нет на внешнем кольце холста;
     заливка дыр, самая большая связная часть, размытие на базе, бикубика x4, мягкий порог (яма круглая - углов нет,
     R-042 не нарушен); край чуть качается шумом, чтобы не был циркульным;
  3. цвет и светотень (тёмная стенка, светлое дно) - гладкое поле цвета КЛАССИКИ целого холста (нормированная свёртка
     по маске, бикубика) плюс скат по полю расстояния до края, свет сверху-слева - одно на всё 2x2, не по клетке (R-265);
  4. мелкая фактура - высокие частоты самой ямы HD-набора (куски 16x16 из текущих кадров пака внутри маски, у MOUNTGRASS
     ещё земля кадра 63), растушёвка hanning;
  5. грунт вокруг - плоский кадр HD того же набора и его варианты .vN (как соседние клетки карты); у края ямы - светлая
     кромка снаружи и тёмный скат внутри;
  6. нарезка: размер 128x160 и альфа - как у кадра пака сейчас (там, где у склейки нет пикселя - пиксель пака).

    py -3.13 tools/hdart/t262_pits.py                    # кадры в art/tickets/t262/out/<набор>/<кадр>.png
    py -3.13 tools/hdart/t262_pits.py --sets MOUNTGRASS  # только набор
    py -3.13 tools/hdart/t262_pits.py --install --yes    # + стейдж в манифест и в обе копии мода hd (под очередью правок)
"""
import argparse
import hashlib
import os
import sys

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import tile_forge as tf  # noqa: E402

HD_ROOT = os.path.join(ROOT, "user", "mods", "hd", "hd", "TERRAIN")
OUT = os.path.join(ROOT, "art", "tickets", "t262", "out")
K = 4
# положение клетки 2x2 на холсте базы 32x40: top=(0,0) right=(+1,0) left=(0,+1) bottom=(+1,+1)
OFF = {"top": (16, 0), "right": (32, 8), "left": (0, 8), "bottom": (16, 16)}
CW, CH = 64, 56
LUM = np.array([0.299, 0.587, 0.114], np.float32)
GR_MAX = 12     # трава MOUNTGRASS: G >> R; земля, камень, серая кромка - G - R <= 12


def _b(name, top, left, right, bottom, base, **kw):
    """Яма 2x2 из записей MCD 17..20 (верх, лево, право, низ): одна и та же раскладка во всех MOUNT*."""
    g = {"name": name, "frames": {"top": top, "left": left, "right": right, "bottom": bottom}, "base": base, "kind": "pit"}
    g.update(kw)
    return g


# набор -> группы. base - кадры HD плоского грунта по клеткам; extra - кадры, откуда ещё берётся фактура
GROUPS = {
    "MOUNTGRASS": [
        _b("B", 16, 17, 18, 19, {"top": "0.v2", "right": "0.v5", "left": "0.v3", "bottom": "0.v1"}, rule="gr", extra=[63]),
        # яма A: только полы 10 и 62 (каждый на своём холсте - они стоят и одиночками); куст 9 и объект 8 не трогаются
        # (не из маски, семьи GOTHIC/CULTIVAT...)
        {"name": "A10", "frames": {"top": 10}, "kind": "ledge", "rule": "gr", "depth": 7.0, "grain": 0.16, "keep_all": True,
         "base": {"top": "0.v6", "right": "0.v5", "left": "0.v2", "bottom": "0.v1"}, "extra": [63]},
        {"name": "A62", "frames": {"top": 62}, "kind": "ledge", "rule": "gr", "depth": 7.0, "grain": 0.16, "keep_all": True,
         "base": {"top": "0.v2", "right": "0.v5", "left": "0.v2", "bottom": "0.v1"}, "extra": [63]},
        # одинарная 61
        {"name": "S61", "frames": {"top": 61}, "kind": "ledge", "rule": "gr", "depth": 7.0, "grain": 0.16, "keep_all": True,
         "base": {"top": "0.v4", "right": "0.v5", "left": "0.v2", "bottom": "0.v1"}, "extra": [63]},
    ],
    "MOUNT": [_b("B", 17, 18, 19, 20, {"top": "0.v1", "right": "0.v3", "left": "0.v2", "bottom": "0"}, rule="brown", lip=0.05)],
    "MOUNTMUD": [_b("B", 15, 16, 17, 18, {"top": "0.v1", "right": "0.v3", "left": "0.v2", "bottom": "0"}, depth=4.0, contrast=0.3, lip=0.05)],
    "MOUNTROCK": [_b("B", 17, 18, 19, 20, {"top": "0.v1", "right": "0.v3", "left": "0.v2", "bottom": "0"}, rule="brown", lip=0.05)],
    "MOUNTSNOW2": [_b("B", 17, 18, 19, 20, {"top": "0.v1", "right": "0.v3", "left": "0.v2", "bottom": "0"}, rule="brown", depth=10.0, lip=0.0, esig=0.45)],
    "MOUNTTROP": [_b("B", 18, 19, 20, 21, {"top": "0", "right": "0", "left": "0", "bottom": "0"}, rule="trop", lip=0.08)],
    "MOUNTWASTE2": [_b("B", 16, 17, 18, 19, {"top": "0.v1", "right": "0.v3", "left": "0.v2", "bottom": "0"}, rule="brown", lip=0.05)],
}

_sheets = {}


def classic(setname, f):
    key = setname.upper()
    if key not in _sheets:
        _sheets[key] = tf.Sheet(os.path.join(ROOT, "art", "TERRAIN"), key + ".PCK")
    return _sheets[key].frame(f).convert("RGBA")


def hd_open(setname, f, root=HD_ROOT):
    return Image.open(os.path.join(root, setname.upper() + ".PCK", "%s.png" % f)).convert("RGBA")


def compose(frames, getter, k=1):
    cv = Image.new("RGBA", (CW * k, CH * k), (0, 0, 0, 0))
    for pos, f in frames.items():
        ox, oy = OFF[pos]
        cv.alpha_composite(getter(f), (ox * k, oy * k))
    return cv


def blur(a, s):
    return cv2.GaussianBlur(a, (0, 0), s, borderType=cv2.BORDER_REFLECT)


def smooth_noise(shape, sigma, seed):
    r = np.random.RandomState(seed)
    n = blur(r.randn(*shape).astype(np.float32), sigma)
    return n / (n.std() + 1e-6)


def detail_field(setname, g, m, shape, seed=7):
    """Высокие частоты ямы HD-набора: куски 16x16 внутри маски на текущих кадрах пака (и extra), растушёвка hanning."""
    k = K
    cur = np.array(compose(g["frames"], lambda f: hd_open(setname, f), k)).astype(np.float32)
    srcs = [(cur[..., :3] @ LUM, ndi.binary_erosion(m > 0.9, iterations=4))]
    for f in g.get("extra", []):
        im = np.array(hd_open(setname, f)).astype(np.float32)
        a = im[..., 3] > 0
        e = ndi.binary_erosion(a & (im[..., 1] <= im[..., 0] + 6), iterations=2)
        srcs.append((im[..., :3] @ LUM, e))
    patches = []
    P = 16
    for lum, region in srcs:
        hp = lum - blur(lum, 4)
        ys, xs = np.nonzero(region)
        for y, x in zip(ys[::3], xs[::3]):
            if y + P <= hp.shape[0] and x + P <= hp.shape[1] and region[y:y + P, x:x + P].mean() > 0.92:
                patches.append(hp[y:y + P, x:x + P])
    H, W = shape
    if not patches:
        return np.zeros(shape, np.float32), 0
    r = np.random.RandomState(seed)
    out = np.zeros(shape, np.float32)
    wsum = np.zeros(shape, np.float32)
    h1 = np.hanning(P + 2)[1:-1].astype(np.float32)
    win = np.outer(h1, h1)
    for _ in range(int(H * W / (P * P) * 8)):
        y = r.randint(-P // 2, H - P // 2)
        x = r.randint(-P // 2, W - P // 2)
        p = patches[r.randint(len(patches))]
        if r.rand() < 0.5:
            p = p[:, ::-1]
        if r.rand() < 0.5:
            p = p[::-1]
        y0, x0 = max(y, 0), max(x, 0)
        y1, x1 = min(y + P, H), min(x + P, W)
        if y1 <= y0 or x1 <= x0:
            continue
        out[y0:y1, x0:x1] += (p * win)[y0 - y:y1 - y, x0 - x:x1 - x]
        wsum[y0:y1, x0:x1] += win[y0 - y:y1 - y, x0 - x:x1 - x]
    out = out / np.maximum(wsum, 1e-3)
    return out, len(patches)


def pit_mask_classic(arr, rule, keep_all=False):
    """Яма в классике: rule 'gr' - не-трава; 'pal' - цвета, которых нет на внешнем кольце холста. Дыры залиты."""
    a = arr[..., 3] > 0
    rgb = arr[..., :3].astype(np.int32)
    if rule == "gr":
        pit = a & (rgb[..., 1] - rgb[..., 0] <= GR_MAX)
    elif rule == "brown":
        # земля на сером/белом/зелёном грунте: красновато (R - B >= 12) и не зелёное (G - R <= 12)
        pit = a & (rgb[..., 0] - rgb[..., 2] >= 12) & (rgb[..., 1] - rgb[..., 0] <= GR_MAX)
    elif rule == "trop":
        # земля джунглей: R - G 25..60 (красные цветы - больше), G - B >= 20, не светлая
        d_rg = rgb[..., 0] - rgb[..., 1]
        pit = a & (d_rg >= 25) & (d_rg <= 60) & (rgb[..., 1] - rgb[..., 2] >= 20) & (rgb[..., 1] < 100)
    else:
        ring = a & ~ndi.binary_erosion(a, iterations=4)
        cols = {tuple(c) for c in rgb[ring]}
        pit = a & ~np.array([tuple(c) in cols for c in rgb.reshape(-1, 3)]).reshape(a.shape)
    pit = ndi.binary_closing(pit, structure=np.ones((3, 3)), iterations=1)
    pit = ndi.binary_fill_holes(pit)
    pit = ndi.binary_opening(pit, structure=np.ones((2, 2)))
    lab, n = ndi.label(pit)
    if n > 1 and not keep_all:
        sizes = ndi.sum(pit, lab, range(1, n + 1))
        pit = lab == (1 + int(np.argmax(sizes)))
    return pit & a


def render_pit(setname, g, k=K, seed=11):
    cl = np.array(compose(g["frames"], lambda f: classic(setname, f), 1)).astype(np.float32)
    pit1 = pit_mask_classic(cl, g.get("rule", "pal"), g.get("keep_all", False))
    H, W = CH * k, CW * k
    # --- маска ямы
    m1 = blur(pit1.astype(np.float32), 0.8)
    m = cv2.resize(m1, (W, H), interpolation=cv2.INTER_CUBIC)
    m = m + 0.07 * smooth_noise((H, W), 5.0, seed)
    t = np.clip((m - 0.38) / 0.24, 0, 1)
    m = t * t * (3 - 2 * t)
    # --- цвет классики: нормированная свёртка по яме, у края - ближайшие пиксели ямы
    w = pit1.astype(np.float32)
    es = g.get('esig', 0.9)
    ec = np.zeros((CH, CW, 3), np.float32)
    idx = ndi.distance_transform_edt(~pit1, return_distances=False, return_indices=True)
    for c in range(3):
        ec[..., c] = blur(cl[..., c] * w, es) / np.maximum(blur(w, es), 1e-3)
        near = cl[..., c][idx[0], idx[1]]
        ec[..., c] = np.where(blur(w, es) > 0.15, ec[..., c], near)
    E = np.stack([cv2.resize(ec[..., c], (W, H), interpolation=cv2.INTER_CUBIC) for c in range(3)], -1)
    inside = m > 0.5
    Lc = E @ LUM
    Lm = float(Lc[inside].mean())
    shade = np.clip((Lc / Lm), 0.3, 1.8) ** g.get("contrast", 0.42)
    # --- скат по расстоянию до края, свет сверху-слева
    d = ndi.distance_transform_edt(inside).astype(np.float32)
    z = -(1 - np.exp(-d / 12.0)) * g.get("depth", 16.0)
    z = blur(z, 2.0)
    gy, gx = np.gradient(z)
    nz = 1 / np.sqrt(1 + gx * gx + gy * gy)
    lx, ly, lz = -0.55, -0.55, 0.65
    geo = np.clip(((-gx * lx - gy * ly + lz) * nz) / lz, 0.65, 1.2)
    # --- фактура
    det, npatch = detail_field(setname, g, m, (H, W), seed)
    sd = det[inside].std() if inside.any() else 1.0
    det = det / (sd + 1e-6)
    earth = E * shade[..., None] * geo[..., None] * (1 + g.get("grain", 0.09) * det[..., None])
    gm = blur(m, 4.0)
    inner = np.clip(m * (1 - gm) * 2.0, 0, 1)
    earth = earth * (1 - 0.22 * inner[..., None])
    # --- грунт вокруг
    base = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for pos, f in g["base"].items():
        ox, oy = OFF[pos]
        base.alpha_composite(hd_open(setname, f), (ox * k, oy * k))
    B = np.array(base).astype(np.float32)
    outer = np.clip((1 - m) * gm * 2.0, 0, 1)
    grass = B[..., :3] * (1 + g.get("lip", 0.14) * outer[..., None])
    rgb = np.clip(grass * (1 - m[..., None]) + earth * m[..., None], 0, 255)
    return rgb, B[..., 3] > 0, m


def cut_frames(setname, g, rgb, cover, k=K):
    outs = {}
    for pos, f in g["frames"].items():
        cur = np.array(hd_open(setname, f)).astype(np.float32)
        ox, oy = OFF[pos]
        sub = rgb[oy * k:(oy + 40) * k, ox * k:(ox + 32) * k]
        cv_ = cover[oy * k:(oy + 40) * k, ox * k:(ox + 32) * k]
        a = cur[..., 3] > 0
        out = np.zeros((40 * k, 32 * k, 4), np.uint8)
        use = a & cv_
        out[..., :3] = np.where(use[..., None], sub, cur[..., :3]).clip(0, 255).astype(np.uint8)
        out[..., 3] = np.where(a, 255, 0).astype(np.uint8)
        out[~a, :3] = 0
        outs[f] = Image.fromarray(out, "RGBA")
    return outs


def run(sets=None, only=None):
    res = {}
    for setname, groups in GROUPS.items():
        if sets and setname not in sets:
            continue
        for g in groups:
            if only and g["name"] not in only:
                continue
            rgb, cover, m = render_pit(setname, g)
            outs = cut_frames(setname, g, rgb, cover)
            d = os.path.join(OUT, setname)
            os.makedirs(d, exist_ok=True)
            for f, im in outs.items():
                im.save(os.path.join(d, "%d.png" % f))
                res[(setname, f)] = os.path.join(d, "%d.png" % f)
            Image.fromarray(np.dstack([rgb, np.where(cover, 255, 0)]).astype(np.uint8), "RGBA").save(
                os.path.join(d, "_comp_%s.png" % g["name"]))
    return res


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sets", help="наборы через запятую (по умолчанию все)")
    ap.add_argument("--only", help="имена групп через запятую")
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    res = run(a.sets.split(",") if a.sets else None, a.only.split(",") if a.only else None)
    print("кадров: %d в %s" % (len(res), OUT))
    if not a.install:
        return 0
    if not a.yes:
        raise SystemExit("сухой прогон; --install --yes - записать в мод")
    import build_hd_pack as bp
    man = bp.load()
    rels = []
    for (setname, f), p in res.items():
        rel = "TERRAIN/%s.PCK/%d.png" % (setname, f)
        bp.stage(man, rel, p, generator="t262_pits", generator_version="t262_pits.py 23.10 процедурно по маске классики, 2x2",
                 source_path="art/tickets/t262/out/%s/%d.png" % (setname, f), approved=True,
                 approval="Vitali 23.10 t262: «чини все», вариант 1 процедурно по маске классики",
                 derived_from=None)
        rels.append(rel)
    bp.save(man, why="t262: ямы MOUNT* цельными композициями 2x2 (%d кадров)" % len(rels))
    print("game:", bp.install(man, "game", only=rels))
    print("repo:", bp.install(man, "repo", only=rels))
    for r in rels:
        for root in bp.TARGETS.values():
            with open(os.path.join(root, r), "rb") as fh:
                if hashlib.sha256(fh.read()).hexdigest() != man["files"][r]["sha256"]:
                    raise SystemExit("РАСХОДИТСЯ %s %s" % (root, r))
    print("сверено: %d файлов в обеих копиях" % len(rels))
    return 0


if __name__ == "__main__":
    sys.exit(main())
