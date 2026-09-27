#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""pedia_push.py - готовые картинки педии из art\pedia_regen в мод hd (обе копии, R-081).

Цель (Vitali 26.09): в обычном режиме - минимум обнажёнки, в 18+ - всё.
Для каждой картинки плана берётся самый свежий результат варианта (папка <вариант>_redo важнее
серии, старшая метка v важнее) и кладётся в hd\UI\<имя>.png. Прежний файл с <имя>.pal.txt
переезжает в hd_18+\UI\ ТОЛЬКО если оригинал раздет (captions.json: topless/bottomless) -
там он остаётся картинкой режима 18+. Остальные прежние файлы просто заменяются.
Уже лежащий в hd_18+ файл не трогается, поэтому повторный запуск не затрёт прежнюю картинку новой.
.pal.txt в hd\UI остаётся: оригинал тот же, палитра та же.

Картинки из --hold (через запятую) не кладутся - их ещё переделывают.

    py -3 tools\hdart\pedia_push.py --dry-run
    py -3 tools\hdart\pedia_push.py
"""
import argparse
import glob
import io
import json
import os
import re
import shutil
import sys
import time

ENC_R = ENC_W = "utf-8-sig"
REGEN = os.path.join("art", "pedia_regen")
MODS = [os.path.join("Пиратки", "Dioxine_XPiratez", "user", "mods", "hd"),
        os.path.join("user", "mods", "hd")]


def newest(variant):
    """{stem в нижнем регистре: путь к самому свежему результату}"""
    best = {}
    pat = re.compile(r"^(.*)__%s__v(\d+)\.png$" % re.escape(variant))
    for d in sorted(glob.glob(os.path.join(REGEN, variant + "_*"))):
        redo = d.endswith("_redo")
        for f in os.listdir(d):
            m = pat.match(f)
            if not m:
                continue
            rank = (1 if redo else 0, int(m.group(2)))
            k = m.group(1).lower()
            if k not in best or rank > best[k][0]:
                best[k] = (rank, os.path.join(d, f))
    return {k: v[1] for k, v in best.items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--variant", default="hd")
    ap.add_argument("--hold", default="", help="не класть эти картинки, через запятую")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    plan = json.load(io.open(os.path.join(REGEN, "plan.json"), encoding=ENC_R))
    caps = json.load(io.open(os.path.join(REGEN, "captions.json"), encoding=ENC_R))
    res = newest(a.variant)
    hold = {n.strip().lower() for n in a.hold.split(",") if n.strip()}
    todo = []
    for key in plan["order"]:
        stem = os.path.splitext(plan["info"][key]["file"])[0]
        src = res.get(stem.lower())
        if src and stem.lower() not in hold:
            c = caps.get(key, {})
            todo.append((stem, src, bool(c.get("topless") or c.get("bottomless"))))
    print("картинок в плане %d, готовых %d, придержано %d, к раскладке %d, из них раздетых %d" % (
        len(plan["order"]), len(res), len(hold), len(todo), sum(1 for t in todo if t[2])))

    stamp = time.strftime("%Y%m%d_%H%M%S")
    log = []
    for root in MODS:
        ui, a18 = os.path.join(root, "hd", "UI"), os.path.join(root, "hd_18+", "UI")
        if not os.path.isdir(ui):
            print("нет папки %s - пропуск" % ui)
            continue
        moved = written = no_old = 0
        if not a.dry_run:
            os.makedirs(a18, exist_ok=True)
        for stem, src, nude in todo:
            old = os.path.join(ui, stem + ".png")
            if not os.path.exists(old):
                no_old += 1
            elif nude and not os.path.exists(os.path.join(a18, stem + ".png")):
                moved += 1
                if not a.dry_run:
                    shutil.copy2(old, os.path.join(a18, stem + ".png"))
                    pal = os.path.join(ui, stem + ".pal.txt")
                    if os.path.exists(pal):
                        shutil.copy2(pal, os.path.join(a18, stem + ".pal.txt"))
            written += 1
            if not a.dry_run:
                shutil.copyfile(src, old)
            log.append((root, stem, src, "18+" if nude else ""))
        print("%s: в hd_18+ перенесено %d, в hd записано %d (прежнего файла не было у %d)" % (
            root, moved, written, no_old))
    if not a.dry_run:
        out = os.path.join(REGEN, "push_%s_%s.tsv" % (a.variant, stamp))
        with io.open(out, "w", encoding=ENC_W) as f:
            for r in log:
                f.write("\t".join(r) + "\n")
        print("журнал: %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
