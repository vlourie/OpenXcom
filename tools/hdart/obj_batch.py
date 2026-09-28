#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Партия очереди предметов -> задания obj_photo (фотореализм) и список неопознанных.

Берёт из items.json (obj_queue) партию --batch: все предметы, у которых нет своего вывода (зеркало,
перекраска выводятся из другого предмета и заказа не получают). Предмет с описанием становится
заданием obj_photo: составной и одиночный - по местам на карте (map + at, куски режутся по клеткам),
анимация - все кадры одним описанием и одним зерном (R-071). Предмет без описания заданием не
становится: он попадает в unknown.tsv - сначала опознать по месту на карте (R-007, R-119).

Описание берётся из --ident (опознание партии: tsv «место<TAB>описание», проверенное) раньше, чем из
подсказок карт в items.json: подсказки карт писала модель по кадру 32x40 и ошибается (краны названы
подсвечниками). Пустое описание в --ident со словом SKIP - предмет не рисовать.

    py -3.13 tools/hdart/obj_batch.py --batch 1 --ident art/objects/queue/ident_01.tsv
"""
import argparse
import csv
import json
import os

ENC = "utf-8-sig"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--items", default="art/objects/queue/items.json")
    ap.add_argument("--batch", type=int, required=True)
    ap.add_argument("--ident", default="")
    ap.add_argument("--out", default="art/objects/queue")
    a = ap.parse_args()
    with open(a.items, encoding=ENC) as f:
        items = [it for it in json.load(f) if it["batch"] == a.batch and not it.get("parent")]
    ident = {}
    if a.ident and os.path.exists(a.ident):
        with open(a.ident, encoding=ENC) as f:
            for r in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
                if r and r[0].isdigit() and len(r) > 1:
                    ident[int(r[0])] = r[1].strip()
    jobs, unknown, skip = [], [], 0
    for it in items:
        what = ident.get(it["rank"]) or it["hint"].replace("[фото] ", "")
        if what == "SKIP":
            skip += 1
            continue
        if not what:
            unknown.append(it)
            continue
        name = "q%04d" % it["rank"]
        if it["kind"] == "анимация":
            s = it["frames"][0].rsplit(":", 1)[0]
            jobs.append({"name": name, "anim": "%s:%s" % (s, ",".join(k.rsplit(":", 1)[1] for k in it["frames"])),
                         "what": what, "rank": it["rank"]})
        else:
            src = it["src"] if len(it["src"]) == len(it["at"]) else it["src"][:1]
            jobs.append({"name": name, "map": it["map"], "at": it["at"][:len(src)], "what": what,
                         "take": ["%s@%d" % (k, i) for i, k in enumerate(src)], "rank": it["rank"]})
    tag = "%02d" % a.batch
    with open(os.path.join(a.out, "jobs_%s.json" % tag), "w", encoding=ENC) as f:
        json.dump(jobs, f, ensure_ascii=False, indent=1)
    with open(os.path.join(a.out, "unknown_%s.tsv" % tag), "w", encoding=ENC, newline="") as f:
        f.write("место\tвид\tмест\tключи\tкарта\tat\n")
        for it in unknown:
            f.write("%d\t%s\t%d\t%s\t%s\t%s\n" % (it["rank"], it["kind"], it["places"], " ".join(it["keys"]),
                                               it["map"], json.dumps(it["at"])))
    calls = sum(len(j["anim"].split(":")[1].split(",")) if "anim" in j else 1 for j in jobs)
    print("партия %d: предметов %d, заданий %d (обращений к модели %d), без описания %d, пропущено %d"
          % (a.batch, len(items), len(jobs), calls, len(unknown), skip))


if __name__ == "__main__":
    main()
