#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""ab_sdxl.py - опыт: прежний конвейер SDXL (gen_hd + build_pack) на кадрах пилота, с новыми
подсказками кадра от prompt_writer и без них.

Ни листы наборов, ни мод не трогает: каждый вариант работает на СВОЕЙ копии папок наборов
(art\gen3\sdxl\<вариант>\sheets) и собирает пак в свой мод (art\gen3\sdxl\<вариант>\mod).
Готовые клетки копируются в art\TERRAIN\<НАБОР>.PCK\returned\sdxl_<вариант>, оценка - в
art\gen3\ab\sdxl_<вариант>\report.tsv, дальше лист ab_sheet.py.

Варианты:
  s0  как прежний батч: run_batch по умолчанию (полы 0.8, объекты вторым проходом 0.55)
  s1  то же + подсказка кадра из prompt_writer (описание и материал, коротко - CLIP читает 77 токенов)
  s2  s1 + стиль без «muted earthy colors» (он толкает всё в бурое)

    tools\hdart\.venv\Scripts\python.exe tools\hdart\ab_sdxl.py --list art\gen3\pilot.txt --variants s0,s1,s2
"""
import argparse
import csv
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import gen_hd                                           # noqa: E402
import build_pack                                       # noqa: E402

ENC = "utf-8-sig"
ROOT = os.path.join("art", "gen3", "sdxl")
AB = os.path.join("art", "gen3", "ab")
KEEP = ("original.png", "layout.json", "hints.json", "mask_x4.png", "original_x4.png")

NEUTRAL = gen_hd.STYLE.replace("muted earthy colors", "true-to-source colors")
NEUTRAL_GROUND = gen_hd.STYLE_GROUND.replace("muted earthy colors", "true-to-source colors")


def read_list(path):
    out = {}
    with open(path, encoding=ENC) as f:
        for line in f:
            p = line.split()
            if len(p) >= 2 and not line.startswith("#"):
                name = p[0].upper()
                name = name if name.endswith(".PCK") else name + ".PCK"
                out.setdefault(name, []).append(int(p[1]))
    return out


def short_hint(r, words=14):
    """Подсказка для CLIP: описание, а если материал в нём не назван - материал впереди."""
    subj = (r.get("описание") or "").strip().rstrip(".")
    mat = (r.get("_material") or "").strip()
    if mat and mat.lower() not in subj.lower():
        subj = "%s, %s" % (mat, subj) if subj else mat
    return " ".join(subj.split()[:words])


def make_hints(plan, path):
    import prompt_writer as pw
    import tile_forge as tf
    w = pw.Writer(os.path.join("art", "TERRAIN"), os.path.join("art", "gen3"), vlm=False)
    out = {}
    for name, frames in plan.items():
        sh = tf.Sheet(os.path.join("art", "TERRAIN"), name)
        for i in frames:
            r = w.row(sh, i)
            h = short_hint(r) if r else ""
            if h:
                out.setdefault(name, {})[str(i)] = h
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding=ENC) as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    return out


def copy_set(name, dst):
    src = os.path.join("art", "TERRAIN", name)
    os.makedirs(dst, exist_ok=True)
    for fn in KEEP:
        if os.path.exists(os.path.join(src, fn)):
            shutil.copy2(os.path.join(src, fn), os.path.join(dst, fn))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", required=True)
    ap.add_argument("--variants", default="s0,s1,s2")
    ap.add_argument("--object-strength", type=float, default=0.55, dest="object_strength")
    args = ap.parse_args()
    plan = read_list(args.list)
    hints_path = os.path.join(ROOT, "hints.json")
    hints = make_hints(plan, hints_path)
    print("подсказок: %d" % sum(len(v) for v in hints.values()), flush=True)

    import score_batch as sb
    import tile_forge as tf
    import paint3 as p3
    sargs = p3.score_args()

    for v in [x.strip() for x in args.variants.split(",") if x.strip()]:
        vdir = os.path.join(ROOT, v)
        sheets, mod = os.path.join(vdir, "sheets"), os.path.join(vdir, "mod")
        extra = []
        if v in ("s1", "s2"):
            extra += ["--extra-hints", hints_path]
        if v == "s2":
            extra += ["--prompt", NEUTRAL, "--prompt-ground", NEUTRAL_GROUND]
        rep_dir = os.path.join(AB, "sdxl_" + v)
        os.makedirs(rep_dir, exist_ok=True)
        rep = open(os.path.join(rep_dir, "report.tsv"), "w", encoding=ENC, newline="")
        wr = csv.DictWriter(rep, ["набор", "кадр", "годен", "балл", "флаги", "с", "подсказка"],
                            delimiter="\t", lineterminator="\n")
        wr.writeheader()
        print("=== вариант %s" % v, flush=True)
        for name, frames in plan.items():
            t0 = time.time()
            sd = os.path.join(sheets, name)
            if os.path.isdir(sd):
                shutil.rmtree(sd)
            copy_set(name, sd)
            fr = ",".join(str(i) for i in frames)
            base = ["--sheets", sheets, "--set", name, "--frame", fr] + extra
            # как run_batch: полы одним проходом, объекты вторым с пониженной силой
            for only, more in (("ground", []), ("objects", ["--strength", "%g" % args.object_strength])):
                try:
                    gen_hd.main(base + ["--only", only] + more)
                except SystemExit as e:
                    print("  %s %s: %s" % (name, only, e), flush=True)
            painted = os.path.join(sd, "painted_x4.png")
            build_pack.main(["--sheets", sheets, "--set", name, "--hd", painted, "--mod", mod,
                             "--pack-path", "TERRAIN", "--frames"] + [str(i) for i in frames]
                            + ["--variants", "off", "--no-preview"])
            dt = (time.time() - t0) / max(1, len(frames))
            sh = tf.Sheet(os.path.join("art", "TERRAIN"), name)
            out = os.path.join("art", "TERRAIN", name, "returned", "sdxl_" + v)
            os.makedirs(out, exist_ok=True)
            for i in frames:
                cell = os.path.join(mod, "hd", "TERRAIN", name, "%d.png" % i)
                if not os.path.exists(cell):
                    print("  %s %d: клетки нет" % (name, i), flush=True)
                    continue
                shutil.copy2(cell, os.path.join(out, "%d.png" % i))
                from PIL import Image
                sc = sb.score_frame(sh, i, Image.open(cell).convert("RGBA"), 4, sargs)
                wr.writerow({"набор": name, "кадр": i, "годен": sc["годен"] if sc else 0,
                             "балл": "%.3f" % (sc["балл"] if sc else -9), "флаги": (sc or {}).get("flags", ""),
                             "с": "%.1f" % dt, "подсказка": hints.get(name, {}).get(str(i), "")})
                rep.flush()
                print("  %-20s %3d  %s  %.1f с" % (name, i, "годен" if sc and sc["годен"] else "брак", dt), flush=True)
        rep.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
