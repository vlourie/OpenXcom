#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Установка принятых предметов в игру: столбец «берём» из review.tsv (obj_review) -> обе копии мода hd.

Что делает на каждый принятый предмет:
  * кадр варианта кладётся на свой номер во ВСЕ копии предмета: копии одной картинки в других наборах
    (очередь obj_queue, R-049) получают тот же файл - копия находится по совпадению оригинала 32x40;
  * предметы очереди, выведенные из принятого точным зеркалом (derive = зеркало), получают
    перевёрнутый кадр (R-051);
  * прежний файл пака, если он был, откладывается в --backup/<копия>/<НАБОР>.PCK/<кадр>.png -
    откат = скопировать обратно;
  * пишет в обе копии мода hd (R-087): репозиторную и ту, что в установке Пираток, и сверяет, что
    файлы легли одинаковые (md5).
Список сделанного - push.tsv рядом с review.tsv.

Файлы мода - файлы игры: запускать, держа очередь правок (py -3 tools/editq.py wait).

    py -3.13 tools/hdart/obj_push.py --review art/_review/ours_vs_pack/review.tsv ^
        --cand strict=art/objects/series --cand photo=art/objects/photo --dry-run
"""
import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np                                  # noqa: E402
from PIL import Image                               # noqa: E402

import map_mockup as mm                             # noqa: E402

ENC = "utf-8-sig"
MODS = ["user/mods/hd/hd/TERRAIN", "Пиратки/Dioxine_XPiratez/user/mods/hd/hd/TERRAIN"]


def key_of(s):
    name, fr = s.rsplit(":", 1)
    return name.upper(), int(fr)


def md5(p):
    with open(p, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--review", required=True)
    ap.add_argument("--items", default="art/objects/queue/items.json")
    ap.add_argument("--cand", action="append", default=[], help="имя=папка, как у obj_review")
    ap.add_argument("--backup", default="art/_backup/hd_objects_" + time.strftime("%Y%m%d_%H%M"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    cands = dict(c.split("=", 1) for c in a.cand)
    world = mm.World()

    def ohash(k):
        s = world.sprite(k[0], k[1], None)
        return hashlib.md5(np.asarray(s).tobytes()).hexdigest() if s is not None else None

    with open(a.items, encoding=ENC) as f:
        items = json.load(f)
    by_key = {}
    by_rank = {}
    for it in items:
        by_rank[it["rank"]] = it
        for k in it["frames"] + it["keys"]:
            by_key.setdefault(key_of(k), it)
    mirrors = {}
    for it in items:
        if it.get("derive") == "зеркало":
            mirrors.setdefault(it["parent"], []).append(it)

    plan = []           # (кадр-источник png, (набор, кадр) назначения, перевернуть, откуда)
    with open(a.review, encoding=ENC) as f:
        for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            take = (r.get("берём") or "").strip()
            if not take:
                continue
            if take not in cands:
                raise SystemExit("строка %s: вариант %r не передан в --cand" % (r["номер"], take))
            root = cands[take]
            keys = [key_of(k) for k in r["ключи"].split()]
            it = next((by_key[k] for k in keys if k in by_key), None)
            targets = [key_of(k) for k in (it["frames"] + it["keys"])] if it else keys
            # источник на каждую картинку оригинала: кадр варианта с тем же оригиналом
            src = {}
            for k in targets:
                p = os.path.join(root, k[0] + ".PCK", "%d.png" % k[1])
                if os.path.exists(p):
                    src.setdefault(ohash(k), p)
            for k in dict.fromkeys(targets):
                p = src.get(ohash(k))
                if p:
                    plan.append((p, k, False, "%s #%s" % (take, r["номер"])))
            for m in mirrors.get(it["rank"], []) if it else []:
                pk = key_of(it["keys"][0])
                p = src.get(ohash(pk))
                if p:
                    for k in (key_of(x) for x in m["keys"]):
                        plan.append((p, k, True, "зеркало #%s" % r["номер"]))

    seen, rows = set(), []
    for p, k, flip, why in plan:
        if k in seen:
            continue
        seen.add(k)
        rel = os.path.join(k[0] + ".PCK", "%d.png" % k[1])
        rows.append([k[0], k[1], p, "да" if flip else "", why])
        if a.dry_run:
            continue
        im = Image.open(p)
        if flip:
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        for mi, mod in enumerate(MODS):
            dst = os.path.join(mod, rel)
            if os.path.exists(dst):
                bk = os.path.join(a.backup, "repo" if mi == 0 else "game", rel)
                if not os.path.exists(bk):
                    os.makedirs(os.path.dirname(bk), exist_ok=True)
                    shutil.copy2(dst, bk)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            im.save(dst)
        if md5(os.path.join(MODS[0], rel)) != md5(os.path.join(MODS[1], rel)):
            raise SystemExit("копии мода разошлись на " + rel)
    out = os.path.join(os.path.dirname(a.review), "push.tsv")
    if not a.dry_run:
        with open(out, "w", encoding=ENC, newline="") as f:
            f.write("набор\tкадр\tисточник\tперевёрнут\tпочему\n")
            for r in rows:
                f.write("\t".join(str(v) for v in r) + "\n")
    print("%s: кадров %d (из них зеркал %d) в %d копии мода hd%s"
          % ("проба" if a.dry_run else "установлено", len(rows), sum(1 for r in rows if r[3]), len(MODS),
             "" if a.dry_run else "; прежние - в " + a.backup))


if __name__ == "__main__":
    main()
