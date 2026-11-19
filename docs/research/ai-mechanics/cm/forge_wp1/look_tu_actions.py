"""AI FORGE WP1: which events carry unit= but no tu=, and did any of them, for that unit, fall into an interval where its time units fell past the hooks? args: run"""
import sys
from collections import Counter

sys.path.insert(0, __file__.rsplit("\\", 1)[0] if "\\" in __file__ else __file__.rsplit("/", 1)[0])
import AIForgeReplayRunner as rr
import scheduler_integrity_check as sic

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
f = [s for s in sic.read_log(*rr.source_of(sys.argv[1])) if s.startswith("[FORGE] ")]
no_tu = Counter()
has_tu = Counter()
last = {}
at = {}
since = {}
hit = []
n = 0
for s in f:
    d = dict(sic.KV.findall(s))
    u, ev = d.get("unit"), d.get("ev")
    if not u or u == "-1":
        continue
    if "tu" not in d:
        no_tu[ev] += 1
        since.setdefault(u, []).append(ev)
        continue
    has_tu[ev] += 1
    shown = int(d["was"]) if ev == "tu" else int(d["tu"])
    if shown < last.get(u, shown):
        n += 1
        hit.append((n, d["n"], u, since.get(u, [])))
    last[u] = int(d["now"]) if ev == "tu" else shown
    since[u] = []
print("events with unit and tu", dict(has_tu))
print("events with unit, no tu", dict(no_tu))
print("falls", n, "with other events of the unit inside", [(a, b, c, e) for a, b, c, e in hit if e])
