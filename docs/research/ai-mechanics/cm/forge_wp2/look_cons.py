"""AI FORGE WP2: real consequences by the engine's own lines: the target and the actor at N and after, the map floors, casualties, the end. Reads only."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import AIForgeCounterfactualRunner as rr
import scheduler_integrity_check as sic

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
runs = {n: rr.Run(n) for n in ("A1", "B1", "C1")}
TARGET = "324"
for name, r in runs.items():
    print("=====", name)
    i, j, ev = rr.decision_at(r)
    n0 = ev[j][0]
    for at, rows in r.dumps.items():
        if at < n0 or not rows:
            continue
        why = rows[0].split(" ")[0]
        if at > n0 + 40:
            break
        tr = rr.unit_rows(rows).get(TARGET, "")
        ac = rr.unit_rows(rows).get(str(rr.UNIT), "")
        print("dump at", at, why)
        print("  target", " ".join(x for x in tr.split(" ") if x.split("=")[0] in ("u", "fac", "st", "pos", "tu", "en", "hp", "stun", "mor", "wounds", "fire")))
        print("  actor ", " ".join(x for x in ac.split(" ") if x.split("=")[0] in ("u", "st", "pos", "dir", "tu", "en", "hp", "ammo", "seen")))
    # everything between N and the next unit's first action, in the engine's order
    seen = 0
    for n, h, t, d in ev[j + 1:]:
        if d.get("ev") in ("branch", "act", "tu", "decide", "casualty", "boundary", "react", "hit", "VIOLATION"):
            print("  ", n, t.strip()[:150])
            seen += 1
        if d.get("ev") == "act" and d.get("unit") != str(rr.UNIT):
            break
        if seen > 18:
            break
    cas = rr.casualties(r)
    print("casualties", len(cas), [f"{c['turn']}/{c['side']}/{c['unit']}/{c['dead']}/f{c['fac']}" for c in cas[:12]])
    last = next(s for s in r.lines if s.startswith("[AIRESULT]"))
    print({k: v for k, v in sic.KV.findall(last) if k in ("how", "turn", "player", "pdead", "pout", "pwounded", "phplost", "hostile", "hdead", "hleft", "pattacks", "hattacks", "pmoves", "hmoves", "vms")})
    fp = [d for *_, d in ev if d.get("ev") == "fp"]
    print("rng last", fp[-1].get("R"), "fingerprints", len(fp))

for pair in (("A1", "B1"), ("C1", "B1")):
    a, b = runs[pair[0]], runs[pair[1]]
    na2, ra = rr.after_dump(a)
    nb2, rb = rr.after_dump(b)
    fa = [x for x in ra if x.startswith("floor=")]
    fb = [x for x in rb if x.startswith("floor=")]
    print(pair, "floors", len(fa), len(fb), "differ", [x.split(" ")[0] for x, y in zip(fa, fb) if x != y])
    ta, tb = [d for *_, d in a.events() if d.get("ev") == "fp"], [d for *_, d in b.events() if d.get("ev") == "fp"]
    i, j, ea = rr.decision_at(a)
    k = sum(1 for *_, d in ea[:j + 1] if d.get("ev") == "fp")
    print(pair, "fingerprints up to N", k, "first differing rng index", next((x for x, (p, q) in enumerate(zip(ta, tb)) if p.get("R") != q.get("R")), None))
