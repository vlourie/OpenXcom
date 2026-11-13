"""COORDINATED_ENGAGEMENT_V2, step 1: how sensitive the reachable count of ce_reach.py is to its proxies - every exposed
unit-turn gets all variants at once, the table is the intersection count per variant (an upper bound when the proxy is loosened).

  which walk:  last  - the last action of the unit-turn (ce_reach.py);
               first - the first action after which the unit stood in sight (spotted 0 -> >0), the place before it hidden;
  known:       K0    - a spotter in some hostile unit's sees at aistart t (ce_reach.py);
               K2    - ... at aistart or pstart of turns t-2..t (the side's memory of the last sightings, FAIR knownPos);
               any   - no requirement (upper bound: the unknown ambush counted as foreseeable);
  ally:        near  - an able ranged hostile unit within 12 tiles, dz <= 1 of the spotter E;
               eng   - near, and it sees E (aistart t / t+1) or attacked E's tile (t / t+1) (ce_reach.py).

  py -3.13 -I ce_reach_v.py <out dir> <prefix> [max turn t]"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.argv += [] if len(sys.argv) > 3 else ["999"]
import ce_reach as R  # noqa: E402  (runs its own funnel first; its parsed battles are reused)

tab = Counter()
best = Counter()
both = Counter()
for name, st, decs in R.battles:
    ut = defaultdict(list)
    attacks = defaultdict(list)
    attacks_eff = defaultdict(list)
    for k, e in decs:
        if k.get("side") != "1":
            continue
        t = int(k["turn"])
        ut[(t, k["unit"])].append((k, e))
        if int(k["act"]) in R.ATT:
            attacks[t].append((k["unit"], R.pos(k["to"]) if k.get("to") else None))
            attacks_eff[t].append((k["unit"], None, bool(e.get("dmg", 0) + e.get("stunned", 0) // 2 > 0 or e.get("downed", 0))))
    seen_by_side = {}
    for (when, t), units in st.items():
        seen_by_side[(when, t)] = {pid for s in units.values() if s["f"] == "1" and s["status"] == "0" for pid in s["sees"]}
    for (t, u), seq in ut.items():
        if t > R.TMAX or any(int(k["act"]) in R.ATT for k, _ in seq):
            continue
        if not seq[-1][1].get("spotted"):
            continue
        a0 = st.get(("aistart", t), {})
        a1 = st.get(("aistart", t + 1), {})
        p1 = st.get(("pstart", t + 1), {})
        me = a0.get(u)
        if not me or me["hp"] * 3 < me["hpmax"] * 2 or me["weapon"] not in R.ranged:
            continue
        spot = [pid for pid, s in p1.items() if s["f"] == "0" and u in s["sees"] and pid in a0]
        execs = [(k, e) for k, e in seq if "pos" in e]
        walks = {}
        k, e = seq[-1]
        prev = [x for x in seq[:-1] if "pos" in x[1]]
        if int(k["act"]) == 2 and k["mode"] in ("0", "2") and ((prev[-1][1].get("spotted", 0) == 0) if prev else me["seenby"] == 0):
            walks["last"] = tuple(e["pos"]) if "pos" in e else me["pos"]
        before = me["seenby"]
        for k2, e2 in execs:
            if before == 0 and e2.get("spotted"):
                if int(k2["act"]) == 2 and k2["mode"] in ("0", "2"):
                    walks["first"] = tuple(e2["pos"])
                break
            before = e2.get("spotted", 0)
        K = {"K0": seen_by_side.get(("aistart", t), set()),
             "K2": set().union(*(seen_by_side.get((w, tt), set()) for w in ("aistart", "pstart") for tt in (t - 2, t - 1, t))),
             "any": None}
        for wk, wpos in walks.items():
            for kk, ks in K.items():
                es = [pid for pid in spot if ks is None or pid in ks]
                ok = {"near": False, "eng": False}
                for E in es:
                    ep = a0[E]["pos"]
                    if R.d2(wpos, ep) > 20:
                        continue
                    for aid, s in a0.items():
                        if aid == u or s["f"] != "1" or s["status"] != "0" or s["hp"] * 3 < s["hpmax"] * 2 or s["weapon"] not in R.ranged:
                            continue
                        if abs(s["pos"][2] - ep[2]) > 1 or R.d2(s["pos"], ep) > 12:
                            continue
                        ok["near"] = True
                        if E in s["sees"] or E in a1.get(aid, {}).get("sees", set()) or any(
                                au == aid and at == ep for tt in (t, t + 1) for au, at in attacks[tt]):
                            ok["eng"] = True
                if es:
                    tab[(wk, kk, "-")] += 1
                for ak, v in ok.items():
                    if v:
                        tab[(wk, kk, ak)] += 1
                if (wk, kk) == ("first", "K2") and ok["eng"]:
                    best[name] += 1
                    # the control's turn t+1: U and some other hostile unit both attacked with effect (no HOLD was given there)
                    eff1 = {uu for uu, _, ef in attacks_eff[t + 1] if ef}
                    both[u in eff1 and len(eff1 - {u}) > 0] += 1

print(f"== variants, {R.PRE}, t <= {R.TMAX} (able exposed unit-turns whose exposing walk is PATROL/COMBAT from a hidden place)")
print("   walk   known  ally   count")
for key in sorted(tab):
    print(f"   {key[0]:6s} {key[1]:6s} {key[2]:5s} {tab[key]:5d}")
top = sorted(best.values(), reverse=True)
print(f"   first/K2/eng per battle: {dict(best.most_common())}")
print(f"   battles with any {len(top)}; the 24 richest battles hold {sum(top[:24])}, the 12 richest {sum(top[:12])}")
print(f"   control t+1 after such a case: U and another unit both useful {both[True]}, not {both[False]}")
