"""Сводит описания сотни по карточкам боеприпасов (describe/part_1..4.tsv) в describe/what_v2.tsv и проверяет их.

Проверки: 100 строк W-001..W-100 по порядку, 13 колонок, master и type совпадают со списком, статус OK или СПОРНО,
в what_v2 нет условного материала (R-221: «where present», «if any»...).

    py -3.13 tools/hdart/weapon_describe_merge.py
"""
import csv
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
D = os.path.join(ROOT, "art/items/weapons100-v1/describe")
LIST = os.path.join(ROOT, "art/items/weapons100-v1/list.tsv")
COLS = ["master", "type", "identity", "identity_status", "identity_note", "orientation", "magazine", "feed",
        "ammo_look", "details", "materials", "what_v2", "changes"]
COND = re.compile(r"where (present|visible|it has|the reference)|if (any|present)", re.I)


def read(p):
    with open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def main():
    lst = {r["master"]: r for r in read(LIST)}
    rows, bad = [], []
    for k in range(1, 5):
        part = read(os.path.join(D, "part_%d.tsv" % k))
        for r in part:
            if list(r.keys()) != COLS:
                bad.append("part_%d: колонки %s" % (k, list(r.keys())))
                break
        rows += part
    want = ["W-%03d" % i for i in range(1, 101)]
    got = [r["master"] for r in rows]
    if got != want:
        bad.append("порядок или состав: лишние %s, нет %s" % (sorted(set(got) - set(want)), sorted(set(want) - set(got))))
    for r in rows:
        if r["master"] in lst and lst[r["master"]]["type"] != r["type"]:
            bad.append("%s: тип %s, в списке %s" % (r["master"], r["type"], lst[r["master"]]["type"]))
        if r["identity_status"] not in ("OK", "СПОРНО"):
            bad.append("%s: статус %r" % (r["master"], r["identity_status"]))
        if COND.search(r["what_v2"]):
            bad.append("%s: условный материал в what_v2: %s" % (r["master"], COND.search(r["what_v2"]).group(0)))
        if not r["what_v2"].strip():
            bad.append("%s: пустой what_v2" % r["master"])
        if any("\t" in v or "\n" in v for v in r.values()):
            bad.append("%s: табуляция или перевод строки в поле" % r["master"])
    for b in bad:
        print("!!", b)
    if bad:
        raise SystemExit(1)
    out = os.path.join(D, "what_v2.tsv")
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter="\t", quoting=csv.QUOTE_NONE, escapechar=None, lineterminator="\n")
        w.writerow(COLS)
        for r in rows:
            w.writerow([r[c] for c in COLS])
    sp = [r for r in rows if r["identity_status"] == "СПОРНО"]
    print("строк %d, OK %d, СПОРНО %d -> %s" % (len(rows), len(rows) - len(sp), len(sp), out))
    for r in sp:
        print("  СПОРНО %s %s: %s" % (r["master"], r["type"], r["identity_note"][:160]))
    lens = sorted(len(r["what_v2"]) for r in rows)
    print("длина what_v2: мин %d, медиана %d, макс %d" % (lens[0], lens[50], lens[-1]))


if __name__ == "__main__":
    main()
