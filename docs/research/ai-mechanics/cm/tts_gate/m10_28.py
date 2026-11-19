"""NATURAL GATE: the 28 M10 situations the solver's own engine checks found, against everything the D0 log holds about each (read only). Args: M10 log."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import gate_lib as G

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
L = [s.rstrip("\n").split("\t")[-1] for s in open(sys.argv[1], encoding="utf-8", errors="replace")]
b = G.Battle(L)


def view(d):
    e = b.exec.get(d["rec"]) or {}
    u = G.attack_target(b, d) if d["t"] in (5, 6, 7, 8, 9, 10, 11, 12) else None
    return f"{d['t']}{'@' + str(u) if u is not None else ''}->{d['to']} tu{d['tu']} sp{e.get('spent')} dmg{e.get('dmg')} f{e.get('fdmg')} [{d['src']}]"


tot = {"moved_cost": [], "no_later": 0}
for no, (i, j) in enumerate([x for x in b.tts if x[1].get("ev") == "cand"], 1):
    A, B, T = j["A"], j["B"], j["T"]
    turn = j["turn"]
    print(f"\n#{no} turn {turn} {j['why']} valA {j['valueA']} valB {j['valueB']}")
    print(f"  A {A['id']} {tuple(A['pos'])} tu{A['tu']} hp{A['hp']}  B {B['id']} {tuple(B['pos'])} tu{B['tu']} hp{B['hp']}  T {T['id']} {tuple(T['pos'])} hp{T['hp']} dBT {G.cheb(B['pos'], T['pos'])} dAB {G.cheb(A['pos'], B['pos'])} dAT {G.cheb(A['pos'], T['pos'])}")
    bd = [d for d in b.by_unit.get(B["id"], []) if d["turn"] == turn and d["side"] == 1]
    ad = [d for d in b.by_unit.get(A["id"], []) if d["turn"] == turn and d["side"] == 1]
    bl, bb = [d for d in bd if d["i"] > i], [d for d in bd if d["i"] < i]
    al, ab = [d for d in ad if d["i"] > i], [d for d in ad if d["i"] < i]
    print(f"  B acted before {len(bb)}, later {len(bl)}; A acted before {len(ab)}, later {len(al)}")
    # B's own list at the first decision on that cell after the moment
    for d in bl[:1]:
        s = G.shots_by_target(b.acts(d["acts"])) if d["acts"] else {}
        o = s.get(T["id"])
        same = d["pos"] == tuple(B["pos"]) and d["tu"] == B["tu"]
        print(f"  B next: same state {same}, T in list {o}, others with line and TU: {[(u, x['tu'], x['p'], x['d']) for u, x in s.items() if x['lof'] and x['tu'] <= d['tu']]}")
    for d in bl[:6]:
        print("    B", d["pos"], view(d))
    for d in al[:4]:
        print("    A", d["pos"], view(d))
    # A's own shot at T from the same cell
    for d in ad:
        if d["pos"] == tuple(A["pos"]):
            s = G.shots_by_target(b.acts(d["acts"])) if d["acts"] else {}
            print(f"  A list on the cell: T {s.get(T['id'])}, with line and TU {[(u, x['tu'], x['p'], x['d']) for u, x in s.items() if x['lof'] and x['tu'] <= d['tu']]}")
            break
