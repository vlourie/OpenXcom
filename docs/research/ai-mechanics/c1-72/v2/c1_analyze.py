"""C1 72-battle pilot: E vs A identity and the work of C1 in B.  usage: c1_analyze.py <dir with c1_*.{tsv,rec.gz,...}> <scen.tsv>

E vs A: every stream decompressed and compared line by line (rec, decide, cand, tiles, path, casualties) plus the table
without seconds; [AIRESULT] without ms/vms. The first differing line is printed.
B: cover records (trail 'cover.*') joined with their [AIEXEC] and the unit's [AIAFTER]; hostile unit-turns that
attacked, A against B; battle totals.
"""
import gzip
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
D = Path(sys.argv[1])
P = sys.argv[3] if len(sys.argv) > 3 else "c1"  # label prefix of the series
SC = [l.split("\t") for l in Path(sys.argv[2]).read_text(encoding="utf-8-sig").splitlines()[1:] if l.strip()]
STREAMS = (".rec.gz", ".decide.gz", ".cand.gz", ".tiles.gz", ".path.gz", ".casualties.txt")
NUM = ("turn", "pdead", "pout", "pwounded", "phplost", "hostile", "hdead", "hout", "hleft", "pattacks", "hattacks",
       "hdecisions", "player", "seconds")


def lines(p):
    if not p.exists():
        return None
    op = gzip.open if p.suffix == ".gz" else open
    with op(p, "rt", encoding="utf-8-sig") as f:
        return f.read().splitlines()


def table(label):
    p = D / f"{label}.tsv"
    if not p.exists():
        return None
    t = p.read_text(encoding="utf-8-sig").splitlines()
    head = t[0].split("\t")
    return dict(zip(head, t[1].split("\t"))) if len(t) > 1 else None


def result(label):
    t = lines(D / f"{label}.result.txt") or []
    return [re.sub(r" (ms|vms)=\d+", "", l) for l in t if "[AIRESULT]" in l]


def ea(sid):
    """None if identical, else the first difference."""
    e, a = f"{P}_E_{sid}", f"{P}_A_{sid}"
    te, ta = table(e), table(a)
    if te is None or ta is None:
        return "no table"
    for k in te:
        if k != "seconds" and te.get(k) != ta.get(k):
            return f"table {k}: E={te.get(k)} A={ta.get(k)}"
    re_, ra = result(e), result(a)
    if re_ != ra:
        return f"AIRESULT: E={re_[:1]} A={ra[:1]}"
    for s in STREAMS:
        le, la = lines(D / (e + s)), lines(D / (a + s))
        if le is None and la is None:
            continue
        if le is None or la is None:
            return f"{s}: only one arm has it"
        for i, (x, y) in enumerate(zip(le, la)):
            if x != y:
                return f"{s} line {i}: E={x[:300]} | A={y[:300]}"
        if len(le) != len(la):
            return f"{s}: E {len(le)} lines, A {len(la)}"
    return None


def recs(label):
    """[AIREC] by rec, [AIEXEC] by rec, [AIAFTER] by (side, unit, turn)."""
    R, X, F = {}, {}, {}
    for l in lines(D / f"{label}.rec.gz") or []:
        tag, _, body = l.partition("] {")
        if not body:
            continue
        j = json.loads("{" + body)
        if tag.endswith("[AIREC"):
            R[j["rec"]] = j
        elif tag.endswith("[AIEXEC"):
            X[j["rec"]] = j
        elif tag.endswith("[AIAFTER"):
            F[(j["side"], j["unit"], j["turn"])] = j
    return R, X, F


def kv(note):
    return {k: int(v) for k, v in re.findall(r"(\w+)=(-?\d+)", note)}


def groups(R):
    """hostile unit-turns: (unit, turn) -> recs in order."""
    g = defaultdict(list)
    for r in sorted(R):
        j = R[r]
        if j["side"] == 1:
            g[(j["unit"], j["turn"])].append(j)
    return g


def attack_turns(R, X, F):
    """Hostile unit-turns with an attack: how many, ended in view (last [AIEXEC] spotted>0), hurt / downed in the
    player's turn after, attacked again on its next turn."""
    g = groups(R)
    out = defaultdict(int)
    for (u, t), lst in g.items():
        out["selections"] += sum(1 for j in lst if j["n"] <= 1)
        for j in lst:
            x = X.get(j["rec"])
            if j["base"]["k"] == "a" and x is not None:
                out["a_dec"] += 1
                out["a_noexec"] += x.get("spent", 0) == 0
        if not any(j["base"]["k"] == "a" for j in lst):
            continue
        out["n"] += 1
        last = X.get(lst[-1]["rec"])
        if last and last.get("down"):
            out["down_own"] += 1
            continue
        if last and last.get("spotted", 0) > 0:
            out["end_seen"] += 1
        f = F.get((1, u, t))
        if f:
            out["after"] += 1
            out["after_hit"] += f.get("hp_lost", 0) > 0
            out["after_hp"] += max(0, f.get("hp_lost", 0))
            out["after_down"] += bool(f.get("dead") or f.get("down"))
            out["after_seen"] += f.get("spotted", 0) > 0
        nxt = g.get((u, t + 1))
        if nxt is not None:
            out["next"] += 1
            out["next_attack"] += any(j["base"]["k"] == "a" for j in nxt)
    return out


def cover(R, X, F):
    g = groups(R)
    out = defaultdict(int)
    bad = []
    for (u, t), lst in g.items():
        out["max_recs"] = max(out["max_recs"], len(lst))
        out["turns_gt3"] += len(lst) > 3
        for j in lst:
            trail = j["base"]["reason"]["trail"]
            notes = [s for s in trail if s.startswith("cover.") and " " in s]
            tags = [s for s in trail if s.startswith("cover.") and " " not in s]
            for s in tags:
                out["tag." + s] += 1
            if not notes:
                continue
            note = notes[-1]
            n = kv(note)
            x = X.get(j["rec"])
            if note.startswith("cover.step"):
                out["step"] += 1
                # the attack that set the debt: the previous rec of this unit-turn; did it spend TU?
                prev = [k for k in lst if k["rec"] < j["rec"]]
                px = X.get(prev[-1]["rec"]) if prev else None
                out["step_after_noexec_attack"] += bool(prev and prev[-1]["base"]["k"] == "a" and px and px.get("spent", 0) == 0)
                out["step_third"] += j["n"] >= 3
                if not x:
                    out["step_noexec"] += 1
                    continue
                moved = x["pos"] != j["state"]["pos"]
                out["moved"] += moved
                out["walk1"] += x.get("walk") == 1
                out["step_hp_lost"] += x.get("hp_lost", 0) > 0
                out["step_hp"] += max(0, x.get("hp_lost", 0))
                out["step_down"] += bool(x.get("down"))
                out["step_unseen_after"] += x.get("spotted", 0) == 0
                out["dist_sum"] += n.get("dist", 0)
                stopped = any(s.startswith("walk.stop.") for s in x.get("trail", []))
                out["step_reaction_stop"] += any(s.startswith("walk.stop.reaction") for s in x.get("trail", []))
                # cost honesty: the step spends what the path costs plus the paid turn at its end (up to 4 steps of
                # 45 degrees; the corrected C1), a walk cut short by reaction fire spends less; and leaves the reserve
                extra = x.get("spent", 0) - n.get("cost", 0)
                out["spent_ne_cost"] += extra != 0
                out["turn_paid"] += extra > 0
                if not stopped and not 0 <= extra <= 8:
                    out["spent_bad"] += 1
                    bad.append(f"spent {x.get('spent')} != cost {n.get('cost')} rec {j['rec']} u{u} t{t}")
                if x.get("tu", 0) < n.get("keep", 0) and not x.get("down"):
                    out["below_keep"] += 1
                    bad.append(f"tu after {x.get('tu')} < keep {n.get('keep')} rec {j['rec']} u{u} t{t}")
                if x.get("tu", 0) != j["state"]["tu"] - x.get("spent", 0):
                    out["tu_mismatch"] += 1
                f = F.get((1, u, t))
                # a clean exit: moved, untouched on the way, nobody sees it after, untouched in the player's turn
                out["clean_exit"] += bool(moved and x.get("hp_lost", 0) <= 0 and x.get("spotted", 0) == 0 and f
                                          and f.get("hp_lost", 0) <= 0 and not f.get("dead") and not f.get("down"))
                out["safe_turn"] += bool(moved and x.get("hp_lost", 0) <= 0 and f and f.get("hp_lost", 0) <= 0
                                         and not f.get("dead") and not f.get("down"))
                if f:
                    out["after"] += 1
                    out["after_hit"] += f.get("hp_lost", 0) > 0
                    out["after_hp"] += max(0, f.get("hp_lost", 0))
                    out["after_down"] += bool(f.get("dead") or f.get("down"))
                    out["after_seen"] += f.get("spotted", 0) > 0
                nxt = g.get((u, t + 1))
                if nxt is not None:
                    out["next"] += 1
                    out["next_attack"] += any(k["base"]["k"] == "a" for k in nxt)
                    xs = [X.get(k["rec"]) for k in nxt]
                    out["next_end_seen"] += bool(xs and xs[-1] and xs[-1].get("spotted", 0) > 0)
            elif note.startswith("cover.none"):
                out["none_tu" if ".tu" in note.split()[0] else "none_cell"] += 1
                out["none_seen_by"] += n.get("seen", 0)
    for (u, t), lst in g.items():
        for j in lst:
            if "cover.unseen" in j["base"]["reason"]["trail"]:
                x = X.get(j["rec"])
                if x:
                    out["unseen_exec"] += 1
                    out["unseen_but_spotted"] += x.get("spotted", 0) > 0
    return out, bad


def tac(row, key):
    for kvp in (row.get("tac") or "").split(","):
        k, _, v = kvp.partition(":")
        if k == key:
            return int(v)
    return 0


def main():
    tot = defaultdict(lambda: defaultdict(int))
    allbad = []
    print("== E vs A")
    same = 0
    for s in SC:
        sid = s[0]
        d = ea(sid)
        same += d is None
        print(f"{sid}: {'IDENTICAL' if d is None else 'DIFF ' + d}")
    print(f"identical {same}/{len(SC)}")
    print("\n== per scenario (A | B)")
    for s in SC:
        sid = s[0]
        ta, tb = table(f"{P}_A_{sid}"), table(f"{P}_B_{sid}")
        if not ta or not tb:
            print(f"{sid}: missing table")
            continue
        for arm, row in (("A", ta), ("B", tb)):
            tot[arm]["battles"] += 1
            tot[arm]["how." + row.get("how", "?")] += 1
            tot[arm]["out." + row.get("outcome", "?")] += 1
            for k in NUM:
                try:
                    tot[arm][k] += int(row.get(k) or 0)
                except ValueError:
                    pass
        for k in ("h.cover.step", "h.cover.none.tu", "h.cover.none.cell", "h.cover.unseen", "h.cover.immobile", "h.act.extra"):
            tot["B"][k] += tac(tb, k)
            tot["A"][k] += tac(ta, k)
        RA, XA, FA = recs(f"{P}_A_{sid}")
        RB, XB, FB = recs(f"{P}_B_{sid}")
        at_a, at_b = attack_turns(RA, XA, FA), attack_turns(RB, XB, FB)
        cv, bad = cover(RB, XB, FB)
        cva, _ = cover(RA, XA, FA)
        allbad += [f"{sid}: {b}" for b in bad]
        for k, v in at_a.items():
            tot["A"]["at." + k] += v
        for k, v in at_b.items():
            tot["B"]["at." + k] += v
        for k, v in cv.items():
            if k == "max_recs":
                tot["B"]["cv.max_recs"] = max(tot["B"]["cv.max_recs"], v)
            else:
                tot["B"]["cv." + k] += v
        tot["A"]["cv.max_recs"] = max(tot["A"]["cv.max_recs"], cva["max_recs"])
        tot["A"]["cv.turns_gt3"] += cva["turns_gt3"]
        print(f"{sid} {s[3]}/{s[4]}: out {ta.get('outcome')}|{tb.get('outcome')} turn {ta.get('turn')}|{tb.get('turn')}"
              f" pdead {ta.get('pdead')}|{tb.get('pdead')} phplost {ta.get('phplost')}|{tb.get('phplost')}"
              f" hdead {ta.get('hdead')}|{tb.get('hdead')} hattacks {ta.get('hattacks')}|{tb.get('hattacks')}"
              f" step {cv['step']} moved {cv['moved']} none.tu {cv['none_tu']} none.cell {cv['none_cell']}"
              f" unseen {tac(tb, 'h.cover.unseen')} how {ta.get('how')}|{tb.get('how')} sec {ta.get('seconds')}|{tb.get('seconds')}")
    print("\n== totals")
    keys = sorted(set(tot["A"]) | set(tot["B"]))
    for k in keys:
        print(f"{k}\tA={tot['A'].get(k, 0)}\tB={tot['B'].get(k, 0)}")
    print("\n== violations")
    for b in allbad:
        print(b)
    print(f"total {len(allbad)}")


main()
