#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикеты XP-000405 (лестницы XB1BR 26-29) и XP-000409 (капсулы XB3BITZ2:15/16, бочка XB2BR:24): заготовки по слову
Vitali «делай как считаешь нужным» (командир, 30.10). В МОД НИЧЕГО НЕ СТАВИТ: кадры - в
art/tickets/t402_409/cand/<вариант>/<НАБОР>_<кадр>.png (так их берёт t402_409_install.py), листы - в
art/_review/tickets_2026-10-30/.

  405B  лестницы: пара 27+26 и пара 28+29 - каждая ОДНОЙ картинкой на две клетки (составной, R-005), нарезка по
        клеткам obj_series.split. Семья: XBR1NEUTRAL 25-28 - копии классики, получают те же кадры; USOINT1 30/32/34 и
        LAM_FRN 7/8 - перенос цвета классики своего набора (obj_derive.transfer). LAM_FRN 9/10 и USOINT1 35 одобрены -
        НЕ трогаются.
  409A  капсула XB3BITZ2:15 новой основой; кадры анимации 50-56 - процедурно из неё (derive_anim: кнопка по яркости
        классики кадра, рябь - яркостная разница классики внутри маски anim_flicker.weight; anim_flicker.build_fix в
        режиме delta не годится - кладёт разницу по координатам классики, а у новой основы кнопка и диск в другом месте);
        обломок :16 нарисован отдельно (из основы не выводится: чёрные осколки вместо стекла), на входе - низ подставки
        новой основы :15. Бочка XB2BR:24 новой основой; семья (копии классики - тот же кадр, перекраски - перенос цвета
        классики своего набора). LINERSHIPC:4 одобрен - НЕ трогается.

Путь генерации - ticket_q21_probe / t276_gen.do_render: Qwen-Image-2.1 strict, 40 шагов, cfg 4, 1 Мп, вход - классика
(у лестниц обе клетки одним холстом) bicubic x16 на подложке pick_background, NEGATIVE probe_object + негатив
battle_view, cut_out (R-089: альфа - силуэт классики x4, а не фон ответа), match_tone 0.7. Ракурс и свет - ТОЛЬКО
battle_view (prompt_block / view_sentence / light_sentence). R-485: ромб - невидимая направляющая, плиты нет, у лестницы
широкая короткая форма без слова long. Три зерна на основу; лучшее выбирается по листу (BEST ниже), остальные -
cand/<вариант>/_seeds. Один процесс на весь прогон, готовое пропускается.

Круги генерации (30.10): 1 - лестница A "about seven treads" дала 9-10 тонких ступеней, капсула - тонкую колонну; 2 -
"exactly six deep steps" (лестница A, годно), "short stocky" (капсула, всё ещё узко); 3 - "fat wide jar" капсулы,
панель 96 вместо 176 (блик купола цвета панели ключ принимал за фон - fix_holes), обломок :16 с низом подставки :15.
Зёрна кругов, что не годятся, - в r1 заданий; их кадры лежат в art/tickets/t405_409/gen/<задание>/<зерно>.png
(нужны build; сырые ответы raw удалены - для перевырезки render нужен заново).

    py -3 tools\gpuq.py add --name t405-409-gen --prio 1 -- tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\t405_409_gen.py render
    py -3 tools\gpuq.py add --name t405-409-gen --prio 1 -- tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\t405_409_gen.py render --jobs capsule16
    py -3.13 tools\hdart\t405_409_gen.py seeds     # лист зёрен art/_review/tickets_2026-10-30/t405_409_seeds.png
    py -3.13 tools\hdart\t405_409_gen.py build     # кандидаты по BEST, семья, проверки, листы t405_cand.png / t409_cand.png
    py -3.13 tools\hdart\t405_409_gen.py scene     # сборка на карте (ticket_scene, override)
"""
import argparse
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (HERE, os.path.join(HERE, "..")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np                                   # noqa: E402
from PIL import Image, ImageDraw, ImageFilter, ImageOps   # noqa: E402

STEPS, CFG, MP, ZOOM, GROW, SOFT, PAD, TONE = 40, 4.0, 1.0, 16, 0, 40, 3, 0.7
CAND = os.path.join(ROOT, "art", "tickets", "t402_409", "cand")
GEN = os.path.join(ROOT, "art", "tickets", "t405_409", "gen")
REV = os.path.join(ROOT, "art", "_review", "tickets_2026-10-30")
GAME = os.path.join(ROOT, "Пиратки", "Dioxine_XPiratez", "user", "mods", "hd", "hd", "TERRAIN")

# --- задания ---------------------------------------------------------------------------------------------
STAIRS_NEG = "long thin ramp, narrow stairs, slab, floor plate, wooden steps, escalator"
JOBS = {
    # members: [(набор, кадр, (dx, dy))] - сдвиги кусков как в игре (27 в (x,y), 26 в (x,y+1): -16,+8)
    "stairsA": dict(
        members=[("XB1BR", 27, (0, 0, 0)), ("XB1BR", 26, (-16, 8, 0))], seeds=[4071, 4072, 4073, 4074],
        r1=[4051, 4052, 4053],        # круг 1 (about seven treads): вышло 9-10 тонких ступеней, лесенка-рампа
        what=("a very short, broad, chunky straight staircase with exactly six deep, wide, thick cream-tan metal "
              "steps, each step as deep as it is tall, each tread with a row of small dark rounded notches along its "
              "back edge, climbing from the lower left to the upper right; on the right side a solid dark "
              "maroon-brown steel side wall with vertical ribs and a column of small square holes, and under the top "
              "steps a dark hollow"),
        neg=STAIRS_NEG, slab=False),
    "stairsB": dict(
        members=[("XB1BR", 28, (0, 0, 0)), ("XB1BR", 29, (16, 8, 0))], seeds=[4061, 4062, 4063], r1=[],
        what=("a broad, short, straight staircase of about six wide dark grey-brown metal treads with thin tan edge "
              "lines, descending from the upper left to the lower right; on the left side a tall dark grey steel side "
              "wall with vertical tan ribs and a column of small round cream rivets, and a dark hollow under the top "
              "steps"),
        neg=STAIRS_NEG, slab=False),
    "capsule15": dict(
        members=[("XB3BITZ2", 15, (0, 0, 0))], seeds=[4195, 4196, 4197, 4198],
        r1=[4151, 4152, 4153, 4171, 4172, 4173, 4174, 4191, 4192, 4193, 4194],   # круги 1 и 2: стекло втрое уже классики (тонкая колонна)
        what=("a fat, wide glass jar-shaped capsule: a dark navy blue glass cylinder as wide as half of the whole "
              "base and about as tall as it is wide, with a bright white glint streak on the glass, a broad golden "
              "dome cap on top, standing on a thin grey metal platform disc with a small red button on its front, "
              "all on a flat low golden-bronze pedestal with a diamond footprint only twice as wide as the glass"),
        neg=("sand heap, pile, rubble, mottled spots, noise, blotches, bright blue, tall thin tube, slim tube, "
             "narrow cylinder, column, pillar, tower"), slab=True, panel=(96, 96, 102), aspect=2.2),
    "capsule16": dict(
        members=[("XB3BITZ2", 16, (0, 0, 0))], seeds=[4185, 4186, 4187, 4188],
        r1=[4161, 4162, 4163, 4181, 4182, 4183, 4184],   # круги 1-2: подставка другая, чем у капсулы, осколки мелкие
        base=("capsule15", 28),       # круг 3: низ подставки (где классики :15 и :16 совпадают) - из новой основы :15
        panel=(96, 96, 102), aspect=2.2,
        what=("a smashed glass capsule: on a flat low golden-bronze pedestal stands a grey metal platform disc with a "
              "small red button on its front, and on the disc a low wide heap of broken black glass shards with a "
              "tiny green spark among them; no golden cap and no intact glass"),
        neg="sand heap, rubble, mottled spots, noise, blotches, intact capsule, golden cap, glass cylinder", slab=True),
    "barrel24": dict(
        members=[("XB2BR", 24, (0, 0, 0))], seeds=[4241, 4242, 4243], r1=[],
        what=("a wooden barrel of grey-lilac brown vertical staves with a visible round lid on top and two dark iron "
              "hoops, one near the top rim and one near the bottom, crisp edges between the staves"),
        neg="barrel on a pallet, cask rack, lid with text, shiny metal", slab=False),
}
CLUSTERS = {"405B": ["stairsA", "stairsB"], "409A": ["capsule15", "capsule16", "barrel24"]}
# лучшее зерно по листу (заполняется после просмотра t405_409_seeds.png)
BEST = {"stairsA": 4071, "stairsB": 4063, "capsule15": 4197, "capsule16": 4186, "barrel24": 4241}


def all_seeds(job):
    return list(JOBS[job].get("r1", [])) + list(JOBS[job]["seeds"])


def comp_of(job):
    import map_mockup as mm
    import obj_series as osr
    w = mm.World()
    ms = JOBS[job]["members"]
    spr = {(s, f): w.sprite(s.lower(), f, None).convert("RGBA") for s, f, _o in ms}
    comp = {"members": [((s, f), o) for s, f, o in ms], "spr": spr, "pl": {(s, f): 0 for s, f, _o in ms}}
    full, at = osr.compose(comp)
    return comp, full, at


def padded_box(img, pad=PAD):
    bb = img.split()[3].getbbox()
    return (max(0, bb[0] - pad), max(0, bb[1] - pad), min(img.width, bb[2] + pad), min(img.height, bb[3] + pad))


def build_prompt(job):
    """Как ticket_q21_probe.build_prompt (R-485): ракурс и свет - фразы battle_view; ромб - невидимая направляющая."""
    import battle_view as bv
    import probe_object as po
    import ticket_q21_probe as q
    J = JOBS[job]
    pb = bv.prompt_block("object")
    what = J["what"]
    tail = q.TAIL_OBJ if not J["slab"] else (
        "Output one isolated object with its own pedestal on the same flat panel, nothing else: no ground, no tile, no "
        "other objects, no frame, no text.")
    text = (q.PANEL_HINT.replace("{what}", what) + bv.view_sentence("object") + " "
            + q.KEEP.replace("{noun}", "object").replace("{what}", what) + bv.light_sentence("object") + " " + tail)
    neg = po.NEGATIVE + ("" if J["slab"] else ", " + q.SLAB_NEG) + ", " + pb["negative"] + ", " + J["neg"]
    return text, neg


def cut_seed(job, seed):
    """Сырой ответ gen/<job>/raw/<seed>.png -> кадр x4 с альфой (cut_out, match_tone), без видеокарты. max_aspect у задания
    свой (J['aspect']): капсула нарисована у́же классики, растяжка 1.3 оставляла её тонкой колонной."""
    import probe_object as po
    J = JOBS[job]
    _comp, full, _at = comp_of(job)
    box = padded_box(full)
    frame = full.crop(box)
    hd = Image.open(os.path.join(GEN, job, "raw", "%d.png" % seed)).convert("RGB")
    part = po.match_tone(po.cut_out(hd, frame, GROW, SOFT, max_aspect=J.get("aspect", 1.3)), frame, TONE)
    cut = Image.new("RGBA", (full.width * 4, full.height * 4), (0, 0, 0, 0))
    cut.paste(part, (box[0] * 4, box[1] * 4))
    cut.save(os.path.join(GEN, job, "%d.png" % seed))


def recut(jobs):
    for job in jobs:
        for seed in all_seeds(job):
            if os.path.exists(os.path.join(GEN, job, "raw", "%d.png" % seed)):
                cut_seed(job, seed)
        print("перевырезано:", job)


def paste_base(base, full, box, src):
    """Вход обломка: низ подставки - новая основа капсулы (HD x4 -> x16 гладко) там, где классика :16 и :15 совпадают
    попиксельно (ниже строки row), чтобы подставка обломка не разошлась с подставкой капсулы."""
    import map_mockup as mm
    job15, row = base
    w = mm.World()
    c15 = np.asarray(w.sprite("xb3bitz2", 15, None).convert("RGBA"))
    c16 = np.asarray(full)
    same = (c15 == c16).all(-1) & (c16[..., 3] > 0)
    same[:row] = False
    hd15 = Image.open(os.path.join(GEN, job15, "%d.png" % BEST[job15])).convert("RGBA")
    sub = hd15.crop((box[0] * 4, box[1] * 4, box[2] * 4, box[3] * 4)).resize(src.size, Image.LANCZOS)
    m = Image.fromarray(same[box[1]:box[3], box[0]:box[2]].astype(np.uint8) * 255).resize(src.size, Image.NEAREST)
    m = m.filter(ImageFilter.GaussianBlur(ZOOM * 0.6))
    a = np.asarray(sub, np.float32).copy()
    a[..., 3] = a[..., 3] * np.asarray(m, np.float32) / 255.0
    out = src.copy()
    out.alpha_composite(Image.fromarray(a.astype(np.uint8), "RGBA"))
    return out


def do_render(jobs):
    import argparse as ap2
    import map_mockup as mm   # noqa: F401
    import probe_object as po
    ns = ap2.Namespace(models=po.gen_hd.DEFAULT_MODELS_DIR, qwen21_model="", qwen21_steps=STEPS, qwen21_cfg=CFG,
                       qwen21_mp=MP, qwen21_strength=0.0, qwen21_offload="model", qwen21_thrifty=False, qwen21_ref="",
                       qwen21_ref_mp=1.0, qwen21_prompt="strict", qwen21_hint="off", qwen21_ref_order="ref-first")
    painter = po.gen_hd.Qwen21Painter(ns, {"ground": ("", "")})        # одна загрузка модели на весь прогон
    args = ap2.Namespace(steps=STEPS, cfg=CFG, mp=MP)
    t0, n = time.time(), 0
    for job in jobs:
        J = JOBS[job]
        sd = os.path.join(GEN, job)
        os.makedirs(os.path.join(sd, "raw"), exist_ok=True)
        text, neg = build_prompt(job)
        print("[%s]\n  PROMPT: %s\n  NEG: %s" % (job, text, neg), flush=True)
        po.gen_fire.NEGATIVE = neg
        _comp, full, _at = comp_of(job)
        box = padded_box(full)
        frame = full.crop(box)
        panel = J.get("panel") or po.pick_background(frame)
        src = frame.resize((frame.width * ZOOM, frame.height * ZOOM), Image.BICUBIC)
        if J.get("base"):
            src = paste_base(J["base"], full, box, src)
        flat = Image.new("RGBA", src.size, tuple(panel) + (255,))
        flat.alpha_composite(src)
        if J.get("base"):
            flat.convert("RGB").save(os.path.join(sd, "raw", "input.png"))
        for seed in J["seeds"]:
            dst = os.path.join(sd, "%d.png" % seed)
            if os.path.exists(dst):
                print("[%s] зерно %d уже есть" % (job, seed), flush=True)
                continue
            hd = po.gen_fire.run_pass(painter, args, text, flat.convert("RGB"), seed)
            po.gen_hd.save_png(hd, os.path.join(sd, "raw", "%d.png" % seed))
            cut_seed(job, seed)
            n += 1
            print("[%s] зерно %d готово (%d), %.0f с" % (job, seed, n, time.time() - t0), flush=True)


# --- дальше - без видеокарты -----------------------------------------------------------------------------
def classic_mask(sprite_k1, size):
    """Силуэт классики x4 (NEAREST), bool."""
    m = (np.asarray(sprite_k1)[..., 3] > 0).astype(np.uint8) * 255
    return np.asarray(Image.fromarray(m).resize(size, Image.NEAREST)) > 0


def clip_to_classic(im, sprite_k1):
    """Альфа не выходит за силуэт классики x4 (R-089). Возвращает (кадр, сколько пикселей срезано)."""
    a = np.asarray(im).copy()
    m = classic_mask(sprite_k1, (a.shape[1], a.shape[0]))
    out = int(((a[..., 3] > 0) & ~m).sum())
    a[~m, 3] = 0
    a[a[..., 3] == 0, :3] = 0
    return Image.fromarray(a, "RGBA"), out


def fix_holes(im, deep=4):
    """Блик цвета подложки ключ принял за фон (R-089): внутри тела (глубже deep пикселей x4 от края) полупрозрачное
    делается непрозрачным, цвет - от ближайших надёжных пикселей (alpha >= 250)."""
    import obj_derive as od
    a = np.asarray(im).astype(np.float32).copy()
    al = a[..., 3]
    body = Image.fromarray(((al > 128) * 255).astype(np.uint8))
    out = body.copy()
    ImageDraw.floodfill(out, (0, 0), 128)          # внешний фон; незалитое нулевое - дыра внутри тела
    o = np.asarray(out)
    solid = (o != 128)                              # тело вместе с внутренними дырами
    inner = np.asarray(Image.fromarray(solid.astype(np.uint8) * 255).filter(ImageFilter.MinFilter(2 * deep + 1))) > 0
    bad = inner & (al < 250)
    if not bad.any():
        return im, 0
    rel = al >= 250
    for c in range(3):
        a[..., c] = od.spread(a[..., c], rel, 40)
    res = np.asarray(im).copy()
    res[bad, :3] = np.clip(a[bad][:, :3], 0, 255).astype(np.uint8)
    res[bad, 3] = 255
    return Image.fromarray(res, "RGBA"), int(bad.sum())


def pieces_of(job, seed):
    """Кадры задания {(набор, кадр): RGBA 128x160} из зерна: составной режется по клеткам, одиночный - как есть."""
    import obj_series as osr
    comp, full, at = comp_of(job)
    cut = Image.open(os.path.join(GEN, job, "%d.png" % seed)).convert("RGBA")
    cut, nfix = fix_holes(cut)
    if nfix:
        print("  %s зерно %d: непрозрачным сделано %d пикс. внутри тела (блик цвета подложки)" % (job, seed, nfix))
    if len(comp["members"]) == 1:
        k = comp["members"][0][0]
        return {k: cut.crop((0, 0, 128, 160))}
    return osr.split(cut, comp, at, GROW)


_SC = []


def classic_of(s, f):
    import ticket_scene as ts
    if (s, f) in NO_CLASSIC:
        s, f = "XB2BR", 24               # классика набора не читается; по таблице семьи - копия XB2BR:24
    if not _SC:
        _SC.append(ts.Scene())
    c = _SC[0].classic(s, f)
    return Image.fromarray(np.asarray(c)[::4, ::4].copy(), "RGBA")


def hd_now(s, f):
    p = os.path.join(GAME, s + ".PCK", "%d.png" % f)
    return Image.open(p).convert("RGBA") if os.path.exists(p) else None


def on_dark(im, bg=(36, 36, 40)):
    b = Image.new("RGBA", im.size, bg + (255,))
    b.alpha_composite(im.convert("RGBA"))
    return b.convert("RGB")


def mean_lum(im):
    a = np.asarray(im.convert("RGBA"), np.float32)
    m = a[..., 3] > 128
    return float((a[..., :3][m] * np.array([0.299, 0.587, 0.114])).sum(-1).mean()) if m.any() else 0.0


def put(variant, s, f, im, seeds=False):
    d = os.path.join(CAND, variant, "_seeds" if seeds else "")
    os.makedirs(d, exist_ok=True)
    im.save(os.path.join(d, "%s_%d.png" % (s, f)))


def do_seeds():
    import ticket_scene as ts
    panels = []
    for job, J in JOBS.items():
        comp, full, at = comp_of(job)
        row = [("%s классика x4" % job, on_dark(full.resize((full.width * 4, full.height * 4), Image.NEAREST)))]
        for seed in all_seeds(job):
            if os.path.exists(os.path.join(GEN, job, "%d.png" % seed)):
                cut = Image.open(os.path.join(GEN, job, "%d.png" % seed)).convert("RGBA")
                row.append(("зерно %d" % seed, on_dark(cut)))
        panels += row
    w = max(p[1].width for p in panels)
    cols = 4
    ts.sheet(panels, os.path.join(REV, "t405_409_seeds.png"), cols=cols)
    print("лист:", os.path.join(REV, "t405_409_seeds.png"))


def derive_anim(new15, work):
    """Кадры 50-56 из новой основы 15 процедурно. Классика 50-56 отличается от 15 двумя местами: огонёк (кнопка гаснет
    до 0.66-0.92 яркости) и рябь серого диска в стекле (до 25 пикселей базы). anim_flicker.build_fix в режиме delta кладёт
    разницу классики по её КООРДИНАТАМ, а у новой основы кнопка и диск стоят в других местах - пятна на подставке и чёрные
    квадраты в стекле. Поэтому здесь: (1) кнопка - красные пиксели новой основы множатся на отношение яркостей кнопки
    классики кадра f и кадра 15; (2) рябь - яркостная (без цвета) разница классики, размытая и ослабленная, внутри маски
    изменений anim_flicker.weight (вне маски кадр равен основе до байта). Альфа не меняется."""
    import anim_flicker as af
    import xcom_sprites as xs
    import loop_twins as lt
    files = lt.game_files()
    tab = files.get("XB3BITZ2.TAB")
    fr = xs.read_pck(str(files["XB3BITZ2.PCK"]), str(tab) if tab else None)
    pal = af.load_pal()
    base = np.asarray(new15, np.float32).copy()
    r, g, b, al = base[..., 0], base[..., 1], base[..., 2], base[..., 3]
    red = (r > 150) & (g < 90) & (b < 90) & (al > 200)
    redsoft = np.asarray(Image.fromarray(red.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(3)).filter(
        ImageFilter.GaussianBlur(1.0)), np.float32) / 255.0 * (al > 0)
    c15 = np.asarray(fr[15])
    lumw = np.array([0.299, 0.587, 0.114], np.float32)

    def cl(ix):
        a = np.zeros(ix.shape + (3,), np.float32)
        m = ix > 0
        a[m] = pal[ix[m]]
        return a

    out = {}
    for f in range(50, 57):
        cf = np.asarray(fr[f])
        a15, af_ = cl(c15), cl(cf)
        # (1) кнопка классики: строки 29-32 (огонёк), только изменённые пиксели
        sl = (slice(29, 33), slice(11, 19))
        ch = (c15[sl] != cf[sl])
        gain = float((af_[sl][ch] @ lumw).mean() / max(1e-3, (a15[sl][ch] @ lumw).mean())) if ch.any() else 1.0
        # (2) рябь: яркостная разница классики, гладко x4
        dl = (af_ @ lumw - a15 @ lumw) * (c15 > 0) * (cf > 0)
        k = base.shape[1] // c15.shape[1]
        big = af.gauss(np.repeat(np.repeat(dl, k, 0), k, 1).astype(np.float32), k * 0.7)
        w = af.weight(c15, cf, k, 2)[..., 0]
        res = base.copy()
        sh = big * w * 0.5
        res[..., :3] += sh[..., None] * (al > 0)[..., None]
        res[..., :3] *= (1.0 - redsoft * (1.0 - gain))[..., None]
        res = np.clip(np.rint(res), 0, 255)
        out[f] = Image.fromarray(res.astype(np.uint8), "RGBA")
        m = af.measure(c15, cf, np.asarray(new15, np.float32), res, 2)
        print("  анимация %d: кнопка x%.2f, классика изменила %d пикс., HD вне маски %.2f (порог мигания %.1f), внутри %.2f"
              % (f, gain, m["ch_px"], m["out_diff"], af.OUT_DIFF, m["in_diff"]))
    return out


def iou(a, b):
    ma, mb = np.asarray(a)[..., 3] > 0, np.asarray(b)[..., 3] > 0
    u = (ma | mb).sum()
    return float((ma & mb).sum() / u) if u else 0.0


def same_px(a, b):
    return np.array_equal(np.asarray(a), np.asarray(b))


def inner_holes(im, sprite_k1):
    """Доля пикселей глубоко внутри силуэта классики (отступ 3 пикс x4), где альфа ниже 200 - подложка/дыры (R-089)."""
    m = classic_mask(sprite_k1, im.size)
    deep = np.asarray(Image.fromarray(m.astype(np.uint8) * 255).filter(ImageFilter.MinFilter(13))) > 0
    a = np.asarray(im)[..., 3]
    return float((a[deep] < 200).mean()) if deep.any() else 0.0


def edge_panel(im, sprite_k1):
    """Подложка по краю: доля полупрозрачных пикселей (1..199) вне глубины силуэта - мягкая кайма, не плита."""
    a = np.asarray(im)[..., 3]
    return float(((a > 0) & (a < 200)).sum() / max(1, (a > 0).sum()))


CHECK_ROWS = []


def check(variant, s, f, new, cls):
    """Строка проверок: силуэт за классикой x4 (до среза), дыры внутри, тон новый/классика/сейчас."""
    out_before = int(((np.asarray(new)[..., 3] > 0) & ~classic_mask(cls, new.size)).sum())
    cur = hd_now(s, f)
    CHECK_ROWS.append([variant, s, f, out_before, "%.4f" % inner_holes(new, cls),
                       "%.1f" % mean_lum(new), "%.1f" % mean_lum(Image.fromarray(np.asarray(cls))),
                       "%.1f" % mean_lum(cur) if cur is not None else "-"])


def finish(variant, s, f, im):
    """Срез по силуэту классики x4, проверки, запись заготовки."""
    cls = classic_of(s, f)
    check(variant, s, f, im, cls)
    im2, _out = clip_to_classic(im, cls)
    put(variant, s, f, im2)
    return im2


NO_CLASSIC = {("MILURBAN", 85)}


def finish_copy(variant, key, im):
    """Копия классики без чтения самой классики: срез по силуэту основы XB2BR:24 (копия побайтно)."""
    im2, _out = clip_to_classic(im, classic_of("XB2BR", 24))
    put(variant, key[0], key[1], im2)
    return im2


def mirror_closer(ob, ot):
    """Рисунок цели ближе к зеркалу основы, чем к самой основе (по яркости на общем силуэте, с запасом 10 процентов)."""
    def lum(im):
        x = np.asarray(im.convert("RGBA"), np.float32)
        return x[..., :3] @ np.array([0.299, 0.587, 0.114], np.float32), x[..., 3] > 0
    lo, mo = lum(ob)
    lm, mm_ = lum(ob.transpose(Image.FLIP_LEFT_RIGHT))
    lt, mt = lum(ot)
    d0 = np.abs(lo - lt)[mo & mt].mean() if (mo & mt).any() else 1e9
    d1 = np.abs(lm - lt)[mm_ & mt].mean() if (mm_ & mt).any() else 1e9
    return bool(d1 < 0.9 * d0)


def colormap_transfer(hd, ob, ot, sigma=18.0):
    """Перенос цвета классики БЕЗ привязки к раскладке: у новой основы ступени, дыры и грани стоят не там, где у классики,
    и попиксельное отношение obj_derive.transfer даёт белые пятна (классика цели светлая там, где у новой основы
    ступень, а у классики основы - чёрная пустота). Здесь по парам пикселей классики основа -> цель (одна раскладка)
    строится таблица цветов: для каждого цвета классики основы - средний цвет цели. Пиксель HD сдвигается на дельту
    (цель - основа) ближайших цветов таблицы, с гауссовым весом по расстоянию в RGB (sigma). Рисунок и яркостные
    переходы HD остаются, меняется только оттенок/насыщенность по классике своего набора."""
    a = np.asarray(hd.convert("RGBA"), np.float32)
    b = np.asarray(ob.convert("RGBA"), np.float32)
    t = np.asarray(ot.convert("RGBA"), np.float32)
    m = (b[..., 3] > 0) & (t[..., 3] > 0)
    bb, tt = b[m][:, :3], t[m][:, :3]
    uniq, inv = np.unique(bb, axis=0, return_inverse=True)
    inv = inv.reshape(-1)
    tmean = np.stack([np.bincount(inv, tt[:, c]) / np.bincount(inv) for c in range(3)], 1)
    delta = tmean - uniq
    cnt = np.bincount(inv).astype(np.float32)          # вес цвета - его площадь на классике: акцент в 4 пикселя не красит стену
    rgb = a[..., :3].reshape(-1, 3)
    out = np.empty_like(rgb)
    for i in range(0, len(rgb), 20000):
        ch = rgb[i:i + 20000]
        d2 = ((ch[:, None, :] - uniq[None, :, :]) ** 2).sum(-1)
        w = np.exp(-(d2 - d2.min(1, keepdims=True)) / (2 * sigma * sigma)) * cnt[None, :]
        out[i:i + 20000] = ch + (w @ delta) / w.sum(1, keepdims=True)
    res = a.copy()
    res[..., :3] = np.clip(out.reshape(a.shape[:2] + (3,)), 0, 255)
    return Image.fromarray(np.rint(res).astype(np.uint8), "RGBA")


def recolor_to(base_img, base_key, tgt_key, layout_free=False):
    import obj_derive as od
    ob, ot = classic_of(*base_key), classic_of(*tgt_key)
    if same_px(ob, ot):
        return base_img.copy()
    mir = ob.transpose(Image.FLIP_LEFT_RIGHT)
    if same_px(mir, ot):
        return od.derive(base_img, ob, ot, "зеркало")
    if not layout_free and mirror_closer(ob, ot):        # зеркало с перекраской (HANGAR2_SCI:108): свет возвращается переносом
        return od.derive(base_img, ob, ot, "зеркало")
    if layout_free:
        return colormap_transfer(base_img, ob, ot)
    return od.transfer(base_img, ob, ot)


def do_build():
    import obj_derive as od
    for v in CLUSTERS:
        shutil.rmtree(os.path.join(CAND, v), ignore_errors=True)
    new = {}                               # (набор, кадр) -> RGBA
    for job, J in JOBS.items():
        variant = [v for v, js in CLUSTERS.items() if job in js][0]
        for seed in all_seeds(job):
            if seed == BEST[job] or not os.path.exists(os.path.join(GEN, job, "%d.png" % seed)):
                continue
            for k, im in pieces_of(job, seed).items():
                d = os.path.join(CAND, variant, "_seeds")
                os.makedirs(d, exist_ok=True)
                im.save(os.path.join(d, "%s_%d_s%d.png" % (k[0], k[1], seed)))
            cut = Image.open(os.path.join(GEN, job, "%d.png" % seed))
            cut.save(os.path.join(CAND, variant, "_seeds", "%s_whole_s%d.png" % (job, seed)))
        for k, im in pieces_of(job, BEST[job]).items():
            new[k] = finish(variant, k[0], k[1], im)
    # --- 405B: семья лестниц
    st = {k: new[k] for k in new if k[0] == "XB1BR"}
    fam405 = [("XBR1NEUTRAL", 25), ("XBR1NEUTRAL", 26), ("XBR1NEUTRAL", 27), ("XBR1NEUTRAL", 28),
              ("USOINT1", 30), ("USOINT1", 32), ("USOINT1", 34), ("LAM_FRN", 7), ("LAM_FRN", 8)]
    picks = []
    for key in fam405:
        ot = classic_of(*key)
        best = max(st, key=lambda b: iou(classic_of(*b), ot))
        q = iou(classic_of(*best), ot)
        picks.append((key, best, q))
        if q < 0.90:
            print("ПРОПУСК %s: нет основы с IoU >= 0.90 (лучшая %s %.2f)" % (key, best, q))
            continue
        new[key] = finish("405B", key[0], key[1], recolor_to(st[best], best, key, layout_free=True))
    for key, best, q in picks:
        print("405B %s <- %s IoU %.2f %s" % (key, best, q, "копия" if same_px(classic_of(*best), classic_of(*key)) else "перенос цвета"))
    # --- 409A: капсула 15 и анимация 50-56, обломок 16 (из BEST), бочка 24 и семья
    n15 = new[("XB3BITZ2", 15)]
    work = os.path.join(GEN, "_work")
    for f, im in derive_anim(n15, work).items():
        new[("XB3BITZ2", f)] = finish("409A", "XB3BITZ2", f, im)
    n24 = new[("XB2BR", 24)]
    fam409 = [("COMMS", 24), ("THULBASES01", 22), ("WHITEBASES01", 23), ("CULTAREA", 85), ("MILURBAN", 85),
              ("HANGAR2_SCI", 107), ("HANGAR2_SCI", 108), ("CARGO1", 65), ("XBITSUFO", 4), ("XBASE2", 25)]
    for key in fam409:
        if key in NO_CLASSIC:            # набор не читается из классики (MILURBAN): по таблице семьи это копия XB2BR:24
            new[key] = finish_copy("409A", key, n24)
            print("409A %s: копия (по таблице семьи, классика набора не читается)" % (key,))
            continue
        kind = ("копия" if same_px(classic_of("XB2BR", 24), classic_of(*key)) else
                "зеркало" if same_px(classic_of("XB2BR", 24).transpose(Image.FLIP_LEFT_RIGHT), classic_of(*key)) else
                ("зеркало+перенос цвета" if mirror_closer(classic_of("XB2BR", 24), classic_of(*key)) else "перенос цвета")
                + " IoU %.2f" % iou(classic_of("XB2BR", 24), classic_of(*key)))
        print("409A %s: %s" % (key, kind))
        new[key] = finish("409A", key[0], key[1], recolor_to(n24, ("XB2BR", 24), key))
    import csv
    os.makedirs(REV, exist_ok=True)
    with open(os.path.join(REV, "t405_409_checks.tsv"), "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["вариант", "набор", "кадр", "за силуэтом классики x4 до среза, пикс", "дыры внутри (доля альфа<200)",
                    "яркость новое", "яркость классика", "яркость сейчас"])
        w.writerows(CHECK_ROWS)
    bad = [r for r in CHECK_ROWS if r[3] > 0]
    print("проверок %d, кадров с выходом за силуэт до среза: %d (после среза везде 0)" % (len(CHECK_ROWS), len(bad)))
    for r in CHECK_ROWS:
        print("  ", r)
    make_sheets(new)


def hstack(ims, bg=(36, 36, 40), gap=6):
    ims = [on_dark(i, bg) for i in ims]
    W = sum(i.width for i in ims) + gap * (len(ims) - 1)
    H = max(i.height for i in ims)
    out = Image.new("RGB", (W, H + 36), (14, 14, 16))      # поле сверху: подпись ts.sheet рисуется поверх картинки
    x = 0
    for i in ims:
        out.paste(i, (x, 36))
        x += i.width + gap
    return out


def triple(s, f, new):
    """Классика x4 | HD сейчас | новое, на тёмном."""
    c = classic_of(s, f).resize((128, 160), Image.NEAREST)
    cur = hd_now(s, f) or Image.new("RGBA", (128, 160))
    return hstack([c, cur, new])


def comp_triple(job, new):
    import obj_series as osr
    comp, full, at = comp_of(job)
    cls = full.resize((full.width * 4, full.height * 4), Image.NEAREST)
    cur = {k: (hd_now(*k) or Image.new("RGBA", (128, 160))) for k, _o in comp["members"]}
    nw = {k: new[k] for k, _o in comp["members"]}
    return hstack([cls, osr.compose(comp, frames=cur, k=4)[0], osr.compose(comp, frames=nw, k=4)[0]])


TITLES = {"stairsA": "лестница XB1BR 27+26", "stairsB": "лестница XB1BR 28+29"}


def make_sheets(new):
    import ticket_scene as ts
    p405 = [("%s: классика x4 | HD сейчас | новое" % TITLES[j], comp_triple(j, new)) for j in CLUSTERS["405B"]]
    fam = [("XBR1NEUTRAL", 25), ("XBR1NEUTRAL", 26), ("XBR1NEUTRAL", 27), ("XBR1NEUTRAL", 28), ("USOINT1", 30),
           ("USOINT1", 32), ("USOINT1", 34), ("LAM_FRN", 7), ("LAM_FRN", 8)]
    p405 += [("%s:%d" % k, triple(k[0], k[1], new[k])) for k in fam if k in new]
    ts.sheet(p405[:2], os.path.join(REV, "_t405_top.png"), cols=1)
    ts.sheet(p405[2:], os.path.join(REV, "_t405_fam.png"), cols=3)
    top, famim = Image.open(os.path.join(REV, "_t405_top.png")), Image.open(os.path.join(REV, "_t405_fam.png"))
    W = max(top.width, famim.width)
    sheet = Image.new("RGB", (W, top.height + famim.height), (12, 12, 14))
    sheet.paste(top, (0, 0))
    sheet.paste(famim, (0, top.height))
    sheet.save(os.path.join(REV, "t405_cand.png"))
    os.remove(os.path.join(REV, "_t405_top.png"))
    os.remove(os.path.join(REV, "_t405_fam.png"))
    print("лист:", os.path.join(REV, "t405_cand.png"))
    # --- 409
    main = [("%s:%d" % k, triple(k[0], k[1], new[k])) for k in (("XB3BITZ2", 15), ("XB3BITZ2", 16), ("XB2BR", 24))]
    ts.sheet(main, os.path.join(REV, "_t409_top.png"), cols=3)
    anim = [("XB3BITZ2:%d" % f, triple("XB3BITZ2", f, new[("XB3BITZ2", f)])) for f in range(50, 57)]
    ts.sheet(anim, os.path.join(REV, "_t409_anim.png"), cols=3)
    fam = [("%s:%d" % k, triple(k[0], k[1], new[k])) for k in
           (("COMMS", 24), ("THULBASES01", 22), ("WHITEBASES01", 23), ("CULTAREA", 85), ("MILURBAN", 85),
            ("HANGAR2_SCI", 107), ("HANGAR2_SCI", 108), ("CARGO1", 65), ("XBITSUFO", 4), ("XBASE2", 25))]
    ts.sheet(fam, os.path.join(REV, "_t409_fam.png"), cols=3)
    parts = [Image.open(os.path.join(REV, n)) for n in ("_t409_top.png", "_t409_anim.png", "_t409_fam.png")]
    W = max(p.width for p in parts)
    sheet = Image.new("RGB", (W, sum(p.height for p in parts)), (12, 12, 14))
    y = 0
    for p in parts:
        sheet.paste(p, (0, y))
        y += p.height
    sheet.save(os.path.join(REV, "t409_cand.png"))
    for n in ("_t409_top.png", "_t409_anim.png", "_t409_fam.png"):
        os.remove(os.path.join(REV, n))
    print("лист:", os.path.join(REV, "t409_cand.png"))


# --- сборка на карте -------------------------------------------------------------------------------------
SCENES = [  # имя листа, терренбокс, блок, нужные кадры, окно (w, h) пикс базы
    ("t405_scene_a.png", "XBASE", "XBR_109", [("XB1BR", 26), ("XB1BR", 27)], (120, 90)),
    ("t405_scene_b.png", "XBASE", "XBR_176", [("XB1BR", 28), ("XB1BR", 29)], (120, 90)),
    ("t409_scene_capsules.png", "XBASE", "XBR_95", [("XB3BITZ2", 15)], (120, 90)),
    ("t409_scene_barrels.png", "XBASE", "XBR_29", [("XB2BR", 24)], (120, 90)),
]


def load_cand():
    ov = {}
    for v in CLUSTERS:
        d = os.path.join(CAND, v)
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".png"):
                s, f = fn[:-4].rsplit("_", 1)
                ov[(s, int(f))] = Image.open(os.path.join(d, fn)).convert("RGBA")
    return ov


def do_scene():
    import ticket_scene as ts
    sc = ts.Scene()
    ov = load_cand()
    for name, terrain, block, keys, (w, h) in SCENES:
        found = ts.find_cells(sc, terrain, block, keys)
        if not found:
            print("нет клеток", name)
            continue
        # окно - вокруг найденной клетки самого нижнего этажа (клетки найдены на k=1); этажи выше
        # её не рисуются: крыша закрывала бы предмет
        cell = max(found, key=lambda f: (-f[3], f[2][1]))
        box = ts.window([(cell[0], cell[1], tuple(v * 4 for v in cell[2]))], w, h, 4)
        maxz = cell[3]
        panels = []
        for title, mode, o in (("классика", "classic", None), ("HD сейчас", "hd", None), ("новое", "hd", ov)):
            im, _f = sc.render(terrain, block, mode, override=o, k=4, maxz=maxz)
            panels.append((title, ts.crop_pad(im, box)))
        ts.sheet(panels, os.path.join(REV, name), cols=1)
        print("лист:", os.path.join(REV, name), "клеток", len(found))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["render", "recut", "prompts", "seeds", "build", "scene"])
    ap.add_argument("--jobs", nargs="*", default=list(JOBS), choices=sorted(JOBS))
    a = ap.parse_args()
    if a.cmd == "prompts":
        for j in a.jobs:
            t, n = build_prompt(j)
            print("[%s]\n  PROMPT: %s\n  NEG: %s" % (j, t, n))
    elif a.cmd == "render":
        do_render(a.jobs)
    elif a.cmd == "recut":
        recut(a.jobs)
    elif a.cmd == "seeds":
        do_seeds()
    elif a.cmd == "build":
        do_build()
    else:
        do_scene()
    return 0


if __name__ == "__main__":
    sys.exit(main())
