"""AI FORGE WP3, before the plan: where decision 49 stands in the sides and turns of A1; what a dump row holds; what ends the battle."""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
F21 = Path(__file__).resolve().parent.parent / "forge21"
sys.path.insert(0, str(F21))
import AIForgeCounterfactualRunner as rr

for name in ("A1", "B1"):
    run = rr.Run(name)
    ev = run.events()
    print(name, "events", len(ev))
    decide = next(i for i, e in enumerate(ev) if e[3].get("ev") == "decide" and e[3].get("d") == "49")
    print(" decide 49:", ev[decide][2][:200])
    seen_sides = 0
    for i, e in enumerate(ev):
        if e[3].get("ev") == "side":
            seen_sides += 1
            if seen_sides <= 14:
                print("  side", e[0], e[2][:70], "before decide49" if i < decide else "after")
    nxt = next(i for i in range(decide + 1, len(ev)) if ev[i][3].get("ev") == "decide")
    print(" next decide:", ev[nxt][2][:160], "events between", nxt - decide)
    rows = rr.dump_of(run, "after_branch")
    print(" dump rows", len(rows))
    u = rr.unit_rows(rows)
    print(" actor row:", u.get("1000006", "")[:520])
    pl = [k for k in u if int(k) < 1000000][:2]
    print(" player rows:", [u[k][:220] for k in pl])
    facs = {}
    for k, r in u.items():
        d = dict(rr.sic.KV.findall(r))
        facs.setdefault((d.get("fac"), d.get("st")), []).append(k)
    print(" faction,status counts:", {k: len(v) for k, v in facs.items()})
    print(" ids", sorted(int(k) for k in u)[:12], sorted(int(k) for k in u)[-6:])
    print(" result", run.result())
    print(" res line", next((x for x in run.lines if x.startswith("[AIRESULT]")), "")[:600])
    print(" time", run.time[:3], run.time[-1:])
    print(" tiles", [r for r in rows if r.startswith("tiles_changed")], len(rr.tiles(rows)))
    print(" boundaries", [e[3].get("kind") for e in ev if e[3].get("ev") == "boundary"][:20])
