#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""map_queue.py - какие карты рисовать map_paint'ом дальше: жадно по охвату клеток.

Кадр стоит на многих картах, одна картинка живёт в десятках наборов (R-049), поэтому ценность
карты - клетки всех карт игры, которые получат новый рисунок, если нарисовать ЕЁ кадры: сумма
клеток по картинкам (хэш census/frame_hash.tsv), которых ещё нет ни в одном обновлении
(art/maps/updates/updates.tsv). Берётся лучшая карта, её картинки считаются готовыми, и так дальше.

Клетки - из макетов (art/maps/usage.json, map_mockup.usage): каждая карта игры считается один раз,
как в переписи census; как часто карта выпадает в игре, здесь не учтено.

    py -3 tools\hdart\map_queue.py              docs\MAP_QUEUE.md, первые 60 карт
    py -3 tools\hdart\map_queue.py --top 100
"""
import argparse
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

ENC = "utf-8-sig"
HASHES = os.path.join("census", "frame_hash.tsv")
LEDGER = os.path.join("art", "maps", "updates", "updates.tsv")
OUT = os.path.join("docs", "MAP_QUEUE.md")


def read_tsv(path):
    with open(path, encoding=ENC, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def queue(usage, hashes, done_keys, top):
    """usage: "НАБОР:кадр" -> [[террейн, карта, клеток]]. Возвращает (всего клеток, готово, строки)."""
    pic = lambda key: hashes.get(key, key)       # noqa: E731
    value, blocks, keys = {}, {}, {}
    for key, rows in usage.items():
        h = pic(key)
        for t, b, n in rows:
            value[h] = value.get(h, 0) + n
            blocks.setdefault((t, b), {}).setdefault(h, 0)
            blocks[(t, b)][h] += n
            keys.setdefault((t, b), set()).add(key)
    total = sum(value.values())
    left = set(value) - {pic(k) for k in done_keys}
    covered = total - sum(value[h] for h in left)
    start = covered
    out = []
    for _ in range(top):
        gain = {tb: sum(value[h] for h in hs if h in left) for tb, hs in blocks.items()}
        tb = max(gain, key=lambda k: (gain[k], k))
        if not gain[tb]:
            break
        new = {h for h in blocks[tb] if h in left}
        covered += gain[tb]
        left -= new
        sets = sorted({k.rsplit(":", 1)[0] for k in keys[tb] if pic(k) in new})
        out.append({"terrain": tb[0], "block": tb[1], "new": len(new), "gain": gain[tb],
                    "cum": covered, "sets": sets})
    return total, start, out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=60)
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args(argv)
    import map_mockup as mm
    if os.path.exists(mm.CACHE):
        import json
        with open(mm.CACHE, encoding=ENC) as f:
            usage = json.load(f)
    else:
        usage = mm.usage(mm.World())
    hashes = {"%s:%s" % (r["набор"].upper(), r["кадр"]): r["хэш"] for r in read_tsv(HASHES)}
    done = set()
    if os.path.exists(LEDGER):
        for r in read_tsv(LEDGER):
            f = r["кадр"]
            if f.isdigit():
                done.add("%s:%s" % (r["набор"].upper(), f))
    total, start, rows = queue(usage, hashes, done, args.top)
    lines = ["# Очередь карт для map_paint", "",
             "Считается `tools/hdart/map_queue.py` из `art/maps/usage.json`, `census/frame_hash.tsv` и "
             "учёта обновлений `art/maps/updates/updates.tsv`. Руками не править.", "",
             "Ценность карты - клетки всех карт игры, чьи картинки получат новый рисунок, если нарисовать её "
             "кадры; одна картинка в разных наборах считается один раз (R-049). Уже нарисованное в "
             "обновлениях (в том числе ждущих решения) - готово.", "",
             "Клеток всего %d, в обновлениях уже %.1f%%." % (total, 100.0 * start / total), "",
             "| # | террейн | карта | новых картинок | прибавка охвата | охват | наборы |",
             "|---|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        lines.append("| %d | %s | %s | %d | %.2f%% | %.1f%% | %s |"
                     % (i, r["terrain"], r["block"], r["new"], 100.0 * r["gain"] / total,
                        100.0 * r["cum"] / total, " ".join(r["sets"])))
    with open(args.out, "w", encoding=ENC) as f:
        f.write("\n".join(lines) + "\n")
    for i, r in enumerate(rows[:20], 1):
        print("%2d %-24s %-26s новых %3d  +%.2f%%  %.1f%%" % (i, r["terrain"], r["block"], r["new"],
                                                          100.0 * r["gain"] / total, 100.0 * r["cum"] / total))
    print("-> %s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
