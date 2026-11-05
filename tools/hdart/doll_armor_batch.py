#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Пачка броней UBERGAL разом: план кадров, волосы без модели, рисование с продолжением. В мод не ставит.

Перепись 05.11: 145 броней, 777 вещей без HD. HAIR_* - те же точки, что голова и тело (100% на 40 слоях), поэтому режутся из готовых
слоёв. Вещь рисуется один раз: первый кадр, где она есть, остальным брони - уже готовая (Vitali 05.11 «общее один раз»).
Цвета одного силуэта - один рисунок, тон от своей классики; LIGHT/DARK различаются кожей, у них свой кадр (R-725).
Серии по внешностям (BIKINI_F0.. - 120 разных вещей) в план не входят.

    E:\OpenXCom\tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\doll_armor_batch.py --dry-run
    py -3.13 tools\gpuq.py add --name doll_batch -- E:\OpenXCom\tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\doll_armor_batch.py
"""
import argparse
import collections
import glob
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import doll_b2_render as db

OUT = os.path.join(db.ROOT, "art", "doll", "pipe_pilot", "armor_batch")
UI = os.path.join(db.ROOT, "Пиратки", "Dioxine_XPiratez", "user", "mods", "hd", "hd", "UI")
PLAN = os.path.join(OUT, "plan.json")
TEXTS = os.path.join(OUT, "texts.json")
SEED = 0
SERIES_MIN = 5                                      # от стольких вещей с суффиксом внешности - серия, не личная вещь


def is_look(x):
    return "_NUDE" in x or "__HEAD_" in x


def short(x):
    return x.split("__")[2]


def is_hair(x):
    return short(x).startswith("HAIR_")


def have_set():
    return {f[:-4].lower() for f in os.listdir(UI) if f.endswith(".png")}


def make_plan(real):
    """real: {броня: кукол на сейвах}. Кадры по убыванию отдачи: кадр - один набор слоёв брони, paint - вещи, которых ещё нет."""
    files, armors = db.sprite_files(), db.armor_layers()
    armors = {a: {k: v for k, v in d.items() if v and v[0].startswith("UBERGAL")} for a, d in armors.items()}
    armors = {a: d for a, d in armors.items() if d}
    have = have_set()
    names = {x for d in armors.values() for v in d.values() for x in v if not is_look(x)}
    fam = collections.Counter(re.sub(r"_[MF]\d+$", "", short(x)) for x in names if re.search(r"_[MF]\d+$", short(x)))
    series = {x for x in names if re.search(r"_[MF]\d+$", short(x)) and fam[re.sub(r"_[MF]\d+$", "", short(x))] >= SERIES_MIN and not is_hair(x)}
    masks, missing = {}, set()
    for x in names:
        if is_hair(x) or x.lower() in have or x in series:
            continue
        try:
            masks[x] = db.load_indices(files[x]) != 0
        except (KeyError, FileNotFoundError):
            missing.add(x)
    armors = {a: {k: [x for x in v if x not in missing] for k, v in d.items()} for a, d in armors.items()}  # файла нет и у классики
    sil = {}
    for x, m in masks.items():
        skin = short(x).endswith(("_LIGHT", "_DARK"))       # кожа под вещью: свой кадр, R-725
        sil[x] = x if skin else m.tobytes()
    owner, frames = {}, []                                  # силуэт -> кадр
    for arm in sorted(armors, key=lambda a: (-real.get(a, 0), a)):
        d = armors[arm]
        todo = {x for v in d.values() for x in v if x in masks}
        for x in sorted(todo):
            if sil[x] in owner:
                owner[sil[x]]["variants"].setdefault(x, next(v for v in d.values() if x in v))
        todo = {x for x in todo if sil[x] not in owner}
        while todo:
            key = max(sorted(d), key=lambda k: len(todo & set(d[k])))
            paint = sorted(todo & set(d[key]))
            fr = {"id": len(frames), "armor": arm, "key": key, "stack": d[key], "paint": paint, "variants": {}, "real": real.get(arm, 0)}
            frames.append(fr)
            for x in paint:
                owner[sil[x]] = fr
            todo -= set(paint)
            for x in sorted(todo):                          # второй цвет того же силуэта в этом же наборе брони
                if sil[x] in owner:
                    owner[sil[x]]["variants"].setdefault(x, next(v for v in d.values() if x in v))
            todo = {x for x in todo if sil[x] not in owner}
    return {"frames": frames, "series": sorted(series), "missing": sorted(missing), "hair": sorted(x for x in names if is_hair(x) and x.lower() not in have)}


def cut_hair(plan):
    """Слой HAIR_<внешность> = голова поверх тела этой внешности, альфа - силуэт классики x4."""
    import doll_pipe_pilot as P
    import doll_photo_pilot as dp
    from PIL import Image
    files = db.sprite_files()
    P.FILES, P.PAL = files, db.game_palette()
    out = os.path.join(OUT, "layers")
    os.makedirs(out, exist_ok=True)
    done = 0
    for x in plan["hair"]:
        fn = os.path.join(out, x.lower() + ".png")
        if os.path.exists(fn):
            continue
        look = short(x)[len("HAIR_"):]
        c = Image.new("RGBA", (db.W * dp.K, db.H * dp.K), (0, 0, 0, 255))
        for n in ("ubergal__2__%s_nude" % look.lower(), "ubergal__10__head_%s" % look.lower()):
            c.alpha_composite(Image.open(os.path.join(UI, n + ".png")).convert("RGBA"))
        import numpy as np
        P.layer_from(np.asarray(c.convert("RGB"), np.float32), dp.layer_mask(files, x), edge=0).save(fn)
        done += 1
    print("волосы: вырезано %d из %d" % (done, len(plan["hair"])), flush=True)


def source(n, batch):
    from PIL import Image
    import doll_photo_pilot as dp
    for d in (UI, batch):
        p = os.path.join(d, n.lower() + ".png")
        if os.path.exists(p):
            return Image.open(p).convert("RGBA")
    return dp.b2_layer(n)[0]


def draw_all(plan, texts):
    """Кадры подряд: следующий кадр видит уже готовые вещи прошлых. Память карты - выход 75, новый процесс продолжит."""
    import doll_armor_solo as S
    import doll_pipe_pilot as P
    import doll_photo_pilot as dp
    import numpy as np
    import vx_control as vc
    from PIL import Image
    S.common()
    raw, batch = os.path.join(OUT, "raw"), os.path.join(OUT, "layers")
    os.makedirs(raw, exist_ok=True)
    os.makedirs(batch, exist_ok=True)
    painter = None
    x0, y0, x1, y1 = (v * dp.K for v in dp.CROP)
    negative = S.NEGATIVE + ", extra limbs, nude, bare breasts"
    left = [x for x in plan["frames"] if not os.path.exists(os.path.join(raw, "f%03d_out.png" % x["id"]))]
    for fr in plan["frames"]:
        tag = "f%03d" % fr["id"]
        done = os.path.join(raw, tag + "_out.png")
        names = fr["stack"]
        paint = set(fr["paint"])

        def visible(stack, todo):
            um = np.zeros((db.H, db.W), bool)
            for k, n in enumerate(stack):
                if n not in todo:
                    continue
                m = dp.layer_mask(P.FILES, n).copy()
                for up in stack[k + 1:]:
                    if up not in todo:
                        m &= ~dp.layer_mask(P.FILES, up)
                um |= m
            return um

        def frame_above(mask):
            """Точки силуэта, которые в кадре закрыла вещь выше: у цвета-варианта там не его рисунок."""
            hit = [k for k, n in enumerate(names) if n in paint and np.array_equal(dp.layer_mask(P.FILES, n), mask)]
            res = np.zeros_like(mask)
            if hit:
                for up in names[hit[0] + 1:]:
                    res |= dp.layer_mask(P.FILES, up)
            return res

        if not os.path.exists(done):
            um = visible(names, paint)
            canvas = Image.new("RGBA", (db.W * dp.K, db.H * dp.K), S.PANEL)
            for n in names:
                canvas.alpha_composite(source(n, batch))
            if not um.any():                                # всё закрыто верхними вещами: рисовать нечего
                Image.fromarray(P.to8(canvas)).save(done)
            else:
                if painter is None:
                    painter = P.Painter([P.ARMOR.format(style=S.STYLE, what=texts[str(x["id"])]) for x in left] + [negative])
                    print("модель загружена за %d с" % painter.load_s, flush=True)
                ctl = vc.control_map(dp.classic(P.FILES, P.PAL, names).crop(dp.CROP), dp.Z, "gray")
                prompt = P.ARMOR.format(style=S.STYLE, what=texts[str(fr["id"])])
                try:
                    rgb, _s0 = painter.paint(P.to8(canvas), P.mask8(um, P.RUN["armor"]["grow8"]), ctl, prompt,
                                             P.RUN["seed"] + 500 + SEED + fr["id"], S.STRENGTH, P.RUN["item"]["control"], negative)
                except Exception as e:
                    print("кадр %s упал: %s" % (tag, str(e)[:300]), flush=True)
                    sys.exit(75)
                Image.fromarray(rgb).save(done)
        rgb8 = np.asarray(Image.open(done).convert("RGB"))
        jobs = [(names, sorted(paint))] + [(stack, [x]) for x, stack in fr["variants"].items()]
        for stack, todo in jobs:
            if all(os.path.exists(os.path.join(batch, n.lower() + ".png")) for n in todo):
                continue
            um = visible(stack, set(todo))
            if not um.any():                                # нет ни одной своей точки: как есть из B2
                for n in todo:
                    dp.b2_layer(n)[0].save(os.path.join(batch, n.lower() + ".png"))
                continue
            f4, d0, d1 = P.tone_lock(P.full4(rgb8), stack, um)
            for k, n in enumerate(stack):
                if n not in todo:
                    continue
                mask = dp.layer_mask(P.FILES, n)
                above = frame_above(mask) if n not in paint else np.zeros_like(mask)
                for up in stack[k + 1:]:
                    above |= dp.layer_mask(P.FILES, up)
                im = P.layer_from(f4, mask)
                hid = P.ws.sil4(mask & above) > 0.5
                inside = np.zeros_like(hid)
                inside[y0:y1, x0:x1] = True
                hid |= ~inside                              # шире рамки кадра - из B2
                if hid.any():
                    px = np.asarray(im).copy()
                    px[hid, :3] = np.asarray(dp.b2_layer(n)[0])[hid, :3]
                    im = Image.fromarray(px, "RGBA")
                im.save(os.path.join(batch, n.lower() + ".png"))
            print("%s %s: %d вещей, dE %.1f -> %.1f" % (tag, fr["armor"], len(todo), d0, d1), flush=True)
        print("кадр %d из %d готов" % (fr["id"] + 1, len(plan["frames"])), flush=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="только план кадров, без карты")
    ap.add_argument("--real", help="JSON {броня: кукол на сейвах} для порядка кадров")
    ap.add_argument("--hair", action="store_true", help="только вырезать волосы, без карты")
    ap.add_argument("--worker", action="store_true", help="(служебное) рисовать недостающие кадры подряд")
    ns = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    if ns.dry_run:
        real = json.load(open(ns.real, encoding="utf-8-sig")) if ns.real else {}
        plan = make_plan(real)
        with open(PLAN, "w", encoding="utf-8-sig") as f:
            json.dump(plan, f, ensure_ascii=False, indent=0)
        fr = plan["frames"]
        print("кадров %d, вещей рисуется %d, цветов к ним %d, волос %d, серий %d, без файла %d" % (
            len(fr), sum(len(x["paint"]) for x in fr), sum(len(x["variants"]) for x in fr), len(plan["hair"]), len(plan["series"]), len(plan["missing"])))
        print("брони в кадрах:", len({x["armor"] for x in fr}))
        return
    plan = json.load(open(PLAN, encoding="utf-8-sig"))
    if ns.hair:
        cut_hair(plan)
        return
    texts = json.load(open(TEXTS, encoding="utf-8-sig"))
    lost = [x["id"] for x in plan["frames"] if str(x["id"]) not in texts]
    if lost:
        raise SystemExit("нет описаний кадров: %s" % lost[:20])
    if ns.worker:
        draw_all(plan, texts)
        return
    cut_hair(plan)
    for attempt in range(8):
        r = subprocess.run([sys.executable, os.path.abspath(__file__), "--worker"])
        print("рабочий процесс вышел с кодом %s (попытка %d)" % (r.returncode, attempt + 1), flush=True)
        if r.returncode == 0:
            return
    raise SystemExit("кадры не дорисованы")


if __name__ == "__main__":
    main()
