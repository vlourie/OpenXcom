"""AI FORGE WP1, Gate 1: every marked boundary of each replay pair: event, fingerprint right after it, units dumped, equal or not (clock counted from the run's own start). args: none; writes WP1_GATE1.json"""
import json
import re
import sys
from collections import Counter

sys.path.insert(0, __file__.rsplit("\\", 1)[0] if "\\" in __file__ else __file__.rsplit("/", 1)[0])
import AIForgeReplayRunner as rr
import scheduler_integrity_check as sic

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
out = {}
for a, b, scen in (("R2", "R3", "M3"), ("P1", "R5", "L8"), ("R5", "R6", "L8 to N")):
    _, fa, da = rr.split(sic.read_log(*rr.source_of(a)))
    _, fb, db = rr.split(sic.read_log(*rr.source_of(b)))
    na, xa = rr.relative_clock(fa, da)
    nb, xb = rr.relative_clock(fb, db)
    rows = []
    for x in na:
        if " ev=boundary " not in x:
            continue
        n = int(re.search(r"n=(\d+)", x).group(1))
        if n > len(nb):
            rows.append({"kind": dict(sic.KV.findall(x))["kind"], "n": n, "state": "past the stop"})
            continue
        same_event = nb[n - 1] == x
        same_dump = xa.get(n) == xb.get(n) and n in xa
        rows.append({"kind": dict(sic.KV.findall(x))["kind"], "n": n, "units": len(xa.get(n, [])) - 1, "rng": dict(sic.KV.findall(fa[n - 1])).get("rng"), "same_event": same_event, "same_dump": same_dump})
    conv = [int(re.search(r"n=(\d+)", s).group(1)) for s in fa if " ev=convert " in s]
    conv_same = all(na[n - 1] == nb[n - 1] for n in conv if n <= len(nb))
    casual = Counter(dict(sic.KV.findall(s)).get("how") for s in fa if " ev=casualty " in s)
    out[f"{a}-{b}"] = {"scenario": scen, "boundaries": rows, "convert_events": conv, "convert_same": conv_same, "casualty": dict(casual)}
    print(a, b, scen, "convert", conv, conv_same, "casualty", dict(casual))
    for r in rows:
        print("  ", r["kind"], r["n"], r.get("units", ""), r.get("same_event", r.get("state")), r.get("same_dump", ""))
_, f6, d6 = rr.split(sic.read_log(*rr.source_of("R6")))
_, f5, _ = rr.split(sic.read_log(*rr.source_of("R5")))
n5, _ = rr.relative_clock(f5, {})
n6, _ = rr.relative_clock(f6, {})
print("R6 last event", n6[-1][:330])
print("R5 same n   ", n5[len(n6) - 1][:330])
print("equal", n6[-1] == n5[len(n6) - 1], "chain raw h", f6[-1][:40], f5[len(n6) - 1][:40])
print("dump at 889 lines", len(d6.get(889, [])), d6.get(889, [""])[0][:120])
(rr.HERE / "WP1_GATE1.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8-sig")
