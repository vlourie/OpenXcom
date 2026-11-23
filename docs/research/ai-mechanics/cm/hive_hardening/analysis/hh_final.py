"""HIVE hardening: the last numbers for the report (read only). Usage: hh_final.py <hive/res/out>"""
import gzip
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
kv = re.compile(r"(\w+)=([^ ]*)")
out = Path(sys.argv[1])


def read(n):
    with gzip.open(out / n / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        return [ln.rstrip("\n").split("\t")[-1] for ln in f]


for n in ["hh4_JA_M6_s2", "hh6_JV_M3_s1", "hh3_JA_M6_s1"]:
    L = read(n)
    print("==", n)
    plan = {}
    rows = []
    for s in L:
        if s.startswith("[HIVEORD]") and "state=VALIDATED" in s and "kind=GO" in s:
            k = dict(kv.findall(s))
            m = re.search(r"tiles=(\d+)", s)
            plan[k["id"]] = (k["turn"], int(m.group(1)) if m else -1, k["at"])
        if s.startswith("[HIVEORD]") and "state=BLOCKED" in s:
            k = dict(kv.findall(s))
            m = re.search(r"tiles=(\d+)", s)
            p = plan.get(k["id"])
            rows.append((k["unit"], "plan turn", p[0], "now", k["turn"], "tiles plan", p[1], "now", int(m.group(1)) if m else -1, "at plan", p[2], "at now", k["at"], "target", k["target"]))
    for r in rows:
        print("  ", *r)
    same = sum(r[6] == r[8] and r[10] == r[12] for r in [(a[0], a[1], a[2], a[3], a[4], a[5], a[6], a[7], a[8], a[9], a[10], a[11], a[12]) for a in rows])
    print("  BLOCKED", len(rows), "same field and same place as at plan", same)
    perf = [dict(kv.findall(s)) for s in L if s.startswith("[HIVEPERF]")]
    print("  rejected at plan: too far", sum(int(k["rejFar"]) for k in perf), "unreachable", sum(int(k["rejUnreachable"]) for k in perf), "refused before under same conditions", sum(int(k["rejMemo"]) for k in perf), "illegal", sum(int(k["rejIllegal"]) for k in perf))
    # locked: how long
    lock = defaultdict(list)
    for s in L:
        if s.startswith("[HIVEORD]") and "kind=STAY" in s and "why=locked" in s and "state=CREATED" in s:
            k = dict(kv.findall(s))
            lock[k["unit"]].append(int(k["turn"]))
    print("  locked by unit", {u: v for u, v in lock.items()})
    tiles = defaultdict(list)
    for s in L:
        if s.startswith("[HIVEREACH]"):
            k = dict(kv.findall(s))
            tiles[k["unit"]].append((int(k["turn"]), int(k["tiles"])))
    swings = sum(1 for v in tiles.values() if len(v) > 1 and max(t for _, t in v) > 3 * min(t for _, t in v))
    print("  units whose field changed threefold", swings, "of", len(tiles))
    for u in list(lock)[:3]:
        print("   ", u, tiles[u][:14])
    # what the units did with their orders
    own = Counter()
    for s in L:
        if s.startswith("[HIVEORD]") and " own=" in s:
            k = dict(kv.findall(s))
            own[(k["order"], k["own"])] += 1
    ex = sum(s.startswith("[HIVEORD]") and "state=EXECUTING" in s and "kind=GO" in s for s in L)
    ex2 = sum(s.startswith("[HIVEORD]") and "state=EXECUTING" in s and "kind=STAY" in s for s in L)
    print("  EXECUTING GO", ex, "STAY", ex2, " own decisions against the order", sum(own.values()), "by order and action", own.most_common(10))
    dec = [dict(kv.findall(s)) for s in L if s.startswith("[AIDECIDE]") and " side=1 " in s]
    print("  decisions of the side", len(dec))
    i = next(i for i, s in enumerate(L) if s.startswith("[HIVEINIT]"))
    d = next(i for i, s in enumerate(L) if s.startswith("[AIDECIDE]"))
    print("  init line", i, "first decision line", d)
a = [s for s in read("hh2_JS_M6_s1") if s.startswith("[HIVEUNIT]")]
b = [s for s in read("hh3_JA_M6_s1") if s.startswith("[HIVEUNIT]")]
print("units at organization: shadow against active, same", a == b, len(a))
o = read("hh1_JO_M6_s1")
print("off: any hive line", sum(s.startswith("[HIVE") for s in o))
