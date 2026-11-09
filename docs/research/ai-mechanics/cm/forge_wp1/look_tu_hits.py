"""AI FORGE WP1: each fall of time units past the hooks: did the unit take a hit between the two lines? args: run"""
import re
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0] if "\\" in __file__ else __file__.rsplit("/", 1)[0])
import AIForgeReplayRunner as rr
import scheduler_integrity_check as sic

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
all_lines = sic.read_log(*rr.source_of(sys.argv[1]))
pos = {}
for i, s in enumerate(all_lines):
    if s.startswith("[FORGE] "):
        m = re.match(r"\[FORGE\] n=(\d+)", s)
        pos[int(m.group(1))] = i
f = [s for s in all_lines if s.startswith("[FORGE] ")]
last = {}
at = {}
n = 0
kinds = {}
for i, s in enumerate(f):
    d = dict(sic.KV.findall(s))
    u, ev = d.get("unit"), d.get("ev")
    if not u or u == "-1" or "tu" not in d:
        continue
    shown = int(d["was"]) if ev == "tu" else int(d["tu"])
    if shown < last.get(u, shown):
        n += 1
        fall = last[u] - shown
        a, b = pos[int(at[u])], pos[int(d["n"])]
        between = all_lines[a + 1:b]
        tags = {}
        for x in between:
            t = x.split(" ", 1)[0] if x.startswith("[") else "other"
            tags[t] = tags.get(t, 0) + 1
        mention = [x[:170] for x in between if re.search(r"(?<!\d)" + u + r"(?!\d)", x) and not x.startswith("[FORGE] ")]
        print(f"#{n} n={d['n']} t={d['t']} s={d['s']} unit={u} {last[u]}->{shown} fall={fall} ev={ev} since n={at[u]} tags={tags}")
        for x in mention[:4]:
            print("    ", x)
    last[u] = int(d["now"]) if ev == "tu" else shown
    at[u] = d["n"]
