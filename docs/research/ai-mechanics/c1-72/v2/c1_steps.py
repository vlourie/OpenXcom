"""Classify every cover.step of arm B: did the record keep the step (k=m, target at the noted distance), was the debt
set by a real attack (spent TU and, for the corrected C1, the cover.confirm the launch notes), what spent the TU, and
does the third think stay a step or nothing (no free attack, no free walk).  usage: c1_steps.py <dir> <scen.tsv> [prefix]"""
import gzip
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
d = Path(sys.argv[1])
ids = [l.split("\t")[0] for l in Path(sys.argv[2]).read_text(encoding="utf-8-sig").splitlines()[1:] if l.strip()]
P = sys.argv[3] if len(sys.argv) > 3 else "c1"  # label prefix of the series
c = Counter()
odd = []
for sid in ids:
    path = d / f"{P}_B_{sid}.rec.gz"
    if not path.exists():
        continue
    c["battles"] += 1
    R, X = {}, {}
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for l in f:
            tag, _, body = l.partition("] {")
            if not body:
                continue
            j = json.loads("{" + body)
            if tag.endswith("[AIREC"):
                R[j["rec"]] = j
            elif tag.endswith("[AIEXEC"):
                X[j["rec"]] = j
    # the third think and later: only the cover step or nothing
    for r, j in sorted(R.items()):
        k = j["base"]["k"]
        step = any(s.startswith("cover.step ") for s in j["base"]["reason"]["trail"])
        if "cover.confirm" in X.get(r, {}).get("trail", []):
            c["confirm"] += 1
            if k != "a" or X[r].get("spent", 0) <= 0:
                c["confirm_without_spent_attack"] += 1
                odd.append(f"{sid} rec {r} CONFIRM WITHOUT SPENT ATTACK: k={k} spent={X[r].get('spent')}")
        if j["n"] < 3:
            continue
        c["n3"] += 1
        c[f"n3_k_{k}"] += 1
        if k not in ("m", "e") or (k == "m" and not step):
            c["n3_free_action"] += 1
            odd.append(f"{sid} rec {r} FREE ACTION n={j['n']} k={k} step={step} trail={j['base']['reason']['trail'][:6]}")
    for r, j in sorted(R.items()):
        notes = [s for s in j["base"]["reason"]["trail"] if s.startswith("cover.step ")]
        if not notes:
            continue
        n = {k: int(v) for k, v in re.findall(r"(\w+)=(-?\d+)", notes[-1])}
        x = X.get(r, {})
        p0, to = j["state"]["pos"], j["base"]["to"]
        dist_to = math.ceil(math.sqrt((p0[0] - to[0]) ** 2 + (p0[1] - to[1]) ** 2))
        prev = [R[k] for k in sorted(R) if k < r and R[k]["unit"] == j["unit"] and R[k]["turn"] == j["turn"]]
        pa = prev[-1] if prev else None
        attacked = bool(pa) and pa["base"]["k"] == "a" and X.get(pa["rec"], {}).get("spent", 0) > 0
        confirmed = bool(pa) and "cover.confirm" in X.get(pa["rec"], {}).get("trail", [])
        kept = j["base"]["k"] == "m" and dist_to == n["dist"]
        walk_tu = n["tu"] - x.get("tu", 0)
        c["steps"] += 1
        c["kept"] += kept
        c["debt_real_attack"] += attacked
        c["debt_confirmed"] += confirmed
        c["pre_spend"] += j["state"]["tu"] != n["tu"]
        if kept:
            extra = walk_tu - n["cost"]
            c[f"kept_turn_paid_{extra if 0 <= extra <= 8 else 'odd'}"] += 1
            c["kept_walk_lt_cost"] += walk_tu < n["cost"]
            c["kept_tu_below_keep"] += x.get("tu", 0) < n["keep"] and not x.get("down")
            if not 0 <= extra <= 8 or (x.get("tu", 0) < n["keep"] and not x.get("down")):
                odd.append(f"{sid} rec {r} kept: walk_tu {walk_tu} cost {n['cost']} keep {n['keep']} tu_after {x.get('tu')} walk {x.get('walk')} trail {[s[:60] for s in x.get('trail', [])]}")
        else:
            odd.append(f"{sid} rec {r} REPLACED: k={j['base']['k']} to={to} dist_to={dist_to} noted dist={n['dist']} exec walk={x.get('walk')} spent={x.get('spent')} prev={[k['base']['k'] for k in prev][-3:]} trail={j['base']['reason']['trail'][:6]}")
        if not attacked or not confirmed:
            odd.append(f"{sid} rec {r} STEP WITHOUT CONFIRMED ATTACK: attacked={attacked} confirmed={confirmed} prev={[(k['base']['k'], X.get(k['rec'], {}).get('spent')) for k in prev][-3:]}")
        # the unit's next turn: does it still think with its full time units and attack
        nxt = [R[k] for k in sorted(R) if R[k]["unit"] == j["unit"] and R[k]["turn"] == j["turn"] + 1]
        c["next_turn_alive"] += bool(nxt)
        c["next_turn_first_n1"] += bool(nxt) and nxt[0]["n"] == 1
        c["next_turn_attacks"] += sum(1 for k in nxt if k["base"]["k"] == "a" and X.get(k["rec"], {}).get("spent", 0) > 0)
        c["next_turn_with_attack"] += any(k["base"]["k"] == "a" for k in nxt)
for k, v in sorted(c.items()):
    print(f"{k}\t{v}")
print()
for o in odd:
    print(o)
