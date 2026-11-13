"""SIDE_TURN_ACTION_SCHEDULER stage 2: the C->B->A example from the first scheduler pick that left the engine's order.
The battle state is the same in S and the control up to that pick (identical record lines); prints, for that turn, the
hostile activation sequences of both, the decisions of A (the chosen one), C (the engine's next one, no attack) and the
units between them (B: no immediate attack), and whether every unit active in the control's turn is active in S's.

  py -3.13 -I sc_example.py <out dir> <label S> <label of the control>"""
import gzip
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT, LS, LC = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
KV = re.compile(r"(\w+)=(\S+)")
ACT = {0: "none", 1: "turn", 2: "walk", 6: "throw", 7: "auto", 8: "snap", 9: "aimed", 10: "hit", 12: "launch", 13: "mindctl",
       14: "panic"}
ATT = {6, 7, 8, 9, 10, 12, 13, 14}


def read(label):
    recs = []
    with gzip.open(OUT / label / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if body.startswith("[AIDECIDE] "):
                recs.append(("D", dict(KV.findall(body.split(" hu=")[0]))))
            elif body.startswith("[AIEXEC] "):
                recs.append(("X", json.loads(body[9:])))
            elif body.startswith("[AISCHED] "):
                recs.append(("S", dict(KV.findall(body))))
    return recs


def turn_acts(recs, turn):
    """[(unit, [(act, aim, tu, spent, walked)])] of the hostile side in that turn, activation by activation."""
    acts, pend = [], None
    for k, d in recs:
        if k == "D" and d["side"] == "1" and int(d["turn"]) == turn:
            if not acts or acts[-1][0] != d["unit"]:
                acts.append((d["unit"], []))
            pend = [int(d["act"]), d["aim"], int(d["tu"]), None, None]
            acts[-1][1].append(pend)
        elif k == "X" and pend is not None and str(x_unit(d)) == acts[-1][0]:
            pend[3], pend[4] = d.get("spent"), bool(d.get("walk"))
            pend = None
    return acts


def x_unit(x):
    return x.get("unit")


def show(ds):
    return "; ".join(f"{ACT.get(a, a)}{'->' + aim if a in ATT else ''} tu{tu}" + (f" spent{sp}{' walk' if w else ''}" if sp is not None else "")
                     for a, aim, tu, sp, w in ds)


s, c = read(LS), read(LC)
pick = next(d for k, d in s if k == "S" and d["why"] == "attack")
turn = int(pick["turn"])
cands = [x.split(":") for x in pick["cands"].split(",")]
ids = [u for u, _ in cands]
A, C = pick["chosen"], pick["order"]
B = ids[ids.index(C) + 1:ids.index(A)]
print(f"first pick out of the engine's order: turn {turn} pick {pick['pick']} pass {pick['pass']} site {pick['site']} left {pick['left']}")
print(f"  C (engine's next, no immediate attack) = {C}; A (chosen, sees {pick['aim']}) = {A}; between them (B, none with an immediate "
      f"attack) {len(B)}: {' '.join(B[:8])}{' ...' if len(B) > 8 else ''}")
sa, ca = turn_acts(s, turn), turn_acts(c, turn)
print(f"  control activation order, turn {turn}: {' '.join(u for u, _ in ca[:14])} ...")
print(f"  S       activation order, turn {turn}: {' '.join(u for u, _ in sa[:14])} ...")
for name, u in (("A", A), ("C", C)) + tuple((f"B{i + 1}", b) for i, b in enumerate(B[:int(sys.argv[4]) if len(sys.argv) > 4 else 3])):
    for lab, acts in (("control", ca), ("S", sa)):
        pos = [(i, ds) for i, (v, ds) in enumerate(acts) if v == u]
        print(f"  {name} {u} {lab:7}: " + " | ".join(f"#{i + 1} {show(ds)}" for i, ds in pos))
# B units of the control that walked and then attacked in their first activation: "cannot fire without moving"
walkfire = [b for b in B for v, ds in ca[:len(ca)] if v == b and any(a == 2 for a, *_ in ds) and any(a in ATT for a, *_ in ds)]
print(f"  B units that in the control walked and attacked within one activation this turn: {len(set(walkfire))} {' '.join(sorted(set(walkfire))[:6])}")
# opportunities: every unit active in the control's turn is active in S's; activations and attacks per unit
cu, su = defaultdict(int), defaultdict(int)
catt, satt = defaultdict(int), defaultdict(int)
for v, ds in ca:
    cu[v] += 1
    catt[v] += sum(a in ATT for a, *_ in ds)
for v, ds in sa:
    su[v] += 1
    satt[v] += sum(a in ATT for a, *_ in ds)
miss = sorted(set(cu) - set(su))
print(f"  units active in the control's turn {len(cu)}, in S's {len(su)}; active in the control but never in S: {len(miss)} {' '.join(miss)}")
print(f"  activations this turn: control {sum(cu.values())}, S {sum(su.values())}; attack decisions: control {sum(catt.values())}, "
      f"S {sum(satt.values())}")
