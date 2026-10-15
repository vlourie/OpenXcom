#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Проба Vitali 04.10 «я переделал движок графики, попробуй с ним»: те же пять стволов (weapons_probe3.ONLY)
производственным рендером RESTORE (DECISIONS 2026-10-03) вместо Edit-2511.

Путь - restore_probe_v1 без правки его кода: модель Qwen-Image-2.1 по замку, вход варианта C (структурный эскиз
struct_guide первой картинкой, оригинал bicubic второй), 40 шагов, cfg 4, 1 Мп, подложка panels_by_margin,
вырезка photo_base.cut, проверки photo_accept, до трёх попыток - цикл struct_probe.Render.job.
Отличия - только то, что требует инвентарь:
  - ракурс: battle_view.KINDS["inventory"] - не боевая изометрия, ракурс с оригинала набора; фраза RESTORE
    «seen from above at 30 degrees in isometric view» заменена на VIEW_INV;
  - подпись предмета - английское имя типа из списка партии (описаний не надо, Vitali 04.10).
Память карты: Qwen21Painter с enable_model_cpu_offload (части по очереди, без pin_memory); после каждого рендера
счётчик Windows (weapons_probe5.gpu_mem), shared больше 0,5 ГБ - стоп (R-213).

Без модели: py -3.13 tools/hdart/weapons_restore.py --dry-run   (промпты и эскизы)
С моделью - только через очередь:
    py -3.13 tools/gpuq.py add --name weapons_restore --prio 1 --cwd E:/OpenXCom -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/weapons_restore.py
Выход art/items/weapons-restore/: raw/, cut/<ТИП>.png (RGBA x4), sheet.png (оригинал | вход | N2 | V | R),
check.tsv, prompts.md, meta.json."""
import os

os.environ["HF_HUB_OFFLINE"] = "1"      # до импорта diffusers (R-145, R-207)

import argparse                         # noqa: E402
import csv                              # noqa: E402
import json                             # noqa: E402
import sys                              # noqa: E402
import time                             # noqa: E402

import numpy as np                      # noqa: E402
from PIL import Image                   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import weapons_edit as we               # noqa: E402
import weapons_probe3 as p3             # noqa: E402
import weapons_probe5 as w5             # noqa: E402

ENC = "utf-8-sig"
OUT = "art/items/weapons-restore"
VARIANT = "C"
ISO = "seen from above at 30 degrees in isometric view exactly like the sprite"
VIEW_INV = "seen from exactly the same side and angle as the sprite, flat side view as in an inventory"
SHEET_BG = (255, 0, 255)                # под замер p3.check: фон - медиана края, у стволов пурпура нет


def frame_of(rgb, m):
    """Кадр как у photo_base.job_frame: RGBA, кроп по габариту с полями pad -> (кадр, box)."""
    import photo_base as pb
    a = np.dstack([rgb, m * 255]).astype(np.uint8)
    whole = Image.fromarray(a, "RGBA")
    x0, y0, x1, y1 = we.bbox(m)
    p = pb.RENDER["pad"]
    box = (max(0, x0 - p), max(0, y0 - p), min(whole.width, x1 + p), min(whole.height, y1 + p))
    return whole, box, whole.crop(box)


def on_sheet_bg(whole, box, im):
    """Вырезка x4 на холсте оригинала x4 поверх SHEET_BG -> RGB для p3.check и листа."""
    canvas = Image.new("RGBA", (whole.width * 4, whole.height * 4), SHEET_BG + (255,))
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    layer.paste(im, (box[0] * 4, box[1] * 4))
    canvas.alpha_composite(layer)
    return canvas.convert("RGB")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--seed", type=int, default=p3.SEED)
    a = ap.parse_args()
    os.chdir(we.ROOT)
    import battle_view as bv
    import gen_fire
    import photo_render as pr
    import restore_probe_v1 as rp
    import struct_probe as sp
    import struct_guide as sg
    if bv.prompt_block("inventory") is not None:
        raise SystemExit("battle_view считает инвентарь боевым видом - проба написана под другое")
    if ISO not in rp.RESTORE:
        raise SystemExit("в RESTORE нет фразы изометрии - текст baseline изменился")
    rp.RESTORE = rp.RESTORE.replace(ISO, VIEW_INV)
    for sub in ("raw", "cut", "guide"):
        os.makedirs(os.path.join(OUT, sub), exist_ok=True)
    we.ONLY = p3.ONLY
    items, lines = [], ["# weapons_restore: промпты", "", "Негатив: `%s`" % rp.negative(), ""]
    for r in we.rows():
        rgb, m = we.original(r["type"])
        whole, box, frame = frame_of(rgb, m)
        panels = pr.panels_by_margin(frame)
        sm = Image.open(os.path.join(p3.OUT, "in_smooth", r["type"] + ".png")).convert("RGB")
        it = {"row": r, "orig": (rgb, m), "smooth": sm, "whole": whole, "box": box, "frame": frame,
              "panels": panels,
              "job": {"asset_id": r["master"], "name": r["type"], "seed": a.seed, "what": "the weapon " + r["en"].strip()}}
        it["smooth_rep"], it["smooth_mask"] = p3.check(sm, rgb, m)
        g, rep = sg.build(frame, pr.RENDER_V1["zoom"], panels[0][1])
        g.save(os.path.join(OUT, "guide", r["type"] + ".png"))
        _ims, extra, _rep = sp.inputs(VARIANT, frame, panels[0][1])
        lines += ["## %s %s (подложка %s, кадр %dx%d)" % (r["master"], r["type"], panels[0][0], frame.width,
                                                        frame.height), "",
                  rp.prompt_for(it["job"]["what"], panels[0][0], panels[0][1]) + extra, ""]
        items.append(it)
    with open(os.path.join(OUT, "prompts.md"), "w", encoding=ENC) as f:
        f.write("\n".join(lines))
    cols = (("N2", "N2 Edit, мой промпт"), ("V", "V Edit, ваш текст"), ("R", "R движок RESTORE"))
    w5.load(items, w5.P4, "N2")
    w5.load(items, w5.OUT, "V")
    p3.OUT = OUT                        # лист пишется в свою папку
    if a.dry_run:
        p3.sheet(items, cols)
        print("dry-run: модель не грузилась -> %s (промпты, эскизы, лист без R)" % OUT)
        return
    R = sp.Render(OUT, None, 0, False)
    pr.prompt_for = rp.prompt_for               # только в этом процессе
    gen_fire.NEGATIVE = rp.negative()           # Render.__init__ поставил obj_photo.NEGATIVE - заменить после
    print("weapons_restore: generator_rev %s, guide_rev %s, cut_rev %s, стволов %d" % (
        R.grev, R.guide_rev, R.cut_rev, len(items)), flush=True)
    t0 = time.time()
    for n, it in enumerate(items, 1):
        ts = time.time()
        final, attempts = R.job(VARIANT, it["job"], it["frame"], it["panels"], os.path.join(OUT, "raw"))
        if w5.gpu_mem("ствол %d" % n) > 0.5:
            raise SystemExit("ушло в shared - стоп")
        im, rep, _g, _m, c, verdict = final
        im.save(os.path.join(OUT, "cut", it["row"]["type"] + ".png"))
        it["R"] = on_sheet_bg(it["whole"], it["box"], im)
        it["R_rep"], it["R_mask"] = p3.check(it["R"], *it["orig"])
        it["verdict"], it["attempts"] = verdict, len(attempts)
        print("[%d/%d] %s %s R: %s, попыток %d, %.0f с, %s" % (
            n, len(items), it["row"]["master"], it["row"]["type"], verdict, len(attempts), time.time() - ts,
            json.dumps(it["R_rep"], ensure_ascii=False)), flush=True)
        p3.sheet(items, cols)
    with open(os.path.join(OUT, "check.tsv"), "w", encoding=ENC, newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["master", "type", "variant", "iou", "aspect_pct", "dcol", "lum", "lum_orig", "miss", "extra",
                    "orig_px", "machine", "attempts"])
        for it in items:
            for v, _h in cols:
                rep = it.get(v + "_rep") or {}
                w.writerow([it["row"]["master"], it["row"]["type"], v] +
                           [rep.get(k) for k in ("iou", "aspect_pct", "dcol", "lum", "lum_orig", "miss", "extra",
                                                 "orig_px")] +
                           ([it.get("verdict"), it.get("attempts")] if v == "R" else ["", ""]))
    meta = {"seed": a.seed, "variant": VARIANT, "params": pr.RENDER_V1, "generator_rev": R.grev,
            "guide_rev": R.guide_rev, "cut_rev": R.cut_rev, "prompt": rp.RESTORE, "negative": gen_fire.NEGATIVE,
            "view": VIEW_INV, "items": list(p3.ONLY), "seconds": round(time.time() - t0),
            "gpuq_job": os.environ.get("GPUQ_JOB_ID", ""), "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
    with open(os.path.join(OUT, "meta.json"), "w", encoding=ENC) as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print("готово за %.0f с -> %s" % (time.time() - t0, OUT), flush=True)


if __name__ == "__main__":
    main()
