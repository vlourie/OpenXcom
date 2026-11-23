"""SIDE_TURN_ACTION_SCHEDULER stage 2: the functional check of a scheduler battle (S) against the same battle without it (Q or
D0) - the hostile side's activation order, where it first differs and what the chosen unit then did, the engine's limits
(two passes, two actions, time units) and the scheduler's own picks ([AISCHED]).

  py -3.13 -I sc_check.py <out dir> <label S> <label of the control>"""
import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT, LS, LC = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
KV = re.compile(r"(\w+)=(\S+)")
ATT = {6, 7, 8, 9, 10, 12, 13, 14}  # throw, auto, snap, aimed, hit, launch, mind control, panic


def read(label):
    """Records in log order: ('D', fields) [AIDECIDE], ('X', json) [AIEXEC], ('S', fields) [AISCHED], ('C', text) [AICASUALTY],
    ('R', fields) reaction [AIEVENT]."""
    recs = []
    with gzip.open(OUT / label / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if body.startswith("[AIDECIDE] "):
                recs.append(("D", dict(KV.findall(body.split(" hu=")[0])), body))
            elif body.startswith("[AIEXEC] "):
                recs.append(("X", json.loads(body[9:]), body))
            elif body.startswith("[AISCHED] "):
                recs.append(("S", dict(KV.findall(body)), body))
            elif body.startswith("[AICASUALTY] "):
                recs.append(("C", None, body))
            elif body.startswith("[AIEVENT] ") and " what=reaction " in body:
                recs.append(("R", dict(KV.findall(body)), body))
    return recs


def activations(recs):
    """(turn, unit, [decisions]) of the hostile side (side=1) in order: consecutive decisions of one unit are one activation."""
    acts = []
    for k, d, _ in recs:
        if k != "D" or d["side"] != "1":
            continue
        t, u = int(d["turn"]), d["unit"]
        if acts and acts[-1][0] == t and acts[-1][1] == u:
            acts[-1][2].append(d)
        else:
            acts.append((t, u, [d]))
    return acts


def ident_lines(recs):
    return [b for k, _, b in recs if k in "DXC"]


def limits(name, recs, acts):
    """The engine's limits: decisions per activation, activations per unit and turn, time units of a unit within its side's turn
    never rising, no decision at 5 time units or fewer."""
    per_act = Counter(len([d for d in a[2] if int(d["n"]) >= 1]) for a in acts)
    per_unit = Counter()
    for t, u, _ in acts:
        per_unit[(t, u)] += 1
    rise = low = 0
    last = {}
    for t, u, ds in acts:
        for d in ds:
            tu = int(d["tu"])
            if tu <= 5:
                low += 1
            if (t, u) in last and tu > last[(t, u)]:
                rise += 1
            last[(t, u)] = tu
    nmax = max((int(d["n"]) for a in acts for d in a[2]), default=0)
    print(f"  {name}: activations {len(acts)}, decisions/activation {dict(sorted(per_act.items()))}, max n {nmax}, "
          f"activations/unit-turn {dict(sorted(Counter(per_unit.values()).items()))}, TU rise {rise}, decisions at TU<=5 {low}")
    return max(per_unit.values(), default=0), rise, low


s, c = read(LS), read(LC)
sa, ca = activations(s), activations(c)
print(f"{LS} vs {LC}")
# the same battle up to the first difference in the decisions and executions
ls_, lc_ = ident_lines(s), ident_lines(c)
first = next((i for i, (x, y) in enumerate(zip(ls_, lc_)) if x != y), None)
print(f"  identical record lines before the first difference: {first if first is not None else min(len(ls_), len(lc_))} "
      f"(S {len(ls_)}, control {len(lc_)})")
# the scheduler's picks
picks = [d for k, d, _ in s if k == "S"]
why = Counter(p["why"] for p in picks)
print(f"  [AISCHED] picks {len(picks)}: {dict(why)}; sites {dict(Counter(p['site'] for p in picks))}; wraps {sum(p['wrap'] == '1' for p in picks)}")
# pass integrity: in a turn's first pass a unit is chosen once per round (between wraps), in the second pass once (sites that
# do not flag the left one - pop - aside)
dup1 = dup2 = 0
seen1, seen2 = defaultdict(set), defaultdict(set)
for p in picks:
    key = (p["turn"], p["side"])
    if p["wrap"] == "1" or p["site"].endswith(".restart"):
        seen1[key] = set()
    if p["chosen"] == "-1":
        continue
    if p["pass"] == "1":
        dup1 += p["chosen"] in seen1[key]
        seen1[key].add(p["chosen"])
    else:
        dup2 += p["chosen"] in seen2[key] and p["site"] != "pop"
        seen2[key].add(p["chosen"])
per_turn = Counter((p["turn"], p["side"]) for p in picks)
units_turn = {}
for p in picks:
    units_turn[(p["turn"], p["side"])] = max(units_turn.get((p["turn"], p["side"]), 0), len(p["cands"].split(",")))
loops = sum(1 for k, n in per_turn.items() if n > 8 * max(units_turn[k], 1))
print(f"  pass integrity: repeated in a first-pass round {dup1}, repeated in the second pass {dup2}; turns over 8 picks/unit {loops}; "
      f"max picks in a turn {max(per_turn.values(), default=0)}")
ms, rs, ls5 = limits("S", s, sa)
# the engine's own bound: a unit gets one activation per first-pass round (1 + the restarts after a death) and one in the second pass
# (a restart that found nobody - the calls after the side's last unit - is not a round)
restarts = Counter(p["turn"] for p in picks if p["site"].endswith(".restart") and p["chosen"] != "-1")
print(f"  restarts after a cleared selection that chose a unit: {sum(restarts.values())}, that found nobody: "
      f"{sum(1 for p in picks if p['site'].endswith('.restart') and p['chosen'] == '-1')}")
per_ut = Counter((str(t), u) for t, u, _ in sa)
over = [(k, n) for k, n in per_ut.items() if n > restarts[k[0]] + 2]
print(f"  activations over the engine's bound (1 + restarts in the first pass, 1 in the second): {len(over)} {over[:5]}")
mc, rc, lc5 = limits("control", c, ca)
# the changed order: a pick that chose another unit than the engine's order, and what that unit then did
moved = [i for i, (k, d, _) in enumerate(s) if k == "S" and d["why"] == "attack"]
done = att = 0
examples = []
for i in moved:
    p = s[i][1]
    dec = next((d for k, d, _ in s[i + 1:i + 400] if k == "D" and d["unit"] == p["chosen"]), None)
    if not dec:
        continue
    j = next(j for j in range(i + 1, len(s)) if s[j][0] == "D" and s[j][1] is dec)
    ex = next((x for k, x, _ in s[j + 1:j + 400] if k == "X" and str(x["unit"]) == p["chosen"]), None)
    a = int(dec["act"])
    if a in ATT:
        att += 1
        if ex and not ex["walk"] and (ex["spent"] or 0) > 0:
            done += 1
        else:
            print(f"    attack not executed: turn {p['turn']} pick {p['pick']} unit {p['chosen']} act {a} aim {dec['aim']} tu {dec['tu']} exec {ex}")
    if len(examples) < 6:
        examples.append((p, dec, ex))
print(f"  picks out of the engine's order: {len(moved)}; the chosen unit's AIModule then attacked {att}, the attack executed "
      f"(time units spent, no walk) {done}")
for p, dec, ex in examples:
    print(f"    turn {p['turn']} pick {p['pick']} pass {p['pass']} site {p['site']}: order {p['order']} -> chosen {p['chosen']} "
          f"(sees target {p['aim']}); cands {p['cands']}")
    print(f"      its decision: act {dec['act']} aim {dec['aim']} weapon {dec['weapon']} tu {dec['tu']} n {dec['n']}; "
          f"exec: {'walk' if ex and ex['walk'] else 'no walk'} spent {ex['spent'] if ex else '-'} dmg {ex['dmg'] if ex else '-'} "
          f"downed {ex['downed'] if ex else '-'}")
# the activation order of the first turn where S and the control differ
for t in sorted({a[0] for a in sa}):
    so = [a[1] for a in sa if a[0] == t]
    co = [a[1] for a in ca if a[0] == t]
    if so != co:
        print(f"  first hostile turn with another activation order: {t}")
        print(f"    control: {' '.join(co)}")
        print(f"    S      : {' '.join(so)}")
        break
reac = (sum(1 for k, *_ in s if k == "R"), sum(1 for k, *_ in c if k == "R"))
print(f"  reaction events S {reac[0]}, control {reac[1]}")
# decisions at 5 time units or fewer happen in the engine too (AIModule spends before it logs): compared with the control
ok = dup1 == 0 and dup2 == 0 and loops == 0 and rs == 0 and not over
print(f"  decisions at TU<=5: S {ls5} of {sum(len(a[2]) for a in sa)}, control {lc5} of {sum(len(a[2]) for a in ca)}; "
      f"max activations/unit-turn S {ms}, control {mc}")
print(f"  LIMITS {'OK' if ok else 'VIOLATED'}")
