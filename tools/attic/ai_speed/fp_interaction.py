#!/usr/bin/env python3
"""Узкая проверка взаимодействия FIREPOINT_BLOCKED_UNIT_STALL V1 с REPEATED_BLOCKED_STEP_V1 (аудит п. 17.7). Движок не трогается.

BASE - V1=1, FP=0 (флаги v53), TEST - V1=1, FP=1; оба на одной машине, бои по меткам <префикс>_<группа>.
По каждому бою:
  детерминизм - BASE против серии-эталона v53 того же блока (таблица без seconds и все потоки по бою);
  исход, ход, секунды; решения сторон;
  след V1 - blockstep.recorded / suppressed (из них -> none) / invalidated;
  след FP - fpblocked.recorded / suppressed / invalidated / retry, after.* и why (смена knownRevision - known_revision);
  повторы цели после срыва (failed_goal.battle): блокировка (unit, supp_none), ресурсы (nomove, energy, reserve, tu),
  цепочки до счётчика 200 и длинные цепочки (>= 20) по источнику - новый цикл через патруль или отход виден здесь;
  BASE против TEST - потоки боя совпали или нет (где FP не сработал, обязаны совпасть).

  py -3.13 tools/ai_speed/fp_interaction.py --arena E:/OXCE_AIWorker/results/arena --base ix53b --test ix53f rc cd wl
FIREPOINT_BLOCKED_V2_INTEROP (п. 17.8): BASE - interop выкл (ix54o, эталон ix53f), TEST - interop вкл; след FP различает
настоящую остановку (recorded / retry) и подавление V1 (v1.recorded / v1.retry):
  py -3.13 tools/ai_speed/fp_interaction.py --arena E:/OXCE_AIWorker/results/arena --base ix54o --test ix54i --ref-prefix ix53f rc cd wl
"""
import argparse
import collections
import gzip
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import failed_goal as fg  # noqa: E402
import series_eq as se  # noqa: E402

REF_BLOCKS = {"s23": (1101, 1110), "s24": (1151, 1160), "s29": (1401, 1410), "s30": (1451, 1460), "s32": (1551, 1560),
              "s35": (1701, 1710)}
TOK = re.compile(r'"((?:fpblocked|blockstep)\.[^"]*)"')
BLOCK = ("unit", "supp_none")
RESOURCE = ("nomove", "energy", "reserve", "tu")


def ref_label(ref, seed):
    s = int(seed)
    return next((ref + b for b, (lo, hi) in REF_BLOCKS.items() if lo <= s <= hi), None)


def tokens(rec_gz):
    """бой -> Counter следа V1 и FP, решения по сторонам"""
    out = collections.defaultdict(collections.Counter)
    with gzip.open(rec_gz, "rt", encoding="utf-8") as f:
        for line in f:
            if "{" not in line:
                continue
            head = line[:line.index("{")]
            k = fg.key_of(head)
            c = out[k]
            if "[AIREC]" in head:   # fpblocked.suppressed / invalidated / why / after - в записи решения, recorded / retry и V1 - в [AIEXEC]
                side = line.split('"side":', 1)[1].split(",", 1)[0].strip() if '"side":' in line else "?"
                c[f"dec.{side}"] += 1
            elif "[AIEXEC]" not in head:
                continue
            for t in TOK.findall(line):
                if t.startswith("blockstep.suppressed"):
                    c["bs.suppressed"] += 1
                    c["bs.none"] += t.endswith("-> none")
                elif t.startswith("blockstep.recorded"):
                    c["bs.recorded"] += 1
                elif t.startswith("blockstep.invalidated"):
                    c["bs.invalidated"] += 1
                elif t.startswith("fpblocked.why "):
                    for w in t.split(" ", 1)[1].split(","):
                        c["fp.why." + w] += 1
                else:
                    c[t.replace("fpblocked.", "fp.")] += 1
    return out


def repeats(arena, label):
    """бой -> сводка повторов цели после срыва"""
    B = fg.load(arena / f"{label}.rec.gz", arena / f"{label}.path.gz")
    out = {}
    for k, recs in B.items():
        rows, chains = fg.battle(recs)
        long_src = collections.Counter(c["src"] for c in chains if c["n"] >= 20)
        out[k] = dict(rep=len(rows), block=sum(r["fail"] in BLOCK for r in rows), res=sum(r["fail"] in RESOURCE for r in rows),
                      cap=sum(c["end"] == "abort_cap" for c in chains), maxc=max((c["n"] for c in chains), default=0),
                      long=dict(long_src))
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # R-001
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--arena", required=True)
    ap.add_argument("--base", required=True, help="префикс меток BASE")
    ap.add_argument("--test", required=True, help="префикс меток TEST")
    ap.add_argument("--ref", default="v53", help="эталон BASE: серии <ref><блок>")
    ap.add_argument("--ref-prefix", default="", help="эталон BASE - серии <префикс>_<группа> той же раскладки (OFF против прежней сборки)")
    ap.add_argument("groups", nargs="+")
    a = ap.parse_args()
    arena = Path(a.arena)
    ref_cache = {}

    def ref(label):
        if label not in ref_cache:
            ref_cache[label] = (se.table(arena / f"{label}.tsv"),
                                {ext: se.stream(arena / f"{label}{ext}", "") for ext in se.STREAMS})
        return ref_cache[label]

    sec_cache = {}

    def secs(label, k):
        """seconds из таблицы (se.table его убирает)"""
        if label not in sec_cache:
            with open(arena / f"{label}.tsv", encoding="utf-8-sig", newline="") as f:
                sec_cache[label] = {(r["seed"], r["want"]): r["seconds"]
                                    for r in se.csv.DictReader(f, delimiter="\t", quoting=se.csv.QUOTE_NONE)}
        return sec_cache[label].get(k, "?")

    det_ok = det_n = 0
    for g in a.groups:
        lb, lt = f"{a.base}_{g}", f"{a.test}_{g}"
        TB, TT = se.table(arena / f"{lb}.tsv"), se.table(arena / f"{lt}.tsv")
        SB = {ext: se.stream(arena / f"{lb}{ext}", "") for ext in se.STREAMS}
        ST = {ext: se.stream(arena / f"{lt}{ext}", "") for ext in se.STREAMS}
        KB, KT = tokens(arena / f"{lb}.rec.gz"), tokens(arena / f"{lt}.rec.gz")
        RB, RT = repeats(arena, lb), repeats(arena, lt)
        print(f"=== группа {g}: {lb} / {lt}")
        for k in sorted(set(TB) | set(TT)):
            b, t = TB.get(k), TT.get(k)
            if not b or not t:
                print(f" {k[0]} {k[1]}: НЕТ БОЯ в {'BASE' if not b else 'TEST'}")
                continue
            rl = f"{a.ref_prefix}_{g}" if a.ref_prefix else ref_label(a.ref, k[0])
            det = "нет эталона"
            if rl and (arena / f"{rl}.tsv").exists():
                rt, rs = ref(rl)
                bad = [] if rt.get(k) == b else ["tsv"]
                bad += [ext for ext in se.STREAMS if SB[ext] and rs[ext] and SB[ext][0].get(k) != rs[ext][0].get(k)]
                det = "= " + rl if not bad else f"РАЗНЫЙ с {rl}: " + ",".join(bad)
                det_n += 1
                det_ok += not bad
            same = [ext for ext in se.STREAMS if SB[ext] and ST[ext] and SB[ext][0].get(k) == ST[ext][0].get(k)]
            print(f" {k[0]} {k[1].replace('STR_', '')}  детерминизм BASE: {det}")
            print(f"   исход BASE {b['how']}/{b['turn']} {secs(lb, k)} с -> TEST {t['how']}/{t['turn']} {secs(lt, k)} с;"
                  f" потоки BASE=TEST: {'все' if len(same) == len(se.STREAMS) else (','.join(same) or 'ни один')}")
            for name, K, R in (("BASE", KB, RB), ("TEST", KT, RT)):
                c, r = K.get(k, collections.Counter()), RB.get(k) if name == "BASE" else RT.get(k)
                fp = " ".join(f"{x[3:]}={v}" for x, v in sorted(c.items()) if x.startswith("fp."))
                print(f"   {name}: решений бот {c['dec.0']} враг {c['dec.1']}; V1 rec {c['bs.recorded']} sup {c['bs.suppressed']}"
                      f" (none {c['bs.none']}) inv {c['bs.invalidated']}; FP {fp or '-'}")
                if r:
                    print(f"         повторов {r['rep']}: блокировка {r['block']}, ресурсы {r['res']}; до 200: {r['cap']};"
                          f" длиннейшая {r['maxc']}; длинные (>=20) по источнику {r['long'] or '-'}")
    print(f"детерминизм BASE против {a.ref_prefix or a.ref}: {det_ok} из {det_n}")


if __name__ == "__main__":
    main()
