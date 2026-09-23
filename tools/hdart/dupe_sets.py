#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Один и тот же кадр в РАЗНЫХ наборах: что рисовать один раз на весь проект.

dupe_frames.py ищет повторы ВНУТРИ набора. Здесь другое: кадры, побайтово совпадающие
между наборами. У X-Piratez наборы делались копированием, поэтому одна и та же плитка
лежит в десятках паков под разными номерами. Нарисовать её один раз и разложить по всем
номерам - это и экономия времени, и защита от заплаток: клетки, одинаковые в оригинале,
обязаны быть одинаковыми и в HD (те же грабли R-006, только между наборами).

Кадр читается из листа original.png, то есть ровно так, как его прочитала игра при
распаковке (грабли R-043 закрыты на шаге extract_pck). Хэш берётся по RGBA-пикселям:
совпадение по хэшу - это совпадение картинки, а не имени файла.

    py -3 tools/hdart/dupe_sets.py                     топ-30 самых частых кадров
    py -3 tools/hdart/dupe_sets.py --top 100 --tsv census/dupe_sets.tsv
    py -3 tools/hdart/dupe_sets.py --show 0 --out art/_review/dupes

--show N выкладывает картинку группы N в PNG, чтобы посмотреть глазами, что это за плитка.
"""
import argparse
import csv
import hashlib
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                                      # noqa: E402
from PIL import Image                                   # noqa: E402

import tile_forge as tf                                 # noqa: E402
import build_dataset as bd                              # noqa: E402

ENC = "utf-8-sig"


def read_tiles(roadmap):
    """Сколько клеток карт занимает набор - чтобы считать не кадры, а вес на экране."""
    tiles = {}
    if not os.path.exists(roadmap):
        return tiles
    with open(roadmap, encoding=ENC, newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            tiles[r["набор"]] = int(r["клеток"])
    return tiles


def scan(sheets):
    """Хэш кадра -> {набор: [номера кадров]}. Пустые кадры пропускаем.

    Заодно собираем ПОДПИСЬ каждого кадра - ту самую, с которой он уйдёт в модель. Одна
    картинка в двух наборах с разными подсказками получит два разных рисунка, и на карте
    это будут две разные плитки там, где в оригинале одна."""
    groups = defaultdict(lambda: defaultdict(list))
    prompts = defaultdict(set)
    sets = sorted(d for d in os.listdir(sheets) if d.endswith(".PCK"))
    bad = 0
    for k, name in enumerate(sets):
        try:
            sh = tf.Sheet(sheets, name)
        except Exception:                               # noqa: BLE001
            bad += 1
            continue
        for i in sh.frames():
            im = sh.frame(i)
            a = np.asarray(im, np.uint8)
            if a.shape[-1] == 4 and a[..., 3].max() < 128:
                continue                                # пустой кадр - не содержание
            h = hashlib.blake2b(a.tobytes(), digest_size=16).hexdigest()
            groups[h][name[:-4]].append(i)
            prompts[h].add("%s|%s" % (bd.prompt_kind(sh, i), sh.hints.get(i) or ""))
        if (k + 1) % 50 == 0:
            print("  просмотрено наборов: %d из %d" % (k + 1, len(sets)), file=sys.stderr)
    return groups, prompts, len(sets), bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheets", default=os.path.join("art", "TERRAIN"))
    ap.add_argument("--roadmap", default=os.path.join("census", "roadmap.tsv"))
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--tsv", default="")
    ap.add_argument("--show", type=int, default=-1, help="выложить картинку группы N")
    ap.add_argument("--out", default=os.path.join("art", "_review", "dupes"))
    args = ap.parse_args()

    tiles = read_tiles(args.roadmap)
    groups, prompts, n_sets, bad = scan(args.sheets)
    print("наборов прочитано: %d, не прочиталось: %d, разных картинок: %d"
          % (n_sets - bad, bad, len(groups)), file=sys.stderr)

    slots_all = sum(sum(len(v) for v in g.values()) for g in groups.values())
    multi = [g for g in groups.values() if len(g) > 1]
    slots_multi = sum(sum(len(v) for v in g.values()) for g in multi)
    print("непустых кадров всего: %d; из них в картинках, общих для НЕСКОЛЬКИХ наборов: "
          "%d (%.1f%%) в %d группах" % (slots_all, slots_multi,
          100.0 * slots_multi / max(1, slots_all), len(multi)), file=sys.stderr)
    split = [h for h, g in groups.items() if len(g) > 1 and len(prompts[h]) > 1]
    print("групп, где одну и ту же картинку просят РАЗНЫМИ словами: %d из %d"
          % (len(split), len(multi)), file=sys.stderr)

    rows = []
    for h, per_set in groups.items():
        n = len(per_set)
        slots = sum(len(v) for v in per_set.values())
        weight = sum(tiles.get(s, 0) for s in per_set)
        rows.append((n, slots, weight, h, per_set))
    rows.sort(key=lambda r: (-r[0], -r[2], -r[1]))

    print("\n%-4s %-7s %-7s %-11s %s" % ("#", "наборов", "клеток", "клеток карт", "где лежит"))
    for k, (n, slots, weight, h, per_set) in enumerate(rows[:args.top]):
        where = ", ".join("%s:%s" % (s, ",".join(str(i) for i in sorted(v)[:3]))
                          for s, v in sorted(per_set.items())[:6])
        if len(per_set) > 6:
            where += ", ... ещё %d" % (len(per_set) - 6)
        print("%-4d %-7d %-7d %-11d %s" % (k, n, slots, weight, where))

    if args.tsv:
        os.makedirs(os.path.dirname(args.tsv) or ".", exist_ok=True)
        with open(args.tsv, "w", encoding=ENC, newline="") as f:
            w = csv.writer(f, delimiter="\t", lineterminator="\n")
            w.writerow(["группа", "наборов", "кадров", "клеток_карт", "хэш", "наборы"])
            for k, (n, slots, weight, h, per_set) in enumerate(rows):
                if n < 2:
                    continue
                w.writerow([k, n, slots, weight, h,
                            " ".join("%s:%s" % (s, ",".join(str(i) for i in sorted(v)))
                                     for s, v in sorted(per_set.items()))])
        print("\nтаблица: %s" % args.tsv)

    if args.show >= 0:
        os.makedirs(args.out, exist_ok=True)
        n, slots, weight, h, per_set = rows[args.show]
        name, nums = sorted(per_set.items())[0]
        sh = tf.Sheet(args.sheets, name + ".PCK")
        im = sh.frame(sorted(nums)[0])
        p = os.path.join(args.out, "group%03d_%s_%d.png" % (args.show, name, sorted(nums)[0]))
        im.resize((im.width * 8, im.height * 8), Image.NEAREST).save(p)
        print("группа %d: %d наборов -> %s" % (args.show, n, p))
    return 0


if __name__ == "__main__":
    sys.exit(main())
