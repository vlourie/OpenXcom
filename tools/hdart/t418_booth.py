#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000418: будка пропускная PORTROADS:34 («аквариум»). Пилот основы 30.10 по выбору Vitali: вариант B (будка с
деталями, 5 кадров: основа PORTROADS:34 + перекраски MILURBITSEXT:18, MILWARE:45, MILWAREGHOUL:44, XBITSUFO:44; обломки :35 НЕ
берём) и стекло B2 (интерьер нарисован в кадре, заднее стекло полупрозрачное 0,28-0,4). В МОД НИЧЕГО НЕ СТАВИТ.

Генерация - как t405_409_gen (Qwen-Image-2.1 strict, 40 шагов, cfg 4, 1 Мп, вход - классика на подложке pick_background, ракурс
и свет - ТОЛЬКО battle_view). Отличия от t405_409_gen:
  - вход xbrz (long_object.model_input) в кругах r2: без лесенки пикселей модель не рисует ступени формой (R-121);
  - ответ режется матрицей obj_photo.edge_matte, а не ключом по цвету подложки: розовое тело близко к серой подложке, ключ
    по цвету красил его в зелёный;
  - силуэт - линиями (probe_object.smooth_silhouette внутри cut_out), срез NEAREST x4 не применяется;
  - тон в вырезке не подгоняется: t418_post.hull_tone берёт только корпус (match_tone по всему кадру тянул тень правой грани
    в зелёный из-за синего стекла классики).
Круги: r1 - зёрна 4181-4183 (вход bicubic); r2 - 4191-4193 (xbrz) и 4195-4197 (xbrz, короткая форма).

    py -3 tools\gpuq.py add --name t418-booth --prio 1 -- tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\t418_booth.py render --jobs boothx
    py -3.13 tools\hdart\t418_booth.py recut | seeds | build | scene
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (HERE, os.path.join(HERE, "..")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np                                   # noqa: E402
from PIL import Image                                # noqa: E402
import t405_409_gen as tg                            # noqa: E402

GEN = os.path.join(ROOT, "art", "tickets", "t418", "gen")
CAND = os.path.join(ROOT, "art", "tickets", "t418", "cand")
REV = os.path.join(ROOT, "art", "_review", "tickets_2026-10-30")
tg.GEN, tg.CAND, tg.REV = GEN, CAND, REV

NEG = ("aquarium, fish tank, water, waves, ripples, plants, seaweed, algae, fish, bubbles, sand, wood grain, wooden planks, "
       "stone slab, floor plate, ground, text, letters")
WHAT = ("a small guard checkpoint booth, a closed security cabin of beige-pink painted metal with a flat roof: on the roof a "
        "small ventilation box with louvres and a small round lamp; the left wall has a large window in a tan frame above a "
        "sloped pale service ledge with a small intercom grille; the right wall, in shade, has a window in a tan frame, below "
        "it a door with a dark handle, and a small sign plate; through the clear glass of the windows the inside is visible "
        "- the lower half of each window shows a desk, a computer monitor and an office chair, the upper half is plain clear "
        "glass; the glass is clear pale grey-blue, with a couple of soft white reflections")
WHAT_SQUAT = ("a squat wide guard checkpoint booth that fills its whole tile, a closed security cabin of pale peach-pink "
              "painted metal; the roof is a thin flat slab that does not overhang, with a small ventilation box with louvres "
              "and a small round lamp on it; the walls are almost all window: on the left wall a very large window in a tan "
              "frame, below it a sloped pale service ledge with a small intercom grille sticking out at the lower left; on the "
              "right wall, in shade, a large window in a tan frame, below it a door with a dark handle and a small sign "
              "plate; through the clear glass the inside is visible - the lower half of each window shows a desk, a computer "
              "monitor and an office chair, the upper half is plain clear glass; the glass is clear pale grey-blue, with a "
              "couple of soft white reflections")
tg.JOBS.clear()
J0 = dict(members=[("PORTROADS", 34, (0, 0, 0))], r1=[], what=WHAT, neg=NEG, slab=False)
tg.JOBS["booth"] = dict(J0, seeds=[4181, 4182, 4183], how="bicubic")
tg.JOBS["boothx"] = dict(J0, seeds=[4191, 4192, 4193], how="xbrz")
tg.JOBS["boothq"] = dict(J0, seeds=[4195, 4196, 4197], how="xbrz", what=WHAT_SQUAT)


def _smooth1(v, sigma):
    """Сглаживание вектора с пропусками (nan): гауссово по соседям, пропуск закрывается ближайшим."""
    import cv2
    v = np.asarray(v, np.float32)
    ok = np.isfinite(v)
    if not ok.any():
        return v
    idx = np.arange(len(v))
    v = np.interp(idx, idx[ok], v[ok]).astype(np.float32)
    return cv2.GaussianBlur(v.reshape(1, -1), (0, 0), sigma).reshape(-1)


def sil_lines(solid, eps=3.0, ss=4):
    """Силуэт классики (L 0/255, k=1) -> x4 ломаной из прямых отрезков (R-121): контур сглаженной маски упрощён approxPolyDP
    (eps пикселей HD), залит на холсте в ss раз крупнее и сжат - край ровный линией с сглаживанием в один пиксель, не лесенка
    и не волна xBRZ."""
    import cv2
    import probe_object as po
    big = np.asarray(po.smooth_silhouette(solid, 4)) > 128
    cs, _h = cv2.findContours(big.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    H, W = big.shape
    canvas = np.zeros((H * ss, W * ss), np.uint8)
    for c in cs:
        poly = cv2.approxPolyDP(c, eps, True).reshape(-1, 2).astype(np.float32) * ss + (ss - 1) / 2.0
        cv2.fillPoly(canvas, [np.rint(poly).astype(np.int32)], 255)
    small = cv2.resize(canvas, (W, H), interpolation=cv2.INTER_AREA)
    return Image.fromarray(small, "L")


BASE_INSET = 1.0      # на сколько пикселей HD низ будки поднят над ромбом основания (R-121, правило 12 CLAUDE.md)


def base_lines(sil, inset=BASE_INSET, ss=4):
    """Нижний контур будки - ПРЯМЫЕ отрезки вдоль ромба основания клетки (изо-наклон 2:1), а не ступени классики. В игре HD-пол
    соседних клеток (и тень углов пола) закрывает ромб ступенькой 8x4 пикселей HD: у пола на 0,5-4 пикселя ниже линии ромба
    (замер в игре 30.10, t418_edge.py / t418_stand.py). Кадр, доходящий до линии, получает от соседа зубцы. Поэтому силуэт
    режется двумя прямыми y <= 128 + x/2 - inset (левое нижнее ребро) и y <= 128 + (128-x)/2 - inset (правое), сглаживание
    через сверхдискретизацию ss; тело потом подгоняется под этот силуэт (fit_silhouette), а не обрезается."""
    a = np.asarray(sil, np.float32) / 255.0
    H, W = a.shape
    yy, xx = np.mgrid[0:H * ss, 0:W * ss].astype(np.float32)
    xs, ys = (xx + 0.5) / ss, (yy + 0.5) / ss
    lim = np.minimum(128.0 + xs / 2.0, 128.0 + (W - xs) / 2.0) - inset
    keep = (ys <= lim).astype(np.float32)
    cov = keep.reshape(H, ss, W, ss).mean((1, 3))
    return Image.fromarray(np.rint(a * cov * 255).astype(np.uint8), "L")


def fill_matte_holes(m):
    """Матрица ответа модели: гладкий блик стекла (белое пятно) близок к серой подложке и ключ вырезал в нём дыру. Всё, что не
    связано с краем кадра и имеет альфу ниже 0,5, - тело: альфа 1 (цвет остаётся цветом ответа)."""
    import cv2
    solid = (np.asarray(m) > 0.5).astype(np.uint8)
    inv = (1 - solid).astype(np.uint8) * 255
    flood = inv.copy()
    h, w = inv.shape
    mask = np.zeros((h + 2, w + 2), np.uint8)
    for pt in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        if flood[pt[1], pt[0]] == 255:
            cv2.floodFill(flood, mask, pt, 128)
    hole = (flood == 255)                            # пустое, до которого заливка с края не дошла
    out = np.asarray(m, np.float32).copy()
    out[hole] = 1.0
    return out


def fit_silhouette(cut, sil, sigma=30.0, lim=1.12, axes=(0, 1)):
    """Подгонка нарисованного тела под силуэт классики: по каждому столбцу тело (альфа > 128) растягивается по вертикали между
    своими верхом и низом так, чтобы верх и низ совпали с верхом и низом силуэта классики; потом то же по строкам
    горизонтально. Параметры сглажены по соседним столбцам (sigma, пикселей HD), чтобы не было сдвига полосками; растяжка
    ограничена lim раз. Нужна затем, что модель рисует низ и бока тела не там, где классика: без неё силуэт классики
    оставляет под телом пустую полосу или режет окно. -> (кадр, макс. растяжка по столбцам, по строкам)."""
    import cv2
    a = np.asarray(cut, np.float32)
    H, W = a.shape[:2]
    body = a[..., 3] > 128
    cl = np.asarray(sil) > 128
    pm = a.copy()
    pm[..., :3] *= pm[..., 3:4] / 255.0                 # премультипликация: края не краснеют при интерполяции
    out_stats = []
    for axis in axes:                                  # 0 - по столбцам (вертикаль), 1 - по строкам (горизонталь)
        b, c = (body, cl) if axis == 0 else (body.T, cl.T)
        n = b.shape[1]
        mt = np.full(n, np.nan, np.float32)
        mb = mt.copy(); ct = mt.copy(); cb = mt.copy()
        for x in range(n):
            ys = np.nonzero(b[:, x])[0]
            yc = np.nonzero(c[:, x])[0]
            if len(ys) > 3 and len(yc) > 3:
                mt[x], mb[x], ct[x], cb[x] = ys[0], ys[-1], yc[0], yc[-1]
        mt, mb, ct, cb = (_smooth1(v, sigma) for v in (mt, mb, ct, cb))
        scale = (mb - mt) / np.maximum(cb - ct, 1.0)
        scale = np.clip(scale, 1.0 / lim, lim)
        out_stats.append(float(np.max(np.abs(scale - 1.0))))
        yy = np.arange(b.shape[0], dtype=np.float32)[:, None]
        src = mt[None, :] + (yy - ct[None, :]) * scale[None, :]
        xx = np.broadcast_to(np.arange(n, dtype=np.float32)[None, :], src.shape)
        if axis == 0:
            mapx, mapy = np.ascontiguousarray(xx), np.ascontiguousarray(src.astype(np.float32))
        else:
            mapx, mapy = np.ascontiguousarray(src.astype(np.float32).T), np.ascontiguousarray(xx.T)
        pm = cv2.remap(pm, mapx, mapy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
        body = pm[..., 3] > 128
    al = pm[..., 3:4]
    rgb = np.where(al > 0, pm[..., :3] / np.maximum(al, 1e-3) * 255.0, 0)
    res = np.concatenate([rgb, al], -1)
    return Image.fromarray(np.clip(np.rint(res), 0, 255).astype(np.uint8), "RGBA"), out_stats[0], (out_stats[1] if len(out_stats) > 1 else 0.0)


FIT = {}


def cut_seed(job, seed):
    """Сырой ответ gen/<job>/raw/<seed>.png -> кадр 128x160 с альфой: матрица edge_matte, вырез с запасом 3 пикселя, подгонка тела
    под силуэт классики (fit_silhouette), затем срез по силуэту классики - линией (R-121)."""
    import obj_photo as op
    import probe_object as po
    _comp, full, _at = tg.comp_of(job)
    box = tg.padded_box(full)
    frame = full.crop(box)
    hd = Image.open(os.path.join(GEN, job, "raw", "%d.png" % seed)).convert("RGB")
    matte = fill_matte_holes(op.edge_matte(hd))
    part = po.cut_out(hd, frame, 3, 40, max_aspect=1.3, matte=matte)
    cut = Image.new("RGBA", (full.width * 4, full.height * 4), (0, 0, 0, 0))
    cut.paste(part, (box[0] * 4, box[1] * 4))
    solid = full.split()[3].point(lambda v: 255 if v > 0 else 0)
    sil = base_lines(sil_lines(solid))                  # силуэт классики прямыми отрезками, низ - по ромбу основания, без ступеней
    cut, sv, sh = fit_silhouette(cut, sil)
    FIT[(job, seed)] = (sv, sh)
    a = np.asarray(cut).astype(np.float32)
    a[..., 3] = a[..., 3] * np.asarray(sil, np.float32) / 255.0
    a[a[..., 3] == 0, :3] = 0
    Image.fromarray(np.rint(a).astype(np.uint8), "RGBA").save(os.path.join(GEN, job, "%d.png" % seed))
    print("  %s %d: растяжка по столбцам до %.2f, по строкам до %.2f" % (job, seed, 1 + sv, 1 + sh))


def do_render(jobs):
    import argparse as ap2
    import long_object as lo
    import probe_object as po
    ns = ap2.Namespace(models=po.gen_hd.DEFAULT_MODELS_DIR, qwen21_model="", qwen21_steps=tg.STEPS, qwen21_cfg=tg.CFG,
                       qwen21_mp=tg.MP, qwen21_strength=0.0, qwen21_offload="model", qwen21_thrifty=False, qwen21_ref="",
                       qwen21_ref_mp=1.0, qwen21_prompt="strict", qwen21_hint="off", qwen21_ref_order="ref-first")
    painter = po.gen_hd.Qwen21Painter(ns, {"ground": ("", "")})
    args = ap2.Namespace(steps=tg.STEPS, cfg=tg.CFG, mp=tg.MP)
    t0, n = time.time(), 0
    for job in jobs:
        J = tg.JOBS[job]
        sd = os.path.join(GEN, job)
        os.makedirs(os.path.join(sd, "raw"), exist_ok=True)
        text, neg = tg.build_prompt(job)
        print("[%s]\n  PROMPT: %s\n  NEG: %s" % (job, text, neg), flush=True)
        po.gen_fire.NEGATIVE = neg
        _comp, full, _at = tg.comp_of(job)
        frame = full.crop(tg.padded_box(full))
        flat = lo.model_input(frame, tg.ZOOM, J["how"])
        flat.save(os.path.join(sd, "raw", "input.png"))
        for seed in J["seeds"]:
            if os.path.exists(os.path.join(sd, "raw", "%d.png" % seed)):
                print("[%s] зерно %d уже есть" % (job, seed), flush=True)
                continue
            hd = po.gen_fire.run_pass(painter, args, text, flat, seed)
            po.gen_hd.save_png(hd, os.path.join(sd, "raw", "%d.png" % seed))
            cut_seed(job, seed)
            n += 1
            print("[%s] зерно %d готово (%d), %.0f с" % (job, seed, n, time.time() - t0), flush=True)


def do_recut(jobs):
    for job in jobs:
        for seed in tg.JOBS[job]["seeds"]:
            if os.path.exists(os.path.join(GEN, job, "raw", "%d.png" % seed)):
                cut_seed(job, seed)
        print("перевырезано:", job)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["render", "recut", "prompts", "seeds", "build", "scene"])
    ap.add_argument("--jobs", nargs="*", default=list(tg.JOBS), choices=sorted(tg.JOBS))
    a = ap.parse_args()
    if a.cmd == "prompts":
        for j in a.jobs:
            t, n = tg.build_prompt(j)
            print("[%s]\n  PROMPT: %s\n  NEG: %s" % (j, t, n))
    elif a.cmd == "render":
        do_render(a.jobs)
    elif a.cmd == "recut":
        do_recut(a.jobs)
    else:
        import t418_post
        getattr(t418_post, "do_" + a.cmd)()
    return 0


if __name__ == "__main__":
    sys.exit(main())
