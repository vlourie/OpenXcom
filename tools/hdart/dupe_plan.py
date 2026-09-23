#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Одна картинка - один заказ модели, дальше копия по всем наборам (грабли R-049).

dupe_sets.py считает, СКОЛЬКО у нас повторов между паками. Здесь то же знание применяется
к работе: план отрисовки строится по картинке, а не по номеру кадра в наборе.

Две стороны, и вторая важнее первой:

ВРЕМЯ. Зелёная плитка входа лежит в 43 паках, кот-заглушка в 30. Нарисовать её сорок три
раза - это сорок два впустую сожжённых заказа.

ОДИНАКОВОСТЬ. Подпись кадра берётся из hints.json СВОЕГО набора, и у 1151 группы из 5814
одна картинка просится разными словами. Значит вернутся разные рисунки на клетки, которые
в игре обязаны быть одинаковыми: те же заплатки, что в R-006, только между наборами.
Копия снимает и это - у группы один рисунок по определению.

    py -3 tools/hdart/dupe_plan.py --spread --dry-run     что разложилось бы
    py -3 tools/hdart/dupe_plan.py --spread               разложить по-настоящему
    py -3 tools/hdart/dupe_plan.py --rescan               пересчитать хэши листов

Хэш кадра берётся из листа original.png, то есть ровно так, как его прочитала игра
(R-043 закрыт на шаге extract_pck). Совпадение по хэшу - совпадение картинки, а не имени.
Индекс лежит в census/frame_hash.tsv и пересчитывается только по --rescan: обход 628
листов идёт около минуты, а в план он входит на каждом запуске.
"""
import argparse
import csv
import hashlib
import os
import shutil
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                                      # noqa: E402

import tile_forge as tf                                 # noqa: E402

ENC = "utf-8-sig"
CACHE = os.path.join("census", "frame_hash.tsv")


def frame_hash(im):
    """Хэш по RGBA-пикселям. Пустой кадр - None: рисовать в нём нечего."""
    a = np.asarray(im, np.uint8)
    if a.ndim == 3 and a.shape[-1] == 4 and a[..., 3].max() < 128:
        return None
    return hashlib.blake2b(a.tobytes(), digest_size=16).hexdigest()


def scan(sheets):
    rows = []
    sets = sorted(d for d in os.listdir(sheets) if d.endswith(".PCK"))
    for k, name in enumerate(sets):
        try:
            sh = tf.Sheet(sheets, name)
        except Exception:                               # noqa: BLE001
            continue
        for i in sh.frames():
            h = frame_hash(sh.frame(i))
            if h:
                rows.append((name[:-4], i, h))
        if (k + 1) % 100 == 0:
            print("  просмотрено листов: %d из %d" % (k + 1, len(sets)),
                  file=sys.stderr, flush=True)
    return rows


def load(sheets=os.path.join("art", "TERRAIN"), cache=CACHE, rescan=False):
    """(набор, кадр) -> хэш и хэш -> список (набор, кадр). Индекс кэшируется на диске."""
    if rescan or not os.path.exists(cache):
        rows = scan(sheets)
        os.makedirs(os.path.dirname(cache) or ".", exist_ok=True)
        with open(cache, "w", encoding=ENC, newline="") as f:
            w = csv.writer(f, delimiter="\t", lineterminator="\n")
            w.writerow(["набор", "кадр", "хэш"])
            for r in rows:
                w.writerow(r)
    else:
        with open(cache, encoding=ENC, newline="") as f:
            rows = [(r["набор"], int(r["кадр"]), r["хэш"]) for r in csv.DictReader(f, delimiter="\t")]
    by_frame = {}
    by_hash = defaultdict(list)
    for name, i, h in rows:
        by_frame[(name, i)] = h
        by_hash[h].append((name, i))
    return by_frame, by_hash


def answer_path(root, name, i, sub="lora"):
    return os.path.join(root, name + ".PCK", "returned", sub, "%d.png" % i)


def spread(root, by_frame, by_hash, sub="lora", dry=False):
    """Разложить уже нарисованные ответы по всем кадрам той же картинки.

    Источник выбирается не первым попавшимся, а по порядку наборов: у одной группы всегда
    один и тот же источник, поэтому повторный запуск ничего не переписывает заново."""
    made = skipped = groups = 0
    for h, members in sorted(by_hash.items()):
        have = [m for m in sorted(members) if os.path.exists(answer_path(root, m[0], m[1], sub))]
        if not have:
            continue
        need = [m for m in sorted(members) if not os.path.exists(answer_path(root, m[0], m[1], sub))]
        if not need:
            continue
        groups += 1
        if len(have) > 1:
            skipped += len(have) - 1                    # столько заказов уже сделано зря
        src = answer_path(root, have[0][0], have[0][1], sub)
        for name, i in need:
            dst = answer_path(root, name, i, sub)
            if not dry:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copyfile(src, dst)
            made += 1
    return made, groups, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheets", default=os.path.join("art", "TERRAIN"))
    ap.add_argument("--cache", default=CACHE)
    ap.add_argument("--sub", default="lora", help="какая папка ответа: lora или lora_cut")
    ap.add_argument("--rescan", action="store_true")
    ap.add_argument("--spread", action="store_true")
    ap.add_argument("--dry-run", dest="dry", action="store_true")
    args = ap.parse_args()

    by_frame, by_hash = load(args.sheets, args.cache, args.rescan)
    multi = [h for h, m in by_hash.items() if len(m) > 1]
    print("кадров с содержимым: %d, разных картинок: %d, из них в нескольких местах: %d"
          % (len(by_frame), len(by_hash), len(multi)))

    if args.spread:
        made, groups, skipped = spread(args.sheets, by_frame, by_hash, args.sub, args.dry)
        print("%s копий: %d в %d группах" % ("разложилось бы" if args.dry else "разложено",
                                             made, groups))
        if skipped:
            print("уже нарисовано дважды одно и то же: %d кадров" % skipped)
    return 0


if __name__ == "__main__":
    sys.exit(main())
