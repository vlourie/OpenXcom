#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Рендер PHOTO_STRUCT_ACCEPTANCE_V1: задания photo_struct.py select, только вариант C (DECISIONS 01.10).

Цикл - struct_probe.Render (тот же код, что прошёл STRUCT_GUIDE_V1): эскиз struct_guide первой картинкой,
bicubic оригинала второй, промпт prompt_for + C_TEXT, RENDER_V1, вырезка photo_base, проверки photo_accept.
Промпт - текст опознания, подтверждённый Vitali на карточке (photo_struct.select).

Модель - только через очередь и только под render_chunks.py (не больше 4 рендеров на процесс):
    py -3.13 tools/gpuq.py add --name photo_struct_accept_v1 --cwd E:/OpenXCom -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/render_chunks.py \
        --out art/objects/generation/probes/photo-struct-accept-v1 --max-renders 4 -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/photo_struct_render.py
Без модели: --dry-run (план, эскизы, промпт первого), --recut (готовые raw; нет ответа - стоп до загрузки).
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
ROOT = os.path.dirname(os.path.dirname(HERE))

import photo_base as pb                 # noqa: E402
import photo_render as pr               # noqa: E402
import struct_guide as sg               # noqa: E402
import struct_probe as sp               # noqa: E402

ENC = "utf-8-sig"
OUT = "art/objects/generation/probes/photo-struct-accept-v1"
VARIANT = "C"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--only", default="")
    ap.add_argument("--dry-run", action="store_true", dest="dry_run")
    ap.add_argument("--recut", action="store_true")
    ap.add_argument("--models", default=None)
    ap.add_argument("--max-renders", type=int, default=0, dest="max_renders",
                    help="новых рендеров на процесс, 0 - без лимита (render_chunks.py ставит 4)")
    args = ap.parse_args()
    os.chdir(ROOT)
    import map_mockup as mm

    path = os.path.join(args.out, "jobs.json")
    if not os.path.exists(path):
        raise SystemExit("нет %s - сначала photo_struct.py select" % path)
    with open(path, encoding=ENC) as f:
        jobs = json.load(f)
    if args.only:
        jobs = [j for j in jobs if j["asset_id"] in args.only.split(",")]
    bad = [j["asset_id"] for j in jobs if not j.get("identity_how") or not j.get("what", "").strip()]
    if bad:
        raise SystemExit("задания без подтверждённого опознания: %s" % bad)
    R = sp.Render(args.out, args.models, args.max_renders, args.recut)
    print("photo_struct_accept_v1: generator_rev %s, guide_rev %s, cut_rev %s, заданий %d, вариант %s" % (
        R.grev, R.guide_rev, R.cut_rev, len(jobs), VARIANT), flush=True)

    world = mm.World()
    plan = []
    gd = os.path.join(args.out, "guide")
    os.makedirs(gd, exist_ok=True)
    for j in jobs:
        comp, whole, at, box, frame = pb.job_frame(world, j)
        panels = pr.panels_by_margin(frame)
        plan.append((j, comp, whole, at, box, frame, panels))
        g, rep = sg.build(frame, pr.RENDER_V1["zoom"], panels[0][1])
        g.save(os.path.join(gd, j["name"] + ".png"))
        print("%-26s %-10s seed %d подложка %s guide %s" % (j["asset_id"], j["stratum"], j["seed"], panels[0][0],
                                                            rep), flush=True)
    if args.dry_run:
        j, *_r, panels = plan[0]
        print("промпт C:", pr.prompt_for(j["what"], panels[0][0], panels[0][1]) + " " + sp.C_TEXT)
        return
    raw_dir, meta_dir = os.path.join(args.out, "render", "raw"), os.path.join(args.out, "render", "meta")
    missing = [j["asset_id"] for j, *_r in plan if not os.path.exists(os.path.join(raw_dir, j["name"] + ".a0.png"))]
    if args.recut and missing:                      # R-127
        raise SystemExit("--recut, а ответа нет у %d: %s" % (len(missing), missing[:5]))
    if missing:
        R.check_lock()
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(meta_dir, exist_ok=True)

    t0, cells = time.time(), []
    try:
        for n, (j, comp, whole, at, box, frame, panels) in enumerate(plan, 1):
            final, attempts = R.job(VARIANT, j, frame, panels, raw_dir)
            if final is None:
                print("%-26s нет ответа (--recut)" % j["asset_id"], flush=True)
                continue
            meta, cell = R.finish(VARIANT, dict(j, group=j["stratum"]), comp, whole, at, box, final, attempts,
                                  os.path.join(args.out, "render"), meta_dir,
                                  extra={"identity_how": j["identity_how"], "identity_when": j.get("identity_when", "")})
            cells.append(cell)
            print("%-26s %-20s попыток %d | готово %d из %d, прошло %.0f мин" % (
                j["asset_id"], meta["outcome"], len(attempts), n, len(plan), (time.time() - t0) / 60), flush=True)
    except sp.Budget:
        print("лимит процесса: новых рендеров %d из %d - выхожу, продолжит новый процесс" % (R.renders, R.max),
              flush=True)
        sys.exit(sp.EXIT_MORE)
    if cells:
        pb.sheet(world, cells, os.path.join(args.out, "render", "machine_sheet.png"))
    ex = {"generator_rev": R.grev, "guide_rev": R.guide_rev, "guide": sg.GUIDE_V1, "cut_rev": R.cut_rev,
          "params": pr.RENDER_V1, "c_text": sp.C_TEXT, "variant": VARIANT, "items": len(plan),
          "renders_last_process": R.renders, "gpuq_job": os.environ.get("GPUQ_JOB_ID", ""),
          "finished": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if not args.recut:
        with open(os.path.join(args.out, "execution.json"), "w", encoding=ENC) as f:
            json.dump(ex, f, ensure_ascii=False, indent=1)
    print("готово: предметов %d, новых рендеров в этом процессе %d" % (len(cells), R.renders), flush=True)


if __name__ == "__main__":
    main()
