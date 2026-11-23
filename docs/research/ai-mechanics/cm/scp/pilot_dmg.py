"""SIDE_TURN_ACTION_SCHEDULER combat pilot: where the player's HP loss comes from, beside the hostile attack damage.

"Player HP lost" ([AIRESULT] phplost) is, per player unit, its health at the start minus max(0, health at the end): every
source, overkill cut at 0. "Hostile attack damage" (pilot_metrics h_dmg) is the [AIEXEC] dmg of the hostile side's executed
attacks: the health every unit of another faction (player AND neutral) lost during that action, overkill included (health
goes below 0). Here the player's loss is cut by the [AISTATE] snapshots (aistart / pstart, after the side switch): the
hostile segment (aistart t -> pstart t+1: hostile turn, then the player's turn-start effects) and the player segment
(before / pstart t -> aistart t: the player's own turn - hostile reaction fire, own fire - then the hostile turn-start
effects); the rest after the last snapshot goes to the segment it falls in. From [AIEXEC] beside it: the hostile damage
of non-attack actions, the player actor's own HP loss during its actions (reaction fire, own blast) and the player's
friendly damage. Then the paired B - A by scenario, the pilot_stats weighting and bootstrap.

  py -3.13 -I pilot_dmg.py <out dir> <A tsv> <B tsv> <tsv out>"""
import gzip
import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT = Path(sys.argv[1])
KV = re.compile(r"(\w+)=(\S+)")
ATT = {6, 7, 8, 9, 10, 12, 13, 14}
N = 10000
SEEN = {"L2", "M10"}
COLS = ["phplost", "p_hseg", "p_pseg", "p_rest_h", "p_rest_p", "p_heal", "h_dmg", "h_dmg_nonatt", "p_actor_lost", "p_fdmg"]


def one(label):
    st = defaultdict(float)
    hp = {}           # player unit -> health at the last snapshot (cut at 0)
    snap = None       # (kind, turn) of the snapshot being gathered
    cur = {}
    seg = None        # "h" or "p": the segment that started at the last snapshot
    pend = None
    phplost = 0

    def close(next_hp):
        nonlocal hp
        if seg is not None:
            for u, h in hp.items():
                d = h - next_hp.get(u, 0)
                if d >= 0:
                    st[f"p_{seg}seg"] += d
                else:
                    st[f"p_{seg}seg"] += d
                    st["p_heal"] += -d
        hp = dict(next_hp)

    for raw in gzip.open(OUT / label / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace"):
        body = raw.rstrip("\n").split("\t", 2)[-1]
        if body.startswith("[AISTATE] "):
            kind = body.split(" ", 2)[1]
            d = dict(KV.findall(body))
            key = (kind, d["turn"])
            if key != snap:
                if snap is not None:
                    close(cur)
                    seg = {"aistart": "h", "pstart": "p", "before": "p", "end": None}[snap[0]]
                snap, cur = key, {}
            if d["faction"] == "0":
                cur[d["unit"]] = max(0, int(d["hp"].split("/")[0]))
        elif body.startswith("[AIDECIDE] "):
            d = dict(KV.findall(body.split(" hu=")[0]))
            pend = (d["side"], d["unit"], int(d["act"]) in ATT)
        elif body.startswith("[AIEXEC] ") and pend:
            x = json.loads(body[9:])
            side, u, att = pend
            pend = None
            if str(x["unit"]) != u:
                continue
            spent, walk = x.get("spent") or 0, bool(x.get("walk"))
            if side == "1" and not (att and spent > 0 and not walk):
                st["h_dmg_nonatt"] += x.get("dmg") or 0
            if side == "1" and att and spent > 0 and not walk:
                st["h_dmg"] += x.get("dmg") or 0
            if side == "0":
                st["p_actor_lost"] += x.get("hp_lost") or 0
                st["p_fdmg"] += x.get("fdmg") or 0
        elif body.startswith("[AIRESULT] "):
            phplost = int(dict(KV.findall(body))["phplost"])
    # the snapshot being gathered when the log ended, then the rest up to the result
    if snap is not None:
        close(cur)
        seg = {"aistart": "h", "pstart": "p", "before": "p", "end": None}[snap[0]]
    rest = phplost - st["p_hseg"] - st["p_pseg"]
    if seg is not None:
        st[f"p_rest_{seg}"] += rest
    elif rest:
        st["p_rest_p"] += rest  # after the "end" snapshot nothing should be left; keep it visible
    st["phplost"] = phplost
    return st


def load(p):
    ls = Path(p).read_text(encoding="utf-8-sig").splitlines()
    head = ls[0].split("\t")
    return {(r["scen"], int(r["seed"])): r for r in (dict(zip(head, l.split("\t"))) for l in ls[1:])}


rows = {}
with open(sys.argv[4], "w", encoding="utf-8-sig") as f:
    f.write("label\tarm\tscen\tseed\t" + "\t".join(COLS) + "\n")
    for arm, p in (("A", sys.argv[2]), ("B", sys.argv[3])):
        for k, r in load(p).items():
            st = one(r["label"])
            rows[(arm,) + k] = st
            f.write(f"{r['label']}\t{arm}\t{k[0]}\t{k[1]}\t" + "\t".join(f"{st[c]:.0f}" for c in COLS) + "\n")


def weighted(per_scen):
    by = defaultdict(list)
    for s, v in per_scen.items():
        by[s[0]].append(v)
    return sum(sum(v) / len(v) for v in by.values()) / len(by)


def estimate(data):
    """data: {scen: [(a, b)]} -> mean A, mean B, B - A and its 95% CI (two-level bootstrap stratified by stage)."""
    point = lambda d: weighted({s: sum(y - x for x, y in v) / len(v) for s, v in d.items()})
    rnd = random.Random(20261030)
    st = defaultdict(list)
    for s in data:
        st[s[0]].append(s)
    boots = []
    for _ in range(N):
        d = {}
        for g, ss in st.items():
            for i, s in enumerate(rnd.choice(ss) for _ in ss):
                v = data[s]
                d[f"{g}{i}_{s}"] = [rnd.choice(v) for _ in v]
        boots.append(point(d))
    boots.sort()
    ma = weighted({s: sum(x for x, _ in v) / len(v) for s, v in data.items()})
    mb = weighted({s: sum(y for _, y in v) / len(v) for s, v in data.items()})
    return ma, mb, point(data), boots[int(0.025 * N)], boots[int(0.975 * N) - 1]


NAMES = [("phplost", "player HP lost (AIRESULT, all sources)"),
         ("p_hseg_all", "  in hostile segments (incl. the rest after the last snapshot)"),
         ("p_pseg_all", "  in player segments (incl. the rest)"),
         ("p_heal", "  healed back (inside the segments above, net)"),
         ("h_dmg", "hostile attack damage (AIEXEC, player+neutral, overkill)"),
         ("h_dmg_nonatt", "hostile damage of non-attack actions"),
         ("hgap", "hostile attack damage - player loss in hostile segments"),
         ("p_actor_lost", "player actor's own HP loss in its actions"),
         ("p_fdmg", "player's friendly damage")]
keys = sorted({k[1:] for k in rows})


def val(st, n):
    if n == "p_hseg_all":
        return st["p_hseg"] + st["p_rest_h"]
    if n == "p_pseg_all":
        return st["p_pseg"] + st["p_rest_p"]
    if n == "hgap":
        return st["h_dmg"] - st["p_hseg"] - st["p_rest_h"]
    return st[n]


for title, ok in (("all 24 scenarios", lambda s: True), ("without L2 and M10", lambda s: s not in SEEN)):
    print(f"\n== {title}")
    print(f"  {'metric':<64} {'A':>8} {'B':>8} {'B-A':>8}  95% CI")
    for n, name in NAMES:
        data = defaultdict(list)
        for s, sd in keys:
            if ok(s):
                data[s].append((val(rows[("A", s, sd)], n), val(rows[("B", s, sd)], n)))
        ma, mb, e, lo, hi = estimate(data)
        flag = " *" if lo > 0 or hi < 0 else ""
        print(f"  {name:<64} {ma:8.1f} {mb:8.1f} {e:+8.1f}  [{lo:+.1f}, {hi:+.1f}]{flag}")
rest = [abs(rows[k]["p_rest_h"] + rows[k]["p_rest_p"]) for k in rows]
print(f"\nrest after the last snapshot: battles with any {sum(1 for r in rest if r)}, total {sum(rest):.0f} HP of "
      f"{sum(rows[k]['phplost'] for k in rows):.0f}")
