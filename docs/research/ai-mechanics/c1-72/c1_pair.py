"""A against B up to the first cover step: do the two arms play the same until C1 first moves a unit, and what happened to
that unit (and to its whole side) in each arm.  usage: c1_pair.py <dir> <scen.tsv>

The records of B that only C1 makes (the extra third think that found no step: 'cover.*' tags with k=e) are left out;
every other [AIREC] is compared on (turn, side, unit, n, k, to, pos, tu, rng hash). The first mismatch must be the
first cover.step or after it. Then the stepping unit's [AIAFTER] (the player's turn after) in A and in B, and among
A's attack turns that ended in view: how often hit or downed in the player's turn after (the baseline for the step).
"""
import gzip
import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
d = Path(sys.argv[1])
ids = [l.split("\t")[0] for l in Path(sys.argv[2]).read_text(encoding="utf-8-sig").splitlines()[1:] if l.strip()]


def load(label):
    R, X, F = [], {}, {}
    with gzip.open(d / f"{label}.rec.gz", "rt", encoding="utf-8") as f:
        for l in f:
            tag, _, body = l.partition("] {")
            if not body:
                continue
            j = json.loads("{" + body)
            if tag.endswith("[AIREC"):
                R.append(j)
            elif tag.endswith("[AIEXEC"):
                X[j["rec"]] = j
            elif tag.endswith("[AIAFTER"):
                F[(j["side"], j["unit"], j["turn"])] = j
    return R, X, F


def key(j):
    s, b = j["state"], j["base"]
    return (j["turn"], j["side"], j["unit"], j["n"], b["k"], tuple(b["to"]), tuple(s["pos"]), s["tu"], s["h"]["r"])


def cover_only(j):
    t = j["base"]["reason"]["trail"]
    return j["base"]["k"] == "e" and any(s.startswith("cover.") and not s.startswith("cover.step") for s in t)


tot = Counter()
for sid in ids:
    RA, XA, FA = load(f"c1_A_{sid}")
    RB, XB, FB = load(f"c1_B_{sid}")
    first = next((j for j in RB if any(s.startswith("cover.step ") for s in j["base"]["reason"]["trail"])), None)
    rb = [j for j in RB if not cover_only(j)]
    div = None
    for i, (a, b) in enumerate(zip(RA, rb)):
        if key(a) != key(b):
            div = (a, b)
            break
    if first is None:
        tot["no_step"] += 1
        print(f"{sid}: no cover step; first mismatch {'none' if div is None else (div[1]['rec'], div[1]['turn'])}")
        continue
    ok = div is None or div[1]["rec"] >= first["rec"]
    tot["battles"] += 1
    tot["same_until_step"] += ok
    u, t = first["unit"], first["turn"]
    fa, fb = FA.get((1, u, t), {}), FB.get((1, u, t), {})
    xb = XB.get(first["rec"], {})
    lst_a = [j for j in RA if j["unit"] == u and j["turn"] == t]
    xa_last = XA.get(lst_a[-1]["rec"], {}) if lst_a else {}
    for arm, f in (("A", fa), ("B", fb)):
        tot[arm + "_after"] += bool(f)
        tot[arm + "_hit"] += f.get("hp_lost", 0) > 0
        tot[arm + "_hp"] += max(0, f.get("hp_lost", 0))
        tot[arm + "_down"] += bool(f.get("dead") or f.get("down"))
        tot[arm + "_seen"] += f.get("spotted", 0) > 0
    tot["A_end_spotted"] += xa_last.get("spotted", 0) > 0
    tot["B_end_spotted"] += xb.get("spotted", 0) > 0
    print(f"{sid}: same until the first step {ok} (first mismatch rec {div[1]['rec'] if div else '-'}, step rec {first['rec']}) unit {u} turn {t}:"
          f" A end spotted {xa_last.get('spotted')} after hp_lost {fa.get('hp_lost')} down {fa.get('dead') or fa.get('down')} |"
          f" B end spotted {xb.get('spotted')} after hp_lost {fb.get('hp_lost')} down {fb.get('dead') or fb.get('down')}")
    # baseline in A: attack turns ending in view - hit / downed in the player's turn after
    g = {}
    for j in RA:
        if j["side"] == 1:
            g.setdefault((j["unit"], j["turn"]), []).append(j)
    for (uu, tt), lst in g.items():
        if not any(j["base"]["k"] == "a" for j in lst):
            continue
        x = XA.get(lst[-1]["rec"], {})
        if x.get("down") or x.get("spotted", 0) == 0:
            continue
        f = FA.get((1, uu, tt))
        if not f:
            continue
        tot["base_n"] += 1
        tot["base_hit"] += f.get("hp_lost", 0) > 0
        tot["base_down"] += bool(f.get("dead") or f.get("down"))
        tot["base_hp"] += max(0, f.get("hp_lost", 0))
print()
for k, v in sorted(tot.items()):
    print(f"{k}\t{v}")
