#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Установка принятых предметов в игру: столбец «берём» из review.tsv (obj_review) -> обе копии мода hd.

Что делает на каждый принятый предмет:
  * кадр варианта кладётся на свой номер во ВСЕ копии предмета: копии одной картинки в других наборах
    (очередь obj_queue, R-049) получают тот же файл - копия находится по совпадению оригинала 32x40;
  * предметы очереди, выведенные из принятого точным зеркалом (derive = зеркало), получают
    перевёрнутый кадр (R-051);
  * Pipeline v2: в папку пака сам не пишет. Кадр кладётся в хранилище и в манифест с происхождением
    (build_hd_pack.stage: вариант, источник, «принято Vitali», строка review), потом build_hd_pack.install
    ставит ровно эти файлы в обе копии мода hd (R-087). Прежний файл остаётся в хранилище, прежний
    манифест - в art/manifest/history: откат = вернуть манифест и install --yes.
Список сделанного - push.tsv рядом с review.tsv.

Файлы мода - файлы игры: запускать, держа очередь правок (py -3 tools/editq.py wait).

    py -3.13 tools/hdart/obj_push.py --review art/_review/ours_vs_pack/review.tsv ^
        --cand strict=art/objects/series --cand photo=art/objects/photo --dry-run
"""
import argparse
import csv
import hashlib
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np                                  # noqa: E402
from PIL import Image                               # noqa: E402

import build_hd_pack as bhp                         # noqa: E402
import map_mockup as mm                             # noqa: E402

ENC = "utf-8-sig"
TARGETS = ("game", "repo")                          # обе копии мода hd (R-087), ставит build_hd_pack


def key_of(s):
    name, fr = s.rsplit(":", 1)
    return name.upper(), int(fr)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--review", required=True)
    ap.add_argument("--items", default="art/objects/discovery/items.json")
    ap.add_argument("--cand", action="append", default=[], help="имя=папка, как у obj_review")
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
    # очередь discovery (Pipeline v2) derive/parent не пишет - зеркала выводит obj_derive; здесь только
    # для прежних items.json из art/objects/queue
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

    seen, rows, rels = set(), [], []
    man = None if a.dry_run else bhp.load()
    for p, k, flip, why in plan:
        if k in seen:
            continue
        seen.add(k)
        rel = "TERRAIN/%s.PCK/%d.png" % k
        rows.append([k[0], k[1], p, "да" if flip else "", why])
        if a.dry_run:
            continue
        take = why.split(" ")[0]
        if flip:
            buf = io.BytesIO()
            Image.open(p).transpose(Image.FLIP_LEFT_RIGHT).save(buf, "PNG")
            obj = buf.getvalue()
        else:
            obj = p                                    # байты варианта как есть: хэш сходится с источником
        bhp.stage(man, rel, obj, generator=take, generator_version="obj_push", source_path=p.replace(os.sep, "/"),
                  approved=True, approval="Vitali", push=why, source_frame="%s:%d" % k,
                  derived_from=(p.replace(os.sep, "/") + " (перевёрнут)") if flip else None)
        rels.append(rel)
    if rels:
        bhp.save(man, why="obj_push %d кадров из %s" % (len(rels), a.review))
        for t in TARGETS:
            bhp.install(man, t, only=rels)
            res = bhp.diff({"files": {r: man["files"][r] for r in rels}}, bhp.TARGETS[t])
            if res["MISSING"] or res["CHANGED"]:
                raise SystemExit("копия %s не сошлась с манифестом: %s" % (t, (res["MISSING"] + res["CHANGED"])[:5]))
    out = os.path.join(os.path.dirname(a.review), "push.tsv")
    if not a.dry_run:
        with open(out, "w", encoding=ENC, newline="") as f:
            f.write("набор\tкадр\tисточник\tперевёрнут\tпочему\n")
            for r in rows:
                f.write("\t".join(str(v) for v in r) + "\n")
    print("%s: кадров %d (из них зеркал %d) в %d копии мода hd%s"
          % ("проба" if a.dry_run else "установлено", len(rows), sum(1 for r in rows if r[3]), len(TARGETS),
             "" if a.dry_run else "; манифест %s, прежний - в %s" % (man["manifest_hash"], bhp.HISTORY)))


if __name__ == "__main__":
    main()
