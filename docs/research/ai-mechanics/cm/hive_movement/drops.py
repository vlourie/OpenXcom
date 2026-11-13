"""Movement diagnosis: every flood of every unit in the order it was logged, and the big changes at one place within one turn (read only)."""
import gzip
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
out = Path("C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad/hive/res/out")
kv = re.compile(r"(\w+)=([^ ]*)")


def read(n):
    with gzip.open(out / n / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        return [ln.rstrip("\n").split("\t")[-1] for ln in f]


for n in ["hh3_JA_M6_s1", "hh4_JA_M6_s2", "hh6_JV_M3_s1", "hh7_HL_M3_s1", "hh8_HL_M3_s1"]:
    L = read(n)
    last = {}
    print("==", n, "lines", len(L))
    drops = 0
    for i, s in enumerate(L):
        if not s.startswith("[HIVEREACH]"):
            continue
        k = dict(kv.findall(s))
        key = (k["unit"], k["turn"], k["at"])
        t = int(k["tiles"])
        if key in last:
            p, pi, pc = last[key]
            if max(p, t) >= 2 * min(p, t):
                drops += 1
                print(f"  line {pi}->{i} turn {k['turn']} unit {k['unit']} at {k['at']} tiles {p} capped {pc} -> {t} capped {k['capped']} tu {k['tu']}")
        last[key] = (t, i, k["capped"])
    print("  changes", drops)
    # the same value twice over: the sizes of closed parts
    small = defaultdict(set)
    for s in L:
        if s.startswith("[HIVEREACH]"):
            k = dict(kv.findall(s))
            if k["capped"] == "0":
                small[int(k["tiles"])].add(k["at"])
    print("  uncapped sizes (places):", sorted(((v, len(p)) for v, p in small.items()))[:60])
