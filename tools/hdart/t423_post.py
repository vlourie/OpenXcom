#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000423, после генерации (t423_carcass_gen.py render): нарезка по клеткам, срез у пола, проверки, семья, листы, установщик.

    py -3.13 tools\hdart\t423_post.py build          # кадры по всем зёрнам art/tickets/t423/cand/s<зерно>/, таблица проверок
    py -3.13 tools\hdart\t423_post.py family         # перекраски U_DISEC2GOLD:5, 8, 9 из основы (по зёрнам, в cand)
    py -3.13 tools\hdart\t423_post.py sheet          # листы t423_whole.png, t423_edges.png, t423_scene_*.png, t423_scene_zoom.png
    py -3.13 tools\hdart\t423_post.py cand           # ведущий лист t423_cand.png из них
    py -3.13 tools\hdart\t423_post.py install --seed N [--yes]   # по выбору Vitali, под очередью правок; без --yes - сухой прогон
В мод ничего не ставит без `install --yes`.
"""
import argparse
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                                   # noqa: E402
from PIL import Image                                # noqa: E402
import t423_carcass_gen as G                         # noqa: E402
import t417_container_gen as g                       # noqa: E402

K, SET, CELLS, FRAMES = G.K, G.SET, G.CELLS, G.FRAMES
GEN, CAND, REV, SEEDS = G.GEN, G.CAND, G.REV, G.SEEDS
BGC = g.BGC
COMPARE = []                  # (подпись, зерно, папка кандидатов) прошлых кругов, которые показываются на листах рядом
RAWDIR = os.path.join(G.GEN, "raw")     # круг 4: ответы с зеркально повёрнутой головой (t423_mirror.py) лежат в raw_r4, кандидаты - в cand_r4
SUF = ""                      # "_r2" - круг 2 (зёрна G.SEEDS_R2, голова перевёрнута): листы и таблица со своим хвостом
GOLD_FRAMES = [5, 8, 9]


# ---------------------------------------------------------------------------------------------------------
# нижняя кромка у пола: срез по ромбам клеток пола, которые движок рисует ПОЗЖЕ клетки кадра
# ---------------------------------------------------------------------------------------------------------
def later_floor_cover(items, lat, shape, inset=G.FLOOR_INSET, ss=4):
    """Для каждой клетки раскладки - доля покрытия (0..1, x4 холст) ромбами пола соседних клеток, которых в раскладке нет и которые
    рисуются после неё (порядок движка: y, потом x). Ромб пола клетки: |x - cx| / 2 + |y - cy| <= 8 (центр (16, 32) окна кадра, базовые пиксели),
    граница отодвинута внутрь на inset пикселей HD (вертикально) - срез идёт ПРЯМОЙ у ромба соседа, а не по ступеньке его HD-пола (t418).
    -> {индекс клетки: float (H4, W4)}."""
    H4, W4 = shape
    yy, xx = np.mgrid[0:H4 * ss, 0:W4 * ss].astype(np.float32)
    X, Y = (xx + 0.5) / (K * ss), (yy + 0.5) / (K * ss)
    have = {(i["c"], i["r"]) for i in items}
    lim = 8.0 - inset / K
    out = {}
    cache = {}
    for n, it in enumerate(items):
        cov = np.zeros((H4 * ss, W4 * ss), bool)
        for c in range(it["c"] - 3, it["c"] + 4):
            for r in range(it["r"] - 3, it["r"] + 4):
                if (c, r) in have or (r, c) <= (it["r"], it["c"]):
                    continue
                if (c, r) not in cache:
                    cx = lat.ox + (c - r) * 16 + 16
                    cy = lat.oy + (c + r) * 8 + 32
                    cache[(c, r)] = (np.abs(X - cx) / 2.0 + np.abs(Y - cy)) <= lim
                cov |= cache[(c, r)]
        out[n] = cov.reshape(H4, ss, W4, ss).mean((1, 3)).astype(np.float32)
    return out


# ---------------------------------------------------------------------------------------------------------
# ответ модели -> холст x4, подогнанный под силуэт классики (оптический поток по силуэтам)
# ---------------------------------------------------------------------------------------------------------
FLOW_S = 8                  # рабочий масштаб потока (пикселей на пиксель базы)
CUT_GROW = 3               # на сколько пикселей x4 силуэт классики отступает от рисунка, прежде чем срезаться по нему
FLOW_BLUR = 6.0             # размытие силуэтов перед потоком (пикс x FLOW_S)


def flow_fit(sc, seed, pre):
    """Ответ модели -> (rgb x4 холста, альфа ответа x4 после подгонки, IoU до / после потока). Модель рисует стол уже и мельче классики и не
    держит соотношение стол/голова (голова вылезает дальше стола, а у классики стол шире головы), поэтому габарит по bbox (po.cut_out)
    даёт грязь по краям силуэта. Здесь: 1) bbox-подгонка матрицы ответа (obj_photo.edge_matte) к габариту классики; 2) плотный
    оптический поток DIS между размытыми силуэтами (цель - многоугольник классики, ровный) и матрицей ответа; 3) ответ переносится потоком.
    Рисунок внутри не трогается ничем, кроме гладкого смещения, - ракурс и детали остаются модельными."""
    import cv2
    import obj_photo as op
    items, W, H, verts, al, sil = pre
    full = g.compose_k1(sc, items, W, H)
    box = g.padded_box(full)
    frame = full.crop(box)
    fw, fh = frame.size
    S = FLOW_S
    cx0, cy0, cx1, cy1 = box
    tgt = cv2.resize(al[cy0 * K:cy1 * K, cx0 * K:cx1 * K].astype(np.float32), (fw * S, fh * S), interpolation=cv2.INTER_AREA)
    hd = Image.open(os.path.join(RAWDIR, "%d.png" % seed)).convert("RGB")
    m = op.edge_matte(hd)
    ys, xs = np.nonzero(m > 0.5)
    rb = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
    ob = tuple(v * S for v in frame.split()[3].getbbox())
    sx, sy = (ob[2] - ob[0]) / (rb[2] - rb[0]), (ob[3] - ob[1]) / (rb[3] - rb[1])
    M = np.array([[sx, 0, ob[0] - rb[0] * sx], [0, sy, ob[1] - rb[1] * sy]], np.float32)
    dsize = (fw * S, fh * S)
    rgb = cv2.warpAffine(np.asarray(hd), M, dsize, flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)
    mat = cv2.warpAffine(m.astype(np.float32), M, dsize, flags=cv2.INTER_LINEAR)
    a8 = np.clip(cv2.GaussianBlur(tgt, (0, 0), FLOW_BLUR) * 255, 0, 255).astype(np.uint8)
    b8 = np.clip(cv2.GaussianBlur(mat, (0, 0), FLOW_BLUR) * 255, 0, 255).astype(np.uint8)
    dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    dis.setFinestScale(1)
    dis.setPatchSize(16)
    dis.setPatchStride(4)
    dis.setVariationalRefinementIterations(10)
    flow = dis.calc(a8, b8, None)
    gx, gy = np.meshgrid(np.arange(dsize[0], dtype=np.float32), np.arange(dsize[1], dtype=np.float32))
    mx, my = gx + flow[..., 0], gy + flow[..., 1]
    wrgb = cv2.remap(rgb, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    wm = cv2.remap(mat, mx, my, cv2.INTER_LINEAR, borderValue=0)
    iou0 = float(((tgt > .5) & (mat > .5)).sum() / ((tgt > .5) | (mat > .5)).sum())
    iou1 = float(((tgt > .5) & (wm > .5)).sum() / ((tgt > .5) | (wm > .5)).sum())
    part = cv2.resize(wrgb, (fw * K, fh * K), interpolation=cv2.INTER_AREA)
    pm = cv2.resize(wm, (fw * K, fh * K), interpolation=cv2.INTER_AREA)
    cut = np.zeros((H * K, W * K, 4), np.uint8)
    cut[cy0 * K:cy1 * K, cx0 * K:cx1 * K, :3] = part
    cut[cy0 * K:cy1 * K, cx0 * K:cx1 * K, 3] = np.clip(pm * 255, 0, 255).astype(np.uint8)
    return cut, full, iou0, iou1


def body_rgb_flow(sc, seed, pre):
    """RGB холста x4: ответ подогнан потоком (flow_fit), тон к классике (po.match_tone), цвет у кромки продлён из ядра (od.spread),
    низкочастотный тон по областям от классики (g.lowfreq_tone) - как g.body_rgb в 417."""
    import probe_object as po
    import obj_derive as od
    from PIL import ImageFilter
    cut, full, iou0, iou1 = flow_fit(sc, seed, pre)
    items, W, H = pre[0], pre[1], pre[2]
    box = g.padded_box(full)
    frame = full.crop(box)
    sub = Image.fromarray(cut[box[1] * K:box[3] * K, box[0] * K:box[2] * K], "RGBA")
    sub = po.match_tone(sub, frame, g.TONE)
    cut2 = cut.copy()
    cut2[box[1] * K:box[3] * K, box[0] * K:box[2] * K] = np.asarray(sub)
    a = cut2.astype(np.float32)
    core = np.asarray(Image.fromarray(((a[..., 3] > 240) * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(3))) > 0   # узкое ядро: ухо и морда тонкие, широкое съедает их
    rgb = np.empty_like(a[..., :3])
    for c in range(3):
        rgb[..., c] = od.spread(a[..., c], core, 40)
    return g.lowfreq_tone(np.clip(rgb, 0, 255), full), (iou0, iou1), cut[..., 3].astype(np.float32) / 255.0


def build_seed(sc, seed, pre):
    """Ответ модели -> холст x4, кадры 128x160 (нарезка 417 + срез у пола), инфо."""
    items, W, H, verts, al, sil = pre
    rgb, ious, pm = body_rgb_flow(sc, seed, pre)
    # контур: ровный многоугольник классики; убирается только то, чего у подогнанного ответа нет с запасом CUT_GROW пикселей x4
    # (кончики ног, выемка у уха) - там край идёт по контуру самого рисунка (гладкому, не лесенкой), везде внутри альфа 255
    import cv2
    sup = (pm > 0.5).astype(np.uint8)
    r = CUT_GROW
    sup = cv2.dilate(sup, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
    keep = cv2.GaussianBlur(sup.astype(np.float32), (0, 0), 0.8)
    al = np.clip(al * keep, 0.0, 1.0)
    al[al < 0.004] = 0.0
    canvas = g.canvas_of(rgb, al)
    lat = g.Lattice(items, al.shape)
    w0 = np.zeros(al.shape[1] + 8)                      # границы рядов - прямые решётки (у стола нет парных кадров)
    own, fb, nfree = g.territory_owners(items, al, sil, lat, w0, 0)
    frames = g.slice_frames(canvas, al, items, sil, own)
    # без головы (D_RET_BASE: кадра 5 на карте нет) стол должен остаться целым: каждый кадр несёт и сплошные пиксели своего силуэта
    # классики вне своей территории (одни и те же пиксели общей картинки у соседей - двойного наложения нет, а у кадра 5 поверх шеи
    # лежат те же пиксели)
    extra = {}
    for n, it in enumerate(items):
        arr = np.asarray(frames[it["f"]]).copy()
        sl = (slice(it["y"] * K, it["y"] * K + 160), slice(it["x"] * K, it["x"] * K + 128))
        add = sil[n][sl] & (al[sl] >= 1.0) & (arr[..., 3] == 0)
        arr[add] = canvas[sl][add]
        frames[it["f"]] = Image.fromarray(arr, "RGBA")
        extra[it["f"]] = int(add.sum())
    cover = later_floor_cover(items, lat, al.shape)
    cut_px = {}
    for n, it in enumerate(items):
        a = np.asarray(frames[it["f"]]).astype(np.float32).copy()
        keep = cover[n][it["y"] * K:it["y"] * K + 160, it["x"] * K:it["x"] * K + 128]
        h, w = keep.shape
        before = int((a[:h, :w, 3] > 0).sum())
        a[:h, :w, 3] *= (1.0 - keep)
        a[a[..., 3] < 1.0, :] = 0
        frames[it["f"]] = Image.fromarray(np.rint(a).astype(np.uint8), "RGBA")
        cut_px[it["f"]] = before - int((a[..., 3] > 0).sum())
    any_cover = np.zeros(al.shape, bool)
    for n in cover:
        any_cover |= cover[n] > 0
    info = dict(extra=extra, verts=verts, al=al, iou=ious, fallback=fb, free=nfree, cut_px=cut_px, any_cover=any_cover, canvas=canvas)
    return canvas, frames, info


def do_build(a=None):
    import ticket_scene as ts
    sc = ts.Scene()
    pre = g.prep(sc)
    items, W, H, verts, al, sil = pre
    print("многоугольник контура: %d вершин" % len(verts))
    cl = g.classic_frames(sc)
    now = g.hd_now_frames(sc)
    ref = g.owner_map(cl, items, W, H)
    rows = []
    variants = [("классика x4", cl, None), ("HD сейчас", now, None)]
    seeds = [s for s in SEEDS if os.path.exists(os.path.join(RAWDIR, "%d.png" % s))]
    for s in seeds:
        canvas, frames, info = build_seed(sc, s, pre)
        d = os.path.join(CAND, "s%d" % s)
        os.makedirs(d, exist_ok=True)
        for f, im in frames.items():
            im.save(os.path.join(d, "%s_%d.png" % (SET, f)))
        Image.fromarray(canvas, "RGBA").save(os.path.join(d, "_canvas.png"))
        variants.append(("зерно %d" % s, frames, info))
        print("зерно %d: IoU матрицы ответа с силуэтом классики по bbox %.3f -> после потока %.3f; запасных назначений кромки %d, свободных сплошных пикселей %d, срезано у пола пикселей по кадрам %s; добавлено пикселей силуэта своей классики %s"
              % (s, info["iou"][0], info["iou"][1], info["fallback"], info["free"], info["cut_px"], info["extra"]))
    for name, frames, info in variants:
        sm = g.seam_metric(frames, items, W, H, ref=ref)
        row = dict(name=name, seam=sm[0], within=sm[1], engine=g.seam_metric(frames, items, W, H)[0])
        if info is not None:
            al, verts = info["al"], info["verts"]
            img = np.asarray(g.assemble(frames, items, W, H, K)).astype(np.float32)
            diff = np.abs(img[..., 3] / 255.0 - al)
            bad = ~info["any_cover"]
            row["holes"] = int(((al >= 0.999) & (img[..., 3] < 250) & bad).sum())
            row["mism"] = int(((diff > 0.02) & bad).sum())
            vis = (img[..., 3] > 250)
            cv = np.asarray(info["canvas"]).astype(np.float32)
            row["canvas_diff"] = float(np.abs(img[..., :3] - cv[..., :3])[vis & bad].max()) if (vis & bad).any() else 0.0
            dv = g.straightness(img[..., 3] / 255.0, verts)
            row["edge"] = max(d_[2] for d_ in dv) if dv else 0.0
        rows.append(row)
    os.makedirs(REV, exist_ok=True)
    out = os.path.join(REV, "t423_checks" + SUF + ".tsv")
    with open(out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["вариант", "шов (по границам клеток классики)", "внутри клетки", "шов как рисует движок", "просвет внутри контура, пикс",
                    "расхождение альфы с целью, пикс", "сборка == холст, макс. RGB", "отклонение кромки от прямой, пикс x4"])
        for r in rows:
            w.writerow([r["name"], "%.1f" % r["seam"], "%.1f" % r["within"], "%.1f" % r["engine"], r.get("holes", "-"), r.get("mism", "-"),
                        "%.1f" % r["canvas_diff"] if "canvas_diff" in r else "-", "%.2f" % r["edge"] if "edge" in r else "-"])
    for r in rows:
        print("%-12s шов %.1f (внутри %.1f, движком %.1f) | просвет %s расхождение %s | сборка-холст %s | кромка +-%s"
              % (r["name"], r["seam"], r["within"], r["engine"], r.get("holes", "-"), r.get("mism", "-"),
                 "%.1f" % r["canvas_diff"] if "canvas_diff" in r else "-", "%.2f" % r["edge"] if "edge" in r else "-"))
    print("таблица:", out)


# ---------------------------------------------------------------------------------------------------------
# семья: U_DISEC2GOLD:5, 8, 9 (GOLD:6 - другая классика, не трогаем; U_DISEC3GOLD - мёртвый набор, нет MCD и PCK в Пиратках)
# ---------------------------------------------------------------------------------------------------------
def gold_groove(im):
    """Классика GOLD 8 и 9 отличается от основы только жёлобом (сиреневый 214/196/178 -> золотой 255/255/180, 255/240/144, 249/231/123);
    кадр 5 совпадает с основой. HD: сиреневые пиксели жёлоба (синий выше зелёного) красятся золотым по яркости, остальное - как есть."""
    a = np.asarray(im.convert("RGBA")).astype(np.float32)
    r, gg, b = a[..., 0], a[..., 1], a[..., 2]
    w = np.clip((b - gg - 4.0) / 10.0, 0.0, 1.0) * (b >= r - 2.0) * (a[..., 3] > 0)
    lum = 0.299 * r + 0.587 * gg + 0.114 * b
    t = np.clip((lum - 165.0) / (218.0 - 165.0), 0.0, 1.0)[..., None]
    gold = np.array([249, 231, 123], np.float32) * (1 - t) + np.array([255, 255, 180], np.float32) * t
    a[..., :3] = a[..., :3] * (1 - w[..., None]) + gold * w[..., None]
    return Image.fromarray(np.clip(np.rint(a), 0, 255).astype(np.uint8), "RGBA"), float(w.sum())


def do_family(a=None):
    for s in avail_seeds():
        d = os.path.join(CAND, "s%d" % s)
        for f in GOLD_FRAMES:
            base = Image.open(os.path.join(d, "%s_%d.png" % (SET, f))).convert("RGBA")
            out, n = (base, 0.0) if f == 5 else gold_groove(base)
            out.save(os.path.join(d, "%sGOLD_%d.png" % (SET, f)))
            print("зерно %d: U_DISEC2GOLD:%d <- U_DISEC2:%d%s" % (s, f, f, "" if f == 5 else " (жёлоб сиреневый -> золотой, вес %.0f пикс)" % n))


# ---------------------------------------------------------------------------------------------------------
# листы
# ---------------------------------------------------------------------------------------------------------
def avail_seeds():
    return [s for s in SEEDS if os.path.exists(os.path.join(CAND, "s%d" % s, "%s_9.png" % SET))]


def seed_frames(seed, base=None):
    d = os.path.join(base or CAND, "s%d" % seed)
    return {f: Image.open(os.path.join(d, "%s_%d.png" % (SET, f))).convert("RGBA") for f in FRAMES}


def zoom_crop(im, box_base, z):
    x0, y0, x1, y1 = box_base
    c = im.crop((x0 * K, y0 * K, x1 * K, y1 * K))
    return c.resize((c.width * z, c.height * z), Image.NEAREST)


def do_sheet(a=None):
    import ticket_scene as ts
    sc = ts.Scene()
    items, W, H = g.make_items(CELLS)
    seeds = avail_seeds()
    variants = [("классика x4", g.classic_frames(sc)), ("HD сейчас", g.hd_now_frames(sc))] + [(lb, seed_frames(s, bd)) for lb, s, bd in COMPARE] + [("зерно %d" % s, seed_frames(s)) for s in seeds]
    full = [(n, g.assemble(f, items, W, H, K, BGC)) for n, f in variants]
    big = [(n, im.resize((im.width * 2, im.height * 2), Image.NEAREST)) for n, im in full]
    ts.sheet(big, os.path.join(REV, "t423_whole" + SUF + ".png"), cols=3)
    edges = []
    for n, im in full:
        edges.append((n + ": нижний край слева", zoom_crop(im, (0, 34, 34, 58), 4)))
        edges.append((n + ": нижний край справа", zoom_crop(im, (28, 34, 64, 58), 4)))
        edges.append((n + ": голова", zoom_crop(im, (0, 30, 28, 58), 4)))
    ts.sheet(edges, os.path.join(REV, "t423_edges" + SUF + ".png"), cols=3)
    heads = [(n + ": голова крупно", zoom_crop(im, (0, 36, 30, 62), 7)) for n, im in full]
    ts.sheet(heads, os.path.join(REV, "t423_head" + SUF + ".png"), cols=3)
    keys = [(SET, f) for f in FRAMES]
    ov = {s: {(SET, f): im for f, im in seed_frames(s).items()} for s in seeds}
    scenes = (("t423_scene_retdung10.png", "RETICULAN_DUNGEON", "RETDUNG_10", (150, 110)),
              ("t423_scene_snakeboat.png", "VES_SNAKEBOAT", "VES_SNAKEBOAT", (150, 110)),
              ("t423_scene_dret_base.png", "D_RET_BASE", "D_RET_BASE", (150, 110)))
    for name, terrain, block, (w, h) in scenes:
        name = name.replace(".png", SUF + ".png")
        found = ts.find_cells(sc, terrain, block, keys)
        zmin = min(f[3] for f in found)
        box = ts.window([(f[0], f[1], tuple(v * K for v in f[2])) for f in found], w, h, K)
        panels = []
        for title, mode, o in [("классика", "classic", None), ("HD сейчас", "hd", None)] + [("зерно %d" % s, "hd", ov[s]) for s in seeds]:
            im, _f = ts.Scene.render(sc, terrain, block, mode, override=o, k=K, maxz=zmin)
            panels.append((block + ": " + title, ts.crop_pad(im, box)))
        ts.sheet(panels, os.path.join(REV, name), cols=3)
        print("лист", os.path.join(REV, name))
        if block == "RETDUNG_10":              # стык стола с полом и нижняя кромка - крупно (в 2 раза больше полного размера, NEAREST)
            zp = []
            for t, im in panels:
                c = im.crop((190, 90, 470, 330))
                zp.append((t, c.resize((c.width * 2, c.height * 2), Image.NEAREST)))
            ts.sheet(zp, os.path.join(REV, "t423_scene_zoom" + SUF + ".png"), cols=3)
            print("лист", os.path.join(REV, "t423_scene_zoom" + SUF + ".png"))


def do_cand(a=None):
    """Ведущий лист t423_cand.png: весь стол (классика | сейчас | зёрна), потом сцена RETDUNG_10 в полный размер и крупно у пола."""
    names = ["t423_whole" + SUF + ".png", "t423_head" + SUF + ".png", "t423_scene_retdung10" + SUF + ".png", "t423_scene_zoom" + SUF + ".png"]
    ims = [Image.open(os.path.join(REV, n)).convert("RGB") for n in names]
    ims = [i if i.width <= 1800 else i.resize((1800, round(i.height * 1800 / i.width)), Image.LANCZOS) for i in ims]   # лист не шире экрана
    Wd = max(i.width for i in ims)
    Hd = sum(i.height for i in ims) + 8 * (len(ims) + 1)
    out = Image.new("RGB", (Wd, Hd), (12, 12, 14))
    y = 8
    for i in ims:
        out.paste(i, (0, y))
        y += i.height + 8
    out.save(os.path.join(REV, {"": "t423_cand.png", "_r2": "t423_cand2.png", "_r3": "t423_cand3.png", "_r4": "t423_cand4.png"}[SUF]))
    print("лист", os.path.join(REV, {"": "t423_cand.png", "_r2": "t423_cand2.png", "_r3": "t423_cand3.png", "_r4": "t423_cand4.png"}[SUF]), out.size)


# ---------------------------------------------------------------------------------------------------------
# установка (по выбору Vitali, под очередью правок)
# ---------------------------------------------------------------------------------------------------------
def do_install(a):
    if not a.seed:
        raise SystemExit("нужно --seed N: зерно, которое выбрал Vitali")
    d = os.path.join(CAND, "s%d" % a.seed)
    files = {}
    for f in FRAMES:
        files["TERRAIN/%s.PCK/%d.png" % (SET, f)] = os.path.join(d, "%s_%d.png" % (SET, f))
    for f in GOLD_FRAMES:
        files["TERRAIN/%sGOLD.PCK/%d.png" % (SET, f)] = os.path.join(d, "%sGOLD_%d.png" % (SET, f))
    for rel, p in files.items():
        im = Image.open(p)
        if im.size != (128, 160) or im.mode != "RGBA":
            raise SystemExit("%s: ждали RGBA 128x160, а %s %s" % (p, im.mode, im.size))
    import build_hd_pack as bp
    man = bp.load()
    for rel, p in files.items():
        old = man["files"].get(rel, {}).get("sha256", "")[:10] or "нет в манифесте"
        print("  %-36s <- s%d/%s  (манифест %s)" % (rel, a.seed, os.path.basename(p), old))
    if not a.yes:
        raise SystemExit("сухой прогон, кадров %d; --yes - записать в мод (под очередью правок, обе копии hd)" % len(files))
    import ticket_scene as ts
    n = ts.install_files(files, "t423_carcass_gen", "XP-000423: стол вскрытия U_DISEC2 одной картинкой, голова коровы, ровный контур",
                         "Vitali 30.10: вариант C по тикету XP-000423, зерно %d" % a.seed,
                         "t423: стол вскрытия U_DISEC2 5-9 и перекраски GOLD 5/8/9 (зерно %d)" % a.seed)
    print("установлено файлов:", n)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["build", "family", "sheet", "cand", "install"])
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--round", type=int, default=1, help="2 - круг 2 (голова на темечке, отменён), 3 - круг 3: голова плашмя на боку в профиль, зёрна 4251-4253, 4 - круг 4: голова 4251 отражена зеркально (t423_mirror.py)")
    a = ap.parse_args()
    global SUF, RAWDIR, CAND
    if a.round == 2:
        SUF = "_r2"
        SEEDS[:] = G.SEEDS_R2
    elif a.round == 3:
        SUF = "_r3"
        SEEDS[:] = G.SEEDS_R3
        COMPARE[:] = [("зерно 4232 (круг 1)", 4232, CAND)]
    elif a.round == 4:
        SUF = "_r4"
        SEEDS[:] = [4251]
        COMPARE[:] = [("4251 как было (круг 3)", 4251, CAND)]
        RAWDIR = os.path.join(G.GEN, "raw_r4")
        CAND = os.path.join(os.path.dirname(G.CAND), "cand_r4")
    globals()["do_" + a.cmd](a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
