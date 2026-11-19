"""HIVE COMMAND CORE V0: the path checks of one battle (read only): success or no path by floor from and to, by target node, by unit, with the unit's movement type. Usage: nopath.py <dir>"""
import gzip
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
kv = re.compile(r"(\w+)=([^ ]*)")
lines = [ln.rstrip("\n").split("\t")[-1] for ln in gzip.open(Path(sys.argv[1]) / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace")]


def xyz(s):
    return tuple(int(v) for v in s.strip("()").split(","))


move = {}
for s in lines:
    if s.startswith("[HIVEUNIT]"):
        k = dict(kv.findall(s))
        move[k["id"]] = k["move"]
floors = Counter()
targets = defaultdict(Counter)
units = defaultdict(Counter)
costs = []
dist = defaultdict(list)
for s in lines:
    if not s.startswith("[HIVEORD]") or "kind=GO" not in s:
        continue
    k = dict(kv.findall(s))
    note = k.get("note", "")
    ok = None
    if k["state"] == "VALIDATED" and note.startswith("path_tu="):
        ok = True
        costs.append(int(note[8:]))
    elif k["state"] == "BLOCKED" and note == "no_path":
        ok = False
    if ok is None:
        continue
    a, b = xyz(k["at"]), xyz(k["target"])
    floors[(a[2], b[2], ok)] += 1
    targets[k["target"]][ok] += 1
    units[k["unit"]][ok] += 1
    dist[ok].append(max(abs(a[0] - b[0]), abs(a[1] - b[1])))
print("from floor, to floor, ok -> count")
for key, v in sorted(floors.items()):
    print(" ", key, v)
print("path TU of the good ones:", sorted(costs)[:60])
print("straight distance: ok", sorted(dist[True])[:40], "\n no path", sorted(dist[False])[:90])
print("targets failing (no path / ok):")
for t, c in sorted(targets.items(), key=lambda x: -x[1][False])[:25]:
    print(" ", t, c[False], c[True])
print("units (movement type) failing / ok:")
for u, c in sorted(units.items(), key=lambda x: -x[1][False])[:25]:
    print(" ", u, move.get(u), c[False], c[True])
