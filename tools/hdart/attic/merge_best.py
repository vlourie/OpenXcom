# -*- coding: utf-8 -*-
"""Слияние двух паков TERRAIN по кадру: в мод идёт лучший из LoRA и прежнего (правило R-061).

Решение по кадру берётся, в порядке убывания надёжности:
  1) прямая оценка этого кадра в обеих таблицах score.tsv;
  2) оценка той же КАРТИНКИ в другом наборе (хэш переписи копий, R-049);
  3) оценка кадра с тем же точным хэшем в переписи census/frames.tsv;
  4) оценка кадра, зеркалом которого этот кадр является (столбец «зеркало», R-051);
  5) доля годных по НАБОРУ: у природных наборов LoRA лучше прежнего пака, у металла хуже;
  6) если у набора нет ни одной оценки - берём прежний пак: он измерен лучше (76% против 47.8%).

Заменяемые кадры LoRA не теряются: перед заменой они складываются в art/_backup/<имя>.
    py -3 merge_best.py --dry-run
"""
import argparse
import csv
import glob
import io
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.join("tools", "hdart"))
import dupe_plan as dup  # noqa: E402

ENC = "utf-8-sig"
MOD = os.path.join(u"Пиратки", "Dioxine_XPiratez", "user", "mods", "hd", "hd", "TERRAIN")
OLD = os.path.join("art", "_backup", "TERRAIN_before_lora_20260924_1057")
SHEETS = os.path.join("art", "TERRAIN")
KEEP = os.path.join("art", "_backup", "TERRAIN_lora_%s" % time.strftime("%Y%m%d_%H%M"))


def load_scores(path):
    out = {}
    with io.open(path, encoding=ENC, newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            out[(r[u"набор"], int(r[u"кадр"]))] = int(r[u"годен"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", dest="dry")
    args = ap.parse_args()

    lora = load_scores(os.path.join("art", "_review", "batch_score", "score.tsv"))
    old = load_scores(os.path.join("art", "_review", "batch_score_old", "score.tsv"))
    by_frame, _ = dup.load(SHEETS)

    exact, mirror = {}, {}
    with io.open(os.path.join("census", "frames.tsv"), encoding=ENC, newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            if r[u"раздел"] != "TERRAIN":
                continue
            key = (r[u"набор"] + ".PCK", int(r[u"кадр"]))
            exact[key] = (r.get(u"точный") or "").strip()
            mirror[key] = (r.get(u"зеркало") or "").strip()

    # сводки решений по картинке, по точному хэшу
    def add(d, h, gl, go):
        if not h:
            return
        a = d.setdefault(h, [0, 0])
        a[0] = max(a[0], gl)
        a[1] = max(a[1], go)

    by_dupe, by_exact = {}, {}
    for key, gl in lora.items():
        go = old.get(key)
        if go is None:
            continue
        add(by_dupe, by_frame.get((key[0][:-4], key[1]), ""), gl, go)
        add(by_exact, exact.get(key, ""), gl, go)

    # доля годных по набору: ею решаются кадры, у которых своей оценки нет
    rate = {}
    for key, gl in lora.items():
        go = old.get(key)
        if go is None:
            continue
        a = rate.setdefault(key[0], [0, 0, 0])
        a[0] += gl
        a[1] += go
        a[2] += 1

    why = {u"кадр": 0, u"копия": 0, u"точный": 0, u"зеркало": 0,
           u"по набору": 0, u"без оценки": 0}
    plan = []
    keep_lora = already = 0
    for p in sorted(glob.glob(os.path.join(MOD, "*.PCK", "*.png"))):
        name = os.path.basename(os.path.dirname(p))
        b = os.path.basename(p)[:-4]
        if not b.isdigit():
            continue
        key = (name, int(b))
        if key in lora and key in old:
            gl, go, tag = lora[key], old[key], u"кадр"
        else:
            h = by_frame.get((name[:-4], key[1]), "")
            e = exact.get(key, "")
            m = mirror.get(key, "")
            if h in by_dupe:
                gl, go = by_dupe[h]; tag = u"копия"
            elif e in by_exact:
                gl, go = by_exact[e]; tag = u"точный"
            elif m in by_exact:
                gl, go = by_exact[m]; tag = u"зеркало"
            elif name in rate and rate[name][2] >= 5:
                a = rate[name]
                gl, go = (1, 0) if a[0] >= a[1] else (0, 1)
                tag = u"по набору"
            else:
                gl, go, tag = 0, 1, u"без оценки"
        why[tag] += 1
        if go and not gl:
            src = os.path.join(OLD, name, "%d.png" % key[1])
            if not os.path.exists(src):
                continue
            # уже возвращённое не переписываем второй раз: прогон идёмпотентен
            if os.path.getsize(src) == os.path.getsize(p):
                already += 1
            else:
                plan.append((src, p, name, key[1]))
        else:
            keep_lora += 1

    print(u"клеток: %d, откуда решение: %s" % (sum(why.values()), why))
    print(u"вернуть из прежнего пака: %d (уже стоит: %d), оставить LoRA: %d"
          % (len(plan), already, keep_lora))
    sets = {}
    for _, _, name, _ in plan:
        sets[name] = sets.get(name, 0) + 1
    whole = [n for n, c in sets.items()
             if c == len(glob.glob(os.path.join(MOD, n, "*.png")))]
    print(u"наборов затронуто: %d, из них целиком: %d" % (len(sets), len(whole)))

    if args.dry:
        print(u"пробный прогон, ничего не записано")
        return

    for src, dst, name, i in plan:
        d = os.path.join(KEEP, name)
        os.makedirs(d, exist_ok=True)
        shutil.move(dst, os.path.join(d, "%d.png" % i))
        shutil.copy2(src, dst)
    print(u"заменено %d клеток, версия LoRA сложена в %s" % (len(plan), KEEP))


if __name__ == "__main__":
    main()
