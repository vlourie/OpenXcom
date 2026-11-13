"""RESTORE COMBAT AUTONOMY: the gates of GATES_AND_RUN_LIST.md over the three pairs, from the journals. Read only. Run chain.py on all runs first.
Usage: ra_final.py"""
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
ATT = set(range(4, 21))
PAIRS = [("M6 s1", "cc3_CO_M6_s1", "cc8_CC_M6_s1", "ra1_AN_M6_s1"), ("M6 s2", "scpa_D_M6_s2", "cc5_CC_M6_s2", "ra2_AN_M6_s2"), ("M3 s1", "scpa_D_M3_s1", "cc6_CV_M3_s1", "ra3_AV_M3_s1")]
LAST = 8


def stream(run):
    """Every decision of the AI side in the log's order, with the answer, the record, the execution and chain.py's row."""
    answer = {}
    out = []
    last = None
    recs = {}
    for s in read(run):
        if s.startswith("[HIVECC] event=AUTONOMY"):
            k = kv(s)
            answer[k["unit"]] = k
        elif s.startswith("[AIDECIDE]"):
            k = kv(s)
            last = None
            if k["side"] == "1" and int(k["turn"]) <= LAST:
                last = dict(k, ans=answer.pop(k["unit"], None), exec=None, rec=None)
                out.append(last)
        elif s.startswith("[AIREC]") and last is not None and last["rec"] is None:
            try:
                j = json.loads(s[8:])
            except ValueError:
                continue
            last["rec"] = j
            recs[j["rec"]] = last
        elif s.startswith("[AIEXEC]"):
            try:
                j = json.loads(s[9:])
            except ValueError:
                continue
            if j["rec"] in recs:
                recs[j["rec"]]["exec"] = j
    rows = list(csv.DictReader(open(HERE / f"decisions_{run}.tsv", encoding="utf-8-sig"), delimiter="\t"))
    if len(rows) != len(out):
        raise SystemExit(f"{run}: rows {len(rows)} decisions {len(out)}")
    for d, r in zip(out, rows):
        d["row"] = r
    return out


def gates(run):
    D = stream(run)
    G = Counter()
    for d in D:
        a = d["ans"]["answer"] if d["ans"] else ""
        cls = d["row"]["cls"]
        act = int(d["act"])
        rolled = d["row"]["rolled"]
        G["F1_stand_art_escape"] += a == "STAND" and d["mode"] == "3" and rolled not in ("3", "-")
        G["F2_rolled_escape"] += rolled == "3"
        G["F2_rolled_escape_kept"] += rolled == "3" and d["mode"] == "3"
        G["free_mode3_fallback"] += a == "FREE" and d["mode"] == "3" and rolled not in ("3", "-")
        G["F3_stand_mode0_walk"] += a == "STAND" and d["mode"] == "0" and act == 2
        G["stand_stood_mode0"] += a == "STAND" and d["mode"] == "0" and act == 0
        G["F3_free_held_stand"] += a == "FREE" and cls == "held_patrol_stand"
        G["stand_combat_walk"] += a == "STAND" and d["mode"] == "2" and act == 2
        G["stand_attack"] += a == "STAND" and act in ATT
        G["stand_esc_dice"] += a == "STAND" and cls.startswith("esc_dice")
        G["stand_esc_kept"] += a == "STAND" and cls.startswith("esc_kept")
    return D, G


def units(D):
    """What each unit-turn with an answer came to."""
    by = defaultdict(list)
    for d in D:
        by[(int(d["turn"]), d["unit"])].append(d)
    C = Counter()
    for (t, u), ds in by.items():
        ans = [d["ans"]["answer"] for d in ds if d["ans"]]
        if not ans:
            C["no_answer_ut"] += 1
            continue
        kind = "FREE" if "FREE" in ans else "STAND"
        C[kind + "_ut"] += 1
        spent = sum((d["exec"] or {}).get("spent", 0) for d in ds)
        moved = any(d["act"] == "2" and (d["exec"] or {}).get("spent", 0) > 0 for d in ds)
        attacked = any(int(d["act"]) in ATT for d in ds)
        after = [d for d in ds if d["ans"]]
        late = any(d["act"] != "0" and (d["exec"] or {}).get("spent", 0) > 0 for d in after)
        C[kind + "_attacked"] += attacked
        C[kind + "_moved"] += moved
        C[kind + "_acted_after_answer"] += late
        C[kind + "_nothing"] += not attacked and not moved
        C[kind + "_tu_spent"] += spent
        C[kind + "_end_tu_idle"] += int(ds[-1]["tu"]) if ds[-1]["act"] == "0" else 0
    return C


def org(run):
    L = read(run)
    S = [s for s in L if s.startswith("[HIVESQUAD]") and "members=" in s]
    T = [kv(s) for s in L if s.startswith("[HIVETASK]")]
    A = [kv(s) for s in L if s.startswith("[HIVECC] event=ASSIGN")]
    O = Counter()
    for s in L:
        if s.startswith("[HIVEORD]"):
            k = kv(s)
            if k.get("state") == "CREATED":
                O[k.get("task", "") + ":" + k.get("kind", "")] += 1
    cmd = [kv(s)["commander"] for s in S]
    return dict(squads=len(S), sq_lines=S, tasks=len(T), kinds=dict(Counter(k.get("kind") for k in T)), assigns=dict(Counter(k["to"] for k in A)), orders=dict(O), commanders=len(set(cmd)))


def stability(run):
    L = read(run)
    c = Counter()
    for s in L:
        if s.startswith("[HIVESAVECHECK]"):
            k = kv(s)
            c["savecheck"] += 1
            c["savecheck_bad"] += k.get("parsed") != "1" or k.get("same") != "1"
        elif s.startswith("[HIVESAVE]"):
            c["hivesave"] += 1
        elif "Exception" in s or "FATAL" in s or ("CRASH" in s and "STR_UFO_CRASH_RECOVERY" not in s):
            c["bad_lines"] += 1
    return dict(c)


def tu_check(D):
    """TU of a unit's first decision of a turn against the most it ever had in the journal's state lines."""
    C = Counter()
    by = defaultdict(list)
    for d in D:
        by[(int(d["turn"]), d["unit"])].append(int(d["tu"]))
        st = (d["rec"] or {}).get("state") or {}
        if "tumax" in st and int(d["tu"]) > st["tumax"]:
            C["above_tumax"] += 1
        C["has_tumax"] += "tumax" in st
    for v in by.values():
        C["rises"] += sum(b > a for a, b in zip(v, v[1:]))
    return dict(C)


def causal(run, unit, turn):
    """Attacks, damage and steps of one unit around the first causal point."""
    out = {}
    for d in stream(run):
        t = int(d["turn"])
        if d["unit"] == unit and turn <= t <= turn + 1:
            x = out.setdefault(t, Counter())
            x["attacks"] += int(d["act"]) in ATT
            e = d["exec"] or {}
            x["dmg"] += e.get("dmg", 0)
            x["esc"] += d["mode"] == "3"
            x["steps_tu"] += e.get("spent", 0) if d["act"] == "2" else 0
    return {k: dict(v) for k, v in out.items()}


def main():
    for name, d0, cc, ra in PAIRS:
        print("=====", name)
        for run in (d0, cc, ra):
            D, G = gates(run)
            print(" ", run, dict((k, v) for k, v in sorted(G.items())))
            print("    units", dict(sorted(units(D).items())))
            print("    tu", tu_check(D), "stability", stability(run))
        a, b = org(cc), org(ra)
        print("  org CC", {k: v for k, v in a.items() if k != "sq_lines"})
        print("  org RA", {k: v for k, v in b.items() if k != "sq_lines"})
        print("  organization lines the same:", a["sq_lines"] == b["sq_lines"])
    print("===== causal units")
    print(" M6 s1 1000003", causal("cc8_CC_M6_s1", "1000003", 1), causal("ra1_AN_M6_s1", "1000003", 1))
    print(" M6 s1 1000007", causal("cc8_CC_M6_s1", "1000007", 1), causal("ra1_AN_M6_s1", "1000007", 1))
    print(" M6 s2 1000000", causal("cc5_CC_M6_s2", "1000000", 1), causal("ra2_AN_M6_s2", "1000000", 1))
    print(" M3 s1 1000006", causal("cc6_CV_M3_s1", "1000006", 1), causal("ra3_AV_M3_s1", "1000006", 1))


main()
