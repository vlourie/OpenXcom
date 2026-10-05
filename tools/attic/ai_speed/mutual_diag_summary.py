#!/usr/bin/env python3
"""Сводка аудита MUTUAL_DIAGONAL_BLOCK по таблицам runs/mutual_diag_<метка>.tsv (их пишет mutual_diag_audit.py).

По когорте (префикс метки): боёв, эпизодов взаимной блокировки (диагональ / прямо), в классе, длинные (цепочка >= 20
попыток одного юнита за ход или >= 10 ходов), карты, стороны, кандидаты рукопашной на партнёра и их lof, обход V1,
чем кончились эпизоды, исход боя у эпизодов «до конца» и связь с timeout.

  py -3.13 tools/ai_speed/mutual_diag_summary.py c53 v53 b46fp f46fp"""
import collections
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import ENC_R, OUT  # noqa: E402


def side_counts(s):
    """'b:3 e:5' -> {'b': 3, 'e': 5}"""
    return {k: int(v) for k, v in (x.split(":") for x in s.split())} if s else {}


def rows_of(prefix):
    out = []
    for p in sorted(OUT.glob(f"mutual_diag_{prefix}*.tsv")):
        with open(p, encoding=ENC_R, newline="") as f:
            out += list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))
    return out


def battles(prefix):
    n = 0
    for p in sorted(OUT.glob(f"mutual_diag_{prefix}*.tsv")):
        lab = p.stem[len("mutual_diag_"):]
        arena = Path("E:/OXCE_AIWorker/results/arena") / f"{lab}.tsv"
        if arena.is_file():
            with open(arena, encoding=ENC_R) as f:
                n += sum(1 for _ in f) - 1
    return n


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # R-001
    for prefix in sys.argv[1:]:
        R = rows_of(prefix)
        nb = battles(prefix)
        D = [r for r in R if r["geom"] == "diag"]
        S = [r for r in R if r["geom"] == "straight"]
        K = [r for r in D if r["cls"] == "1"]
        print(f"=== {prefix}: боёв {nb}; эпизодов взаимной блокировки {len(R)} (диагональ {len(D)}, прямо {len(S)}, "
              f"иначе {len(R) - len(D) - len(S)}); боёв с диагональной {len({(r['label'], r['battle']) for r in D})}")
        for name, X in (("диагональ, класс", K), ("диагональ, вне класса", [r for r in D if r["cls"] != "1"]), ("прямо", S)):
            if not X:
                print(f"  {name}: 0")
                continue
            longc = [r for r in X if int(r["chain"]) >= 20 or int(r["nturns"]) >= 10]
            ends = collections.Counter(r["end"] for r in X)
            sides = collections.Counter(r["sides"] for r in X)
            terr = collections.Counter(r["terrain"] for r in X)
            m = collections.Counter()
            for r in X:
                for k in ("dec", "melee", "melee_lof", "rng", "rng_lof", "other_lof", "noatt"):
                    for s, v in side_counts(r[k]).items():
                        m[(k, s)] += v
            seen = sum(int(r["seen_exec"]) + int(r["seen_snap"]) > 0 for r in X)
            det = sum(int(r["detour"]) > 0 for r in X)
            held = [r for r in X if r["end"] in ("held", "end")]
            print(f"  {name}: {len(X)} эп. в {len({(r['label'], r['battle']) for r in X})} боях; длинных {len(longc)}; "
                  f"ходов всего {sum(int(r['nturns']) for r in X)}, попыток {sum(int(r['na']) + int(r['nb']) for r in X)}; "
                  f"наибольшая цепочка {max(int(r['chain']) for r in X)}")
            print(f"    стороны {dict(sides)}; карты {dict(terr.most_common(8))}")
            print(f"    кто-то увидел партнёра: {seen}; обход V1 найден: {det}")
            print(f"    решений со своей клетки: бот {m[('dec', 'b')]}, враг {m[('dec', 'e')]}; "
                  f"рукопашная на партнёра бот {m[('melee', 'b')]} (lof {m[('melee_lof', 'b')]}), враг {m[('melee', 'e')]} "
                  f"(lof {m[('melee_lof', 'e')]}); выстрел на партнёра бот {m[('rng', 'b')]} (lof {m[('rng_lof', 'b')]}), "
                  f"враг {m[('rng', 'e')]} (lof {m[('rng_lof', 'e')]}); линия на кого-то другого бот {m[('other_lof', 'b')]}, "
                  f"враг {m[('other_lof', 'e')]}; без кандидатов атаки бот {m[('noatt', 'b')]}, враг {m[('noatt', 'e')]}")
            print(f"    конец: {dict(ends)}; «до конца» по исходу боя {dict(collections.Counter(r['how'] for r in held))}")
            for r in sorted(longc, key=lambda r: -int(r["nturns"]))[:12]:
                print(f"      {r['label']} {r['battle']} {r['sides']} {r['ta']}@{r['fa']} <-> {r['tp']}@{r['fb']} "
                      f"ходы {r['t0']}-{r['t1']} ({r['nturns']}), попыток {r['na']}/{r['nb']}, цепочка {r['chain']}, "
                      f"конец {r['end']}@{r['end_turn']}, бой {r['how']}/{r['bturn']}, src {r['src']}")


if __name__ == "__main__":
    main()
