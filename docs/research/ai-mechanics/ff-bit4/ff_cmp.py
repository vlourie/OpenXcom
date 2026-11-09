"""FF bit 4 on today's stand: E0 vs E identity (the blast record is passive), then E against F per battle and in total.
usage: ff_cmp.py <dir with ff_*> <ff_battles.tsv> [prefix]

Measures per side 1 (HOSTILE) by census/ai3_2026-10-14/ff/ff_ana.py (read-only import): own+self knocked out fresh by
blasts of each kind (sec = terrain set off by the side's attack), damage to own, attacks, useful attacks, damage to the
player's units, the ff.* notes; plus own-side casualties (casualties file), and here: HOSTILE secondary blasts that hit
any of their own (the dangerous ones), and the table's outcome / turns / player and enemy losses.
"""
import collections
import gzip
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "E:/OpenXCom/census/ai3_2026-10-14/ff")
import ff_ana  # noqa: E402

D = Path(sys.argv[1])
P = sys.argv[3] if len(sys.argv) > 3 else "ff"
# [4] [5]: the pair that must be identical (E0 E); [6]: the candidate arm read in the "F" column (F)
IA, IB = (sys.argv[4], sys.argv[5]) if len(sys.argv) > 5 else ("E0", "E")
ARM = {"E": sys.argv[7] if len(sys.argv) > 7 else "E", "F": sys.argv[6] if len(sys.argv) > 6 else "F"}  # [7]: the base arm
BT = [l.split("\t") for l in Path(sys.argv[2]).read_text(encoding="utf-8-sig").splitlines()[1:] if l.strip()]
STREAMS = (".rec.gz", ".decide.gz", ".cand.gz", ".tiles.gz", ".path.gz", ".casualties.txt")
RX = re.compile(r"^seed=(\d+) want=(\S+) \[(\w+)\] (.*)$")


def lines(p):
    if not p.exists():
        return None
    op = gzip.open if p.suffix == ".gz" else open
    with op(p, "rt", encoding="utf-8-sig", errors="replace") as f:
        return f.read().splitlines()


def table(label):
    t = lines(D / f"{label}.tsv")
    return dict(zip(t[0].split("\t"), t[1].split("\t"))) if t and len(t) > 1 else None


def strip_blast(ls):
    return [l for l in ls if "[AIBLAST]" not in l and "[AIBHIT]" not in l and "[AIEFF]" not in l]


def ident(a, b):
    ta, tb = table(a), table(b)
    if not ta or not tb:
        return "no table"
    for k in ta:
        if k not in ("seconds",) and ta.get(k) != tb.get(k):
            return f"table {k}: {ta.get(k)} | {tb.get(k)}"
    n = 0
    for s in STREAMS:
        la, lb = lines(D / (a + s)), lines(D / (b + s))
        if la is None and lb is None:
            continue
        if la is None or lb is None:
            return f"{s}: only one has it"
        la, lb = strip_blast(la), strip_blast(lb)
        if la != lb:
            i = next((i for i, (x, y) in enumerate(zip(la, lb)) if x != y), min(len(la), len(lb)))
            return f"{s} line {i}: {la[i][:200] if i < len(la) else '-'} | {lb[i][:200] if i < len(lb) else '-'}"
        n += len(la)
    return n


def danger(label):
    """HOSTILE secondary blasts (terrain set off by a HOSTILE attack) that hit their own side; and all HOSTILE sec blasts."""
    pend = collections.defaultdict(list)
    c = collections.Counter()
    for l in lines(D / f"{label}.rec.gz") or []:
        m = RX.match(l)
        if not m or m.group(3) not in ("AIBLAST", "AIBHIT"):
            continue
        o = json.loads(m.group(4))
        if m.group(3) == "AIBHIT":
            pend[o.get("b")].append(o)
            continue
        hs = pend.pop(o.get("b"), [])
        if o.get("of") != 1 or ff_ana.kind(o.get("at"), o.get("att", -1)) != "sec":
            continue
        c["sec_blasts"] += 1
        own = [h for h in hs if h.get("rel") in ("ally", "self")]
        c["sec_blasts_own_hit"] += bool(own)
        c["sec_blasts_own_ko"] += any((h.get("dead") or h.get("ko")) and not h.get("down0") for h in own)
    return c


KEYS = ["s1_fsec_ko", "s1_fgren_ko", "s1_flaunch_ko", "s1_fshot_ko", "s1_fsec_dmg", "s1_cas_ff", "s1_att", "s1_useful", "s1_edmg",
        "s1_thr", "s1_lch", "s1_cyc", "s1_n_sec", "s1_n_secsn", "s1_n_secre", "s1_n_trade", "s0_fsec_ko", "s0_cas_ff"]


def main():
    print(f"== {IA} vs {IB} (must play the same); the F column below is {ARM['F']}")
    same = 0
    for b in BT:
        r = ident(f"{P}_{IA}_{b[0]}", f"{P}_{IB}_{b[0]}")
        same += isinstance(r, int)
        print(f"{b[0]}: {'IDENTICAL (' + str(r) + ' lines)' if isinstance(r, int) else 'DIFF ' + str(r)}")
    print(f"identical {same}/{len(BT)}")
    tot = {g: {a: collections.Counter() for a in ("E", "F")} for g in ("target", "control")}
    rows = []
    for b in BT:
        bid, grp = b[0], b[3]
        rr = {}
        for arm in ("E", "F"):
            label = f"{P}_{ARM[arm]}_{bid}"
            rec = D / f"{label}.rec.gz"
            if not rec.exists():
                rr[arm] = None
                continue
            B = ff_ana.scan_file(str(rec))
            ff_ana.add_cas_tsv(B, str(rec))
            C = next(iter(B.values())) if B else collections.Counter()
            C = collections.Counter({k: v for k, v in C.items() if isinstance(v, int)})
            C.update(danger(label))
            t = table(label) or {}
            for k in ("pdead", "pout", "pwounded", "phplost", "hdead", "hout", "hattacks", "turn"):
                try:
                    C["t_" + k] = int(t.get(k) or 0)
                except ValueError:
                    pass
            C["outcome." + t.get("outcome", "?")] += 1
            C["how." + t.get("how", "?")] += 1
            rr[arm] = (C, t)
            tot[grp][arm].update(C)
        if not rr.get("E") or not rr.get("F"):
            print(f"{bid}: missing")
            continue
        e, f = rr["E"][0], rr["F"][0]
        rows.append((bid, grp, e, f, rr["E"][1].get("outcome"), rr["F"][1].get("outcome")))
    print("\n== per battle, E -> F (HOSTILE)")
    print("battle\tgroup\toutcome\tturns\town KO sec\town KO all blasts\tsec blasts own hit\tcas own\tuseful att\tdmg to player\tplayer dead+out\tenemy dead+out\tveto ff.sec/sniper/react")
    for bid, grp, e, f, oe, of in rows:
        ko = lambda c: c["s1_fsec_ko"] + c["s1_fgren_ko"] + c["s1_flaunch_ko"] + c["s1_fshot_ko"]
        print(f"{bid}\t{grp}\t{oe}->{of}\t{e['t_turn']}->{f['t_turn']}\t{e['s1_fsec_ko']}->{f['s1_fsec_ko']}\t{ko(e)}->{ko(f)}"
              f"\t{e['sec_blasts_own_hit']}->{f['sec_blasts_own_hit']}\t{e['s1_cas_ff']}->{f['s1_cas_ff']}\t{e['s1_useful']}->{f['s1_useful']}"
              f"\t{e['s1_edmg']}->{f['s1_edmg']}\t{e['t_pdead'] + e['t_pout']}->{f['t_pdead'] + f['t_pout']}"
              f"\t{e['t_hdead'] + e['t_hout']}->{f['t_hdead'] + f['t_hout']}\t{f['s1_n_sec']}/{f['s1_n_secsn']}/{f['s1_n_secre']}")
    print("\n== totals E | F")
    for g in ("target", "control"):
        print(f"-- {g}")
        keys = sorted(set(tot[g]["E"]) | set(tot[g]["F"]))
        for k in keys:
            print(f"{k}\t{tot[g]['E'].get(k, 0)}\t{tot[g]['F'].get(k, 0)}")
    # signs per battle on the main measures
    print("\n== per-battle signs F vs E (less / same / more), target battles")
    for k in ("s1_fsec_ko", "s1_cas_ff", "s1_useful", "s1_edmg", "t_phplost", "t_pdead"):
        lt = sum(1 for r in rows if r[1] == "target" and r[3][k] < r[2][k])
        eq = sum(1 for r in rows if r[1] == "target" and r[3][k] == r[2][k])
        gt = sum(1 for r in rows if r[1] == "target" and r[3][k] > r[2][k])
        print(f"{k}\t{lt} / {eq} / {gt}")


main()
