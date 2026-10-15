#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Синтетический фото-эталон оружия СОТНИ (art/items/weapons100-v1) - сразу в раскладке оригинала.

Зачем. Подгонка настоящего фото под пиксельный кадр (weapon_fit.py) до уровня АК не доходит: пропорции
стилизованного кадра не как у настоящей вещи, фото тянется (растяжение 2-7) и несёт кайму своего фона. Эталон,
который уже нарисован в раскладке кадра (рефы Vitali autogun, street sweeper, mutant mg), проходит все проверки
weapon_fit с первого раза. Отсюда этот путь: эталон рисуется сразу на месте оригинала, а weapon_fit его проверяет.

Решение Vitali 04.10 (смешанный способ): для вымышленных и для настоящих без подходящего фото - фотореалистичный
эталон по описанию (synth_prompt из ident/batch_N.tsv - педия, рулсет, оригинал); это синтетический эталон,
его конструкцию проверяет человек. Оригинал задаёт размер, места частей, ракурс, цвета и дуло.

Рендер - struct_probe.Render как есть (RENDER_V1, вариант C, ДВЕ картинки: эскиз struct_guide и оригинал
bicubic; третьей картинки нет - R-205), вырезка - item_photo.cut_fixed и place_fixed (без подгонки по
содержимому, замер модели против оригинала +-3 %). Свой здесь только промпт: описание предмета одной фразой
вместо {what}, предложения про фон из описания убраны (фон - подложка названного цвета, R-157).

Модель - только через очередь и под render_chunks.py (не больше 4 рендеров на процесс, R-215):
    py -3.13 tools/gpuq.py add --name weapons_synth_b1 --prio 1 --cwd E:/OpenXCom -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/render_chunks.py \
        --out art/items/weapons100-v3/synth --max-renders 4 -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/weapons_synth.py --batch 1
Без модели: --dry-run (план и эскизы). Выход: <out>/pack/BIGOBS.PCK/<кадр>.<ТИП>.png, <out>/raw, <out>/meta,
<out>/refs/<ТИП>.png - ответ модели, вырезанный по своему матту, вход для weapon_fit (--ident с ref на него).
В мод не идёт.
"""
import argparse
import csv
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

import numpy as np                      # noqa: E402
from PIL import Image                   # noqa: E402

import item_photo as ip                 # noqa: E402

ENC = "utf-8-sig"
OUT = "art/items/weapons100-v3/synth"
BATCH = "art/items/weapons100-v1"
IDENT = "art/items/weapons100-v3/ident"
SEED0 = 7300
WEAPON = ("<image1> is a clean shape sketch of the object described below, shown on a flat preview panel of colour "
          "RGB({r}, {g}, {b}). The panel is background, not part of the object. "
          "Make a photorealistic studio product photograph of this object. "
          "Orthographic view straight at the object, no perspective, the object in exactly the orientation, "
          "position and size of <image1>. Keep the silhouette, the proportions, the parts and their places, and the "
          "colour areas of <image1>. The object: {desc} "
          "Real materials with natural surface detail and light wear, soft light from the upper left, sharp focus. "
          "Output one isolated object on the same flat panel. No hands, no straps unless described, no other objects, "
          "no shadow outside the object, no frame, no text, no letters, no logos.")
# --fill (04.10): модель держит высоту и место, но рисует части тоньше спрайта (реальные пропорции) - ширина
# пусковых -20...-46 %, тетива луков невидима. Одна поправка на всю партию, без серий на одном стволе.
FILL_TEXT = ("The object fills the whole outline of <image1>: every part is exactly as thick and as wide as in "
             "<image1>, not slimmer, not narrower and not shorter. The chunky stylised proportions of <image1> are "
             "intended - do not make any part more slender or more realistic than in <image1>. Thin parts such as a "
             "bow string, wires or rods are clearly visible solid cords as wide as in <image1>.")
FILL = ""


def read_tsv(p):
    with open(p, encoding=ENC, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def desc_of(s):
    """Описание без предложений про фон и свет (их задаёт промпт) и без 'Studio product photograph of'."""
    s = re.sub(r"^\s*(studio\s+)?(product\s+)?photo(graph)?\s+of\s+", "", s.strip(), flags=re.I)
    parts = [p.strip() for p in re.split(r"(?<=\.)\s+", s) if p.strip()]
    keep = [p for p in parts if not re.search(r"background|studio light|soft (even )?light|even (soft )?light", p, re.I)]
    out = " ".join(keep).strip()
    return out[0].upper() + out[1:] if out else out


def weapon_prompt(what, name, rgb):
    r, g, b = [int(v) for v in rgb]
    kind = "neutral " if name.startswith("grey") else ""
    return WEAPON.format(desc=what, r=r, g=g, b=b) + (" " + FILL if FILL else "") + " " + \
        ip.pr.PANEL_TEXT.format(kind=kind, r=r, g=g, b=b)


def jobs_for(batches, only, synth_only):
    lst = {r["master"]: r for r in read_tsv(os.path.join(BATCH, "list.tsv"))}
    jobs = []
    for k in batches:
        for r in read_tsv(os.path.join(IDENT, "batch_%d.tsv" % k)):
            m, t = r["master"], r["type"]
            if only and m not in only and t not in only:
                continue
            ref = r["ref"].strip()
            if synth_only and ref not in ("", "-"):
                continue
            sp_ = r["synth_prompt"].strip()
            if sp_ in ("", "-"):
                print("%s %s: нет synth_prompt - пропуск" % (m, t), flush=True)
                continue
            lr = lst[m]
            w, h = [int(v) for v in lr["cells"].split("x")]
            frame = int(lr["frame"])
            full, src = ip.load_frame(t, frame)
            crop, box = ip.crop_job(full)
            jobs.append({"asset_id": t, "name": t, "master": m, "frame": frame, "cells": [w, h],
                         "what": desc_of(sp_), "status_ident": r["status"], "seed": SEED0 + int(r["n"]),
                         "src": src, "full": full, "crop": crop, "box": box})
    return jobs


def ref_cut(raw, rgb):
    """Ответ модели -> эталон для weapon_fit: RGBA по своему матту (подложка ответа прозрачна), кадр ответа целиком.
    Матт - как у ответа на подложке: расстояние до цвета подложки, пороги photo_base.shadow_dist."""
    a = np.asarray(Image.open(raw).convert("RGB"), np.float32)
    det = ip.pr.detect_panel(Image.open(raw).convert("RGB"))
    ds = ip.pb.shadow_dist(a, det)
    al = np.clip((ds - 10.0) / 14.0, 0, 1)
    return Image.fromarray(np.dstack([a, al[..., None] * 255]).astype(np.uint8), "RGBA")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--batch", default="1", help="номера партий через запятую")
    ap.add_argument("--only", default="")
    ap.add_argument("--all", action="store_true", help="и предметы с готовым эталоном (по умолчанию - только без)")
    ap.add_argument("--dry-run", action="store_true", dest="dry_run")
    ap.add_argument("--recut", action="store_true")
    ap.add_argument("--models", default=None)
    ap.add_argument("--max-renders", type=int, default=0, dest="max_renders")
    ap.add_argument("--fill", action="store_true", help="поправка толщины частей (FILL_TEXT) в промпт")
    args = ap.parse_args()
    global FILL
    FILL = FILL_TEXT if args.fill else ""
    os.chdir(ROOT)
    ip.CARDS = os.path.join(BATCH, "cards")         # load_frame: <CARDS>/originals/<тип>/BIGOBS_<кадр>__*.png
    only = set(filter(None, args.only.split(",")))
    jobs = jobs_for([int(b) for b in args.batch.split(",")], only, not args.all)
    sp, pr, pb = ip.sp, ip.pr, ip.pb
    R = sp.Render(args.out, args.models, args.max_renders, args.recut)
    import gen_fire
    import obj_photo as op
    neg0 = op.NEGATIVE + ip.NEGATIVE_EXTRA
    gen_fire.NEGATIVE = R.po.gen_fire.NEGATIVE = neg0
    pr.prompt_for = weapon_prompt
    pb.cut = ip.cut_fixed
    import asset_rev as ar
    import obj_gen_spec as ogs
    R.grev = ar.h12({"params": pr.RENDER_V1, "prompt": WEAPON + FILL, "negative_extra": ip.NEGATIVE_EXTRA,
                     "c_text": sp.C_TEXT, "lock_rev": ogs.lock_rev(R.lock),
                     "code": ogs.code_parts((("weapons_synth.py", ("desc_of", "weapon_prompt")),))})
    print("weapons_synth: generator_rev %s, guide_rev %s, предметов %d" % (R.grev, R.guide_rev, len(jobs)), flush=True)
    gd = os.path.join(args.out, "guide")
    os.makedirs(gd, exist_ok=True)
    plan = []
    for j in jobs:
        panels = pr.panels_by_margin(j["crop"])
        g, rep = ip.sg.build(j["crop"], pr.RENDER_V1["zoom"], panels[0][1])
        g.save(os.path.join(gd, j["name"] + ".png"))
        plan.append((j, panels))
        print("%-6s %-24s %-9s %dx%d seed %d подложка %s" % (j["master"], j["asset_id"], j["status_ident"],
                                                          j["cells"][0], j["cells"][1], j["seed"], panels[0][0]),
              flush=True)
    if args.dry_run:
        with open(os.path.join(args.out, "plan.md"), "w", encoding=ENC) as f:
            f.write("# weapons_synth - план (generator_rev %s)\n\nnegative: %s\n\n" % (R.grev, neg0))
            for j, panels in plan:
                f.write("## %s %s, кадр %d, %dx%d, %s\n\n%s %s\n\n" % (
                    j["master"], j["asset_id"], j["frame"], j["cells"][0], j["cells"][1], j["status_ident"],
                    weapon_prompt(j["what"], panels[0][0], panels[0][1]), sp.C_TEXT))
        print("план: %s" % os.path.join(args.out, "plan.md"))
        return
    raw_dir, meta_dir, ref_dir = (os.path.join(args.out, d) for d in ("raw", "meta", "refs"))
    pack = os.path.join(args.out, "pack", "BIGOBS.PCK")
    missing = [j["asset_id"] for j, _p in plan if not os.path.exists(os.path.join(raw_dir, j["name"] + ".a0.png"))]
    if args.recut and missing:                      # R-127
        raise SystemExit("--recut, а ответа нет у %d: %s" % (len(missing), missing[:5]))
    if missing:
        R.check_lock()
    for d in (raw_dir, meta_dir, pack, ref_dir):
        os.makedirs(d, exist_ok=True)
    t0, cells = time.time(), []
    try:
        for n, (j, panels) in enumerate(plan, 1):
            final, attempts = R.job("C", j, j["crop"], panels, raw_dir)
            if final is None:
                print("%-24s нет ответа (--recut)" % j["asset_id"], flush=True)
                continue
            im, rep, _g, m_c, c, verdict = final
            hd, prep = ip.place_fixed(im, j["box"], *j["cells"], j["full"], False)
            pp = os.path.join(pack, "%d.%s.png" % (j["frame"], j["asset_id"]))
            hd.save(pp)
            raw = attempts[-1]["raw"]
            ref_cut(raw, attempts[-1]["panel_rgb"]).save(os.path.join(ref_dir, j["name"] + ".png"))
            mg = rep["model"]
            meta = {"asset_id": j["asset_id"], "master": j["master"], "frame": j["frame"], "cells": j["cells"],
                    "what": j["what"], "status_ident": j["status_ident"], "src": j["src"],
                    "generator_rev": R.grev, "guide_rev": R.guide_rev, "cut_rev": R.cut_rev, "attempts": attempts,
                    "report": rep, "machine": verdict, "model_geometry": mg, "place": prep,
                    "file": pp.replace("\\", "/"), "raw": raw, "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
            with open(os.path.join(meta_dir, j["name"] + ".json"), "w", encoding=ENC) as f:
                json.dump(meta, f, ensure_ascii=False, indent=1)
            cells.append(("%s %s" % (j["master"], mg.get("geometry")), j, raw, hd, mg))
            print("%-6s %-24s %-12s модель %s / %s, края %s | готово %d из %d, прошло %.0f мин" % (
                j["master"], j["asset_id"], mg.get("geometry"), mg.get("dw_pct"), mg.get("dh_pct"), mg.get("edges"),
                n, len(plan), (time.time() - t0) / 60), flush=True)
    except sp.Budget:
        print("лимит процесса: новых рендеров %d из %d - выхожу, продолжит новый процесс" % (R.renders, R.max),
              flush=True)
        sys.exit(sp.EXIT_MORE)
    if cells:
        ip.sheet(cells, os.path.join(args.out, "sheet_b%s.png" % args.batch.replace(",", "_")))
    print("готово: предметов %d, новых рендеров в этом процессе %d" % (len(cells), R.renders), flush=True)


if __name__ == "__main__":
    main()
