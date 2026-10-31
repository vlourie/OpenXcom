#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Партия очереди генерации -> задания obj_photo (фотореализм) и список неопознанных.

Pipeline v2 (docs/HD_PIPELINE_V2.md, разделы 12-13, 23): заказ модели получает только строка очереди
генерации (obj_generation.py) с действием GENERATE и статусом READY - канонический кадр семейства или
предмет без семейства, опознание подтверждено человеком (identity.tsv), проверка семейства пройдена.
DERIVE (перекраска, зеркало) заказа не получает - их выводит obj_derive; BLOCKED ждёт человека.
Места и куски - из items.json стадии discovery (obj_queue): составной и одиночный - по местам на карте
(map + at, куски режутся по клеткам), анимация - все кадры одним описанием и одним зерном (R-071).

Описание - из identity.tsv (поле what строки очереди). --ident (tsv «место<TAB>описание») может только
уточнить текст готовой строки, но не сделать готовой неопознанную. Слово SKIP - не рисовать.

    py -3.13 tools/hdart/obj_batch.py --batch 1

--batch 0 - ровно те готовые места, что перечислены в --ident; имя файлов заданий тогда --tag.

    py -3.13 tools/hdart/obj_batch.py --batch 0 --ident art/objects/generation/pick_01.tsv --tag pick01
"""
import argparse
import csv
import json
import os

ENC = "utf-8-sig"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--items", default="art/objects/discovery/items.json")
    ap.add_argument("--generation", default="art/objects/generation/generation.json")
    ap.add_argument("--batch", type=int, required=True)
    ap.add_argument("--ident", default="")
    ap.add_argument("--out", default="art/objects/generation")
    ap.add_argument("--tag", default="", help="имя файлов заданий вместо номера партии")
    a = ap.parse_args()
    ident = {}
    if a.ident and os.path.exists(a.ident):
        with open(a.ident, encoding=ENC) as f:
            for r in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
                if r and r[0].isdigit() and len(r) > 1:
                    ident[int(r[0])] = r[1].strip()
    if a.batch == 0 and not ident:
        raise SystemExit("--batch 0 без --ident: нечего брать")
    with open(a.generation, encoding=ENC) as f:
        gen = {r["rank"]: r for r in json.load(f)}
    held = sorted(r for r in ident if r not in gen or gen[r]["status"] != "READY")
    if held:
        # неопознанное, выводимое и ждущее проверки модели не отдаётся (раздел 23)
        print("!! в --ident не готовы к генерации %d: %s" % (len(held), " ".join(
            "#%d %s" % (r, gen[r]["action"] + "/" + gen[r]["status"] if r in gen else "нет в очереди")
            for r in held[:20])))
    with open(a.items, encoding=ENC) as f:
        items = [it for it in json.load(f) if it["rank"] in gen and gen[it["rank"]]["status"] == "READY"
                 and (it["rank"] in ident if a.batch == 0 else gen[it["rank"]].get("batch") == a.batch)]
    jobs, unknown, skip, cut = [], [], 0, []
    for it in items:
        what = ident.get(it["rank"]) or gen[it["rank"]].get("what", "")
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
            if it["kind"] == "составной" and len(src) < len(it["src"]):
                cut.append(it["rank"])
            jobs.append({"name": name, "map": it["map"], "at": it["at"][:len(src)], "what": what,
                         "take": ["%s@%d" % (k, i) for i, k in enumerate(src)], "rank": it["rank"]})
    tag = a.tag or "%02d" % a.batch
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
    if cut:
        # мест кусков на карте нет - составной нарисуется одним куском (R-132): пересобрать очередь obj_queue
        print("!! составных одним куском %d: %s" % (len(cut), " ".join("#%d" % r for r in cut)))


if __name__ == "__main__":
    main()
