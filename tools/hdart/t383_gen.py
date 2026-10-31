#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000383 (лестницы PORTROADS на карте рудника/порта), вариант B по выбору Vitali 31.10:
  (1) низ центральной лестницы PORTROADS:23 = зеркало чистой HD PORTROADS:20 с цветом классики 23 (без видеокарты);
  (2) боковая лесенка у знака электричества PORTROADS 62, 64, 67, 69 и её семья - 37 кадров в 10 наборах: две основы
      Qwen strict (A - без ножек, 350 пикселей классики; B - с ножками, 427), остальные - зеркало и перенос цвета
      классики своего набора (g.colormap_transfer; у копий классики - тот же кадр).
В МОД НИЧЕГО НЕ СТАВИТ: кадры - art/tickets/t383/cand/<НАБОР>_<кадр>.png, листы - art/_review/tickets_2026-10-31/.

Семья считана по силуэту классики (все 37 кадров попадают ровно в две группы: силуэт совпал или отзеркален), цвет
сверен листом (R-468). Путь генерации - t405_409_gen / t443_gen: Qwen-Image-2.1 strict, 40 шагов, cfg 4, 1 Мп, вход -
классика bicubic x16 на подложке pick_background, негатив probe_object + battle_view, cut_out (альфа - силуэт классики
x4, спрямлённый xBRZ: R-089, R-121), match_tone 0.7. Ракурс и свет - только battle_view. R-485: ромб - невидимая
направляющая, плиты нет; описание - по картинке классики (R-460): светло-серые плоские ступени-плиты, стойка справа.

    py -3.13 tools\hdart\t383_gen.py prompts
    py -3 tools\gpuq.py add --name t383 --prio 1 -- tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\t383_gen.py render
    py -3.13 tools\hdart\t383_gen.py seeds      # лист зёрен t383_seeds.png
    py -3.13 tools\hdart\t383_gen.py build      # кандидаты по BEST: 38 кадров в art/tickets/t383/cand
    py -3.13 tools\hdart\t383_gen.py sheets     # t383_cand.png
    py -3.13 tools\hdart\t383_gen.py scene      # сцены на карте t383_cand_scene_*.png
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
g.CAND = os.path.join(ROOT, "art", "tickets", "t383", "cand")
g.GEN = os.path.join(ROOT, "art", "tickets", "t383", "gen")
g.REV = REVD
CAND = g.CAND
REV = REVD

SLAB = "stone slab, paving tiles, diamond outline"
STAIR_NEG = ("wooden planks, wooden steps, brown wood, beige, tan, solid closed risers, solid block, escalator, ramp, "
             "long thin ramp, slab, floor plate, handrail, text")
BASE_WHAT = ("a short open staircase of four wide flat light grey steel tread plates, each plate thick like a slab with "
             "a slightly lighter top face and a darker front edge, the plates stepping up from the lower left to the "
             "upper right with open gaps between them, and one thin dark grey steel vertical post at the right end of "
             "the steps")
JOBS = {
    "stairsA": dict(
        members=[("PORTROADS", 62, (0, 0, 0))], seeds=[3831, 3832, 3833, 3834], r1=[],
        what=BASE_WHAT + ", nothing under the left side of the steps",
        neg=STAIR_NEG + ", legs, support posts at the left, table", slab=False),
    "stairsB": dict(
        members=[("PORTROADS", 64, (0, 0, 0))], seeds=[3841, 3842, 3843, 3844], r1=[],
        what=BASE_WHAT + " and, under the left end of the steps, two thin dark grey steel vertical legs hanging down "
                         "from the plates to the ground",
        neg=STAIR_NEG, slab=False),
}
for _j in JOBS.values():
    _j["neg"] = _j["neg"] + ", " + SLAB
CLUSTERS = {"383": list(JOBS)}
BEST = {"stairsA": 3833, "stairsB": 3841}

g.JOBS = JOBS
g.CLUSTERS = CLUSTERS
g.BEST = BEST

# --- семья: кадр -> (основа, 'same'|'mirror') по силуэту классики -----------------------------------------------
FAM = {
    "stairsA": [("PORTROADS", 62, "base"), ("PORTROADS", 69, "mirror"), ("BARN_JUNK", 15, "same"), ("COMMS", 14, "same"),
                ("CULTAREA", 48, "same"), ("MILURBAN", 48, "same"), ("MILWARE", 22, "same"), ("MILWAREGHOUL", 22, "same"),
                ("MOORINGS", 5, "same"), ("XOPSDESERTRUINS", 15, "same"), ("COMMS", 20, "mirror"),
                ("CULTAREA", 55, "mirror"), ("MILURBAN", 55, "mirror"), ("MILWARE", 26, "mirror"),
                ("MILWAREGHOUL", 26, "mirror"), ("MOORINGS", 12, "mirror"), ("XOPSDESERT", 68, "mirror"),
                ("XOPSDESERTRUINS", 22, "mirror")],
    "stairsB": [("PORTROADS", 64, "base"), ("PORTROADS", 67, "mirror"), ("BARN_JUNK", 16, "same"), ("COMMS", 15, "same"),
                ("CULTAREA", 49, "same"), ("MILURBAN", 49, "same"), ("MILWARE", 23, "same"), ("MILWAREGHOUL", 23, "same"),
                ("MOORINGS", 7, "same"), ("XOPSDESERT", 63, "same"), ("XOPSDESERTRUINS", 17, "same"),
                ("COMMS", 21, "mirror"), ("CULTAREA", 56, "mirror"), ("MILURBAN", 56, "mirror"),
                ("MILWARE", 27, "mirror"), ("MILWAREGHOUL", 27, "mirror"), ("MOORINGS", 10, "mirror"),
                ("XOPSDESERT", 66, "mirror"), ("XOPSDESERTRUINS", 20, "mirror")],
}


def classic_of(s, f):
    """Классика кадра k=1 RGBA; MILURBAN читается только из листа набора (ticket_scene его не находит)."""
    key = (s, f)
    if key not in _CL:
        try:
            _CL[key] = Image.fromarray(np.asarray(_scene().classic(s, f))[::4, ::4].copy(), "RGBA")
        except Exception:
            import glass_alpha as ga
            S = ga.SetSheet(s)
            fr = S.frame(f)
            a = np.zeros((40, 32, 4), np.uint8)
            a[..., :3] = S.pal[fr].astype(np.uint8)
            a[..., 3] = S.opaque(fr).astype(np.uint8) * 255
            _CL[key] = Image.fromarray(a, "RGBA")
    return _CL[key]


_CL = {}
_SCN = []


def _scene():
    import ticket_scene as ts
    if not _SCN:
        _SCN.append(ts.Scene())
    return _SCN[0]


g.classic_of = classic_of
GAME = g.GAME


def hd_now(s, f):
    p = os.path.join(GAME, s + ".PCK", "%d.png" % f)
    return Image.open(p).convert("RGBA") if os.path.exists(p) else None


g.hd_now = hd_now


def clip_smooth(im, sprite_k1):
    """Альфа не выходит за силуэт классики, сглаженный xBRZ x4 (R-121); как t443_gen.clip_smooth."""
    import probe_object as po
    m = Image.fromarray((np.asarray(sprite_k1)[..., 3] > 0).astype(np.uint8) * 255, "L")
    sil = np.asarray(po.smooth_silhouette(m, 4)) > 8
    a = np.asarray(im).copy()
    out = int(((a[..., 3] > 0) & ~sil).sum())
    a[~sil, 3] = 0
    a[a[..., 3] == 0, :3] = 0
    return Image.fromarray(a, "RGBA"), out


g.clip_to_classic = clip_smooth


def recolor_pos(hd, ob, ot, sigma=1.0):
    """Перенос цвета классики цели на HD основы по ПОЛОЖЕНИЮ (одна раскладка: у основы и цели силуэт тот же, ступени на тех
    же местах): отношение цвета классики цели к классике основы по каналам, сглаженное по пикселям классики (сигма
    sigma, нормированное по маске), растянутое x4 гладко и умноженное на HD. Тон ступеней по рисунку HD сохраняется,
    оттенок - классики цели (лиловый серый COMMS, чередующиеся ржавые и серые ступени XOPSDESERT), а не один цвет на
    всю лестницу, как у g.colormap_transfer (таблица цветов без раскладки)."""
    from scipy import ndimage
    a = np.asarray(ob.convert("RGBA"), np.float32)
    b = np.asarray(ot.convert("RGBA"), np.float32)
    m = ((a[..., 3] > 0) & (b[..., 3] > 0)).astype(np.float32)
    r = np.clip((b[..., :3] + 6.0) / (a[..., :3] + 6.0), 0.15, 6.0) * m[..., None]
    den = np.maximum(ndimage.gaussian_filter(m, sigma), 1e-3)
    sm = np.stack([ndimage.gaussian_filter(r[..., c], sigma) / den for c in range(3)], -1)
    # за маской (по краю) - ближайшее значение внутри
    _d, ind = ndimage.distance_transform_edt(m < 0.5, return_indices=True)
    sm = sm[ind[0], ind[1]]
    big = np.stack([np.asarray(Image.fromarray(sm[..., c].astype(np.float32), "F").resize(hd.size, Image.BICUBIC))
                    for c in range(3)], -1)
    h = np.asarray(hd.convert("RGBA"), np.float32).copy()
    h[..., :3] = np.clip(h[..., :3] * big, 0, 255)
    return Image.fromarray(np.rint(h).astype(np.uint8), "RGBA")


def cut_seed_matte(job, seed):
    """g.cut_seed, но альфа ответа - obj_photo.edge_matte (заливка от края останавливается на контуре предмета), а не ключ
    по цвету подложки: светло-серые ступени на светлой подложке (176) ключом стали полупрозрачными на 60 процентов (R-089)."""
    import obj_photo
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


g.cut_seed = cut_seed_matte


def derive(base_img, base_key, key, rel):
    """Кадр цели из основы: зеркало по силуэту - зеркало основы; цвет - классики цели (копия классики - тот же кадр)."""
    ob = classic_of(*base_key)
    ot = classic_of(*key)
    if rel == "mirror":
        base_img = base_img.transpose(Image.FLIP_LEFT_RIGHT)
        ob = ob.transpose(Image.FLIP_LEFT_RIGHT)
    if g.same_px(ob, ot):
        return base_img.copy(), ("зеркало" if rel == "mirror" else "копия")
    return recolor_pos(base_img, ob, ot), ("зеркало+перенос цвета" if rel == "mirror" else "перенос цвета")


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
    n = 0
    for job, rows in FAM.items():
        bkey = rows[0][:2]
        for s, f, rel in rows:
            if rel == "base":
                im, kind = new[job], "основа"
            else:
                im, kind = derive(new[job], bkey, (s, f), rel)
            cls = classic_of(s, f)
            g.check("383", s, f, im, cls)
            im2, cut = clip_smooth(im, cls)
            im2.save(os.path.join(CAND, "%s_%d.png" % (s, f)))
            out[(s, f)] = im2
            n += 1
            print("%s:%d <- %s: %s, срезано за силуэтом %d пикс." % (s, f, job, kind, cut))
    # --- PORTROADS:23 = зеркало HD 20 с цветом классики 23
    im23, kind = p23()
    im23.save(os.path.join(CAND, "PORTROADS_23.png"))
    out[("PORTROADS", 23)] = im23
    print("PORTROADS:23 <- PORTROADS:20 (HD сейчас): %s" % kind)
    with open(os.path.join(REV, "t383_checks.tsv"), "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["вариант", "набор", "кадр", "за силуэтом классики x4 до среза, пикс", "дыры внутри (доля альфа<200)",
                    "яркость новое", "яркость классика", "яркость сейчас"])
        w.writerows(g.CHECK_ROWS)
    print("кадров %d + PORTROADS:23" % n)
    return out


def p23(transfer=False):
    """PORTROADS:23: классика почти зеркальна 20 (IoU 1.00, силуэт отличается парой пикселей); HD 20 чистая. Основной
    вариант - чистое зеркало (ступени HD резкие, бежевая полоса у края на той же стороне, что у классики 23); цвет у
    зеркала и классики 23 тот же по среднему (см. mean_gap). transfer=True - с переносом цвета классики 23 по таблице:
    ступени размываются, запасной вариант в cand/_alt."""
    hd20 = hd_now("PORTROADS", 20)
    c20, c23 = classic_of("PORTROADS", 20), classic_of("PORTROADS", 23)
    fl = hd20.transpose(Image.FLIP_LEFT_RIGHT)
    c20f = c20.transpose(Image.FLIP_LEFT_RIGHT)
    q = g.iou(c20f, c23)
    a = np.asarray(c20f, np.float32)
    b = np.asarray(c23, np.float32)
    m = (a[..., 3] > 0) & (b[..., 3] > 0)
    gap = float(np.abs(a[m][:, :3].mean(0) - b[m][:, :3].mean(0)).max())
    if transfer:
        im, kind = g.colormap_transfer(fl, c20f, c23), "зеркало+перенос цвета классики 23"
    else:
        im, kind = fl, "чистое зеркало HD 20"
    im, cut = clip_smooth(im, c23)
    return im, "%s, IoU %.3f, средний цвет классики 23 и зеркала 20 расходится на %.1f из 255, срезано %d пикс." % (kind, q, gap, cut)


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
    ts.sheet(panels, os.path.join(REV, "t383_seeds.png"), cols=5)
    print("лист:", os.path.join(REV, "t383_seeds.png"))


def do_sheets():
    """t383_cand.png: центр (PORTROADS 20-23) и боковая лесенка; в каждой ячейке классика | сейчас | кандидат."""
    import ticket_scene as ts
    ov = load_cand()
    top = []
    for f in (20, 21, 22, 23):
        s = ("PORTROADS", f)
        cand = ov.get(s) or hd_now(*s)
        top.append(("PORTROADS:%d%s" % (f, " - кандидат: зеркало HD 20" if f == 23 else " - не меняется"), g.triple(s[0], s[1], cand)))
    side = []
    for job, rows in FAM.items():
        for s, f, _rel in rows:
            side.append(("%s:%d  (%s)" % (s, f, "основа A без ножек" if job == "stairsA" else "основа B с ножками"),
                         g.triple(s, f, ov[(s, f)])))
    ts.sheet(top, os.path.join(REV, "_t383_top.png"), cols=2)
    ts.sheet(side, os.path.join(REV, "_t383_side.png"), cols=4)
    a, b = Image.open(os.path.join(REV, "_t383_top.png")), Image.open(os.path.join(REV, "_t383_side.png"))
    W = max(a.width, b.width)
    sh = Image.new("RGB", (W, a.height + b.height), (12, 12, 14))
    sh.paste(a, (0, 0))
    sh.paste(b, (0, a.height))
    sh.save(os.path.join(REV, "t383_cand.png"))
    os.remove(os.path.join(REV, "_t383_top.png"))
    os.remove(os.path.join(REV, "_t383_side.png"))
    print("лист:", os.path.join(REV, "t383_cand.png"), sh.size)


SCENES = [
    ("t383_cand_scene_center.png", "PORTUFO", "PORTUFO07", [("PORTROADS", 23)], (140, 100)),
    ("t383_cand_scene_side.png", "INDUSTRIALSLUM", "INDUSTRIALSLUM32", [("PORTROADS", 62), ("PORTROADS", 64)], (140, 100)),
    ("t383_cand_scene_side2.png", "OLD_FORT_SLUM", "D_OLD_FORT", [("PORTROADS", 62), ("PORTROADS", 64)], (170, 120)),
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
    ap.add_argument("cmd", choices=["render", "recut", "prompts", "seeds", "build", "sheets", "scene", "p23"])
    ap.add_argument("--jobs", nargs="*", default=list(JOBS), choices=sorted(JOBS))
    a = ap.parse_args()
    if a.cmd == "prompts":
        for j in a.jobs:
            t, n = g.build_prompt(j)
            print("[%s]\n  PROMPT: %s\n  NEG: %s" % (j, t, n))
    elif a.cmd == "render":
        g.do_render(a.jobs)
    elif a.cmd == "recut":
        g.recut(a.jobs)
    elif a.cmd == "seeds":
        do_seeds()
    elif a.cmd == "build":
        do_build()
    elif a.cmd == "p23":
        os.makedirs(CAND, exist_ok=True)
        im, kind = p23()
        im.save(os.path.join(CAND, "PORTROADS_23.png"))
        print("PORTROADS:23:", kind)
        os.makedirs(os.path.join(CAND, "_alt"), exist_ok=True)
        im2, kind2 = p23(True)
        im2.save(os.path.join(CAND, "_alt", "PORTROADS_23_transfer.png"))
        print("запасной:", kind2)
    elif a.cmd == "sheets":
        do_sheets()
    else:
        do_scene()
    return 0


if __name__ == "__main__":
    sys.exit(main())
