"""REINFORCEMENT INTELLIGENCE V0, stage 1: every REINFORCE assignment of the CONTACT_COORDINATION logs, what could be known when it was made and what came of it (read only).
Usage: diag.py [run ...]; writes assignments.tsv and unit_turns.tsv next to itself and prints the tally."""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read, tup  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ATT = set(range(4, 21))
RUNS = ["cc8_CC_M6_s1", "cc5_CC_M6_s2", "cc6_CV_M3_s1", "cc7_CL_M3_s1", "cc1_CC_M6_s1"]
HERE = Path(__file__).parent


def d2(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def load(run):
    L = read(run)
    R = {"L": L, "dec": defaultdict(lambda: defaultdict(list)), "state": {}, "orders": defaultdict(dict), "contact": {}, "rec": {}, "exec": {}, "assign": [], "check": {}, "cas": []}
    for s in L:
        if s.startswith("[AIDECIDE]"):
            k = kv(s)
            if k["side"] == "1":
                R["dec"][int(k["turn"])][int(k["unit"])].append(k)
        elif s.startswith("[AISTATE] aistart"):
            k = kv(s)
            R["state"][(int(k["turn"]), int(k["unit"]))] = k
        elif s.startswith("[HIVECC]"):
            k = kv(s)
            e = k["event"]
            if e == "ORDER":
                R["orders"][int(k["turn"])][int(k["unit"])] = k
            elif e == "CONTACT":
                R["contact"][(int(k["turn"]), k["target"])] = k
            elif e == "ASSIGN":
                R["assign"].append(k)
            elif e == "REINFORCE_CHECK":
                R["check"][(int(k["turn"]), k["squad"], k["contact"])] = k
        elif s.startswith("[AIREC]"):
            try:
                j = json.loads(s[len("[AIREC] "):])
            except ValueError:
                continue
            R["rec"][(j["turn"], j["unit"], j["n"], j["rec"])] = j
        elif s.startswith("[AIEXEC]"):
            try:
                j = json.loads(s[len("[AIEXEC] "):])
            except ValueError:
                continue
            R["exec"][j["rec"]] = j
        elif s.startswith("[AICASUALTY]"):
            R["cas"].append(kv(s))
    return R


def spells(R, last=8):
    """One row per assignment: a change of contact under the same order counts as its own assignment, as it is a new choice."""
    open_, done = {}, []
    for k in R["assign"]:
        sq, t = k["squad"], int(k["turn"])
        if k["to"] == "REINFORCE":
            if sq in open_:
                open_[sq]["to"] = t - 1
                open_[sq]["end"] = "retarget"
                done.append(open_.pop(sq))
            open_[sq] = {"squad": sq, "from": t, "contact": k["contact"], "why": k["why"], "end": "battle_end", "to": last, "objective": k["objective"]}
        elif sq in open_:
            open_[sq]["to"] = t - 1 if int(k["turn"]) > open_[sq]["from"] else t
            open_[sq]["end"] = k["why"]
            done.append(open_.pop(sq))
    done += open_.values()
    return sorted(done, key=lambda x: (x["from"], int(x["squad"])))


def rec_of(R, turn, unit):
    return [j for (t, u, n, r), j in sorted(R["rec"].items(), key=lambda x: x[0][3]) if t == turn and u == unit]


def main():
    runs = sys.argv[1:] or RUNS
    rows, urows = [], []
    for run in runs:
        R = load(run)
        for sp in spells(R):
            t0, sq, c = sp["from"], sp["squad"], sp["contact"]
            orders0 = {u: o for u, o in R["orders"][t0].items() if o["squad"] == sq}
            kinds0 = Counter(o["kind"] for o in orders0.values())
            cpos = R["contact"].get((t0, c), {}).get("pos", "?")
            members = sorted(orders0)
            weapons, ready, shotfit = [], 0, 0
            mstates = Counter()
            for u in members:
                st = R["state"].get((t0, u), {})
                weapons.append(st.get("weapon", "?").replace("STR_", ""))
                o = orders0[u]
                shot = int(o.get("shot", 0))
                tu = int(st.get("tu", 0))
                shotfit += shot > 0 and shot <= tu
                ready += o["kind"] in ("fire", "in_place")
                ds = R["dec"][t0].get(u, [])
                mstates[("attack" if any(int(d["act"]) in ATT for d in ds) else "walk" if any(d["act"] == "2" for d in ds) else "stand" + "/".join(sorted({d["mode"] for d in ds})))] += 1
            atk_c = atk_o = dmg = first = 0
            first = None
            lost = 0
            uturns = Counter()
            for t in range(t0, sp["to"] + 1):
                for u, o in R["orders"][t].items():
                    if o["squad"] != sq or o["role"] != "REINFORCE":
                        continue
                    ds = R["dec"][t].get(u, [])
                    uturns[o["kind"]] += 1
                    st = R["state"].get((t, u), {})
                    a = sum(int(d["act"]) in ATT for d in ds)
                    fate = "attack" if a else "walk" if any(d["act"] == "2" for d in ds) else "stand"
                    recs = rec_of(R, t, u)
                    src = [(j.get("base") or {}).get("src") for j in recs]
                    odds = [((j.get("base") or {}).get("reason") or {}).get("odds") for j in recs]
                    urows.append([run, sq, t, u, o["kind"], fate, "/".join(d["mode"] for d in ds), "/".join(d["act"] for d in ds), st.get("tu", "?"), st.get("tumax", "?"), st.get("hp", "?"), st.get("morale", "?"), st.get("known", "?"), st.get("reach", "?"), st.get("weapon", "?"), o.get("cost", "-"), o.get("shot", "-"), str(src[:2]), json.dumps(odds[:1])])
                    for d in ds:
                        if int(d["act"]) in ATT:
                            if d["aim"] == c:
                                atk_c += 1
                                if first is None:
                                    first = t - t0
                            else:
                                atk_o += 1
                    for j in recs:
                        e = R["exec"].get(j["rec"])
                        if e and not e.get("walk"):
                            dmg += e.get("dmg", 0)
                    lost += sum(1 for x in R["cas"] if int(x["turn"]) == t and x.get("victim") == str(u))
            chk = R["check"].get((t0, sq, c), {})
            rows.append([run, sq, t0, sp["to"], c, cpos, sp["why"], sp["end"], chk.get("dist", "-"), chk.get("able", "-"), len(members), ",".join(sorted(set(weapons))), shotfit, ready, dict(kinds0), dict(mstates), sp["objective"], dict(uturns), atk_c, atk_o, dmg, first if first is not None else "-", lost])
    head = "run squad from to contact cpos why end dist able members weapons shot_fit ready_now kinds_t0 fate_t0 objective_left uturn_kinds atk_contact atk_other dmg first_atk_after lost".split()
    with open(HERE / "assignments.tsv", "w", encoding="utf-8-sig") as f:
        f.write("\t".join(head) + "\n")
        for r in rows:
            f.write("\t".join(str(x) for x in r) + "\n")
    with open(HERE / "unit_turns.tsv", "w", encoding="utf-8-sig") as f:
        f.write("\t".join("run squad turn unit kind fate modes acts tu tumax hp morale known reach weapon cost shot src odds".split()) + "\n")
        for r in urows:
            f.write("\t".join(str(x) for x in r) + "\n")
    print("\t".join(head))
    for r in rows:
        print("\t".join(str(x) for x in r))
    print("assignments", len(rows), "unit-turns", len(urows))


if __name__ == "__main__":
    main()
