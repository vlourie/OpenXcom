"""COUNTERFIRE: one attack decision of a saved battle - the decision line (mode, target, the shooter's own view list: does it
see the target itself), the AI's proposals ([AIREC] base.reason.props), the AI mode history of the turn, the window after it
(reactions, explosions, casualties with positions) and the shooter's own units within 3 cells at the turn's aistart.

  py -3.13 -I fl_case.py <log.gz> <turn> <unit> <n>
"""
import gzip
import json
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")
P3 = re.compile(r"\((-?\d+),(-?\d+),(-?\d+)\)")
path, T, U, N = sys.argv[1:5]
pos, fac, kind = {}, {}, {}
on = False
with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
    for raw in f:
        l = raw.rstrip("\n").split("\t", 2)[-1]
        if l.startswith("[AISTATE] aistart ") and f" turn={T} " in l:
            d = dict(KV.findall(l))
            pos[d["unit"]] = tuple(int(v) for v in P3.search(d["pos"]).groups())
            fac[d["unit"]] = d["faction"]
            kind[d["unit"]] = d.get("weapon", "")
        if l.startswith("[AIDECIDE] "):
            d = dict(KV.findall(l.split(" hu=")[0]))
            if on:
                break
            if d.get("turn") == T and d.get("side") == "1" and d.get("unit") == U and d.get("n") == N:
                on = True
                me = tuple(int(v) for v in P3.search(d["from"]).groups())
                seen = d.get("seen", "").split(",")
                print(f"decision: mode={d['mode']} act={d['act']} to={d['to']} aim={d['aim']} ({kind.get(d['aim'], '')}) "
                      f"weapon={d['weapon']} from={d['from']} tu={d['tu']}; target in the shooter's own view: {d['aim'] in seen}")
                near = [f"{u}{pos[u]}" for u in pos if fac[u] == "1" and u != U and max(abs(pos[u][0] - me[0]), abs(pos[u][1] - me[1])) <= 3
                        and abs(pos[u][2] - me[2]) <= 1]
                print(f"own units within 3 cells (aistart positions): {len(near)}: {' '.join(near)}")
                continue
        if not on:
            continue
        if l.startswith("[AIREC] "):
            r = json.loads(l[8:])
            b = r.get("base") or {}
            props = (b.get("reason") or {}).get("props") or []
            print(f"chosen: src={b.get('src')} score={b.get('score')} slot={b.get('slot')}; proposals: "
                  + "; ".join(f"{p.get('src')} {p.get('sc')} t{p.get('t')}->{p.get('to')}" for p in props))
        elif l.startswith(("[AIEVENT] ", "[AICASUALTY] ")):
            print("  " + l[:230])
        elif l.startswith("[AIEXEC] "):
            x = json.loads(l[9:])
            print(f"  exec: spent={x.get('spent')} dmg={x.get('dmg')} downed={x.get('downed')} spotted_after={x.get('spotted')} "
                  f"hp_lost={x.get('hp_lost')} down={x.get('down')}")
