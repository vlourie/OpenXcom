#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикеты XP-000394 (дерево с жёлтыми цветами на ферме CULTA_UBER) и XP-000395 (грядка капусты), варианты A по выбору Vitali
31.10, делаются вместе (один набор, один заход на видеокарте):
  394  основа - CULTIVAT_UBER:12 (дерево с цветами), семья: CULTIVAT:12 (зелёное), CULTIVAT_PP:12 (пурпурное, ОДОБРЕННЫЙ
       кадр - на листе помечен), GOTHIC:22 (побайтная копия классики CULTIVAT:12 - копия кандидата CULTIVAT:12).
       CULTIVAT_VR:12 НЕ делается (по слову Vitali). Трава под деревом - чистая: кадр = HD-пол набора (:0) под слоем
       дерева; слой дерева - из основы, граница слоя - по классике (трава ромба вне кроны и ствола берётся с HD-пола).
  395  основа - CULTIVAT_UBER:7 (кочан со складчатыми листьями на земле, ромб пола), семья: CULTIVAT:7 (серая серединка),
       CULTIVAT_PP:7 (пурпур) - перенос цвета классики своего набора (R-272), VILFRNITURE:104 - копия CULTIVAT:7.
В МОД НИЧЕГО НЕ СТАВИТ: кадры - art/tickets/t394/cand/<НАБОР>_<кадр>.png (394 и 395 вместе), листы -
art/_review/tickets_2026-10-31/.

Путь генерации - t405_409_gen / t443_gen (Qwen-Image-2.1 strict, 40 шагов, cfg 4, 1 Мп, вход - классика bicubic x16 на
подложке pick_background, негатив probe_object + battle_view, cut_out, match_tone 0.7); ракурс и свет - только battle_view
(дерево - вид object со своей травяной подушкой, грядка - вид floor, как XP-000302/304 в ticket_q21_probe).

    py -3.13 tools\hdart\t394_395_gen.py prompts
    py -3 tools\gpuq.py add --name t394-395 --prio 1 -- tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\t394_395_gen.py render
    py -3.13 tools\hdart\t394_395_gen.py seeds     # лист зёрен t394_395_seeds.png
    py -3.13 tools\hdart\t394_395_gen.py build     # кандидаты по BEST
    py -3.13 tools\hdart\t394_395_gen.py sheets    # t394_395_cand.png
    py -3.13 tools\hdart\t394_395_gen.py scene     # поле фермы на карте
"""
import argparse
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

REVD = os.path.join(ROOT, "art", "_review", "tickets_2026-10-31")
g.CAND = os.path.join(ROOT, "art", "tickets", "t394", "cand")
g.GEN = os.path.join(ROOT, "art", "tickets", "t394", "gen")
g.REV = REVD
CAND, REV = g.CAND, REVD

TREE_NEG = ("apples, red fruit, conifer, fir, palm, purple, dark almost black crown, fence, flower bed, fallen leaves, "
            "mushrooms, rocks")
CAB_NEG = ("flowers, tree, bush, rocks, grey stone, pebbles, weeds, grass blades, wheat, sand dune, bright orange, "
           "text, bowl, plate, vase, lettuce leaves on a plate")
JOBS = {
    "tree12": dict(
        members=[("CULTIVAT_UBER", 12, (0, 0, 0))], seeds=[3941, 3942, 3943, 3944, 3945, 3946, 3947, 3948], r1=[],
        kind="object",
        what=("one round broadleaf tree with a dense rounded crown of mid green leaves covered with many small bright "
              "yellow flowers, a few thin brown branches visible between the clumps of leaves, and a short thick dark "
              "brown trunk that ends in the ground, standing on a small flat diamond-shaped patch of short mid green "
              "grass"),
        neg=TREE_NEG, slab=True),
    "cab7": dict(
        members=[("CULTIVAT_UBER", 7, (0, 0, 0))], seeds=[3951, 3952, 3953, 3954, 3955, 3956, 3957, 3958], r1=[],
        kind="floor",
        what=("a diamond-shaped bed of brown tilled soil with one big round cabbage head growing in the middle of it: "
              "tightly folded, wavy, ruffled leaves in several shades of green with pale cream-green veins, the leaves "
              "wrapping around a small pale cream-beige heart at the top centre of the head, a little bare brown soil "
              "visible around the cabbage"),
        neg=CAB_NEG, slab=False),
}
# --- переделка 31.10 (Vitali: «Переделать: без сердечка, кочан крупнее, до края ромба»): слово heart модель рисовала
# розовым сердечком, а «сохрани размер оригинала» держало кочан в 53% ширины ромба. Здесь сердцевина - гладкие бледные
# внутренние листья, размер оригинала не требуется, листья доходят до краёв ромба.
CAB2_NEG = CAB_NEG + (", heart shape, pink, red, rose, magenta, flower, pink centre, bright cream-white blob, "
                      "brown soil in the middle of the head")
KEEP2 = ("Redraw this same {noun} as detailed hand-painted game artwork: {what}. Keep the position of the diamond and "
         "the palette of <image1>, but the cabbage is much larger than in <image1>. Clear readable shapes, crisp "
         "edges, fine painted detail. ")
JOBS["cab7b"] = dict(
    members=[("CULTIVAT_UBER", 7, (0, 0, 0))], seeds=[3961, 3962, 3963, 3964, 3965, 3966], r1=[], kind="floor",
    keep=KEEP2,
    what=("a diamond-shaped bed of brown tilled soil almost completely covered by one huge round cabbage head: wavy, "
          "ruffled outer leaves in several shades of green with pale cream-green veins spread out over the whole bed "
          "until their tips almost reach the four edges of the diamond, and the top of the head is formed by smooth "
          "tightly folded pale cream-green inner leaves; only a thin strip of brown soil is visible at the very edge "
          "of the diamond"),
    neg=CAB2_NEG, slab=False)
JOBS["cab7c"] = dict(
    members=[("CULTIVAT_UBER", 7, (0, 0, 0))], seeds=[3971, 3972, 3973, 3974, 3975, 3976], r1=[], kind="floor",
    keep=KEEP2,
    what=("a diamond-shaped bed of brown tilled soil with one very large flat-spread cabbage plant: a ring of big "
          "wavy ruffled dark and mid green outer leaves lying out wide across the soil, one leaf pointing to each of "
          "the four corners of the diamond, and in the centre a rounded head of smooth pale cream-green inner leaves "
          "with gentle fold lines; the soil shows only in small gaps between the leaves"),
    neg=CAB2_NEG, slab=False)
CLUSTERS = {"394": ["tree12"], "395": ["cab7"]}
BEST = {"tree12": 3941, "cab7": 3953, "cab7b": 3961, "cab7c": 3971}

g.JOBS = JOBS
g.CLUSTERS = CLUSTERS
g.BEST = BEST
GAME = g.GAME


def build_prompt(job):
    """Как g.build_prompt (R-485), но вид у задания свой: object (дерево) или floor (грядка, TAIL_FLOOR)."""
    import battle_view as bv
    import probe_object as po
    import ticket_q21_probe as q
    J = JOBS[job]
    kind = J["kind"]
    pb = bv.prompt_block(kind)
    what = J["what"]
    if kind == "floor":
        tail = q.TAIL_FLOOR
        neg = po.NEGATIVE.replace("ground, grass tile, floor, ", "")
    else:
        tail = ("Output one isolated object with its own small grass patch on the same flat panel, nothing else: no "
                "other ground, no other tile, no other objects, no frame, no text.")
        neg = po.NEGATIVE.replace("ground, grass tile, floor, ", "")      # у дерева своя травяная подушка
    noun = "ground tile" if kind == "floor" else "object"
    text = (q.PANEL_HINT.replace("{what}", what) + bv.view_sentence(kind) + " "
            + J.get("keep", q.KEEP).replace("{noun}", noun).replace("{what}", what) + bv.light_sentence(kind) + " " + tail)
    neg = neg + ", " + pb["negative"] + ", " + J["neg"]
    return text, neg


g.build_prompt = build_prompt


def classic_of(s, f):
    return g_classic(s, f)


_CL = {}
_SCN = []


def g_classic(s, f):
    key = (s, f)
    if key not in _CL:
        import ticket_scene as ts
        if not _SCN:
            _SCN.append(ts.Scene())
        _CL[key] = Image.fromarray(np.asarray(_SCN[0].classic(s, f))[::4, ::4].copy(), "RGBA")
    return _CL[key]


def classic_idx(s, f):
    import water_build as wb
    if s not in _IDX:
        _IDX[s] = wb.read_set(s)
    return _IDX[s][f]


_IDX = {}
g.classic_of = g_classic


def hd_now(s, f):
    p = os.path.join(GAME, s + ".PCK", "%d.png" % f)
    return Image.open(p).convert("RGBA") if os.path.exists(p) else None


g.hd_now = hd_now


def clip_smooth(im, sprite_k1):
    import probe_object as po
    m = Image.fromarray((np.asarray(sprite_k1)[..., 3] > 0).astype(np.uint8) * 255, "L")
    sil = np.asarray(po.smooth_silhouette(m, 4)) > 8
    a = np.asarray(im).copy()
    out = int(((a[..., 3] > 0) & ~sil).sum())
    a[~sil, 3] = 0
    a[a[..., 3] == 0, :3] = 0
    return Image.fromarray(a, "RGBA"), out


g.clip_to_classic = clip_smooth

def cut_seed_matte(job, seed):
    """g.cut_seed, но альфа ответа - obj_photo.edge_matte (заливка от края останавливается на контуре предмета), а не ключ
    по цвету подложки (R-089: светлое тело на светлой подложке ключом полупрозрачно)."""
    try:
        import obj_photo
    except Exception:                    # venv видеокарты: сырой ответ сохранён, перевырезка - recut на CPU
        return _CUT_ORIG(job, seed)
    import probe_object as po
    J = JOBS[job]
    _comp, full, _at = g.comp_of(job)
    box = g.padded_box(full)
    frame = full.crop(box)
    hd = Image.open(os.path.join(g.GEN, job, "raw", "%d.png" % seed)).convert("RGB")
    matte = obj_photo.edge_matte(hd)
    part = po.match_tone(po.cut_out(hd, frame, g.GROW, g.SOFT, max_aspect=J.get("aspect", 1.3), matte=matte), frame, g.TONE)
    cut = Image.new("RGBA", (full.width * 4, full.height * 4), (0, 0, 0, 0))
    cut.paste(part, (box[0] * 4, box[1] * 4))
    cut.save(os.path.join(g.GEN, job, "%d.png" % seed))


_CUT_ORIG = g.cut_seed
g.cut_seed = cut_seed_matte

# --- семьи ----------------------------------------------------------------------------------------------------------
TREE_BASE = ("CULTIVAT_UBER", 12)
TREE_FAM = [("CULTIVAT_UBER", 12), ("CULTIVAT", 12), ("CULTIVAT_PP", 12)]   # + GOTHIC:22 копией CULTIVAT:12
CAB_BASE = ("CULTIVAT_UBER", 7)
CAB_FAM = [("CULTIVAT_UBER", 7), ("CULTIVAT", 7), ("CULTIVAT_PP", 7)]        # + VILFRNITURE:104 копией CULTIVAT:7
TREE_COPY = {("CULTIVAT", 12): ("GOTHIC", 22)}
CAB_COPY = {("CULTIVAT", 7): ("VILFRNITURE", 104)}


LOW_ROW = 29      # ниже этой строки классики (k=1) в ромбе - ствол, тень и трава; выше - крона (низ кроны уходит в ромб до строки 28)


def floor_pix_mask():
    """Трава ромба пола в кадре дерева: пиксели ромба кадра 0, цвет которых - рампа травы пола (индексы 70-75 у зелёных
    наборов; у PP рампа 198-203, маска от зелёной классики общая - раскладка кадров 12 одна), и строки не выше 27
    (выше - низ кроны, у неё те же индексы). Возвращает bool 40x32."""
    a = classic_idx("CULTIVAT", 12)
    z = classic_idx("CULTIVAT", 0)
    fl = (a > 0) & (z > 0) & (a >= 70) & (a <= 75)
    fl[:27] = False
    return fl


def soft(mask_k1, sigma=2.2):
    """Мягкая доля x4 из маски классики: гауссиан и крутой порог, чтобы край был ровным."""
    from scipy import ndimage
    m4 = np.kron(mask_k1, np.ones((4, 4), bool)).astype(np.float32)
    s = ndimage.gaussian_filter(m4, sigma)
    return np.clip((s - 0.5) * 3.0 + 0.5, 0.0, 1.0)


def crown_alpha():
    """Доля слоя дерева для кроны: классика без травы ромба, строки выше LOW_ROW; ниже - только ствол (по цвету HD)."""
    cl = np.asarray(g_classic("CULTIVAT", 12))[..., 3] > 0
    crown = cl & ~floor_pix_mask()
    crown[LOW_ROW:] = False
    return soft(crown)


def shade_alpha():
    """Тень у основания ствола (тёмные пиксели ромба классики ниже кроны): множитель на HD-пол, 0..1."""
    z = classic_idx("CULTIVAT", 12)
    sh = (z > 0) & ~floor_pix_mask() & ~np.isin(z, list(WOOD_IDX))
    sh[:LOW_ROW] = False
    return soft(sh, 3.0)


WOOD_IDX = {168, 169, 170, 171, 172, 173, 248, 249, 250, 251, 252, 253}


def wood_mask_hd(layer):
    """Ствол и ветки HD по цвету (бурый, тёмный): bool x4. Читается у ОСНОВЫ до перекраски."""
    import cv2
    a = np.asarray(layer.convert("RGBA"), np.float32)
    hsv = cv2.cvtColor((a[..., :3] / 255.0).astype(np.float32), cv2.COLOR_RGB2HSV)
    hue, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    return (a[..., 3] > 128) & (hue >= 5) & (hue <= 42) & (val < 0.55) & (sat > 0.2)


def _lab(rgb):
    import cv2
    return cv2.cvtColor((np.clip(rgb, 0, 255) / 255.0).astype(np.float32).reshape(-1, 1, 3), cv2.COLOR_RGB2LAB).reshape(-1, 3)


def _rgb(lab):
    import cv2
    return np.clip(cv2.cvtColor(lab.astype(np.float32).reshape(-1, 1, 3), cv2.COLOR_LAB2RGB).reshape(-1, 3) * 255.0, 0, 255)


def _colorize(lab_src, lab_tgt, max_gain=1.6, lum_amount=0.9):
    """Яркость слоя - к статистике яркости классики цели (среднее и разброс, не раздувая разброс выше max_gain), цвет (a, b) -
    по яркости из классики цели (квадратичная подгонка a(L), b(L)). Оттенок рисунка основы (жёлтые цветы) не переносится:
    у зелёной и пурпурной классики цветов нет, иначе они остаются охристыми и малиновыми пятнами."""
    ms, ss = lab_src[:, 0].mean(), lab_src[:, 0].std() + 1e-3
    mt, st = lab_tgt[:, 0].mean(), lab_tgt[:, 0].std() + 1e-3
    gain = min(st / ss, max_gain)
    L = lab_src[:, 0] + (((lab_src[:, 0] - ms) * gain + mt) - lab_src[:, 0]) * lum_amount
    Lt = lab_tgt[:, 0]
    out = np.empty_like(lab_src)
    out[:, 0] = L
    for c in (1, 2):
        co = np.polyfit(Lt, lab_tgt[:, c], 2 if len(Lt) > 20 and Lt.std() > 1.0 else 0)
        out[:, c] = np.polyval(co, np.clip(L, Lt.min(), Lt.max()))
    return out


def recolor_stats(layer, base_key, key):
    """Слой дерева основы -> цвет классики цели (зелёное, пурпурное). Таблица цветов colormap_transfer на дереве даёт
    красно-синюю крапину (цветы основы лежат не там, где листья цели). Здесь по областям (листва и ствол отдельно;
    ствол HD - по цвету, эталон - ствол классики цели по индексам палитры): яркость по статистике классики цели, цвет -
    по яркости из классики цели (_colorize). Пол ромба в эталон не входит."""
    a = np.asarray(layer.convert("RGBA"), np.float32)
    cls = np.asarray(g_classic(*key), np.float32)
    idx = classic_idx(key[0], key[1])
    tree = (np.asarray(g_classic("CULTIVAT", 12))[..., 3] > 0) & ~floor_pix_mask()
    wood_c = np.isin(idx, list(WOOD_IDX)) & tree
    fol_c = tree & ~wood_c
    wood_h = wood_mask_hd(layer)
    live = (a[..., 3] > 128)
    out = a.copy()
    for src_m, tgt_m in ((live & ~wood_h, fol_c), (live & wood_h, wood_c)):
        if src_m.sum() < 50 or tgt_m.sum() < 5:
            continue
        out[..., :3][src_m] = _rgb(_colorize(_lab(a[..., :3][src_m]), _lab(cls[..., :3][tgt_m])))
    return Image.fromarray(np.rint(out).astype(np.uint8), "RGBA")


def compose_tree(layer, floor_img, wood4):
    """Слой дерева (RGBA x4, уже в цвете набора) поверх HD-пола набора. Слой берётся: крона (выше LOW_ROW) - по классике,
    ствол ниже - по цвету HD (wood4, у основы); трава ромба и фон слоя не берутся - вместо них HD-пол. Тень у ствола -
    множитель на пол. Альфа результата - объединение пола и слоя."""
    from scipy import ndimage
    L = np.asarray(layer, np.float32)
    F = np.asarray(floor_img.convert("RGBA"), np.float32)
    low = np.zeros(L.shape[:2], bool)
    low[LOW_ROW * 4:] = True
    trunk = ndimage.gaussian_filter(ndimage.binary_dilation(wood4 & low, iterations=2).astype(np.float32), 1.6)
    ta = np.maximum(crown_alpha(), np.clip((trunk - 0.5) * 3.0 + 0.5, 0, 1))
    la = L[..., 3] / 255.0 * ta
    sh = shade_alpha()
    Fr = F[..., :3] * (1.0 - 0.42 * sh)[..., None]
    fa = F[..., 3] / 255.0
    a = la + fa * (1 - la)
    rgb = (L[..., :3] * la[..., None] + Fr * (fa * (1 - la))[..., None]) / np.maximum(a, 1e-4)[..., None]
    out = np.zeros(L.shape, np.uint8)
    out[..., :3] = np.rint(np.clip(rgb, 0, 255))
    out[..., 3] = np.rint(np.clip(a, 0, 1) * 255)
    return Image.fromarray(out, "RGBA")


def diamond_alpha(overlap=0.04, aa=0.02):
    """Ромб пола x4 с перехлёстом (R-291) и мягкой кромкой около 1.3 пикселя - прямая линия 2:1 без лесенки (R-568)."""
    import rim_alpha as ra
    d, _u, _v = ra.diamond(4)
    return np.clip((1.0 + overlap + aa / 2 - d) / aa, 0.0, 1.0)


def _seg_cab(rgb):
    """Области грядки по цвету: 0 земля (бурая), 1 листья (зелёные и прочие), 2 сердцевина (светлая, бледная)."""
    import cv2
    x = np.clip(rgb, 0, 255).astype(np.float32).reshape(-1, 1, 3) / 255.0
    hsv = cv2.cvtColor(x, cv2.COLOR_RGB2HSV).reshape(-1, 3)
    hue, sat, val = hsv[:, 0], hsv[:, 1], hsv[:, 2]
    lab = np.ones(len(hue), np.int8)
    soil = (hue >= 8) & (hue <= 48) & (sat > 0.35)
    core = (sat < 0.5) & (val > 0.55) & ~soil
    lab[soil] = 0
    lab[core] = 2
    return lab


def cab_recolor(gen_img, ob_key, key):
    """Грядка основы -> цвет классики цели по областям (земля, листья, сердцевина): яркость по статистике области классики
    цели, цвет по яркости из той же области (_colorize). Области цели берутся по раскладке классики ОСНОВЫ (одна на семью),
    colormap_transfer на грядке даёт сине-серый кочан и зелёное пятно в пурпурной."""
    a = np.asarray(gen_img.convert("RGBA"), np.float32)
    cb = np.asarray(g_classic(*ob_key), np.float32)
    ct = np.asarray(g_classic(*key), np.float32)
    live_b = cb[..., 3] > 0
    seg_b = np.full(cb.shape[:2], -1, np.int8)
    seg_b[live_b] = _seg_cab(cb[..., :3][live_b])
    live = a[..., 3] >= 128
    seg_h = np.full(a.shape[:2], -1, np.int8)
    seg_h[live] = _seg_cab(a[..., :3][live])
    out = a.copy()
    for r in (0, 1, 2):
        src = seg_h == r
        tm = (seg_b == r) & (ct[..., 3] > 0)
        if src.sum() < 50 or tm.sum() < 5:
            continue
        out[..., :3][src] = _rgb(_colorize(_lab(a[..., :3][src]), _lab(ct[..., :3][tm])))
    return Image.fromarray(np.rint(out).astype(np.uint8), "RGBA")


def cab_frame(gen_img, ob_key, key):
    """Грядка: кадр из основы (перенос цвета классики своего набора), альфа - точный ромб; пустоты ответа залиты тоном середины."""
    import rim_alpha as ra
    im = gen_img if key == ob_key else cab_recolor(gen_img, ob_key, key)
    a = np.asarray(im).copy()
    solid = a[..., 3] >= 200
    cur = a.copy()
    cur[..., 3] = np.where(solid, 255, 0)
    rgb = ra.fill(cur)
    d = diamond_alpha()
    out = np.zeros_like(a)
    out[..., :3] = np.where(solid[..., None], a[..., :3], np.clip(np.rint(rgb), 0, 255).astype(np.uint8))
    out[..., 3] = np.rint(d * 255).astype(np.uint8)
    out[..., :3][out[..., 3] == 0] = 0
    return Image.fromarray(out, "RGBA")


def do_build():
    import csv
    os.makedirs(CAND, exist_ok=True)
    new = {}
    for job in JOBS:
        for seed in g.all_seeds(job):
            if seed == BEST[job] or not os.path.exists(os.path.join(g.GEN, job, "%d.png" % seed)):
                continue
            for k, im in g.pieces_of(job, seed).items():
                d = os.path.join(CAND, "_seeds")
                os.makedirs(d, exist_ok=True)
                im.save(os.path.join(d, "%s_%d_s%d.png" % (k[0], k[1], seed)))
        for k, im in g.pieces_of(job, BEST[job]).items():
            new[job] = im
    out = {}
    # --- 394
    for key in TREE_FAM:
        base = new["tree12"]
        layer = base if key == TREE_BASE else recolor_stats(base, TREE_BASE, key)
        floor = hd_now(key[0], 0)
        im = compose_tree(layer, floor, wood_mask_hd(base))
        cls = g_classic(*key)
        g.check("394", key[0], key[1], im, cls)
        im2, cut = clip_smooth(im, cls)
        im2.save(os.path.join(CAND, "%s_%d.png" % key))
        out[key] = im2
        print("394 %s:%d: %s, срезано за силуэтом %d пикс." % (key[0], key[1], "основа" if key == TREE_BASE else "перенос цвета классики", cut))
        if key in TREE_COPY:
            c = TREE_COPY[key]
            im2.save(os.path.join(CAND, "%s_%d.png" % c))
            out[c] = im2
            print("394 %s:%d: копия %s:%d (классика побайтно та же)" % (c[0], c[1], key[0], key[1]))
    # --- 395
    for key in CAB_FAM:
        im = cab_frame(new["cab7"], CAB_BASE, key)
        g.check("395", key[0], key[1], im, g_classic(*key))
        im.save(os.path.join(CAND, "%s_%d.png" % key))
        out[key] = im
        print("395 %s:%d: %s" % (key[0], key[1], "основа" if key == CAB_BASE else "перенос цвета классики"))
        if key in CAB_COPY:
            c = CAB_COPY[key]
            im.save(os.path.join(CAND, "%s_%d.png" % c))
            out[c] = im
            print("395 %s:%d: копия %s:%d" % (c[0], c[1], key[0], key[1]))
    with open(os.path.join(REV, "t394_395_checks.tsv"), "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["вариант", "набор", "кадр", "за силуэтом классики x4 до среза, пикс", "дыры внутри (доля альфа<200)",
                    "яркость новое", "яркость классика", "яркость сейчас"])
        w.writerows(g.CHECK_ROWS)
    return out


def load_cand():
    ov = {}
    for fn in sorted(os.listdir(CAND)):
        if fn.endswith(".png"):
            s, f = fn[:-4].rsplit("_", 1)
            ov[(s, int(f))] = Image.open(os.path.join(CAND, fn)).convert("RGBA")
    return ov


def do_seeds():
    import ticket_scene as ts
    panels = []
    for job in JOBS:
        comp, full, at = g.comp_of(job)
        panels.append(("%s классика x4" % job, g.on_dark(full.resize((full.width * 4, full.height * 4), Image.NEAREST))))
        for seed in g.all_seeds(job):
            p = os.path.join(g.GEN, job, "%d.png" % seed)
            if os.path.exists(p):
                panels.append(("зерно %d" % seed, g.on_dark(Image.open(p).convert("RGBA"))))
    ts.sheet(panels, os.path.join(REV, "t394_395_seeds.png"), cols=5)
    print("лист:", os.path.join(REV, "t394_395_seeds.png"))


def do_sheets():
    """t394_395_cand.png: каждая строка - классика | сейчас | кандидат (394 сверху, 395 ниже)."""
    import ticket_scene as ts
    ov = load_cand()
    rows = []
    for key in TREE_FAM + [("GOTHIC", 22)]:
        mark = " (ОДОБРЕННЫЙ кадр - ПП)" if key[0] == "CULTIVAT_PP" else (" (копия классики CULTIVAT:12)" if key[0] == "GOTHIC" else "")
        rows.append(("394 %s:%d%s" % (key[0], key[1], mark), g.triple(key[0], key[1], ov[key])))
    for key in CAB_FAM + [("VILFRNITURE", 104)]:
        mark = " (ОДОБРЕННЫЙ кадр - ПП)" if key[0] == "CULTIVAT_PP" else (" (копия классики CULTIVAT:7)" if key[0] == "VILFRNITURE" else "")
        rows.append(("395 %s:%d%s" % (key[0], key[1], mark), g.triple(key[0], key[1], ov[key])))
    ts.sheet(rows, os.path.join(REV, "t394_395_cand.png"), cols=2)
    print("лист:", os.path.join(REV, "t394_395_cand.png"))


SCENES = [
    ("t394_cand_scene_trees.png", "CULTA_UBER", "CULTAFARM09", [("CULTIVAT_UBER", 12)], (150, 110)),
    ("t395_cand_scene_cabbage.png", "CULTA_UBER", "CULTAFARM11", [("CULTIVAT_UBER", 7)], (150, 110)),
]


def do_scene():
    import ticket_scene as ts
    sc = ts.Scene()
    ov = load_cand()
    for name, terrain, block, keys, (w, h) in SCENES:
        found = ts.find_cells(sc, terrain, block, keys)
        if not found:
            print("нет клеток", name)
            continue
        cell = max(found, key=lambda f: (-f[3], f[2][1]))
        box = ts.window([(cell[0], cell[1], tuple(v * 4 for v in cell[2]))], w, h, 4)
        maxz = cell[3]
        panels = []
        for title, mode, o in (("классика", "classic", None), ("HD сейчас", "hd", None), ("кандидат", "hd", ov)):
            im, _f = sc.render(terrain, block, mode, override=o, k=4, maxz=maxz)
            panels.append((title, ts.crop_pad(im, box)))
        ts.sheet(panels, os.path.join(REV, name), cols=1)
        print("лист:", os.path.join(REV, name), "клеток", len(found))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["render", "recut", "prompts", "seeds", "build", "sheets", "scene"])
    ap.add_argument("--jobs", nargs="*", default=[j for j in JOBS if j in ("tree12", "cab7")], choices=sorted(JOBS))
    ap.add_argument("--seq", action="store_true", help="render: последовательная выгрузка на CPU (карта занята Ollama)")
    a = ap.parse_args()
    if a.cmd == "prompts":
        for j in a.jobs:
            t, n = g.build_prompt(j)
            print("[%s]\n  PROMPT: %s\n  NEG: %s" % (j, t, n))
    elif a.cmd == "render":
        if a.seq:
            # карту делит Ollama (около 22 ГБ): трансформер fp8 целиком на карте уходит в shared, и сторож gpuq (R-213)
            # снимает задание на последнем шаге. Последовательная выгрузка держит на карте единицы ГБ
            import argparse as _ap
            _NS = _ap.Namespace

            class _SeqNS(_NS):
                def __init__(self, **kw):
                    if "qwen21_offload" in kw:
                        kw["qwen21_offload"] = "seq"
                    super().__init__(**kw)
            _ap.Namespace = _SeqNS
        g.do_render(a.jobs)
    elif a.cmd == "recut":
        g.recut(a.jobs)
    elif a.cmd == "seeds":
        do_seeds()
    elif a.cmd == "build":
        do_build()
    elif a.cmd == "sheets":
        do_sheets()
    else:
        do_scene()
    return 0


if __name__ == "__main__":
    sys.exit(main())
