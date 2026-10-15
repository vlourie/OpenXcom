#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Проба специалиста 05.10: перерисовка ХОРОШЕЙ картинки оружия с сохранением дизайна, без подгонки по контуру.

Зачем. Подгонка эталона под пиксельный кадр (weapon_fit.py, TPS) деформирует картинку под контур вместо
качественной перерисовки; синтетика по описанию (weapons_synth.py) рисует части тоньше спрайта (R-220).
Здесь модели дают хорошую картинку и просят улучшить исполнение, сохранив дизайн:
  <image1> - эталон (рисунок Vitali), матт с его фона, РАВНОМЕРНО уменьшенный до габарита оригинала и
             поставленный на место оригинала в кропе x16 (ни растяжки, ни TPS);
  <image2> - оригинал кадра чистым эскизом struct_guide (тот же холст): геометрия, места частей, цвета, дуло.
Промпт - текст специалиста дословно (PROMPT_SPEC) плюс строка ролей картинок, особенности предмета (EXTRA) и
подложка названного цвета (R-157; «прозрачный фон» модель дать не может).

Рендер - struct_probe.Render как есть (Qwen-Image-2.1, RENDER_V1: 40 шагов, cfg 4, две картинки), вырезка -
item_photo.cut_fixed и place_fixed (без подгонки по содержимому). Проверка - weapon_fit.py --synth <out>:
сырой ответ и итог, размер +-3 % по ширине и высоте, дуло, пропажа частей, кайма. В мод не идёт.

Без модели: py -3.13 tools/hdart/weapons_redraw.py --dry-run   (входы и промпт в <out>/plan.md, <out>/inputs)
С моделью - только через очередь:
    py -3.13 tools/gpuq.py add --name weapons_redraw_w019 --prio 1 --cwd E:/OpenXCom -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/render_chunks.py \
        --out art/items/weapons-redraw-v1 --max-renders 4 -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/weapons_redraw.py
Выход: <out>/raw, <out>/meta, <out>/pack/BIGOBS.PCK/<кадр>.<ТИП>.png, <out>/inputs, <out>/sheet.png.
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

import numpy as np                      # noqa: E402
from PIL import Image                   # noqa: E402

import item_photo as ip                 # noqa: E402
import weapon_fit as wf                 # noqa: E402
import weapons_synth as ws              # noqa: E402

ENC = "utf-8-sig"
OUT = "art/items/weapons-redraw-v1"
SEED0 = 7700
ROLES = ("<image1> is the reference image: a high-quality picture of the weapon, already placed on the canvas "
         "exactly where it belongs; it is also the photographic reference. <image2> is the original game image of "
         "the same weapon, drawn as a clean flat sketch on the same canvas.")
PROMPT_SPEC = """Create a high-quality photorealistic redraw of the weapon in the
reference image, suitable for a transparent inventory sprite.

Treat the reference as an existing weapon design to preserve.
Do not redesign it or replace it with a familiar real-world gun.

Preserve:
- the exact orientation and placement on the canvas;
- overall width and height, within ±3%;
- the muzzle position and barrel direction;
- the proportions and positions of every major component;
- the original color regions and distinctive features;
- the magazine orientation, stock construction and real openings.

Improve the rendering substantially:
- crisp, clearly defined mechanical parts;
- convincing steel with controlled highlights and dark recesses;
- visible wood grain where the reference contains wood;
- readable small details and strong material separation;
- clean, continuous edges instead of pixel stair steps.

Use the photographic reference for material appearance, surface
detail and lighting. Use the original game image for geometry,
placement, colors and component layout. If they conflict, preserve
the game design.

The result must look detailed, solid and attractive at inventory size.
Do not make it thinner, smaller, duller or less detailed.

No added components, no missing components, no excessive rust,
no plastic-looking metal, no blur, no bright outline or halo.
Transparent background, including genuine internal openings.
No text, labels, arrows, guide marks or comparison panels."""
# особенности предмета - по оригиналу кадра и эталону (ident/batch_1.tsv, details), без догадок о прототипе
EXTRA = {
    "STR_STREET_SWEEPER": (
        "The two barrels are parallel and point straight up, side by side, with the muzzles at the top; keep the "
        "gap between them. The cylindrical front handle sticks out to the right exactly where shown. The dark boxy "
        "receiver keeps its small red and orange indicator lights. The black pistol grip is angled to the right. "
        "The dark rear body stays at the bottom."),
}
PANEL_NOTE = "Here the transparent background is represented by a flat panel. "
CURRENT = {}                            # вход текущего задания: эталон на холсте (inputs() задания не видит)


def ref_matte(path):
    """Матт эталона на ровном фоне без вырезки внутренних областей: weapon_fit.matte принимает тёмный корпус на
    тёмно-синем фоне рисунка Vitali за отверстия (белые пятна у рукояти). Снаружи - заливка от края по близкому к
    фону цвету (подписи и крошки отброшены там же), внутренние области, не связанные с краем, - тело.
    -> (RGB, альфа, фон)."""
    rgb, a, bg = wf.matte(path)
    return rgb, np.maximum(a, wf.holes_of(a > 0.5).astype(np.float32)), bg


def place_ref(crop, ref_path, panel_rgb, zoom):
    """Эталон -> холст кропа x zoom: матт ref_matte, равномерный масштаб (среднее геометрическое отношений
    высоты и ширины к габариту оригинала), центр к центру габарита. -> (RGB, отчёт)."""
    a_o = np.asarray(crop)[..., 3] > 0
    ys, xs = np.nonzero(a_o)
    ob = (xs.min() * zoom, ys.min() * zoom, (xs.max() + 1) * zoom, (ys.max() + 1) * zoom)
    tw, th = ob[2] - ob[0], ob[3] - ob[1]
    rgb, a, bg = ref_matte(ref_path)
    h, w = a.shape
    sw, sh = tw / float(w), th / float(h)
    s = float(np.sqrt(sw * sh))
    nw, nh = max(1, int(round(w * s))), max(1, int(round(h * s)))
    rgba = Image.fromarray(np.dstack([np.clip(rgb, 0, 255), a[..., None] * 255]).astype(np.uint8), "RGBA")
    rgba = rgba.resize((nw, nh), Image.LANCZOS)
    W, H = crop.width * zoom, crop.height * zoom
    canvas = Image.new("RGBA", (W, H), tuple(int(v) for v in panel_rgb) + (255,))
    cx, cy = (ob[0] + ob[2]) / 2.0, (ob[1] + ob[3]) / 2.0
    canvas.alpha_composite(rgba, (int(round(cx - nw / 2.0)), int(round(cy - nh / 2.0))))
    rep = {"ref": ref_path, "ref_bg": bg, "ref_px": [w, h], "orig_box16": [int(v) for v in ob],
           "scale": round(s, 4), "placed_px": [nw, nh],
           "aspect_ref_vs_orig_pct": round(100 * ((w / float(h)) / (tw / float(th)) - 1), 1),
           "placed_dw_pct": round(100 * (nw / float(tw) - 1), 1), "placed_dh_pct": round(100 * (nh / float(th) - 1), 1)}
    return canvas.convert("RGB"), rep


def inputs(variant, frame, rgb):
    """Замена struct_probe.inputs: [эталон на холсте, эскиз оригинала], добавки к промпту нет (она в prompt_for)."""
    zoom = ip.pr.RENDER_V1["zoom"]
    guide, grep_ = ip.sg.build(frame, zoom, rgb)
    ref_img, rrep = place_ref(frame, CURRENT["ref"], rgb, zoom)
    grep_ = dict(grep_, ref_place=rrep)
    return [ref_img, guide], "", grep_


def redraw_prompt(what, name, rgb):
    r, g, b = [int(v) for v in rgb]
    kind = "neutral " if name.startswith("grey") else ""
    extra = EXTRA.get(CURRENT.get("type", ""), "")
    return " ".join([ROLES, PROMPT_SPEC, extra, PANEL_NOTE + ip.pr.PANEL_TEXT.format(kind=kind, r=r, g=g, b=b)]).strip()


def jobs_for(only):
    lst = {r["master"]: r for r in ws.read_tsv(os.path.join(ws.BATCH, "list.tsv"))}
    jobs = []
    for k in range(1, 6):
        p = os.path.join(ws.IDENT, "batch_%d.tsv" % k)
        if not os.path.exists(p):
            continue
        for r in ws.read_tsv(p):
            m, t = r["master"], r["type"]
            if m not in only and t not in only:
                continue
            ref = r["ref"].strip()
            if ref in ("", "-") or not os.path.exists(os.path.join(ROOT, ref)):
                print("%s %s: нет эталона - пропуск" % (m, t), flush=True)
                continue
            lr = lst[m]
            w, h = [int(v) for v in lr["cells"].split("x")]
            frame = int(lr["frame"])
            full, src = ip.load_frame(t, frame)
            crop, box = ip.crop_job(full)
            jobs.append({"asset_id": t, "name": t, "master": m, "frame": frame, "cells": [w, h], "ref": ref,
                         "what": r.get("details", "").strip(), "status_ident": r["status"],
                         "seed": SEED0 + int(r["n"]), "src": src, "full": full, "crop": crop, "box": box})
    return jobs


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--only", default="STR_STREET_SWEEPER")
    ap.add_argument("--dry-run", action="store_true", dest="dry_run")
    ap.add_argument("--recut", action="store_true")
    ap.add_argument("--models", default=None)
    ap.add_argument("--max-renders", type=int, default=0, dest="max_renders")
    args = ap.parse_args()
    os.chdir(ROOT)
    ip.CARDS = os.path.join(ws.BATCH, "cards")
    jobs = jobs_for(set(filter(None, args.only.split(","))))
    if not jobs:
        raise SystemExit("нет заданий")
    sp, pr, pb = ip.sp, ip.pr, ip.pb
    R = sp.Render(args.out, args.models, args.max_renders, args.recut)
    import gen_fire
    import obj_photo as op
    neg0 = op.NEGATIVE + ip.NEGATIVE_EXTRA
    gen_fire.NEGATIVE = R.po.gen_fire.NEGATIVE = neg0
    pr.prompt_for = redraw_prompt
    sp.inputs = inputs
    pb.cut = ip.cut_fixed
    import asset_rev as ar
    import obj_gen_spec as ogs
    R.grev = ar.h12({"params": pr.RENDER_V1, "prompt": ROLES + PROMPT_SPEC + json.dumps(EXTRA, sort_keys=True),
                     "negative_extra": ip.NEGATIVE_EXTRA, "lock_rev": ogs.lock_rev(R.lock),
                     "code": ogs.code_parts((("weapons_redraw.py", ("place_ref", "inputs", "redraw_prompt")),))})
    print("weapons_redraw: generator_rev %s, предметов %d" % (R.grev, len(jobs)), flush=True)
    ind = os.path.join(args.out, "inputs")
    os.makedirs(ind, exist_ok=True)
    plan = []
    for j in jobs:
        CURRENT.update(ref=j["ref"], type=j["asset_id"])
        panels = pr.panels_by_margin(j["crop"])
        ims, _e, grep_ = inputs("R", j["crop"], panels[0][1])
        ims[0].save(os.path.join(ind, j["name"] + ".in1_ref.png"))
        ims[1].save(os.path.join(ind, j["name"] + ".in2_guide.png"))
        plan.append((j, panels))
        print("%-6s %-24s seed %d подложка %s, эталон: %s" % (j["master"], j["asset_id"], j["seed"], panels[0][0],
                                                            json.dumps(grep_["ref_place"], ensure_ascii=False)),
              flush=True)
    if args.dry_run:
        with open(os.path.join(args.out, "plan.md"), "w", encoding=ENC) as f:
            f.write("# weapons_redraw - план (generator_rev %s)\n\nnegative: %s\n\n" % (R.grev, neg0))
            for j, panels in plan:
                CURRENT.update(ref=j["ref"], type=j["asset_id"])
                f.write("## %s %s, кадр %d, эталон %s\n\n%s\n\n" % (
                    j["master"], j["asset_id"], j["frame"], j["ref"], redraw_prompt("", panels[0][0], panels[0][1])))
        print("план: %s" % os.path.join(args.out, "plan.md"))
        return
    raw_dir, meta_dir = os.path.join(args.out, "raw"), os.path.join(args.out, "meta")
    pack = os.path.join(args.out, "pack", "BIGOBS.PCK")
    missing = [j["asset_id"] for j, _p in plan if not os.path.exists(os.path.join(raw_dir, j["name"] + ".a0.png"))]
    if args.recut and missing:                      # R-127
        raise SystemExit("--recut, а ответа нет у %d: %s" % (len(missing), missing[:5]))
    if missing:
        R.check_lock()
    for d in (raw_dir, meta_dir, pack):
        os.makedirs(d, exist_ok=True)
    t0, cells = time.time(), []
    try:
        for n, (j, panels) in enumerate(plan, 1):
            CURRENT.update(ref=j["ref"], type=j["asset_id"])
            final, attempts = R.job("R", j, j["crop"], panels, raw_dir)
            if final is None:
                print("%-24s нет ответа (--recut)" % j["asset_id"], flush=True)
                continue
            im, rep, _g, _m, _c, verdict = final
            hd, prep = ip.place_fixed(im, j["box"], *j["cells"], j["full"], False)
            pp = os.path.join(pack, "%d.%s.png" % (j["frame"], j["asset_id"]))
            hd.save(pp)
            raw = attempts[-1]["raw"]
            mg = rep["model"]
            meta = {"asset_id": j["asset_id"], "master": j["master"], "frame": j["frame"], "cells": j["cells"],
                    "ref": j["ref"], "status_ident": j["status_ident"], "src": j["src"],
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
        print("лимит процесса: новых рендеров %d из %d - выхожу" % (R.renders, R.max), flush=True)
        sys.exit(sp.EXIT_MORE)
    if cells:
        ip.sheet(cells, os.path.join(args.out, "sheet.png"))
    print("готово: предметов %d, новых рендеров в этом процессе %d" % (len(cells), R.renders), flush=True)


if __name__ == "__main__":
    main()
