"""HIVE COMMAND CORE V0: fair play by the journal (read only). Every contact record names an observer and a target; was that target in the observer's sees at any AIDECIDE or AISTATE line of that side turn, or in the side's seen? Prints the ones that were not. Usage: fair.py <dir>"""
import gzip
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
kv = re.compile(r"(\w+)=([^ ]*)")
lines = [ln.rstrip("\n").split("\t")[-1] for ln in gzip.open(Path(sys.argv[1]) / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace")]

sees = defaultdict(set)
seen = defaultdict(set)
for s in lines:
    if s.startswith("[AISTATE]"):
        k = dict(kv.findall(s))
        for v in k.get("sees", "-").split(","):
            if v != "-":
                sees[(k.get("turn"), k.get("unit"))].add(v)
    elif s.startswith("[AIDECIDE]"):
        k = dict(kv.findall(s))
        if k.get("side") == "1":
            for v in k.get("seen", "-").split(","):
                if v != "-":
                    seen[k.get("turn")].add(v)

total = 0
direct = 0
side = 0
miss = []
for s in lines:
    if not s.startswith("[HIVEFAIR]"):
        continue
    k = dict(kv.findall(s))
    total += 1
    t, o, c = k.get("turn"), k.get("observer", k.get("by")), k.get("contact", k.get("target", k.get("unit")))
    if c in sees[(t, o)]:
        direct += 1
    elif c in seen[t]:
        side += 1
    else:
        miss.append(s)
print("records", total, "in the observer's own sees", direct, "only in the side's seen of that turn", side, "in neither", len(miss))
for s in miss[:20]:
    print("  ", s[:200])
print("sample:", next((s[:200] for s in lines if s.startswith("[HIVEFAIR]")), "none"))
