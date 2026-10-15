#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Контроль 4-го слота PHOTO_STRUCT_ACCEPTANCE_V1 (специалист 01.10): тот же предмет первым рендером свежего
процесса против прежнего ответа, сырой против сырого, до любой обработки.

Все три дефекта рендера приёмки (CARGO1:25, TOILET:15, CRIBDECOR:66) - 4-й рендер своего процесса. Если ответ
первого рендера свежего процесса с тем же зерном, замком, generator_rev, промптом, эскизом и подложкой совпал
побайтно - место в процессе ни при чём. Разошёлся - модель к 4-му рендеру меняет состояние, это баг исполнения.

    py -3.13 tools/hdart/slot_control.py        (CPU; рендер - photo_struct_render.py под render_chunks --max-renders 1)
Пишет <control>/compare.json, compare.md и sheet.png (прежний | свежий | разница x8).
"""
import hashlib
import json
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = os.path.join(ROOT, "art", "objects", "generation", "probes", "photo-struct-accept-v1")
CTRL = os.path.join(BASE, "control-slot4")
ENC = "utf-8-sig"


def sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def manifest(d):
    p = os.path.join(d, "renders.jsonl")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return {os.path.basename(r["raw"]): r for r in (json.loads(s) for s in f if s.strip())}


def diff(a, b):
    """Сырые ответы -> числа расхождения; разный размер или режим - расхождение без попиксельных чисел."""
    A, B = Image.open(a), Image.open(b)
    if A.size != B.size or A.mode != B.mode:
        return {"same_shape": False, "size_old": A.size, "size_new": B.size, "mode_old": A.mode, "mode_new": B.mode}
    x = np.asarray(A).astype(np.int16)
    y = np.asarray(B).astype(np.int16)
    d = np.abs(x - y)
    px = d.reshape(d.shape[0], d.shape[1], -1).max(axis=2)
    ys, xs = np.nonzero(px)
    return {"same_shape": True, "size": list(A.size), "mode": A.mode,
            "pixel_diff_count": int((px > 0).sum()), "pixels": int(px.size),
            "bbox": [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1] if len(xs) else None,
            "max_channel_delta": int(d.max()), "mean_abs_delta": round(float(d.mean()), 4)}, px


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    with open(os.path.join(CTRL, "jobs.json"), encoding=ENC) as f:
        jobs = json.load(f)
    old_m, new_m = manifest(BASE), manifest(CTRL)
    rows, tiles = [], []
    for j in jobs:
        fn = j["name"] + ".a0.png"
        a, b = os.path.join(BASE, "render", "raw", fn), os.path.join(CTRL, "render", "raw", fn)
        if not os.path.exists(b):
            rows.append({"asset_id": j["asset_id"], "error": "нет свежего ответа"})
            continue
        with open(os.path.join(BASE, "render", "meta", j["name"] + ".json"), encoding=ENC) as f:
            mo = json.load(f)
        with open(os.path.join(CTRL, "render", "meta", j["name"] + ".json"), encoding=ENC) as f:
            mn = json.load(f)
        ao, an = mo["attempts"][0], mn["attempts"][0]
        r = {"asset_id": j["asset_id"], "raw": fn, "raw_sha256_old": sha(a), "raw_sha256_new": sha(b),
             "old_process_render": old_m.get(fn, {}).get("process_render"),
             "new_process_render": new_m.get(fn, {}).get("process_render"),
             "same_inputs": {"seed": ao["seed"] == an["seed"], "prompt": ao["prompt"] == an["prompt"],
                             "panel": ao["panel_rgb"] == an["panel_rgb"], "guide": ao["guide"] == an["guide"],
                             "generator_rev": mo["generator_rev"] == mn["generator_rev"],
                             "model_lock": old_m.get(fn, {}).get("model_lock") == new_m.get(fn, {}).get("model_lock")}}
        r["byte_identical"] = r["raw_sha256_old"] == r["raw_sha256_new"]
        dd = diff(a, b)
        if isinstance(dd, tuple):
            r.update(dd[0])
            A = Image.open(a).convert("RGB")
            B = Image.open(b).convert("RGB")
            heat = Image.fromarray(np.clip(dd[1].astype(np.int32) * 8, 0, 255).astype(np.uint8)).convert("RGB")
            w, h = 384, int(384 * A.height / A.width)
            tiles.append([im.resize((w, h), Image.LANCZOS) for im in (A, B, heat)])
        else:
            r.update(dd)
        rows.append(r)
    if tiles:
        w, h = tiles[0][0].size
        sh = Image.new("RGB", (w * 3, h * len(tiles)), (20, 20, 20))
        for i, t in enumerate(tiles):
            for k, im in enumerate(t):
                sh.paste(im, (k * w, i * h))
        sh.save(os.path.join(CTRL, "sheet.png"))
    ident = [r for r in rows if r.get("byte_identical")]
    verdict = ("CLOSED: все побайтно совпали - место в процессе ни при чём" if len(ident) == len(jobs)
               else "OPEN: есть расхождения - баг исполнения, production до локализации нельзя")
    with open(os.path.join(CTRL, "compare.json"), "w", encoding=ENC) as f:
        json.dump({"verdict": verdict, "rows": rows}, f, ensure_ascii=False, indent=1)
    L = ["# Контроль 4-го слота", "", "Итог: **%s**." % verdict, "",
         "| предмет | слот был | слот стал | входы те же | побайтно | пикселей разных | bbox | max delta | mean delta |",
         "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if "error" in r:
            L.append("| %s | | | | %s | | | | |" % (r["asset_id"], r["error"]))
            continue
        L.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["asset_id"], r["old_process_render"], r["new_process_render"],
            "да" if all(r["same_inputs"].values()) else "НЕТ: " + ",".join(k for k, v in r["same_inputs"].items() if not v),
            "да" if r["byte_identical"] else "нет", r.get("pixel_diff_count", "-"), r.get("bbox", "-"),
            r.get("max_channel_delta", "-"), r.get("mean_abs_delta", "-")))
    with open(os.path.join(CTRL, "compare.md"), "w", encoding=ENC) as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
