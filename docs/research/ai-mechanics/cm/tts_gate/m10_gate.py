"""NATURAL GATE, phase A: the 28 M10 situations one by one, B's own cell against A's step, in TU and shots. Engine facts: the solver's journal (line without A, own cell exists) and the lists; own-cell cost is a flat lower bound, the log does not hold it. Args: M10 log."""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import gate_lib as G

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ATT = {5, 6, 7, 8, 9, 10, 11, 12}
L = [s.rstrip("\n").split("\t")[-1] for s in open(sys.argv[1], encoding="utf-8", errors="replace")]
b = G.Battle(L)
hurt = Counter()
for d in b.dec:
    if d["side"] == 1 and d["t"] in G.SHOT:
        hurt[(d["w"], G.attack_target(b, d))] += (b.exec.get(d["rec"]) or {}).get("dmg") or 0
V = Counter()
print("no turn why | B T d weapon tuB shot p | block | other shots | wounded | valB | own(flat) place>self | A step, shots A before>after | D0 B")
for no, (i, j) in enumerate([x for x in b.tts if x[1].get("ev") == "cand"], 1):
    Ax, Bx, Tx = j["A"], j["B"], j["T"]
    bl = [d for d in b.by_unit.get(Bx["id"], []) if d["turn"] == j["turn"] and d["side"] == 1 and d["i"] > i]
    d0 = bl[0]
    s = G.shots_by_target(b.acts(d0["acts"]))
    o = s[Tx["id"]]
    others = [(u, x["tu"]) for u, x in s.items() if x["lof"] and x["tu"] <= d0["tu"] and u != Tx["id"]]
    com = b.comrades(d0["i"], d0["unit"])
    taken = {a[0] for a in com.values()} | {d0["pos"]}
    mv = b.moves(d0["moves"])
    best = None
    for c, cost in mv.items():
        if cost > d0["tu"] or c in taken or any(p != c and G.near_line(p, c, o["to"]) for p in taken if p != d0["pos"]):
            continue
        if best is None or cost < best[0]:
            best = (cost, c)
    place = d0["tu"] // o["tu"]
    selfn = (d0["tu"] - best[0]) // o["tu"] if best else 0
    # A: its list on this cell in the turn
    ad = [d for d in b.by_unit.get(Ax["id"], []) if d["turn"] == j["turn"] and d["side"] == 1 and d["pos"] == tuple(Ax["pos"]) and d["acts"]]
    astep, abefore, aafter = None, None, None
    if ad:
        m2 = b.moves(ad[0]["moves"])
        for c, cost in m2.items():
            if c[2] == Ax["pos"][2] and c not in taken and not G.near_line(c, d0["pos"], o["to"]) and cost <= Ax["tu"]:
                if astep is None or cost < astep:
                    astep = cost
        sa = [x for x in G.shots_by_target(b.acts(ad[0]["acts"])).values() if x["lof"]]
        if sa:
            cheap = min(x["tu"] for x in sa)
            abefore = Ax["tu"] // cheap
            aafter = (Ax["tu"] - (astep or 0)) // cheap
    acts = [x for x in bl if x["t"] in ATT]
    fired = [G.attack_target(b, x) for x in acts]
    d0txt = "fired T" if Tx["id"] in fired else "fired other" if fired else "no attack"
    hurtT = hurt[(o["w"], Tx["id"])]
    if o["lof"]:
        v = "A not blocked: the engine's list has the line (solver's lineNow failed on visibility)"
    elif others:
        v = "B has another shot with a line"
    elif not hurtT and j["valueB"] <= 0:
        v = "no evidence the weapon can wound T (value 0, no wound in 8 turns)"
    elif place <= selfn:
        v = "own move costs no shot"
    elif astep is None:
        v = "A has no cell off the lane"
    elif abefore is not None and aafter < abefore:
        v = "the step costs A a shot"
    else:
        v = "PASSES"
    V[v] += 1
    print(no, j["turn"], j["why"], "| B", Bx["id"], tuple(Bx["pos"]), "T", Tx["id"], tuple(Tx["pos"]), "d", o["d"], o["w"], "tu", d0["tu"], "shot", o["tu"], "p", o["p"], "| lof", o["lof"], "| other", len(others), "| wounded", hurtT, "| valB", j["valueB"], "| own", best, place, ">", selfn,
          "| A", Ax["id"], tuple(Ax["pos"]), "tu", Ax["tu"], "step", astep, "shots", abefore, ">", aafter, "|", d0txt, "|", v)
print()
for k, n in V.most_common():
    print(f"{n:3d}  {k}")
