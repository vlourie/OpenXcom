#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Проба Vitali 04.10 после «отвратительно, пробуй как ты думаешь»: что держит Edit-2511 на уровне клякс.
Две прошлые партии (weapons-edit-v1 A, weapons-edit-v2-literal) шли на xBRZ-входе и Lightning 8 шагов без CFG:
модель обводила плоские пятна xBRZ (R-004) и не слушала негатив (cfg 1). Здесь на тех же стволах четыре способа:

  S1 - вход ГЛАДКИЙ (оригинал bicubic, без xBRZ), Lightning 8 шагов, текст Vitali дословно;
  S2 - вход гладкий, полные 40 шагов, cfg 4 (Lightning выключен), свой промпт выделки + негатив;
  S3 - как S2, но вход xBRZ - отделяет вклад входа от вклада шагов;
  S4 - второй проход: ответ S2 снова в Edit (40 шагов, cfg 4) - «дорисуй мелочь, ничего не меняя».

Одна модель на всё: сначала все S1 с Lightning, потом Lightning гасится (вес 0) и идут полные.
Ответ - как есть; маска по краю ответа (фон мог смениться) только для замера и листа. В мод ничего не идёт.

Без модели (входы и пустой лист): py -3.13 tools/hdart/weapons_probe3.py --dry-run
С моделью - только через очередь:
    py -3.13 tools/gpuq.py add --name weapons_probe3 --prio 1 --cwd E:/OpenXCom -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/weapons_probe3.py
Выход art/items/weapons-probe3/: in_smooth/, in_xbrz/, S1..S4/<ТИП>.png, sheet.png, check.tsv, meta.json."""
import os

os.environ["HF_HUB_OFFLINE"] = "1"      # до импорта diffusers (R-145, R-207)

import argparse                         # noqa: E402
import csv                              # noqa: E402
import json                             # noqa: E402
import sys                              # noqa: E402
import time                             # noqa: E402

import numpy as np                      # noqa: E402
from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import weapons_edit as we               # noqa: E402

ENC = "utf-8-sig"
OUT = "art/items/weapons-probe3"
ONLY = ("W-014", "W-015", "W-033", "W-040", "W-055")
SEED = 4242
FULL = {"steps": 40, "cfg": 4.0}

PROMPT_VITALI = we.PROMPT_LIT
PROMPT_ART = ("Redraw <image1> at high resolution as a detailed hand-painted game inventory item. It is exactly "
              "the same weapon in the same view: the same outline, size, proportions and colours, every part in "
              "the same place, nothing added and nothing removed. Give it clear volume and real materials: "
              "blued and worn steel with soft highlights along the edges, wood with visible grain, crisp clean "
              "edges, small parts readable - screws, trigger, sights, joints. Keep the same plain flat background "
              "colour, no shadow, no text.")
PROMPT_REFINE = ("Refine <image1>: it is the same weapon, keep the outline, size, colours and every part exactly "
                 "where they are. Add finer painted detail and cleaner material shading - steel highlights, wood "
                 "grain, sharp small parts. Keep the same plain flat background colour, no shadow, no text.")
NEGATIVE = ("pixel art, blocky pixels, jagged stair-step edges, flat colour blobs, posterized, smeared, blurry, "
            "photo, photograph, rust, dirt, text, watermark, white background, gradient background, shadow, "
            "extra parts, a different weapon")


def smooth_input(rgb, m, box, size, panel):
    """Оригинал на подложке в своём масштабе, затем bicubic до размера xBRZ-входа: никаких плоских пятен."""
    x0, y0, x1, y1 = box
    a = m[y0:y1, x0:x1, None].astype(np.float32)
    px = rgb[y0:y1, x0:x1] * a + np.asarray(panel, np.float32) * (1 - a)
    big = Image.fromarray(px.astype(np.uint8)).resize(size, Image.BICUBIC)
    # bicubic сам сетку не стирает - ступеньки видны; размытие на полпикселя оригинала их снимает (R-004)
    return big.filter(ImageFilter.GaussianBlur(0.45 * size[0] / float(x1 - x0)))


def check(raw, rgb, m):
    """Замер weapons_edit.check, но фон - медиана края ответа (модель могла сменить подложку)."""
    rm, bg = we.object_mask(np.asarray(raw), bg=None, thr=24.0)
    return we.check(raw, tuple(float(v) for v in bg), rgb, m)


def sheet(items, cols):
    try:
        font = ImageFont.truetype("arial.ttf", 15)
    except OSError:
        font = ImageFont.load_default()
    CW, CH = 220, 380
    heads = ("оригинал", "вход гладкий") + tuple(h for _v, h in cols)
    out = Image.new("RGB", (len(heads) * (CW + 6) + 10, len(items) * (CH + 52) + 30), (20, 22, 30))
    d = ImageDraw.Draw(out)
    for k, hname in enumerate(heads):
        d.text((10 + k * (CW + 6), 6), hname, fill=(200, 200, 210), font=font)
    for i, it in enumerate(items):
        Y = 28 + i * (CH + 52)
        rgb, m = it["orig"]
        x0, y0, x1, y1 = we.bbox(m)
        oi = Image.fromarray(np.dstack([rgb, m * 255]).astype(np.uint8)[y0:y1, x0:x1], "RGBA")
        s = max(1, int(min(CW / oi.width, CH / oi.height)))
        oi = oi.resize((oi.width * s, oi.height * s), Image.NEAREST)
        tile = Image.new("RGBA", (CW, CH), (34, 36, 44, 255))
        tile.alpha_composite(oi, ((CW - oi.width) // 2, (CH - oi.height) // 2))
        cells = [tile.convert("RGB"), we.view(it["smooth"], it["smooth_mask"], (CW, CH))] + [
            we.view(it.get(v), it.get(v + "_mask"), (CW, CH)) for v, _h in cols]
        for k, c in enumerate(cells):
            out.paste(c, (10 + k * (CW + 6), Y))
        r = it["row"]
        d.text((10, Y + CH + 4), "%s %s" % (r["master"], r["en"]), fill=(225, 225, 235), font=font)
        for j, (v, _h) in enumerate(cols):
            rep = it.get(v + "_rep")
            if rep:
                X = 10 + (2 + j) * (CW + 6)
                d.text((X, Y + CH + 4), "IoU %.3f  ш/в %+.1f%%" % (rep["iou"], rep["aspect_pct"]),
                       fill=(225, 225, 235), font=font)
                d.text((X, Y + CH + 22), "цвет %s  ярк %s/%s" % (rep["dcol"], rep["lum"], rep["lum_orig"]),
                       fill=(170, 170, 185), font=font)
    out.save(os.path.join(OUT, "sheet.png"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--models", default="")
    ap.add_argument("--seed", type=int, default=SEED)
    a = ap.parse_args()
    os.chdir(we.ROOT)
    cols = (("S1", "S1 гладкий, 8 шагов, ваш текст"), ("S2", "S2 гладкий, 40 шагов"),
            ("S3", "S3 xBRZ, 40 шагов"), ("S4", "S4 = S2 + второй проход"))
    for sub in ("in_smooth", "in_xbrz") + tuple(v for v, _h in cols):
        os.makedirs(os.path.join(OUT, sub), exist_ok=True)
    we.ONLY = ONLY
    items = []
    for r in we.rows():
        rgb, m = we.original(r["type"])
        xb, panel, box = we.make_input(r["type"], rgb, m)
        sm = smooth_input(rgb, m, box, xb.size, panel)
        xb.save(os.path.join(OUT, "in_xbrz", r["type"] + ".png"))
        sm.save(os.path.join(OUT, "in_smooth", r["type"] + ".png"))
        it = {"row": r, "orig": (rgb, m), "xbrz": xb, "smooth": sm, "panel": panel}
        it["smooth_rep"], it["smooth_mask"] = check(sm, rgb, m)
        print("%s %s: вход %dx%d, подложка %s, гладкий вход против оригинала IoU %s" % (
            r["master"], r["type"], sm.width, sm.height, panel, it["smooth_rep"] and it["smooth_rep"]["iou"]), flush=True)
        items.append(it)
    with open(os.path.join(OUT, "prompt.txt"), "w", encoding=ENC) as f:
        f.write("S1 (8 шагов, cfg 1):\n%s\n\nS2, S3 (40 шагов, cfg 4):\n%s\n\nS4 второй проход:\n%s\n\nнегатив:\n%s\n"
                % (PROMPT_VITALI, PROMPT_ART, PROMPT_REFINE, NEGATIVE))
    if a.dry_run:
        sheet(items, cols)
        print("dry-run: модель не грузилась ->", OUT)
        return
    import gen_hd
    import item_photo as ip
    import torch
    models = a.models or gen_hd.DEFAULT_MODELS_DIR
    ip.edit_model_check(models)
    painter = ip.EditPainter(models)
    t0 = time.time()
    n, total = 0, 4 * len(items)

    def render(it, v, img, prompt, steps, cfg, neg=""):
        nonlocal n
        ts = time.time()
        res = painter.pipe(prompt=prompt, image=[img], num_inference_steps=steps,
                           generator=torch.Generator("cpu").manual_seed(a.seed), negative_prompt=neg,
                           true_cfg_scale=cfg, width=img.width, height=img.height)
        raw = res.images[0].convert("RGB")
        raw.save(os.path.join(OUT, v, it["row"]["type"] + ".png"))
        it[v] = raw
        it[v + "_rep"], it[v + "_mask"] = check(raw, *it["orig"])
        n += 1
        print("[%d/%d] %s %s %s: %.0f с, %s" % (n, total, it["row"]["master"], it["row"]["type"], v,
                                                time.time() - ts, json.dumps(it[v + "_rep"], ensure_ascii=False)),
              flush=True)

    for it in items:                    # Lightning: модель грузится здесь с LoRA
        render(it, "S1", it["smooth"], PROMPT_VITALI, ip.EDIT_RUN["steps"], ip.EDIT_RUN["cfg"])
    pp = painter.p                      # Lightning гасится: вес 0, базовый планировщик, CFG работает
    pp.pipe.set_adapters(["lightning"], [0.0])
    pp.adapters, pp.fast = [], False
    print("Lightning выключен: %d шагов, cfg %.1f" % (FULL["steps"], FULL["cfg"]), flush=True)
    for it in items:
        render(it, "S2", it["smooth"], PROMPT_ART, FULL["steps"], FULL["cfg"], NEGATIVE)
        render(it, "S3", it["xbrz"], PROMPT_ART, FULL["steps"], FULL["cfg"], NEGATIVE)
        render(it, "S4", it["S2"], PROMPT_REFINE, FULL["steps"], FULL["cfg"], NEGATIVE)
        sheet(items, cols)              # лист растёт по ходу - можно смотреть, не дожидаясь конца
    sheet(items, cols)
    with open(os.path.join(OUT, "check.tsv"), "w", encoding=ENC, newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["master", "type", "variant", "iou", "aspect_pct", "dcol", "lum", "lum_orig", "miss", "extra", "orig_px"])
        for it in items:
            for v, _h in cols:
                rep = it.get(v + "_rep") or {}
                w.writerow([it["row"]["master"], it["row"]["type"], v] +
                           [rep.get(k) for k in ("iou", "aspect_pct", "dcol", "lum", "lum_orig", "miss", "extra", "orig_px")])
    meta = {"seed": a.seed, "fast": ip.EDIT_RUN, "full": FULL, "model_rev": ip.EDIT_MODEL_REV,
            "prompts": {"S1": PROMPT_VITALI, "S2": PROMPT_ART, "S3": PROMPT_ART, "S4": PROMPT_REFINE},
            "negative": NEGATIVE, "items": list(ONLY), "seconds": round(time.time() - t0),
            "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
    with open(os.path.join(OUT, "meta.json"), "w", encoding=ENC) as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    if torch.cuda.is_available():
        print("пик памяти карты %.1f ГБ" % (torch.cuda.max_memory_allocated() / 2 ** 30), flush=True)
    print("готово за %.0f с -> %s" % (time.time() - t0, OUT), flush=True)


if __name__ == "__main__":
    main()
