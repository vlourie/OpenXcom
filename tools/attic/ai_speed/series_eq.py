#!/usr/bin/env python3
"""Побайтная сверка двух серий стенда (tools/ai_arena.py) - шлюз пассивности на 22 боях fair22 (R-113, R-149).

  py -3.13 tools/ai_speed/series_eq.py p39a p39f [--strip walk.stop] [--dir <папка arena>]

По каждому бою (зерно + миссия; порядок боёв в файлах не важен, при jobs > 1 он свой): таблица <метка>.tsv без
столбца seconds, запись .rec.gz, кандидаты .cand.gz, клетки .tiles.gz, пути .path.gz, потери .casualties.txt.
Ничего не нормируется: cfg записи не должен зависеть от флага стенда (AiProbe::cfgText, список skip).
--strip <регэксп> - вырезать совпадения из строк перед сравнением (поле прибора, добавленного между сборками;
элемент trail walk.stop сборки build-ai38+ против build-ai37: --strip '("walk[.]stop[.][^"]*",|,?"walk[.]stop[.][^"]*")',
так p37a = p39a 22 из 22); без него сравнение побайтное.
Вердикт IDENTICAL - только при совпадении всего; печатает, какие бои и потоки разошлись. Поток, которого нет ни у
одной серии (запись выключена в обеих), - NOT_RECORDED и в вердикт не входит; есть только у одной - DIFFERENT.
"""
import argparse
import csv
import gzip
import hashlib
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ai_probe  # noqa: E402  (WORK - папка стенда)

SKIP_COLS = ("seconds",)
STREAMS = (".rec.gz", ".cand.gz", ".tiles.gz", ".path.gz", ".casualties.txt")


def table(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))
    return {(r["seed"], r["want"]): {k: v for k, v in r.items() if k not in SKIP_COLS} for r in rows}


def stream(path, strip):
    """Отпечаток строк потока по каждому бою, число строк и бои с несколькими заголовками [AIRECHEAD] - метка
    серии переиспользована, ai_arena.py дописывает потоки (грабли R-164, docs/rakes/aibench.md); None, если файла нет."""
    if not path.exists():
        return None
    per = defaultdict(hashlib.sha1)
    heads = defaultdict(int)
    n = 0
    op = gzip.open if path.suffix == ".gz" else open
    rx = re.compile(strip) if strip else None
    with op(path, "rt", encoding="utf-8") as f:
        for line in f:
            if rx:
                line = rx.sub("", line)
            head, _, rest = line.partition(" [")
            seed = head.split("seed=")[1].split()[0]
            want = head.split("want=")[1].split()[0]
            per[(seed, want)].update(("[" + rest).encode("utf-8"))
            if rest.startswith("AIRECHEAD]"):
                heads[(seed, want)] += 1
            n += 1
    return {k: v.hexdigest() for k, v in per.items()}, n, {k: c for k, c in heads.items() if c > 1}


def compare(a, b, arena, strip=""):
    """Список строк отчёта и вердикт."""
    out = []
    A, B = table(arena / f"{a}.tsv"), table(arena / f"{b}.tsv")
    keys = sorted(set(A) | set(B))
    same = 0
    for k in keys:
        if k not in A or k not in B:
            out.append(f"НЕТ БОЯ {k[0]} {k[1]} в {a if k not in A else b}")
            continue
        d = [f"{c} {A[k][c]}->{B[k][c]}" for c in A[k] if A[k].get(c) != B[k].get(c)]
        if d:
            out.append(f"ТАБЛИЦА РАЗНАЯ {k[0]} {k[1]} " + "; ".join(d)[:300])
        else:
            same += 1
    out.append(f"таблица: боёв {len(keys)}, совпали {same} (без столбца seconds)")
    verdict = same == len(keys) and len(A) == len(B)
    for ext in STREAMS:
        sa, sb = stream(arena / f"{a}{ext}", strip), stream(arena / f"{b}{ext}", strip)
        if sa is None and sb is None:
            out.append(f"{ext}: NOT_RECORDED - нет ни у одной серии, в вердикт не входит")
            continue
        if sa is None or sb is None:
            out.append(f"{ext}: нет файла у {a if sa is None else b}")
            verdict = False
            continue
        (ha, na, da), (hb, nb, db) = sa, sb
        for label, dup in ((a, da), (b, db)):
            if dup:
                out.append(f"{ext}: ЗАДВОЕН у {label} - заголовков [AIRECHEAD] больше одного: "
                           + ", ".join(f"{s}/{w} x{c}" for (s, w), c in sorted(dup.items())[:5])
                           + " (метка серии переиспользована, ai_arena.py дописывает потоки - серию под новой меткой)")
                verdict = False
        bad = [k for k in keys if ha.get(k) != hb.get(k)]
        out.append(f"{ext}: строк {na} против {nb}, боёв разошлось {len(bad)}"
                   + (" " + ", ".join(f"{s}/{w}" for s, w in bad[:5]) if bad else ""))
        verdict = verdict and not bad and na == nb
    out.append("ВЕРДИКТ: " + ("IDENTICAL" if verdict else "DIFFERENT"))
    return out, verdict


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # R-001
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("a", help="метка серии-базы")
    ap.add_argument("b", help="метка серии-варианта")
    ap.add_argument("--strip", default="", help="регэксп: вырезать совпадения из строк перед сравнением")
    ap.add_argument("--dir", default=str(ai_probe.WORK / "arena"), help="папка таблиц ai_arena.py")
    a = ap.parse_args()
    lines, verdict = compare(a.a, a.b, Path(a.dir), a.strip)
    print("\n".join(lines))
    sys.exit(0 if verdict else 1)


if __name__ == "__main__":
    main()
