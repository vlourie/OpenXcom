"""SIDE_TURN_ACTION_SCHEDULER combat pilot: paired differences B - A by scenario and seed (pilot_metrics.py tables).

Per scenario the mean over its seeds; stages M and L of equal weight, scenarios of equal weight inside a stage; 95% CI by the
two-level bootstrap stratified by stage (scenarios with replacement inside the stage, seeds with replacement inside the
scenario, the pair kept), 10 000 repeats, fixed seed - never by battles. For the totals (player HP lost, hostile damage,
hostile losses) also the ratio of the weighted means B/A - 1. Twice: all 24 scenarios, and without L2 and M10 (seen before).
Then per scenario the sign of the main differences, the outcomes, and the scheduler's own counts of arm B.

  py -3.13 -I pilot_stats.py <A tsv> <B tsv>"""
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
SEEN = {"L2", "M10"}
N = 10000


def load(p):
    ls = Path(p).read_text(encoding="utf-8-sig").splitlines()
    head = ls[0].split("\t")
    out = {}
    for l in ls[1:]:
        r = dict(zip(head, l.split("\t")))
        for k in head:
            if k not in ("label", "arm", "scen", "outcome", "how"):
                r[k] = float(r[k])
        out[(r["scen"], int(r["seed"]))] = r
    return out


A, B = load(sys.argv[1]), load(sys.argv[2])
keys = sorted(set(A) & set(B))
print(f"pairs {len(keys)}, missing {sorted(set(A) ^ set(B)) or '-'}")

# metric -> function of a battle row (None: not defined for that battle)
M = [
    ("phplost", "1 player HP lost", lambda r: r["phplost"]),
    ("pinc", "2 player units out (share)", lambda r: r["pinc"]),
    ("pdead", "2 player dead", lambda r: r["pdead"]),
    ("hinc", "3 hostile units out (share)", lambda r: r["hinc"]),
    ("hdead", "3 hostile dead", lambda r: r["hdead"]),
    ("ploss", "4 player lost the battle (0/1)", lambda r: 1.0 if r["outcome"] == "loss" else 0.0),
    ("turns", "4 battle turns", lambda r: r["turns"]),
    ("h_attexec", "5/7 hostile attacks executed", lambda r: r["h_attexec"]),
    ("h_atthit", "5 hostile attacks that did damage", lambda r: r["h_atthit"]),
    ("hitrate", "5 share of executed attacks with damage", lambda r: r["h_atthit"] / r["h_attexec"] if r["h_attexec"] else None),
    ("h_dmg", "5 damage dealt by hostile attacks", lambda r: r["h_dmg"]),
    ("dmg_per_turn", "5 hostile attack damage per turn", lambda r: r["h_dmg"] / r["turns"] if r["turns"] else None),
    ("h_fdmg", "5 friendly damage by hostile attacks", lambda r: r["h_fdmg"]),
    ("p_react", "6 player reactions in hostile turns", lambda r: r["p_react"]),
    ("p_react_per10", "6 player reactions per 10 hostile walks+attacks", lambda r: r["p_react_per10"]),
    ("p_react_turn", "6 player reactions per turn", lambda r: r["p_react"] / r["turns"] if r["turns"] else None),
    ("h_down_hturn", "6 hostile units down in hostile turns", lambda r: r["h_down_hturn"]),
    ("h_react", "6 hostile reactions in player turns", lambda r: r["h_react"]),
    ("h_spent", "7 hostile time units spent", lambda r: r["h_spent"]),
    ("h_spent_turn", "7 hostile time units spent per turn", lambda r: r["h_spent"] / r["turns"] if r["turns"] else None),
    ("h_dec", "7 hostile decisions", lambda r: r["h_dec"]),
    ("ms_turn", "8 battle ms per turn", lambda r: r["ms_turn"]),
    ("t1_h_attexec", "T1 hostile attacks executed, turn 1", lambda r: r["t1_h_attexec"]),
    ("t1_h_dmg", "T1 hostile attack damage, turn 1", lambda r: r["t1_h_dmg"]),
    ("t1_p_react", "T1 player reactions, hostile turn 1", lambda r: r["t1_p_react"]),
    ("t1_h_walks", "T1 hostile walks, turn 1", lambda r: r["t1_h_walks"]),
    ("t1_h_down", "T1 hostile down, hostile turn 1", lambda r: r["t1_h_down"]),
    ("t1_p_down", "T1 player down, hostile turn 1", lambda r: r["t1_p_down"]),
]
RATIO = {"phplost", "h_dmg", "hdead", "h_attexec", "p_react"}


def stage(s):
    return s[0]


def weighted(per_scen):
    """per_scen: {scen: value} -> stages of equal weight, scenarios equal inside."""
    by = defaultdict(list)
    for s, v in per_scen.items():
        by[stage(s)].append(v)
    return sum(sum(v) / len(v) for v in by.values()) / len(by)


def estimate(pairs, fn, ratio=False):
    """pairs: {scen: [(a_row, b_row)]}; the point estimate and the bootstrap 95% CI."""
    data = {}
    for s, ps in pairs.items():
        v = [(fn(a), fn(b)) for a, b in ps]
        v = [(x, y) for x, y in v if x is not None and y is not None]
        if v:
            data[s] = v

    def point(d):
        if ratio:
            ma = weighted({s: sum(x for x, _ in v) / len(v) for s, v in d.items()})
            mb = weighted({s: sum(y for _, y in v) / len(v) for s, v in d.items()})
            return mb / ma - 1 if ma else float("nan")
        return weighted({s: sum(y - x for x, y in v) / len(v) for s, v in d.items()})

    est = point(data)
    rnd = random.Random(20261030)
    st = defaultdict(list)
    for s in data:
        st[stage(s)].append(s)
    boots = []
    for _ in range(N):
        d = {}
        for g, ss in st.items():
            for i, s in enumerate(rnd.choice(ss) for _ in ss):
                v = data[s]
                d[(g, i, s)] = [rnd.choice(v) for _ in v]
        # keys keep the stage letter first
        boots.append(point({f"{g}{i}_{s}": v for (g, i, s), v in d.items()}))
    boots.sort()
    return est, boots[int(0.025 * N)], boots[int(0.975 * N) - 1], len(data)


def table(title, scen_ok):
    pairs = defaultdict(list)
    for k in keys:
        if scen_ok(k[0]):
            pairs[k[0]].append((A[k], B[k]))
    print(f"\n== {title}: scenarios {len(pairs)} (M {sum(1 for s in pairs if s[0] == 'M')}, L {sum(1 for s in pairs if s[0] == 'L')}), "
          f"pairs {sum(len(v) for v in pairs.values())}")
    print(f"  {'metric':<52} {'A mean':>9} {'B mean':>9} {'B-A':>9}  95% CI")
    for key, name, fn in M:
        est, lo, hi, n = estimate(pairs, fn)
        ma = weighted({s: sum(fn(a) for a, _ in v if fn(a) is not None) / max(1, sum(1 for a, _ in v if fn(a) is not None)) for s, v in pairs.items()})
        mb = weighted({s: sum(fn(b) for _, b in v if fn(b) is not None) / max(1, sum(1 for _, b in v if fn(b) is not None)) for s, v in pairs.items()})
        flag = " *" if lo > 0 or hi < 0 else ""
        print(f"  {name:<52} {ma:9.3f} {mb:9.3f} {est:+9.3f}  [{lo:+.3f}, {hi:+.3f}]{flag}")
        if key in RATIO:
            r, rlo, rhi, _ = estimate(pairs, fn, ratio=True)
            flag = " *" if rlo > 0 or rhi < 0 else ""
            print(f"  {'   ratio B/A-1':<52} {'':9} {'':9} {100 * r:+8.1f}%  [{100 * rlo:+.1f}%, {100 * rhi:+.1f}%]{flag}")
    return pairs


pairs = table("all 24 scenarios", lambda s: True)
table("without L2 and M10 (seen before)", lambda s: s not in SEEN)

print("\n== per scenario (mean over seeds): player HP lost A -> B, player out A -> B, hostile out A -> B, hostile attack dmg A -> B")
sign = Counter()
for s in sorted(pairs, key=lambda x: (x[0], int(x[1:]))):
    v = pairs[s]
    m = lambda fn, side: sum(fn(p[side]) for p in v) / len(v)
    pa, pb = m(lambda r: r["phplost"], 0), m(lambda r: r["phplost"], 1)
    sign["B>A" if pb > pa else "B<A" if pb < pa else "="] += 1
    print(f"  {s:<4} {pa:7.0f} -> {pb:7.0f}   {m(lambda r: r['pinc'], 0):.2f} -> {m(lambda r: r['pinc'], 1):.2f}   "
          f"{m(lambda r: r['hinc'], 0):.2f} -> {m(lambda r: r['hinc'], 1):.2f}   {m(lambda r: r['h_dmg'], 0):6.0f} -> {m(lambda r: r['h_dmg'], 1):6.0f}"
          f"   seeds: " + " ".join(f"{p[0]['phplost']:.0f}->{p[1]['phplost']:.0f}" for p in v))
print(f"  player HP lost by scenario: {dict(sign)}")

print("\n== outcomes (player side): A " + str(dict(Counter(A[k]["outcome"] for k in keys))) + ", B " + str(dict(Counter(B[k]["outcome"] for k in keys))))
print("  pairs A -> B: " + str(dict(Counter(f"{A[k]['outcome']}->{B[k]['outcome']}" for k in keys))))
print("  how A: " + str(dict(Counter(A[k]["how"] for k in keys))) + ", B: " + str(dict(Counter(B[k]["how"] for k in keys))))

tot = lambda k: sum(B[x][k] for x in keys)
print(f"\n== scheduler (arm B, all pairs): picks {tot('s_picks'):.0f}, attack picks out of the engine's order {tot('s_promo'):.0f}; "
      f"the promoted unit's first decision an attack {tot('s_promo_att'):.0f}, executed {tot('s_promo_exec'):.0f}, with damage "
      f"{tot('s_promo_hit'):.0f}, damage {tot('s_promo_dmg'):.0f}; scheduler time {tot('s_us') / 1000:.0f} ms total, "
      f"{tot('s_us') / max(1, tot('s_picks')):.0f} us per pick")
print(f"  executed attacks of the other units in B {tot('nonpromo_attexec'):.0f} vs all executed attacks in A "
      f"{sum(A[x]['h_attexec'] for x in keys):.0f} (B all {tot('h_attexec'):.0f})")
