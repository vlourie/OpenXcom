"""HIVE COMBAT INTENT V0: the gates of GATES_AND_RUN_LIST.md over the three scenarios against D0, CC and RA, turns up to 8. Read only. Run chain.py on the CI runs first (decisions_*.tsv here, the others' in ../ra).
[AIDECIDE] aim is the module's target at the end of think(), not the action's: an attack's real target is resolved from its tile: the most common aim of that tile in that turn. Checked against RESULT aim on the CI runs."""
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
RA = HERE.parent / "ra"
ATT = set(range(4, 21))
LAST = 8
TRIPLES = [
    ("M6 s1", "cc3_CO_M6_s1", "cc8_CC_M6_s1", "ra1_AN_M6_s1", "ci5_IA_M6_s1"),
    ("M6 s2", "scpa_D_M6_s2", "cc5_CC_M6_s2", "ra2_AN_M6_s2", "ci6_IA_M6_s2"),
    ("M3 s1", "scpa_D_M3_s1", "cc6_CV_M3_s1", "ra3_AV_M3_s1", "ci7_IV_M3_s1"),
]


def stream(run):
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
    return out


def resolve(D):
    tally = defaultdict(Counter)
    for d in D:
        if int(d["act"]) in ATT and d["aim"] != "-1":
            tally[(d["turn"], d["to"])][d["aim"]] += 1
    return {k: v.most_common(1)[0][0] for k, v in tally.items()}


def is_player(a):
    return a.isdigit() and int(a) < 1000000


def fight(run):
    D = stream(run)
    place = resolve(D)
    C = Counter()
    per = defaultdict(lambda: defaultdict(set))
    hurt = defaultdict(lambda: defaultdict(int))
    for d in D:
        if int(d["act"]) in ATT:
            aim = place.get((d["turn"], d["to"]), d["aim"])
            e = d["exec"] or {}
            C["attacks"] += 1
            C["attacks_dmg"] += e.get("dmg", 0) > 0
            C["dmg"] += e.get("dmg", 0)
            C["downed"] += e.get("downed", 0)
            C["ally_dmg"] += e.get("fdmg", 0)
            per[d["turn"]][aim].add(d["unit"])
            hurt[d["turn"]][aim] += e.get("dmg", 0)
        if d["act"] == "2":
            e = d["exec"] or {}
            C["walks"] += 1
            C["walks_empty"] += e.get("spent", 1) == 0
        if d["mode"] == "3":
            C["mode3"] += 1
    for t, a in per.items():
        for aim, who in a.items():
            if len(who) >= 2 and is_player(aim):
                C["joint_targets"] += 1
                C["joint_fighters"] += len(who)
                C["joint_with_dmg"] += hurt[t][aim] > 0
                C["joint_dmg"] += hurt[t][aim]
    by = defaultdict(list)
    for d in D:
        by[(d["turn"], d["unit"])].append(d)
    C["unit_turns"] = len(by)
    for ds in by.values():
        attacked = any(int(d["act"]) in ATT for d in ds)
        moved = any(d["act"] == "2" and (d["exec"] or {}).get("spent", 0) > 0 for d in ds)
        C["ut_attacked"] += attacked
        C["ut_moved"] += moved
        if not attacked and not moved:
            C["ut_nothing"] += 1
            C["ut_nothing_tu"] += int(ds[0]["tu"])
        C["tu_left_at_stand"] += int(ds[-1]["tu"]) if ds[-1]["act"] == "0" else 0
    return D, C, place


def losses(run):
    L = read(run)
    out = {"ai": defaultdict(int), "pl": defaultdict(int)}
    res = ""
    last_turn = 0
    for s in L:
        if s.startswith("[AICASUALTY]"):
            k = kv(s)
            t = int(k["turn"])
            if t > LAST:
                continue
            if k.get("vfaction") == "1":
                out["ai"][t] += 1
            elif k.get("vfaction") == "0" or is_player(k.get("victim", "x")):
                out["pl"][t] += 1
        elif s.startswith("[AIRESULT]"):
            k = kv(s)
            res = {x: k.get(x) for x in ("turn", "hostile", "hdead", "hout", "hleft", "player", "pdead", "pout", "pleft", "livealiens", "result") if x in k}
        elif s.startswith("[AIDECIDE]"):
            last_turn = max(last_turn, int(kv(s)["turn"]))
    return out, res, last_turn


def tsv_gates(run, D):
    d = HERE if run.startswith("ci") else RA
    rows = list(csv.DictReader(open(d / f"decisions_{run}.tsv", encoding="utf-8-sig"), delimiter="\t"))
    if len(rows) != len(D):
        return {"rows": len(rows), "decisions": len(D)}
    G = Counter()
    for x, r in zip(D, rows):
        a = x["ans"]["answer"] if x["ans"] else ""
        rolled = r["rolled"]
        G["art_escape_stand"] += a == "STAND" and x["mode"] == "3" and rolled not in ("3", "-")
        G["free_mode3_fallback"] += a == "FREE" and x["mode"] == "3" and rolled not in ("3", "-")
        G["rolled3"] += rolled == "3"
        G["rolled3_kept"] += rolled == "3" and x["mode"] == "3"
        G["stand_mode0_walk"] += a == "STAND" and x["mode"] == "0" and x["act"] == "2"
        G["free_held_stand"] += a == "FREE" and r["cls"] == "held_patrol_stand"
    return dict(G)


def starts(run):
    early = set()
    for s in read(run):
        if s.startswith("[AISTATE]"):
            k = kv(s)
            if k.get("faction") == "1" and int(k.get("turn", 99)) <= 1:
                early.add(k["unit"])
    return early


def tu_ok(run):
    C = Counter()
    for s in read(run):
        if s.startswith("[AISTATE]"):
            k = kv(s)
            if k.get("faction") == "1":
                C["lines"] += 1
                C["above_tumax"] += int(k["tu"]) > int(k["tumax"])
        elif s.startswith("[HIVESAVECHECK]"):
            k = kv(s)
            C["savecheck"] += 1
            C["savecheck_bad"] += k.get("parsed") != "1" or k.get("same") != "1"
        elif "Exception" in s or "FATAL" in s or ("CRASH" in s and "STR_UFO_CRASH_RECOVERY" not in s):
            C["bad_lines"] += 1
    return dict(C)


def intent(run, place):
    L = read(run)
    C = Counter()
    effect = defaultdict(lambda: [0, 0, 0])
    atk_contact = Counter()
    sites = Counter()
    for s in L:
        if not s.startswith("[HIVEINTENT]"):
            continue
        k = kv(s)
        ev = k["event"]
        if ev == "CHOICE":
            sites[k["no"] if k["no"] != "-" else ("takes" if k["changed"] == "1" else "would")] += 1
        elif ev == "RESULT":
            C[k["kind"]] += 1
            if k["kind"] == "ATTACKED_CONTACT":
                x = effect["changed" if k["changed"] == "1" else "own_choice"]
            elif k["kind"] == "OTHER_ATTACK":
                x = effect["other"]
            else:
                continue
            x[0] += 1
            x[1] += int(k["hit"])
            x[2] += int(k["hp_lost"])
    return dict(C), {a: b for a, b in effect.items()}, dict(sites.most_common())


def check_aim(run, D, place):
    """the resolved target against the RESULT aim of the same attacks, in order."""
    res = [kv(s) for s in read(run) if s.startswith("[HIVEINTENT] event=RESULT") and int(kv(s)["act"]) in ATT and int(kv(s)["turn"]) <= LAST]
    want = [(d["turn"], d["unit"], place.get((d["turn"], d["to"]), d["aim"]), d["aim"]) for d in D if int(d["act"]) in ATT]
    resk = Counter((r["turn"], r["unit"], r["aim"]) for r in res)
    ok_res = sum(1 for w in want if resk[(w[0], w[1], w[2])] > 0)
    ok_raw = sum(1 for w in want if resk[(w[0], w[1], w[3])] > 0)
    return f"attacks {len(want)}, RESULT lines {len(res)}, resolved target agrees {ok_res}, raw aim agrees {ok_raw}"


for name, d0, cc, ra, ci in TRIPLES:
    print("=====", name)
    base = None
    for run in (d0, cc, ra, ci):
        D, C, place = fight(run)
        lo, res, t = losses(run)
        print(run, "last turn", t, "result", res)
        print("   ", {x: C[x] for x in ("unit_turns", "attacks", "attacks_dmg", "dmg", "downed", "ally_dmg", "joint_targets", "joint_fighters", "joint_with_dmg", "joint_dmg", "ut_attacked", "ut_moved", "ut_nothing", "ut_nothing_tu", "tu_left_at_stand", "walks", "walks_empty", "mode3")})
        print("    losses by turn: AI", dict(sorted(lo["ai"].items())), "players", dict(sorted(lo["pl"].items())), "totals", sum(lo["ai"].values()), sum(lo["pl"].values()))
        print("    gates", tsv_gates(run, D), "ok", tu_ok(run))
        s = starts(run)
        if base is None:
            base = s
        print("    start list: units", len(s), "only here", sorted(s - base)[:10], "only in D0", sorted(base - s)[:10])
        if run == ci:
            print("    aim check:", check_aim(run, D, place))
            a, b, c = intent(run, place)
            print("    result kinds", a)
            print("    attacks, hits, hp lost:", b)
            print("    choices", c)
