"""AI FORGE WP1: where two replays part: the first differing event, the sections per fingerprint, the first differing lines of a dump. args: run run"""
import json
import re
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0] if "\\" in __file__ else __file__.rsplit("/", 1)[0])
import AIForgeReplayRunner as rr
import scheduler_integrity_check as sic

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
a, b = sys.argv[1:3]
ga, fa, da = rr.split(sic.read_log(*rr.source_of(a)))
gb, fb, db = rr.split(sic.read_log(*rr.source_of(b)))
strip = lambda s: re.sub(r"^\[FORGE\] n=\d+ h=[0-9a-f]+", "", s)
print("events", len(fa), len(fb))
nd = 0
kinds = {}
first = None
for x, y in zip(fa, fb):
    if strip(x) != strip(y):
        nd += 1
        ev = dict(sic.KV.findall(x)).get("ev")
        secs = tuple(rr.section_diff(x, y)) if ev == "fp" else ()
        kinds[(ev, secs)] = kinds.get((ev, secs), 0) + 1
        if first is None:
            first = (x, y)
print("event text differs in", nd, "of", len(fa))
for k, v in sorted(kinds.items(), key=lambda kv: -kv[1])[:20]:
    print(" ", v, k)
if first:
    print("A", first[0][:520])
    print("B", first[1][:520])
n = 0
for at in sorted(set(da) & set(db)):
    for x, y in zip(da[at], db[at]):
        if x != y:
            dx = dict(sic.KV.findall(x))
            dy = dict(sic.KV.findall(y))
            diff = {k: (dx.get(k), dy.get(k)) for k in dx if dx.get(k) != dy.get(k)}
            print("dump at", at, "unit", dx.get("u"), dx.get("type"), diff)
            n += 1
            if n >= 14:
                break
    if n >= 14:
        break
