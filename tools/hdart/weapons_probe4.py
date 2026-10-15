#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Проба Vitali 04.10 «там случаем лоры нет? кажись лора его ломает»: Edit-2511 БЕЗ единой LoRA.
В weapons_probe3 S1 и обе прошлые партии шли с Lightning (8 шагов, cfg 1), S2-S4 - с Lightning, погашенным весом 0.
Здесь photo_ui.Painter строится с fast=False и photoreal=False: LoRA не грузится вовсе, список адаптеров в лог.

Тот же гладкий вход и те же стволы, что в weapons_probe3, 40 шагов, cfg 4:
  N1 - текст Vitali дословно (как S1, но без Lightning) + негатив probe3;
  N2 - промпт выделки probe3 без слова «blued» (в S2 модель покрасила металл в синий) + негатив.
Лист: оригинал | гладкий вход | S1 (Lightning) | N1 | S2 (Lightning вес 0) | N2.

Без модели: py -3.13 tools/hdart/weapons_probe4.py --dry-run
С моделью - только через очередь:
    py -3.13 tools/gpuq.py add --name weapons_probe4 --prio 1 --cwd E:/OpenXCom -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/weapons_probe4.py
Выход art/items/weapons-probe4/: N1/, N2/<ТИП>.png, sheet.png, check.tsv, meta.json."""
import os

os.environ["HF_HUB_OFFLINE"] = "1"      # до импорта diffusers (R-145, R-207)

import argparse                         # noqa: E402
import csv                              # noqa: E402
import json                             # noqa: E402
import sys                              # noqa: E402
import time                             # noqa: E402

from PIL import Image                   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import weapons_edit as we               # noqa: E402
import weapons_probe3 as p3             # noqa: E402

ENC = "utf-8-sig"
OUT = "art/items/weapons-probe4"
P3 = p3.OUT
FULL = {"steps": 40, "cfg": 4.0}
PROMPT_ART = p3.PROMPT_ART.replace("blued and worn steel", "dark gunmetal steel, a little worn,")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--models", default="")
    ap.add_argument("--seed", type=int, default=p3.SEED)
    a = ap.parse_args()
    os.chdir(we.ROOT)
    assert PROMPT_ART != p3.PROMPT_ART, "замена слова blued не сработала"
    cols = (("S1", "S1 Lightning, ваш текст"), ("N1", "N1 без LoRA, ваш текст"),
            ("S2", "S2 Lightning вес 0"), ("N2", "N2 без LoRA, без blued"))
    for sub in ("N1", "N2"):
        os.makedirs(os.path.join(OUT, sub), exist_ok=True)
    we.ONLY = p3.ONLY
    items = []
    for r in we.rows():
        rgb, m = we.original(r["type"])
        sm = Image.open(os.path.join(P3, "in_smooth", r["type"] + ".png")).convert("RGB")
        it = {"row": r, "orig": (rgb, m), "smooth": sm}
        it["smooth_rep"], it["smooth_mask"] = p3.check(sm, rgb, m)
        for v in ("S1", "S2"):          # готовые ответы probe3 - для сравнения на листе
            pth = os.path.join(P3, v, r["type"] + ".png")
            if os.path.exists(pth):
                it[v] = Image.open(pth).convert("RGB")
                it[v + "_rep"], it[v + "_mask"] = p3.check(it[v], rgb, m)
        items.append(it)
    with open(os.path.join(OUT, "prompt.txt"), "w", encoding=ENC) as f:
        f.write("N1:\n%s\n\nN2:\n%s\n\nнегатив:\n%s\n" % (p3.PROMPT_VITALI, PROMPT_ART, p3.NEGATIVE))
    p3.OUT = OUT                        # лист пишется в свою папку
    if a.dry_run:
        p3.sheet(items, cols)
        print("dry-run: модель не грузилась ->", OUT)
        return
    import gen_hd
    import item_photo as ip
    import photo_ui as pu
    import torch
    models = a.models or gen_hd.DEFAULT_MODELS_DIR
    ip.edit_model_check(models)
    pu.MODEL = os.path.join(models, "hub", "models--Qwen--Qwen-Image-Edit-2511", "snapshots", ip.EDIT_MODEL_REV)
    painter = pu.Painter(models, fast=False, steps=FULL["steps"], photoreal=False)
    loaded = painter.pipe.get_list_adapters() if hasattr(painter.pipe, "get_list_adapters") else "?"
    print("LoRA в модели: %s (adapters %s, fast %s)" % (loaded or "нет", painter.adapters, painter.fast), flush=True)
    if painter.adapters or loaded:
        raise SystemExit("LoRA загружена - проба не про то")
    t0 = time.time()
    n, total = 0, 2 * len(items)
    for it in items:
        for v, prompt in (("N1", p3.PROMPT_VITALI), ("N2", PROMPT_ART)):
            ts = time.time()
            img = it["smooth"]
            out = painter.edit([img], prompt, p3.NEGATIVE, a.seed, FULL["steps"], FULL["cfg"], img.width, img.height)
            raw = Image.fromarray(out)
            raw.save(os.path.join(OUT, v, it["row"]["type"] + ".png"))
            it[v] = raw
            it[v + "_rep"], it[v + "_mask"] = p3.check(raw, *it["orig"])
            n += 1
            print("[%d/%d] %s %s %s: %.0f с, %s" % (n, total, it["row"]["master"], it["row"]["type"], v,
                                                    time.time() - ts, json.dumps(it[v + "_rep"], ensure_ascii=False)),
                  flush=True)
        p3.sheet(items, cols)
    with open(os.path.join(OUT, "check.tsv"), "w", encoding=ENC, newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["master", "type", "variant", "iou", "aspect_pct", "dcol", "lum", "lum_orig", "miss", "extra", "orig_px"])
        for it in items:
            for v, _h in cols:
                rep = it.get(v + "_rep") or {}
                w.writerow([it["row"]["master"], it["row"]["type"], v] +
                           [rep.get(k) for k in ("iou", "aspect_pct", "dcol", "lum", "lum_orig", "miss", "extra", "orig_px")])
    meta = {"seed": a.seed, "full": FULL, "lora": "нет", "model_rev": ip.EDIT_MODEL_REV,
            "prompts": {"N1": p3.PROMPT_VITALI, "N2": PROMPT_ART}, "negative": p3.NEGATIVE,
            "items": list(p3.ONLY), "seconds": round(time.time() - t0), "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
    with open(os.path.join(OUT, "meta.json"), "w", encoding=ENC) as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    if torch.cuda.is_available():
        print("пик памяти карты %.1f ГБ" % (torch.cuda.max_memory_allocated() / 2 ** 30), flush=True)
    print("готово за %.0f с -> %s" % (time.time() - t0, OUT), flush=True)


if __name__ == "__main__":
    main()
