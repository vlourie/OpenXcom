"""P0 vs P1: per-battle metrics from the full battle logs and the paired analysis by scenario (PREREG.md).

  py -3.13 pv_analyze.py <out dir: D0_M1_s1/openxcom.log.gz ...> <scen.tsv> <report prefix>

Writes <prefix>_battles.tsv (one row per battle), <prefix>_pairs.tsv (D1 - D0 per scenario, the mean of two seeds) and
<prefix>.txt (the summary)."""
import gzip
import random
import re
import sys
from collections import defaultdict
from math import comb
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT, SCEN, PFX = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
ATTACK = {6, 7, 8, 9, 10, 12, 13, 14}
KV = re.compile(r"(\w+)=(\S+)")


def fields(line):
    return dict(KV.findall(line))


def outcome(r):
    """As ai_arena.outcome: win - no enemies on their feet, loss - no player's, draw - the turn cap, held - the mission timer."""
    if not r:
        return "none"
    how = r.get("how")
    if how not in ("over", "abort", "timeout"):
        return how or "?"
    if how == "timeout":
        return "draw"
    if int(r["livealiens"]) == 0:
        return "win"
    if int(r["livesoldiers"]) == 0:
        return "loss"
    return "held" if how == "abort" or r.get("aborted") == "1" else "end-other"


def battle(path):
    m = {"lines": 0}
    res, stuck = None, None
    snaps = defaultdict(dict)  # (when, turn) -> unit -> (faction, status, hp, tu, tumax)
    dec = []
    cas = []
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if not body.startswith("[AI"):
                continue
            m["lines"] += 1
            if body.startswith("[AIDECIDE] "):
                dec.append(fields(body))
            elif body.startswith("[AISTATE] "):
                when = body.split(" ", 2)[1]
                if when in ("aistart", "pstart"):
                    j = fields(body)
                    hp = j["hp"].split("/")[0]
                    snaps[(when, int(j["turn"]))][j["unit"]] = (int(j["faction"]), int(j["status"]), int(hp), int(j["tu"]),
                                                                int(j["tumax"]))
            elif body.startswith("[AICASUALTY] "):
                cas.append(fields(body))
            elif body.startswith("[AIRESULT] "):
                res = fields(body)
            elif body.startswith("[AIPROBE] stuck"):
                stuck = body
            elif body.startswith("[AIPROBE] battle"):
                m["battle"] = body
    m["res"] = res
    m["stuck"] = stuck
    # the start: the state and RNG hashes of the battle's first decision (taken before it acts)
    m["start"] = tuple(dec[0].get(k) for k in ("turn", "side", "unit", "from", "tu", "hu", "hi", "ho", "hm", "hr0")) if dec else None
    m["outcome"] = outcome(res)
    # the enemy's decisions
    h = [d for d in dec if d.get("side") == "1"]
    m["hdec"] = len(h)
    m["hatk_dec"] = sum(1 for d in h if int(d["act"]) in ATTACK)
    m["hempty"] = sum(1 for d in h if d["act"] == "0")
    m["hrethink"] = sum(1 for d in h if d["act"] == "15")
    m["hwalk"] = sum(1 for d in h if d["act"] == "2")
    # cycles: the same unit in the same turn repeating its decision (from, tu, act, to) right after itself
    rep = 0
    prev = {}
    for d in h:
        key = (d["turn"], d["unit"])
        sig = (d["from"], d["tu"], d["act"], d["to"])
        rep += prev.get(key) == sig
        prev[key] = sig
    m["hrepeat"] = rep
    per = defaultdict(int)
    for d in h:
        per[(d["turn"], d["unit"])] += 1
    m["hunit_turns"] = len(per)
    m["hmax_dec"] = max(per.values()) if per else 0
    # TU of the enemy over its turn T: aistart T -> pstart T+1, units on their feet at the start
    avail = used = 0
    useful = 0
    pdmg_eturn = 0
    for (when, t), units in snaps.items():
        if when != "aistart":
            continue
        after = snaps.get(("pstart", t + 1))
        if not after:
            continue
        for u, (fac, st, hp, tu, tumax) in units.items():
            if fac == 1 and st not in (6, 7) and hp > 0:
                avail += tu
                a = after.get(u)
                used += tu - (a[3] if a and a[1] not in (6, 7) else 0) if a else tu
            if fac == 0 and st not in (6, 7) and hp > 0:
                a = after.get(u)
                pdmg_eturn += max(0, hp - (a[2] if a else 0))
        # useful attacks: the aim is a player's unit that lost health or went down in this enemy turn
        for d in h:
            if int(d["turn"]) != t or int(d["act"]) not in ATTACK:
                continue
            tgt = d.get("aim")
            b, a = units.get(tgt), after.get(tgt)
            if b and b[0] == 0 and (a is None or a[2] < b[2] or a[1] in (6, 7)):
                useful += 1
    m["htu_avail"], m["htu_used"] = avail, used
    m["huseful"] = useful
    m["pdmg_eturn"] = pdmg_eturn
    m["hkills"] = sum(1 for c in cas if c.get("kfaction") == "1" and c.get("vfaction") == "0" and c.get("how") == "dead")
    m["hstuns"] = sum(1 for c in cas if c.get("kfaction") == "1" and c.get("vfaction") == "0" and c.get("how") != "dead")
    m["pkills"] = sum(1 for c in cas if c.get("kfaction") == "0" and c.get("vfaction") == "1")
    return m


def num(r, k):
    return int(r[k]) if r and k in r else 0


def row(m):
    r = m["res"] or {}
    player, hostile = max(1, num(r, "player")), max(1, num(r, "hostile"))
    return {
        "outcome": m["outcome"], "turn": num(r, "turn"), "player": num(r, "player"), "pdead": num(r, "pdead"),
        "pout": num(r, "pout"), "pwounded": num(r, "pwounded"), "phplost": num(r, "phplost"), "hostile": num(r, "hostile"),
        "hdead": num(r, "hdead"), "hout": num(r, "hout"), "hleft": num(r, "hleft"),
        "ploss": (num(r, "pdead") + num(r, "pout")) / player, "hloss": (num(r, "hdead") + num(r, "hout")) / hostile,
        "pattacks": num(r, "pattacks"), "hattacks": num(r, "hattacks"), "hmoves": num(r, "hmoves"),
        "hdec": m["hdec"], "hatk_dec": m["hatk_dec"], "huseful": m["huseful"],
        "useful_rate": m["huseful"] / m["hatk_dec"] if m["hatk_dec"] else 0.0,
        "hkills": m["hkills"], "hstuns": m["hstuns"], "pkills": m["pkills"], "pdmg_eturn": m["pdmg_eturn"],
        "htu_used": m["htu_used"], "htu_avail": m["htu_avail"],
        "tu_rate": m["htu_used"] / m["htu_avail"] if m["htu_avail"] else 0.0,
        "hempty": m["hempty"], "hrethink": m["hrethink"], "hrepeat": m["hrepeat"], "hmax_dec": m["hmax_dec"],
        "hunit_turns": m["hunit_turns"], "ms": num(r, "ms"), "vms": num(r, "vms"),
        "stuck": 1 if m["stuck"] else 0,
    }


def boot(xs, n=20000, seed=1):
    rnd = random.Random(seed)
    k = len(xs)
    means = sorted(sum(xs[rnd.randrange(k)] for _ in range(k)) / k for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n) - 1]


def sign_p(pos, neg):
    n = pos + neg
    if n == 0:
        return 1.0
    k = min(pos, neg)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


def main():
    sc = [l.split("\t") for l in SCEN.read_text(encoding="utf-8-sig").splitlines()[1:] if l.strip()]
    ids = [s[0] for s in sc]
    rows = {}
    for sid in ids:
        for k in (1, 2):
            for c in ("D0", "D1"):
                p = OUT / f"{c}_{sid}_s{k}" / "openxcom.log.gz"
                rows[(c, sid, k)] = None
                if p.is_file():
                    m = battle(p)
                    rows[(c, sid, k)] = row(m)
                    rows[(c, sid, k)]["battle"] = (m.get("battle", ""), m["start"])
    cols = list(next(r for r in rows.values() if r).keys())
    cols = [c for c in cols if c != "battle"]
    with open(f"{PFX}_battles.tsv", "w", encoding="utf-8-sig") as f:
        f.write("cfg\tscen\tseed\t" + "\t".join(cols) + "\n")
        for (c, sid, k), r in rows.items():
            if r:
                f.write(f"{c}\t{sid}\t{k}\t" + "\t".join(f"{r[x]:.4f}" if isinstance(r[x], float) else str(r[x]) for x in cols) + "\n")
    lines = []
    ok = lambda r: r is not None and r["outcome"] in ("win", "loss", "draw", "held", "end-other")
    bad = [(c, s, k, (r or {}).get("outcome", "missing")) for (c, s, k), r in rows.items() if not ok(r)]
    lines.append(f"battles {sum(1 for r in rows.values() if r)} of {len(rows)}; not finished: {bad if bad else 'none'}")
    # the same start: the battle line ([AIPROBE] battle) equal in D0 and D1 of each scenario-seed
    same = sum(1 for sid in ids for k in (1, 2) if rows[("D0", sid, k)] and rows[("D1", sid, k)]
               and rows[("D0", sid, k)]["battle"] == rows[("D1", sid, k)]["battle"])
    lines.append(f"same battle line D0 = D1: {same} of {len(ids) * 2}")
    # outcomes
    for c in ("D0", "D1"):
        cnt = defaultdict(int)
        for (cc, s, k), r in rows.items():
            if cc == c and r:
                cnt[r["outcome"]] += 1
        lines.append(f"{c} outcomes: " + ", ".join(f"{k} {v}" for k, v in sorted(cnt.items())))
    # paired by scenario
    metrics = ["ploss", "pdead", "pout", "pwounded", "phplost", "pdmg_eturn", "hloss", "hdead", "hout", "hkills", "hstuns",
               "pkills", "hattacks", "hatk_dec", "huseful", "useful_rate", "tu_rate", "hdec", "hempty", "hrethink", "hrepeat",
               "hmax_dec", "turn", "ms"]
    pairs = {}
    for sid in ids:
        ds = []
        for k in (1, 2):
            a, b = rows[("D0", sid, k)], rows[("D1", sid, k)]
            if ok(a) and ok(b):
                ds.append({x: b[x] - a[x] for x in metrics} | {"wl": (b["outcome"] == "loss") - (a["outcome"] == "loss")})
        if ds:
            pairs[sid] = {x: sum(d[x] for d in ds) / len(ds) for x in metrics + ["wl"]} | {"n": len(ds)}
    with open(f"{PFX}_pairs.tsv", "w", encoding="utf-8-sig") as f:
        f.write("scen\tn\t" + "\t".join(metrics + ["wl"]) + "\n")
        for sid, p in pairs.items():
            f.write(f"{sid}\t{p['n']}\t" + "\t".join(f"{p[x]:.4f}" for x in metrics + ["wl"]) + "\n")
    lines.append(f"clusters {len(pairs)}")
    lines.append("metric | D0 mean | D1 mean | mean D1-D0 by scenario | 95% CI (bootstrap by scenario) | scen + / - / 0 | sign p")
    for x in metrics + ["wl"]:
        xs = [p[x] for p in pairs.values()]
        if not xs:
            continue
        lo, hi = boot(xs)
        pos, neg = sum(v > 1e-12 for v in xs), sum(v < -1e-12 for v in xs)
        if x == "wl":
            m0 = sum(r["outcome"] == "loss" for (c, s, k), r in rows.items() if c == "D0" and ok(r)) / max(1, sum(1 for (c, s, k), r in rows.items() if c == "D0" and ok(r)))
            m1 = sum(r["outcome"] == "loss" for (c, s, k), r in rows.items() if c == "D1" and ok(r)) / max(1, sum(1 for (c, s, k), r in rows.items() if c == "D1" and ok(r)))
        else:
            v0 = [r[x] for (c, s, k), r in rows.items() if c == "D0" and ok(r)]
            v1 = [r[x] for (c, s, k), r in rows.items() if c == "D1" and ok(r)]
            m0, m1 = sum(v0) / max(1, len(v0)), sum(v1) / max(1, len(v1))
        lines.append(f"{x} | {m0:.4f} | {m1:.4f} | {sum(xs) / len(xs):+.4f} | [{lo:+.4f}, {hi:+.4f}] | {pos} / {neg} / {len(xs) - pos - neg} | {sign_p(pos, neg):.3f}")
    xs = [p["ploss"] for p in pairs.values()]
    lo, hi = boot(xs)
    verdict = "BETTER" if lo > 0 else "WORSE" if hi < 0 else "INCONCLUSIVE"
    lines.append(f"PRIMARY ploss: mean {sum(xs) / len(xs):+.4f} CI [{lo:+.4f}, {hi:+.4f}] -> {verdict}")
    # per scenario detail
    lines.append("scen seed | D0: outcome turn ploss phplost hloss hatk useful tu_rate empty repeat | D1: the same")
    for sid in ids:
        for k in (1, 2):
            parts = []
            for c in ("D0", "D1"):
                r = rows[(c, sid, k)]
                parts.append("-" if not r else f"{r['outcome']} t{r['turn']} {r['ploss']:.2f} {r['phplost']} {r['hloss']:.2f} "
                             f"{r['hatk_dec']} {r['huseful']} {r['tu_rate']:.2f} {r['hempty']} {r['hrepeat']}")
            lines.append(f"{sid} s{k} | " + " | ".join(parts))
    text = "\n".join(lines) + "\n"
    Path(f"{PFX}.txt").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
