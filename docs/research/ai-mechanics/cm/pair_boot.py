"""Protocol v1 estimate of a candidate (section 4): pairs B - A by scenario and seed; per scenario the mean over seeds; stages
(M - middle, L - late) of equal weight, scenarios of equal weight inside a stage; HP as the ratio of weighted means B/A - 1,
deaths as B - A per battle; 95% CI by the two-level bootstrap stratified by stage (scenarios with replacement inside the
stage, seeds with replacement inside the scenario, the pair kept), 10 000 repeats, fixed seed. Never by battles.

  py -3.13 -I pair_boot.py <arena dir> <prefix A> <prefix B>     (tables <prefix>_<arm>_<scen>_s<k>.tsv)"""
import random
import sys
from collections import defaultdict
from pathlib import Path

D, PA, PB = Path(sys.argv[1]), sys.argv[2], sys.argv[3]


def load(pre):
    out = {}
    for p in D.glob(f"{pre}_*.tsv"):
        if p.name.endswith(".data_manifest.tsv"):
            continue
        scen, s = p.stem[len(pre) + 1:].split("_", 1)[1].rsplit("_s", 1)
        lines = p.read_text(encoding="utf-8-sig").splitlines()
        r = dict(zip(lines[0].split("\t"), lines[-1].split("\t")))
        out[(scen, int(s))] = (float(r["phplost"]), float(r["pdead"]), float(r["hdead"]), float(r["turn"]))
    return out


A, B = load(PA), load(PB)
keys = sorted(set(A) & set(B))
missing = sorted(set(A) ^ set(B))
pairs = defaultdict(list)  # scen -> [(a, b)]
for k in keys:
    pairs[k[0]].append((A[k], B[k]))
stages = {"M": sorted(s for s in pairs if s.startswith("M")), "L": sorted(s for s in pairs if s.startswith("L"))}


def estimate(sample):
    """sample: stage -> list of (list of pairs) per scenario. Returns (HP ratio - 1, deaths B - A)."""
    ha = hb = da = db = 0.0
    for st, scens in sample.items():
        if not scens:
            continue
        w = 1.0 / len([x for x in sample.values() if x]) / len(scens)
        for ps in scens:
            n = len(ps)
            ha += w * sum(a[0] for a, _ in ps) / n
            hb += w * sum(b[0] for _, b in ps) / n
            da += w * sum(a[1] for a, _ in ps) / n
            db += w * sum(b[1] for _, b in ps) / n
    return (hb / ha - 1 if ha else 0.0), db - da


point = estimate({st: [pairs[s] for s in ss] for st, ss in stages.items()})
rng = random.Random(20261027)
hp, de = [], []
for _ in range(10000):
    smp = {}
    for st, ss in stages.items():
        pick = [rng.choice(ss) for _ in ss]
        smp[st] = [[rng.choice(pairs[s]) for _ in pairs[s]] for s in pick]
    h, d = estimate(smp)
    hp.append(h)
    de.append(d)
hp.sort()
de.sort()
lo, hi = int(0.025 * 10000), int(0.975 * 10000) - 1
print(f"pairs {len(keys)} scenarios {len(pairs)} (M {len(stages['M'])}, L {len(stages['L'])}) missing {missing or '-'}")
print(f"HP lost B/A-1 {100 * point[0]:+.1f}%  95% CI [{100 * hp[lo]:+.1f}%, {100 * hp[hi]:+.1f}%]")
print(f"deaths B-A per battle {point[1]:+.3f}  95% CI [{de[lo]:+.3f}, {de[hi]:+.3f}]")
tot = lambda X, i: sum(X[k][i] for k in keys)
print(f"totals A/B: phplost {tot(A, 0):.0f}/{tot(B, 0):.0f} pdead {tot(A, 1):.0f}/{tot(B, 1):.0f} hdead {tot(A, 2):.0f}/{tot(B, 2):.0f} "
      f"turns {tot(A, 3):.0f}/{tot(B, 3):.0f}")
print("by scenario (mean over seeds) phplost A -> B, pdead A -> B:")
for st, ss in stages.items():
    for s in ss:
        ps = pairs[s]
        n = len(ps)
        print(f"  {s:4s} {sum(a[0] for a, _ in ps) / n:7.0f} -> {sum(b[0] for _, b in ps) / n:7.0f}   "
              f"{sum(a[1] for a, _ in ps) / n:5.1f} -> {sum(b[1] for _, b in ps) / n:5.1f}")
