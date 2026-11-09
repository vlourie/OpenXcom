"""SIDE_TURN_ACTION_SCHEDULER stage 3: the COVER order turn by turn. For every [AICOVER] of a battle with COVER (K) and the same
battle without it (S, the same seed): where the two records first differ (the state up to B's order is the same); A - the
attack pick that came before B in that side turn and its executed shots (time units spent); B - the order (time units, facing,
the enemy it faces), whether B made any decision afterwards in that turn, its time units and facing at the start of the
player's next turn and the reactions it fired in that turn (and the casualties it caused); C - the pick after B and what it
did; then the same unit in S: its activations in that turn, its time units and facing at the player's turn, its reactions.

  py -3.13 -I sc_cover.py <out dir> <label K> <label S>"""
import gzip
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT, LK, LS = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
KV = re.compile(r"(\w+)=(\S+)")
ATT = {6, 7, 8, 9, 10, 12, 13, 14}
TAGS = ("[AIDECIDE] ", "[AIEXEC] ", "[AISCHED] ", "[AICASUALTY] ")


def read(label):
    recs = []
    with gzip.open(OUT / label / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if body.startswith("[AIDECIDE] "):
                recs.append(("D", dict(KV.findall(body.split(" hu=")[0])), body))
            elif body.startswith("[AIEXEC] "):
                recs.append(("X", json.loads(body[9:]), body))
            elif body.startswith("[AISCHED] "):
                recs.append(("S", dict(KV.findall(body.split(" cands=")[0])), body.split(" ", 2)[2]))  # without us=
            elif body.startswith("[AICOVER] "):
                recs.append(("K", dict(KV.findall(body)), body))
            elif body.startswith("[AISTATE] pstart "):
                recs.append(("P", dict(KV.findall(body)), body))
            elif body.startswith("[AIEVENT] ") and " what=reaction " in body:
                recs.append(("R", dict(KV.findall(body)), body))
            elif body.startswith("[AICASUALTY] "):
                recs.append(("C", dict(KV.findall(body)), body))
            elif body.startswith("[AIRESULT] "):
                recs.append(("E", dict(KV.findall(body)), body))
    return recs


def record(recs):
    return [b for k, _, b in recs if k in ("D", "X", "S", "C")]


def activation(recs, turn, unit, start=0):
    """The unit's decisions in that hostile turn from index start: [(act, aim, tu, spent, walked)]."""
    out, pend = [], None
    for k, d, _ in recs[start:]:
        if k == "D" and int(d["turn"]) == turn and d["side"] == "1" and d["unit"] == unit:
            pend = [int(d["act"]), d["aim"], int(d["tu"]), None, None]
            out.append(pend)
        elif k == "X" and pend is not None and str(d["unit"]) == unit:
            pend[3], pend[4] = d.get("spent"), bool(d.get("walk"))
            pend = None
        elif k == "D" and (int(d["turn"]) > turn or (int(d["turn"]) == turn and d["side"] == "2")):
            break
    return out


def show(ds):
    names = {1: "turn", 2: "walk", 6: "throw", 7: "auto", 8: "snap", 9: "aimed", 10: "hit"}
    return "; ".join(f"{names.get(a, a)}{'->' + aim if a in ATT else ''} tu{tu}" + (f" spent{sp}{' walk' if w else ''}" if sp is not None else "")
                     for a, aim, tu, sp, w in ds) or "-"


def pstate(recs, turn, unit):
    for k, d, _ in recs:
        if k == "P" and int(d["turn"]) == turn and d["unit"] == unit:
            return d
    return None


def reactions(recs, turn, unit):
    r = [d["pos"] for k, d, _ in recs if k == "R" and int(d["turn"]) == turn and d["side"] == "0" and d["unit"] == unit]
    c = [f"{d['victim']}:{d['how']}" for k, d, _ in recs if k == "C" and int(d["turn"]) == turn and d["side"] == "0" and d.get("killer") == unit]
    return r, c


k, s = read(LK), read(LS)
rk, rs = record(k), record(s)
div = next((i for i, (a, b) in enumerate(zip(rk, rs)) if a != b), min(len(rk), len(rs)))
print(f"{LK} vs {LS}: record lines {len(rk)} / {len(rs)}, identical up to line {div}"
      + (f"\n  first difference K: {rk[div][:150]}\n                   S: {rs[div][:150]}" if div < min(len(rk), len(rs)) else ""))
for lab, recs in ((LK, k), (LS, s)):
    e = next((d for kk, d, _ in recs if kk == "E"), None)
    if e:
        print(f"  {lab}: result how={e.get('how')} turn={e.get('turn')} pdead={e.get('pdead')} hdead={e.get('hdead')} "
              f"livesoldiers={e.get('livesoldiers')} livealiens={e.get('livealiens')}")
covers = [(i, d) for i, (kk, d, _) in enumerate(k) if kk == "K"]
print(f"COVER orders: {len(covers)}")
fired = 0
for i, d in covers:
    turn, B, A = int(d["turn"]), d["unit"], d["a"]
    print(f"\n== turn {turn} pick {d['pick']}: B {B} at {d['pos']} tu {d['tu']} dir {d['dir']} -> face {d['face']} ({d['steps']} steps, "
          f"tu after {d['tuAfter']}), {d['weapon']} snap {d['snapTU']} TU, reactions {d['reactions']}; enemy {d['enemy']} at {d['epos']} "
          f"distSq {d['distSq']}; order {d['n']} of the turn")
    # A: its attack pick in this turn and its decisions
    apick = next((x for kk, x, _ in k[:i] if kk == "S" and int(x["turn"]) == turn and x["chosen"] == A and x["why"].startswith("attack")), None)
    if apick:
        print(f"  A {A}: pick {apick['pick']} ({apick['why']}, aim {apick['aim']}): {show(activation(k, turn, A))}")
    # B after the order: decisions in this turn after it
    after = activation(k, turn, B, i)
    print(f"  B {B}: decisions after the order in turn {turn}: {len(after)} {show(after)}")
    # C: the pick that followed
    cpick = next((x for kk, x, _ in k[i:] if kk == "S" and int(x["turn"]) == turn), None)
    if cpick:
        C = cpick["chosen"]
        print(f"  C {C}: pick {cpick['pick']} ({cpick['why']}, left {cpick['left']}): {show(activation(k, turn, C, i)[:4])}")
    p = pstate(k, turn + 1, B)
    r, c = reactions(k, turn + 1, B)
    if p:
        print(f"  B at the player's turn {turn + 1}: tu {p['tu']} (snap {d['snapTU']}: {'kept' if int(p['tu']) >= int(d['snapTU']) else 'NOT kept'}), "
              f"dir {p['dir']} (face {d['face']}: {'facing' if p['dir'] == d['face'] else 'NOT facing'}), pos {p['pos']}, hp {p['hp']}")
    else:
        print(f"  B at the player's turn {turn + 1}: no state (out or the battle ended)")
    print(f"  B's reactions in the player's turn {turn + 1}: {len(r)} at {' '.join(r) or '-'}; casualties by B: {' '.join(c) or '-'}")
    fired += len(r) > 0
    # the same unit without COVER
    ps = pstate(s, turn + 1, B)
    rs_, cs = reactions(s, turn + 1, B)
    print(f"  without COVER ({LS}): B {B} in turn {turn}: {show(activation(s, turn, B))}")
    if ps:
        print(f"    at the player's turn {turn + 1}: tu {ps['tu']}, dir {ps['dir']}, pos {ps['pos']}; reactions {len(rs_)} at {' '.join(rs_) or '-'}; "
              f"casualties by it: {' '.join(cs) or '-'}")
    else:
        print(f"    at the player's turn {turn + 1}: no state")
print(f"\nCOVER orders followed by a reaction of B in the player's next turn: {fired} of {len(covers)}")
