#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Перепроверка правды контрольной сотни (P1-C, решение специалиста 30.09): насколько надёжна CODEX_BLIND.

Из сотни берутся 28 карточек трёх групп (по ответам V1 и правде; группа в лист не попадает):
    SAME_ONE  6  - V1 назвал A и B одним предметом (SAME / BROADER_NARROWER), правда - только одна из них,
                   и V1 выбрал её (верно по правде, но спорно по сути);
    AGREE    10  - V1 выбрал A/B, и правда с ним согласна (остальные верные выборы);
    FC       12  - FALSE_CONFIDENT V1 по правде.
Лист слепой, как у truth_sheet: номера карточек вместо ассетов, порядок по хэшу, ответов V1 и правды нет.
Ответ перепроверки пишется ОТДЕЛЬНО - recheck_<who>.tsv, truth.tsv не меняется. Сравнение показывает
согласие с правдой по группам и главное - сколько исходов V1 (верно / FALSE_CONFIDENT) поменялось бы.

    py -3.13 tools/hdart/truth_recheck.py make    <снимок.json> [--rev acf097a4c063]
    py -3.13 tools/hdart/truth_recheck.py import  <снимок.json> <ответы.tsv> --who <кто>
    py -3.13 tools/hdart/truth_recheck.py compare <снимок.json> --who <кто> [--rev acf097a4c063]
"""
import argparse
import hashlib
import json
import os
import sys
import time
import zipfile
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import arbiter as ar                                   # noqa: E402
import truth_sheet as ts                               # noqa: E402

ENC = "utf-8-sig"
V1_REV = "acf097a4c063"
GROUPS = (("SAME_ONE", 6), ("AGREE", 10), ("FC", 12))
SALT = "truth-recheck:1"

INSTRUCTIONS = ts.INSTRUCTIONS.replace("контрольные 100 карточек", "перепроверка, %d карточек") \
    .replace("Ровно 100 строк", "Ровно %d строк").replace("(1..100)", "(1..%d)")


def h(s):
    return hashlib.sha1((SALT + ":" + s).encode()).hexdigest()


def groups_of(snap, d, rev):
    answers = ar.load_json(os.path.join(d, "runs", rev, "answers.json"), {})
    truth = ar.load_truth(d)
    pools = {g: [] for g, _ in GROUPS}
    for x in snap["items"]:
        a, t = answers.get(x["asset_id"]), truth.get(x["asset_id"])
        if not a or not t or not a.get("valid") or a["decision"] not in ("A", "B"):
            continue
        o = ar.outcome(a, t)
        if o == "false_confident":
            pools["FC"].append(x)
        elif o == "correct" and a["relation"] in ("SAME", "BROADER_NARROWER") and t["truth"] in ("A", "B"):
            pools["SAME_ONE"].append(x)
        elif o == "correct":
            pools["AGREE"].append(x)
    chosen = {}
    for g, n in GROUPS:
        for x in sorted(pools[g], key=lambda x: h(x["asset_id"]))[:n]:
            chosen[x["asset_id"]] = (g, x)
    return chosen, {g: len(p) for g, p in pools.items()}


def make(path, rev):
    from PIL import Image, ImageFont
    snap, d = ar.check_snapshot(path)
    chosen, pools = groups_of(snap, d, rev)
    items = [x for _g, x in sorted(chosen.values(), key=lambda gx: h("order:" + gx[1]["asset_id"]))]
    out = os.path.join(d, "truth_recheck")
    up = os.path.join(out, "upload")
    os.makedirs(up, exist_ok=True)
    for fn in os.listdir(up):                           # прежний лист целиком заменяется
        os.remove(os.path.join(up, fn))
    fonts = (ImageFont.truetype(ts.FONT_B, 44), ImageFont.truetype(ts.FONT_B, 24),
             ImageFont.truetype(ts.FONT, 19), ImageFont.truetype(ts.FONT, 15))
    for p0 in range(0, len(items), ts.PER_PAGE):
        chunk = items[p0:p0 + ts.PER_PAGE]
        page = Image.new("RGB", (ts.W, ts.H * len(chunk)), (16, 16, 19))
        for i, x in enumerate(chunk):
            page.paste(ts.draw_card(d, p0 + i + 1, x, fonts), (0, ts.H * i))
        page.save(os.path.join(up, "page_%02d_cards_%03d-%03d.png" % (p0 // ts.PER_PAGE + 1, p0 + 1, p0 + len(chunk))),
                  optimize=True)
    n = len(items)
    with open(os.path.join(up, "cards.md"), "w", encoding=ENC) as f:
        f.write("# Карточки 1..%d (текст с листов)\n\n" % n)
        f.write("\n".join(ts.card_text(i + 1, x) for i, x in enumerate(items)))
    with open(os.path.join(up, "INSTRUCTIONS.md"), "w", encoding=ENC) as f:
        f.write(INSTRUCTIONS % (n, n, n))
    with open(os.path.join(up, "answers_template.tsv"), "w", encoding=ENC, newline="") as f:
        f.write("card\ttruth\tnote\n" + "".join("%d\t\t\n" % (i + 1) for i in range(n)))
    key = {"snapshot_id": snap["snapshot_id"], "items_hash": snap["items_hash"], "rev": rev,
           "cards": {str(i + 1): x["asset_id"] for i, x in enumerate(items)},
           "groups": {x["asset_id"]: chosen[x["asset_id"]][0] for x in items}}
    with open(os.path.join(out, "key.json"), "w", encoding=ENC) as f:
        json.dump(key, f, ensure_ascii=False, indent=1)
    body = open(os.path.join(up, "cards.md"), encoding=ENC).read()
    leak = [x["asset_id"] for x in items if x["asset_id"] in body]
    if leak:
        raise SystemExit("в cards.md попали имена ассетов: %s" % leak[:3])
    zp = os.path.join(out, "upload.zip")
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for fn in sorted(os.listdir(up)):
            z.write(os.path.join(up, fn), fn)
    got = Counter(g for g, _x in chosen.values())
    print("в пуле: %s; взято: %s; карточек %d -> %s" % (
        ", ".join("%s %d" % (g, pools[g]) for g, _ in GROUPS), ", ".join("%s %d" % (g, got[g]) for g, _ in GROUPS),
        n, up))
    print("пакет -> %s (%.1f МБ); ключ -> %s" % (zp, os.path.getsize(zp) / 1e6, os.path.join(out, "key.json")))
    return up


def load_key(path):
    snap, d = ar.check_snapshot(path)
    with open(os.path.join(d, "truth_recheck", "key.json"), encoding=ENC) as f:
        key = json.load(f)
    if (key["snapshot_id"], key["items_hash"]) != (snap["snapshot_id"], snap["items_hash"]):
        raise SystemExit("ключ перепроверки от другого снимка - make заново")
    return snap, d, key


def recheck_path(d, who):
    return os.path.join(d, "truth_recheck", "recheck_%s.tsv" % who.lower())


def import_answers(path, answers, who):
    snap, d, key = load_key(path)
    cards = {int(k): v for k, v in key["cards"].items()}
    got, bad = ts.parse_answers(answers)
    if bad:
        raise SystemExit("не разобраны строки: %s" % bad[:5])
    unknown = sorted(c for c in got if c not in cards)
    if unknown:
        raise SystemExit("нет таких карточек: %s" % unknown)
    miss = sorted(c for c in cards if c not in got)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    rows = {cards[c]: {"truth": t, "who": who, "when": now, "note": note[:300]} for c, (t, note) in got.items()}
    p = recheck_path(d, who)
    with open(p, "w", encoding=ENC, newline="") as f:
        f.write("asset_id\ttruth\twho\ttruth_source\twhen\tnote\n")
        for aid in sorted(rows):
            r = rows[aid]
            f.write("%s\t%s\t%s\t%s\t%s\t%s\n" % (aid, r["truth"], who, ar.truth_source(who), r["when"],
                                                  " ".join(r["note"].split())))
    print("принято %d из %d -> %s%s" % (len(rows), len(cards), p, ("; нет карточек %s" % miss) if miss else ""))
    return compare(path, who)


def load_recheck(d, who):
    import csv
    p = recheck_path(d, who)
    if not os.path.exists(p):
        raise SystemExit("нет %s - сначала import" % p)
    with open(p, encoding=ENC, newline="") as f:
        return {r["asset_id"]: r for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE)}


def compare(path, who, rev=None):
    """Согласие перепроверки с правдой по группам и сдвиг исходов V1: верно <-> FALSE_CONFIDENT."""
    snap, d, key = load_key(path)
    rev = rev or key["rev"]
    answers = ar.load_json(os.path.join(d, "runs", rev, "answers.json"), {})
    truth, re_ = ar.load_truth(d), load_recheck(d, who)
    per = {g: Counter() for g, _ in GROUPS}
    rows = []
    for aid, g in key["groups"].items():
        if aid not in re_:
            continue
        k, t0, t1, a = per[g], truth[aid], re_[aid], answers[aid]
        k["n"] += 1
        k["exact"] += t0["truth"] == t1["truth"]
        o0, o1 = ar.outcome(a, t0), ar.outcome(a, t1)
        k["same_outcome"] += o0 == o1
        k["%s->%s" % (o0, o1)] += o0 != o1
        rows.append((g, aid, a["decision"], a["relation"], t0["truth"], t1["truth"], o0, o1, t1.get("note", "")))
    L = ["Перепроверка правды: %s против %s (V1 %s)" % (ar.truth_source(who), "CODEX_BLIND", rev), ""]
    for g, _n in GROUPS:
        k = per[g]
        if not k["n"]:
            continue
        flips = ", ".join("%s %d" % (x, v) for x, v in sorted(k.items()) if "->" in x and v)
        L.append("%-9s %2d: метка совпала %d, исход V1 тот же %d%s" % (
            g, k["n"], k["exact"], k["same_outcome"], ("; сдвиг: " + flips) if flips else ""))
    tot = sum((per[g] for g, _ in GROUPS), Counter())
    L += ["", "ВСЕГО %d: метка совпала %d (%.0f %%), исход V1 тот же %d (%.0f %%)" % (
        tot["n"], tot["exact"], 100.0 * tot["exact"] / max(1, tot["n"]), tot["same_outcome"],
        100.0 * tot["same_outcome"] / max(1, tot["n"])), "",
        "группа\tассет\tV1\tсвязь V1\tправда\tперепроверка\tисход по правде\tисход по перепроверке\tзаметка"]
    L += ["\t".join(str(v) for v in r) for r in sorted(rows)]
    p = os.path.join(d, "truth_recheck", "compare_%s.txt" % who.lower())
    with open(p, "w", encoding=ENC) as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L[:len(GROUPS) + 4]))
    print("-> %s" % p)
    return per


def main():
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["make", "import", "compare"])
    ap.add_argument("snapshot")
    ap.add_argument("answers", nargs="?")
    ap.add_argument("--who")
    ap.add_argument("--rev", default=V1_REV)
    a = ap.parse_args()
    if a.cmd == "make":
        make(a.snapshot, a.rev)
    elif a.cmd == "import":
        if not a.answers or not a.who:
            raise SystemExit("import: <ответы.tsv> --who <кто>")
        import_answers(a.snapshot, a.answers, a.who)
    else:
        if not a.who:
            raise SystemExit("compare: --who <кто>")
        compare(a.snapshot, a.who, a.rev)
    return 0


if __name__ == "__main__":
    sys.exit(main())
