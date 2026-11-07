#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000390 (заправка, блок URBANWASTE12), второй круг кандидатов 04.11: кандидаты 31.10 забракованы Vitali
(колонка уже классики с прозрачными полями, бак - квадратный короб). В МОД НИЧЕГО НЕ СТАВИТ: кадры - art/tickets/t390/cand2/,
сырьё - art/tickets/t390/gen2/, листы - art/_review/tickets_2026-11-04/. Старые art/tickets/t390/cand не трогаются.

Основы: колонка URBAN_WASTE:85 -> MADDECOR_WASTE:49 (зеркало с перекраской по классике 49), RUSTSHACKS2:51 (копия);
        бак URBITS_WASTE:23 -> CATACDECOR_CONC:23 (копия). 5 кадров. Два варианта описания на основу (A, B), по 3 зерна.

Что другое, чем 31.10:
  * в описании колонки нет «tall slim»: классика 18x30 пикс (шире 0,6 высоты), прежний текст рисовал худую колонну;
  * cut_out растягивает габарит ответа на габарит классики, а не «не больше 1.3 по форме» (aspect у задания - 2.2);
  * заливка по классической маске: альфа = силуэт классики x4, сглаженный xBRZ (R-121); там, где предмет модели
    не дотянул до маски, цвет - от ближайших надёжных пикселей (od.spread), доля залитого считается и пишется в таблицу;
  * IoU (силуэт ответа после подгонки на габарит классики / маска классики x4) - до заливки, по нему выбирается зерно.
Ракурс и свет - только battle_view (g.build_prompt). R-570: слов stencil/mark/label/sign нет, в негативе letters/logo.

    py -3.13 tools\hdart\t390_gen2.py prompts
    py -3 tools\gpuq.py add --name t390-cand2 --prio 1 -- tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\t390_gen2.py render
    py -3.13 tools\hdart\t390_gen2.py seeds        # листы зёрен + таблица IoU
    py -3.13 tools\hdart\t390_gen2.py build        # кандидаты по BEST + семья + листы
    py -3.13 tools\hdart\t390_gen2.py scene        # сцена блока URBANWASTE12 (классика / сейчас / кандидат)
"""
import argparse
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (HERE, os.path.join(HERE, "..")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np                                   # noqa: E402
from PIL import Image                                # noqa: E402

import t405_409_gen as g                             # noqa: E402
import t379_391_gen as t                             # noqa: E402

REV = os.path.join(ROOT, "art", "_review", "tickets_2026-11-04")
GEN = os.path.join(ROOT, "art", "tickets", "t390", "gen2")
CAND = os.path.join(ROOT, "art", "tickets", "t390", "cand2")
g.GEN, g.REV, t.GEN, t.REV = GEN, REV, GEN, REV

GLOSS = "glossy, shiny, plastic, specular highlights, wet look, chrome, clean new, cartoon outline"
PUMP_NEG = (GLOSS + ", tall slim column, thin tower, narrow pillar, fuel nozzle hose, cable, screen with digits, "
            "lettering, letters, logo, bin, trash can, vending machine, text")
BIN_NEG = (GLOSS + ", round drum, cylinder, barrel, oil drum, circular rim, round lid, lettering, letters, X, logo, "
           "wooden staves, plastic bin, wheels, handle, tall cabinet, text")
JOBS = {
    "pumpA": dict(
        members=[("URBAN_WASTE", 85, (0, 0, 0))], seeds=[4011, 4012, 4013], r1=[], aspect=2.2,
        what=("a chunky, stout old petrol pump cabinet of dull lilac-violet painted sheet metal, broad and deep, "
              "only about one and a half times as tall as it is wide: a sloping grey-lilac metal cap on top with a "
              "lighter edge, below it a large black rounded-corner window opening filling the upper right of the "
              "front, in the middle of the front a small dark square plate with a faded brown blotch, below it a "
              "black rectangular nozzle bay, a narrow darker lilac left side face with a thin black vertical slot, "
              "a flat plinth, a little grit at its foot; scuffed, matte, weathered paint"),
        neg=PUMP_NEG, slab=False),
    "pumpB": dict(
        members=[("URBAN_WASTE", 85, (0, 0, 0))], seeds=[4021, 4022, 4023], r1=[], aspect=2.2,
        what=("a squat broad old fuel dispenser unit of dull lilac-violet metal with soft rounded shoulders, a wide "
              "body that fills most of the sprite, about as wide as two thirds of its height: a rounded grey cap "
              "on top, a big black rounded window in the upper right of the lighter front face, a small dark square "
              "plate with a faded brown blotch in the middle of the front, a black rectangular opening low on the "
              "front, a darker narrow left side face with a black vertical slot; scuffed matte paint, a few chips "
              "of rubble at the base"),
        neg=PUMP_NEG, slab=False),
    "binA": dict(
        members=[("URBITS_WASTE", 23, (0, 0, 0))], seeds=[4031, 4032, 4033], r1=[], aspect=2.2,
        what=("a small dark charcoal-grey steel street waste bin with softly rounded vertical corners, a little "
              "wider than half of its height: a flat dark lid band at the top with only a thin pale grey worn rim "
              "on its upper left edge (the top of the lid is barely visible), a narrow lighter grey left side face "
              "and a wide front face with vertical rolled ribs and a patch of rust-brown and orange grime with "
              "maroon streaks; matte, scratched, weathered steel, no letters and no markings"),
        neg=BIN_NEG, slab=False),
    "binB": dict(
        members=[("URBITS_WASTE", 23, (0, 0, 0))], seeds=[4041, 4042, 4043], r1=[], aspect=2.2,
        what=("a small dark grey rounded-rectangle steel litter bin, a block with softly rounded top corners and "
              "slightly narrower than it is tall: a heavy dark lid with a thin pale rim only along its upper left "
              "edge, the lid seen almost edge-on, below it a dark ribbed front panel with vertical grooves and "
              "rust-brown, orange and maroon grime streaks, a lighter left side strip; matte, scratched steel, no "
              "letters and no markings"),
        neg=BIN_NEG, slab=False),
}
for _j in JOBS.values():
    _j["neg"] = _j["neg"] + ", " + t.SLAB
g.JOBS = JOBS
g.CLUSTERS = {}
BEST = {"pump": ("pumpB", 4021), "bin": ("binA", 4032)}          # выбрано по листу зёрен 04.11
SPARE = {"pump": ("pumpA", 4011), "bin": ("binB", 4041)}   # второй вариант (cand2/alt)
ALT = False
FAM = {
    "pump": [("URBAN_WASTE", 85), ("MADDECOR_WASTE", 49), ("RUSTSHACKS2", 51)],
    "bin": [("URBITS_WASTE", 23), ("CATACDECOR_CONC", 23)],
}
BASE_JOBS = {"pump": ["pumpA", "pumpB"], "bin": ["binA", "binB"]}
BASE_KEY = {"pump": ("URBAN_WASTE", 85), "bin": ("URBITS_WASTE", 23)}


def sil_of(cls_k1):
    """Силуэт классики x4, сглаженный xBRZ (R-121), 0..255."""
    import probe_object as po
    m = Image.fromarray((np.asarray(cls_k1)[..., 3] > 0).astype(np.uint8) * 255, "L")
    return np.asarray(po.smooth_silhouette(m, 4))


def raw_cut(job, seed):
    return Image.open(os.path.join(GEN, job, "%d.png" % seed)).convert("RGBA").crop((0, 0, 128, 160))


def iou_before(cut, cls_k1):
    """IoU силуэта ответа (после подгонки на габарит классики cut_out) и маски классики x4; доля маски, не закрытая ответом."""
    sil = sil_of(cls_k1) > 128
    a = np.asarray(cut)[..., 3] > 128
    u = (a | sil).sum()
    return float((a & sil).sum() / u), float((sil & ~a).sum() / sil.sum()), float((a & ~sil).sum() / a.sum())


def fill_by_mask(cut, cls_k1):
    """Заливка по классической маске: альфа = силуэт классики x4 (сглаженный, края прямые), цвет - ответ модели, а где
    его нет (не дотянул до маски) - от ближайших надёжных пикселей. Возвращает (кадр, число залитых пикселей x4)."""
    import obj_derive as od
    from PIL import ImageFilter
    sil = sil_of(cls_k1).astype(np.float32)
    a = np.asarray(cut).astype(np.float32).copy()
    rel = (a[..., 3] >= 250)
    # кайма в 1 пикс x4 у края ответа: смесь с подложкой - не надёжна
    rel = np.asarray(Image.fromarray(rel.astype(np.uint8) * 255).filter(ImageFilter.MinFilter(3))) > 0
    need = (sil > 128) & ~rel
    for c in range(3):
        a[..., c] = od.spread(a[..., c], rel, 24)
    out = np.zeros(a.shape, np.uint8)
    out[..., :3] = np.clip(a[..., :3], 0, 255).astype(np.uint8)
    out[..., 3] = np.clip(sil, 0, 255).astype(np.uint8)
    out[out[..., 3] == 0, :3] = 0
    return Image.fromarray(out, "RGBA"), int(need.sum())


def _ext(al, axis):
    """Границы непрозрачного по строкам (axis=1) или колонкам (axis=0): (первый, последний, есть)."""
    m = al > 128
    has = m.any(axis=axis)
    first = np.where(has, m.argmax(axis=axis), 0)
    last = np.where(has, m.shape[axis] - 1 - np.flip(m, axis=axis).argmax(axis=axis), 0)
    return first.astype(np.float32), last.astype(np.float32), has


def _smooth1(v, has, sigma):
    """Сглаживание по ряду границ; места без предмета - по ближайшим."""
    idx = np.arange(len(v))
    if not has.any():
        return v
    v = np.interp(idx, idx[has], v[has]).astype(np.float32)
    k = np.exp(-0.5 * (np.arange(-3 * sigma, 3 * sigma + 1) / sigma) ** 2)
    k /= k.sum()
    pad = np.pad(v, (3 * sigma, 3 * sigma), mode="edge")
    return np.convolve(pad, k, mode="valid")


LAST_PRM = None
WARP_SIGMA = 24      # сглаживание границ предмета модели (шум)
TGT_SIGMA = 4        # сглаживание границ маски (лесенка классики уже снята xBRZ)


def _warp_axis(pm, sil, axis, delta=3, sigma=None):
    """Растяжка по строкам (axis=1) / колонкам (axis=0): предмет в каждой строке ложится на ширину маски в этой строке.
    pm - премноженный float (H,W,4); sil - bool маска. Строки маски без предмета берут ближайшую строку с предметом."""
    sigma = sigma or WARP_SIGMA
    sf, sl, sh = _ext(sil, axis)
    sf, sl = _smooth1(sf, sh, TGT_SIGMA), _smooth1(sl, sh, TGT_SIGMA)
    mf, ml, mh = _ext(pm[..., 3], axis)
    mf, ml = _smooth1(mf, mh, sigma), _smooth1(ml, mh, sigma)
    out = np.zeros_like(pm)
    n = pm.shape[axis]
    for i in range(len(sf)):
        if not sh[i]:
            continue
        L, R = sf[i], sl[i]
        l, r = mf[i] + delta, ml[i] - delta
        if r <= l:
            l, r = mf[i], ml[i]
        xs = np.arange(int(round(L)), int(round(R)) + 1)
        sx = l + (xs - L) * (r - l) / max(R - L, 1.0)
        sx = np.clip(sx, 0, n - 1)
        x0 = np.floor(sx).astype(int)
        x1 = np.minimum(x0 + 1, n - 1)
        f = (sx - x0)[:, None]
        # ряд источника: строка i, но если в ней нет предмета - ближайшая строка с предметом
        j = i
        if not mh[i]:
            hs = np.where(mh)[0]
            j = hs[np.abs(hs - i).argmin()] if len(hs) else i
        if axis == 1:
            row = pm[j]
            out[i, xs] = row[x0] * (1 - f) + row[x1] * f
        else:
            col = pm[:, j]
            out[xs, i] = col[x0] * (1 - f) + col[x1] * f
    return out


def affine_fit(cut, sil):
    """Подгонка предмета под маску ОДНИМ аффинным преобразованием (масштаб по осям, сдвиг, наклон), без деформации
    внутри: рисунок (окна, табличка) остаётся прямым. Поиск шаблоном по IoU на 1/4 размера. Возвращает (кадр, коэффициенты)."""
    al = np.asarray(cut)[..., 3]
    h, w = al.shape
    small_sil = np.asarray(Image.fromarray(sil.astype(np.uint8) * 255).resize((w // 4, h // 4), Image.BILINEAR)) > 128
    small_al = Image.fromarray(al).resize((w // 4, h // 4), Image.BILINEAR)

    def apply(img, prm, size, k):
        sx, sy, shx, shy, tx, ty = prm
        cx, cy = size[0] / 2, size[1] / 2
        a1, b1 = 1.0 / sx, -shx / sy
        d1, e1 = -shy / sx, 1.0 / sy
        Tx, Ty = tx * k, ty * k
        c1 = cx - a1 * (cx + Tx) - b1 * (cy + Ty)
        f1 = cy - d1 * (cx + Tx) - e1 * (cy + Ty)
        return img.transform(size, Image.AFFINE, (a1, b1, c1, d1, e1, f1), Image.BILINEAR)

    def score(prm):
        m = np.asarray(apply(small_al, prm, small_al.size, 1)) > 128
        u = (m | small_sil).sum()
        return (m & small_sil).sum() / u if u else 0.0

    prm = [1.0, 1.0, 0.0, 0.0, 0.0, 0.0]
    best = score(prm)
    steps = [0.08, 0.08, 0.08, 0.04, 3.0, 3.0]
    for _ in range(40):
        moved = False
        for i in range(6):
            for sgn in (1, -1):
                q = list(prm)
                q[i] += sgn * steps[i]
                sc = score(q)
                if sc > best + 1e-5:
                    prm, best, moved = q, sc, True
        if not moved:
            steps = [v / 2 for v in steps]
            if steps[0] < 0.004:
                break
    pm = np.asarray(cut).astype(np.float32).copy()
    pm[..., :3] *= pm[..., 3:4] / 255.0
    chans = [apply(Image.fromarray(np.clip(pm[..., c], 0, 255).astype(np.uint8)), prm, (w, h), 4) for c in range(4)]
    out = np.stack([np.asarray(c).astype(np.float32) for c in chans], -1)
    al2 = out[..., 3]
    rgb = np.where(al2[..., None] > 1, out[..., :3] / np.maximum(al2[..., None] / 255.0, 1e-3), 0)
    return Image.fromarray(np.concatenate([np.clip(rgb, 0, 255), al2[..., None]], -1).astype(np.uint8), "RGBA"), prm, best


def warp_to_mask(cut, cls_k1):
    """Заливка по классической маске, мягко: сначала каждая строка предмета растягивается на ширину маски в этой строке,
    потом каждая колонка - на высоту маски; затем остатки (альфа < 250 внутри маски) - от ближайших надёжных пикселей,
    альфа = силуэт классики x4 (сглаженный, края прямые). Возвращает (кадр, число пикселей, где пришлось дорисовывать цвет)."""
    sil_a = sil_of(cls_k1)
    sil = sil_a > 128
    global LAST_PRM
    tmp_im, LAST_PRM, _sc = affine_fit(cut, sil)
    tmp = np.asarray(tmp_im)
    al = tmp[..., 3].astype(np.float32)
    a2 = al > 128
    iou_w = float((a2 & sil).sum() / (a2 | sil).sum())
    im, n = fill_by_mask(Image.fromarray(tmp, "RGBA"), cls_k1)
    return im, n, iou_w


def do_seeds():
    import ticket_scene as ts
    rows = [["основа", "задание", "зерно", "IoU ответа (габарит на габарит классики)", "IoU после растяжки по маске",
             "дорисовано цвета, пикс x4"]]
    panels = []
    for fam, jobs in BASE_JOBS.items():
        cls = g.classic_of(*BASE_KEY[fam])
        panels.append(("классика %s:%d x4" % BASE_KEY[fam], t.fit(cls.resize((512, 640), Image.NEAREST), (0, 0, 512, 640), 300)))
        for job in jobs:
            for s in JOBS[job]["seeds"]:
                p = os.path.join(GEN, job, "%d.png" % s)
                if not os.path.exists(p):
                    continue
                cut = raw_cut(job, s)
                i, miss, over = iou_before(cut, cls)
                fl, n, iw = warp_to_mask(cut, cls)
                rows.append([fam, job, s, "%.3f" % i, "%.3f" % iw, n])
                panels.append(("%s %d IoU %.2f -> %.2f" % (job, s, i, iw), t.fit(fl.resize((512, 640), Image.LANCZOS), (0, 0, 512, 640), 300)))
    os.makedirs(REV, exist_ok=True)
    with open(os.path.join(REV, "t390_cand2_iou.tsv"), "w", encoding="utf-8-sig", newline="") as fh:
        csv.writer(fh, delimiter="\t").writerows(rows)
    for r in rows:
        print(*r)
    ts.sheet(panels, os.path.join(REV, "t390_cand2_seeds.png"), cols=4)
    print("лист:", os.path.join(REV, "t390_cand2_seeds.png"))


def cdir():
    d = os.path.join(CAND, "alt") if ALT else CAND
    os.makedirs(d, exist_ok=True)
    return d


def do_build():
    cdir()
    new, rows = {}, [["кадр", "вид", "зерно", "IoU основы до подгонки", "IoU основы после растяжки по маске", "IoU классик цель/основа",
                      "залито по маске, пикс x4", "яркость новое", "яркость классика"]]
    for fam, keys in FAM.items():
        job, seed = (SPARE if ALT else BEST)[fam]
        bk = BASE_KEY[fam]
        cut0 = raw_cut(job, seed)
        iou0, miss, over = iou_before(cut0, g.classic_of(*bk))
        base, nfill, iou_w = warp_to_mask(cut0, g.classic_of(*bk))
        for key in keys:
            if key == bk:
                im, kind, q = base, "основа", 1.0
            else:
                ob, ot = g.classic_of(*bk), g.classic_of(*key)
                if g.same_px(ob, ot):
                    im, kind, q = base.copy(), "копия", 1.0
                else:
                    flip = g.mirror_closer(ob, ot)
                    b2, o2 = (base.transpose(Image.FLIP_LEFT_RIGHT), ob.transpose(Image.FLIP_LEFT_RIGHT)) if flip else (base, ob)
                    q = g.iou(o2, ot)
                    im = g.colormap_transfer(b2, o2, ot) if not g.same_px(o2, ot) else b2
                    kind = "зеркало+перенос цвета" if flip else "перенос цвета"
                    # заливка по маске цели: альфа = силуэт классики цели
                    im, _n = fill_by_mask(im, ot)
            cls = g.classic_of(*key)
            sil = sil_of(cls) > 128
            a = np.asarray(im)[..., 3] > 128
            iou_f = float((a & sil).sum() / (a | sil).sum())
            im.save(os.path.join(cdir(), "%s_%d.png" % key))
            new[key] = im
            rows.append(["%s:%d" % key, kind, "%s/%d" % (job, seed), "%.3f" % iou0, "%.3f" % iou_w, "%.3f" % q, nfill,
                         "%.0f" % g.mean_lum(im), "%.0f" % g.mean_lum(cls)])
    with open(os.path.join(REV, "t390_cand2%s_checks.tsv" % ("_alt" if ALT else "")), "w", encoding="utf-8-sig", newline="") as fh:
        csv.writer(fh, delimiter="\t").writerows(rows)
    for r in rows:
        print(*r)
    import ticket_scene as ts
    panels = []
    for fam, keys in FAM.items():
        for key in keys:
            panels.append(("%s:%d - классика | сейчас | кандидат 04.11%s" % (key + ((" (вариант 2)" if ALT else ""),)), t.triple_big(key[0], key[1], new[key])))
    ts.sheet(panels, os.path.join(REV, "t390_cand2%s.png" % ("_alt" if ALT else "")), cols=1)
    print("лист:", os.path.join(REV, "t390_cand2%s.png" % ("_alt" if ALT else "")))


def do_scene():
    import ticket_scene as ts
    sc = ts.Scene()
    ov = {}
    for fn in sorted(os.listdir(cdir())):
        if fn.endswith(".png"):
            s, f = fn[:-4].rsplit("_", 1)
            ov[(s, int(f))] = Image.open(os.path.join(cdir(), fn)).convert("RGBA")
    keys = [("URBAN_WASTE", 85), ("URBITS_WASTE", 23)]
    found = ts.find_cells(sc, "URBAN_WASTE", "URBANWASTE12", keys)
    box = ts.window([(f[0], f[1], tuple(v * 4 for v in f[2])) for f in found], 200, 140, 4)
    maxz = max(f[3] for f in found)
    panels = []
    for title, mode, o in (("классика", "classic", None), ("HD сейчас", "hd", None), ("кандидат 04.11" + (" (вариант 2)" if ALT else ""), "hd", ov)):
        im, _f = sc.render("URBAN_WASTE", "URBANWASTE12", mode, override=o, k=4, maxz=maxz)
        panels.append(("%s (URBANWASTE12)" % title, ts.crop_pad(im, box)))
        if o:
            im.crop(box).save(os.path.join(REV, "t390_cand2%s_scene_full.png" % ("_alt" if ALT else "")))
    ts.sheet(panels, os.path.join(REV, "t390_cand2%s_scene.png" % ("_alt" if ALT else "")), cols=1)
    print("лист:", os.path.join(REV, "t390_cand2%s_scene.png" % ("_alt" if ALT else "")))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["render", "recut", "prompts", "seeds", "build", "scene"])
    ap.add_argument("--alt", action="store_true", help="второй вариант (SPARE) -> cand2/alt")
    ap.add_argument("--jobs", nargs="*", default=list(JOBS), choices=sorted(JOBS))
    a = ap.parse_args()
    global ALT
    ALT = a.alt
    if a.cmd == "prompts":
        for j in a.jobs:
            tx, n = g.build_prompt(j)
            print("[%s]\n  PROMPT: %s\n  NEG: %s" % (j, tx, n))
    elif a.cmd == "render":
        g.do_render(a.jobs)
    elif a.cmd == "recut":
        g.recut(a.jobs)
    elif a.cmd == "seeds":
        do_seeds()
    elif a.cmd == "build":
        do_build()
    else:
        do_scene()
    return 0


if __name__ == "__main__":
    sys.exit(main())
