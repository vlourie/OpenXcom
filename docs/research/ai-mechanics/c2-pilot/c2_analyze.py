"""C2 PREATTACK_COVER functional pilot (18 battles): E vs A identity, B = A up to the first C2 decision, the work of C2
in B by its tags (c2.*), and the tactics against the base.  usage: c2_analyze.py <dir> <scen.tsv> <ids comma> [prefix]

E vs A: every stream compared line by line (rec, decide, cand, tiles, path, casualties), the table without seconds,
[AIRESULT] without ms/vms.
B = A: [AIREC] compared on (turn, side, unit, n, k, to, pos, tu, rng hash); the first mismatch must be at or after the
first rec where C2 changed the action (c2.plan.move or c2.exit) - the other c2 tags only write the trail.
C2 in B (per tag, from the notes the code writes):
  move  - c2.plan.move: the walk carried out to the planned cell (exec pos == to), hp lost on the way, the next think of
          the same unit-turn arrived (c2.arrived) and attacked with a shot that spent TU (c2.confirm in its exec);
  exit  - c2.exit: TU before it below the shot of the turn's plan, spent == cost + stand (unless reaction fire stopped
          the walk), hp lost on the way, nobody spots it after, the player's turn after (hit, downed);
  base  - arm A, hostile attack unit-turns ending in view: hit / downed in the player's turn after (as for C1).
Loops: the most recs a hostile unit-turn has, A against B; max n; h.act.extra.
"""
import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
D = Path(sys.argv[1])
IDS = sys.argv[3].split(",")
P = sys.argv[4] if len(sys.argv) > 4 else "c2"
SC = {l.split("\t")[0]: l.split("\t") for l in Path(sys.argv[2]).read_text(encoding="utf-8-sig").splitlines()[1:] if l.strip()}
STREAMS = (".rec.gz", ".decide.gz", ".cand.gz", ".tiles.gz", ".path.gz", ".casualties.txt")
NUM = ("turn", "pdead", "pout", "pwounded", "phplost", "hostile", "hdead", "hout", "hleft", "pattacks", "hattacks",
       "hdecisions", "seconds")
SHOTS = ("BA_SNAPSHOT", "BA_AUTOSHOT", "BA_AIMEDSHOT")


def lines(p):
    if not p.exists():
        return None
    op = gzip.open if p.suffix == ".gz" else open
    with op(p, "rt", encoding="utf-8-sig") as f:
        return f.read().splitlines()


def table(label):
    t = lines(D / f"{label}.tsv")
    if not t or len(t) < 2:
        return None
    return dict(zip(t[0].split("\t"), t[1].split("\t")))


def result(label):
    return [re.sub(r" (ms|vms)=\d+", "", l) for l in lines(D / f"{label}.result.txt") or [] if "[AIRESULT]" in l]


def ea(sid):
    e, a = f"{P}_E_{sid}", f"{P}_A_{sid}"
    te, ta = table(e), table(a)
    if te is None or ta is None:
        return "no table"
    for k in te:
        if k != "seconds" and te.get(k) != ta.get(k):
            return f"table {k}: E={te.get(k)} A={ta.get(k)}"
    if result(e) != result(a):
        return "AIRESULT differs"
    n = 0
    for s in STREAMS:
        le, la = lines(D / (e + s)), lines(D / (a + s))
        if le is None and la is None:
            continue
        if le is None or la is None:
            return f"{s}: only one arm has it"
        if le != la:
            i = next((i for i, (x, y) in enumerate(zip(le, la)) if x != y), min(len(le), len(la)))
            return f"{s} line {i}"
        n += len(le)
    return None, n


def load(label):
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


def trail(j):
    return j["base"]["reason"]["trail"]


def note(j, head):
    return next((s for s in reversed(trail(j)) if s.startswith(head + " ")), None)


def kv(s):
    return {k: int(v) for k, v in re.findall(r"(\w+)=(-?\d+)", s or "")}


def key(j):
    s, b = j["state"], j["base"]
    return (j["turn"], j["side"], j["unit"], j["n"], b["k"], tuple(b["to"]), tuple(s["pos"]), s["tu"], s["h"]["r"])


def groups(R):
    g = defaultdict(list)
    for r in sorted(R):
        if R[r]["side"] == 1:
            g[(R[r]["unit"], R[r]["turn"])].append(R[r])
    return g


def tac(row, k):
    for p in (row.get("tac") or "").split(","):
        a, _, v = p.partition(":")
        if a == k:
            return int(v)
    return 0


def after(c, pre, f):
    if not f:
        return
    c[pre + "after"] += 1
    c[pre + "hit"] += f.get("hp_lost", 0) > 0
    c[pre + "hp"] += max(0, f.get("hp_lost", 0))
    c[pre + "down"] += bool(f.get("dead") or f.get("down"))


def base(c, pre, R, X, F):
    """Hostile attack unit-turns that ended in view, the player's turn after (the C1 base)."""
    for (u, t), lst in groups(R).items():
        if not any(j["base"]["k"] == "a" for j in lst):
            continue
        c[pre + "attack_turns"] += 1
        x = X.get(lst[-1]["rec"], {})
        if x.get("down") or x.get("spotted", 0) == 0:
            continue
        after(c, pre, F.get((1, u, t)))


def main():
    tot = Counter()
    odd = []
    print("== E vs A")
    for sid in IDS:
        d = ea(sid)
        ok = isinstance(d, tuple)
        tot["ea_identical"] += ok
        print(f"{sid}: {'IDENTICAL (' + str(d[1]) + ' lines)' if ok else 'DIFF ' + str(d)}")
    print("\n== per scenario: A | B")
    for sid in IDS:
        ta, tb = table(f"{P}_A_{sid}"), table(f"{P}_B_{sid}")
        if not ta or not tb:
            print(f"{sid}: missing table")
            continue
        RA, XA, FA = load(f"{P}_A_{sid}")
        RB, XB, FB = load(f"{P}_B_{sid}")
        for arm, row in (("A", ta), ("B", tb)):
            tot[arm + ".battles"] += 1
            tot[arm + ".how." + row.get("how", "?")] += 1
            tot[arm + ".out." + row.get("outcome", "?")] += 1
            tot[arm + ".act.extra"] += tac(row, "h.act.extra")
            for k in NUM:
                try:
                    tot[arm + "." + k] += int(row.get(k) or 0)
                except ValueError:
                    pass
        # B = A up to the first C2 decision that changes an action
        first = next((j for r, j in sorted(RB.items()) if note(j, "c2.plan.move") or note(j, "c2.exit")), None)
        ra, rb = [RA[r] for r in sorted(RA)], [RB[r] for r in sorted(RB)]
        div = next((b for a, b in zip(ra, rb) if key(a) != key(b)), None)
        if div is None and len(ra) != len(rb):
            div = rb[min(len(ra), len(rb))] if len(rb) > len(ra) else {"rec": len(rb)}
        same = div is None or (first is not None and div["rec"] >= first["rec"])
        tot["ba_same_until_c2"] += same
        tot["ba_battles"] += 1
        if not same:
            odd.append(f"{sid}: B differs from A at rec {div['rec']} before the first C2 action (rec {first['rec'] if first else '-'})")
        # loops
        for arm, R in (("A", RA), ("B", RB)):
            g = groups(R)
            tot[arm + ".max_recs"] = max(tot[arm + ".max_recs"], max((len(v) for v in g.values()), default=0))
            tot[arm + ".max_n"] = max(tot[arm + ".max_n"], max((j["n"] for j in R.values() if j["side"] == 1), default=0))
        base(tot, "baseA.", RA, XA, FA)
        base(tot, "baseB.", RB, XB, FB)
        # every c2 tag
        for j in RB.values():
            for s in trail(j):
                if s.startswith("c2."):
                    tot["tag." + s.split()[0]] += 1
        for x in XB.values():
            for s in x.get("trail", []):
                if s.startswith("c2."):
                    tot["xtag." + s.split()[0]] += 1
        g = groups(RB)
        for (u, t), lst in g.items():
            plan = None
            for i, j in enumerate(lst):
                x = XB.get(j["rec"], {})
                for head in ("c2.plan.here", "c2.plan.fp", "c2.plan.move"):
                    if note(j, head):
                        plan = (head, kv(note(j, head)), note(j, head))
                pm = note(j, "c2.plan.move")
                if pm:
                    n = kv(pm)
                    seen = re.search(r"seen=(\d+)>(\d+)", pm)
                    tot["move"] += 1
                    tot["move_lof_before"] += int(seen.group(1))
                    tot["move_lof_after"] += int(seen.group(2))
                    tot["move_lof_fewer"] += int(seen.group(2)) < int(seen.group(1))
                    tot["move_dist_sum"] += n.get("dist", 0)
                    if j["base"]["k"] != "m":
                        odd.append(f"{sid} rec {j['rec']}: c2.plan.move but k={j['base']['k']}")
                    if not x:
                        tot["move_noexec"] += 1
                        continue
                    reached = list(x["pos"]) == list(j["base"]["to"])
                    tot["move_reached"] += reached
                    tot["move_reaction_stop"] += any(s.startswith("walk.stop.reaction") for s in x.get("trail", []))
                    tot["move_hit"] += x.get("hp_lost", 0) > 0
                    tot["move_hp"] += max(0, x.get("hp_lost", 0))
                    tot["move_down"] += bool(x.get("down"))
                    nxt = lst[i + 1] if i + 1 < len(lst) else None
                    if nxt is None:
                        tot["move_no_next_think"] += 1
                        odd.append(f"{sid} rec {j['rec']} u{u} t{t}: walked to F (reached {reached}, down {x.get('down')}), no next think")
                        continue
                    nx = XB.get(nxt["rec"], {})
                    tot["move_next_arrived"] += "c2.arrived" in trail(nxt)
                    shot = nxt["base"]["k"] == "a" and nx.get("spent", 0) > 0
                    tot["move_then_shot"] += shot
                    tot["move_then_confirm"] += "c2.confirm" in nx.get("trail", [])
                    if not shot:
                        odd.append(f"{sid} rec {nxt['rec']} u{u} t{t}: after the move k={nxt['base']['k']} spent={nx.get('spent')}"
                                   f" reached={reached} trail={[s for s in trail(nxt) if s.startswith('c2.')]}")
                ex = note(j, "c2.exit")
                if ex:
                    n = kv(ex)
                    tot["exit"] += 1
                    tot["exit_dist_sum"] += n.get("dist", 0)
                    if plan:
                        tot["exit_after_" + plan[0]] += 1
                        if j["state"]["tu"] >= plan[1].get("shot", 0):
                            tot["exit_tu_buys_shot"] += 1
                            odd.append(f"{sid} rec {j['rec']}: exit with tu {j['state']['tu']} >= shot {plan[1].get('shot')}")
                    else:
                        tot["exit_without_plan"] += 1
                    if j["base"]["k"] != "m":
                        odd.append(f"{sid} rec {j['rec']}: c2.exit but k={j['base']['k']}")
                    if j["n"] > 2:
                        tot["exit_n_gt2"] += 1
                    if not x:
                        tot["exit_noexec"] += 1
                        continue
                    moved = list(x["pos"]) != list(j["state"]["pos"])
                    stopped = any(s.startswith("walk.stop.") for s in x.get("trail", []))
                    want = n.get("cost", 0) + n.get("stand", 0)
                    tot["exit_moved"] += moved
                    tot["exit_reached"] += list(x["pos"]) == list(j["base"]["to"])
                    tot["exit_stopped"] += stopped
                    if x.get("spent", 0) != want and not stopped:
                        tot["exit_spent_bad"] += 1
                        odd.append(f"{sid} rec {j['rec']}: exit spent {x.get('spent')} != cost {n.get('cost')} + stand {n.get('stand')}")
                    tot["exit_spent_eq"] += x.get("spent", 0) == want
                    tot["exit_hit"] += x.get("hp_lost", 0) > 0
                    tot["exit_hp"] += max(0, x.get("hp_lost", 0))
                    tot["exit_down"] += bool(x.get("down"))
                    tot["exit_unspotted"] += x.get("spotted", 0) == 0
                    f = FB.get((1, u, t))
                    tot["exit_clean"] += bool(moved and x.get("hp_lost", 0) <= 0 and x.get("spotted", 0) == 0 and f
                                              and f.get("hp_lost", 0) <= 0 and not f.get("dead") and not f.get("down"))
                    after(tot, "exitF.", f)
                if note(j, "c2.noexit"):
                    tot["noexit_seen_sum"] += kv(note(j, "c2.noexit")).get("seen", 0)
                if "c2.lost.attack" in trail(j):
                    tot["lost_attack"] += 1
                    odd.append(f"{sid} rec {j['rec']} u{u} t{t}: lost attack {note(j, 'c2.lost.attack')} k={j['base']['k']}")
        print(f"{sid} {SC[sid][3]}/{SC[sid][4]}: out {ta.get('outcome')}|{tb.get('outcome')} turn {ta.get('turn')}|{tb.get('turn')}"
              f" pdead {ta.get('pdead')}|{tb.get('pdead')} phplost {ta.get('phplost')}|{tb.get('phplost')}"
              f" hdead {ta.get('hdead')}|{tb.get('hdead')} hattacks {ta.get('hattacks')}|{tb.get('hattacks')}"
              f" how {ta.get('how')}|{tb.get('how')} sec {ta.get('seconds')}|{tb.get('seconds')}"
              f" | first C2 action rec {first['rec'] if first else '-'} first B!=A rec {div['rec'] if div else '-'}")
    print("\n== totals")
    for k in sorted(tot):
        print(f"{k}\t{tot[k]}")
    print("\n== to look at")
    for o in odd:
        print(o)
    print(f"total {len(odd)}")


main()
