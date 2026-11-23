"""AI FORGE WP1: every fall of time units with no event to account for it: by how much, and the lines around it. args: run"""
import re
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0] if "\\" in __file__ else __file__.rsplit("/", 1)[0])
import AIForgeReplayRunner as rr
import scheduler_integrity_check as sic

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
lines = sic.read_log(*rr.source_of(sys.argv[1]))
f = [s for s in lines if s.startswith("[FORGE] ")]
last = {}
at = {}
n = 0
for i, s in enumerate(f):
    d = dict(sic.KV.findall(s))
    u, ev = d.get("unit"), d.get("ev")
    if not u or u == "-1" or "tu" not in d:
        continue
    shown = int(d["was"]) if ev == "tu" else int(d["tu"])
    if shown < last.get(u, shown):
        n += 1
        print(f"#{n} n={d['n']} t={d['t']} s={d['s']} unit={u} last={last[u]} (at n={at[u]}) shown={shown} fall={last[u] - shown} marked={d.get('noresel')} st={d.get('st')} ev={ev}")
        if n <= 3:
            for x in f[max(0, at[u] - 1):i + 1][-9:]:
                print("    ", re.sub(r" h=[0-9a-f]+ rng=[0-9a-f]+", "", x)[8:150])
    last[u] = int(d["now"]) if ev == "tu" else shown
    at[u] = i + 1
