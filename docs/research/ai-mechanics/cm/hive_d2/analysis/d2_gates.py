"""HIVE D2 CORRECTION, read only: the same measures as V0, gates T6, T9, F1-F8 and the measures of the GO, ON against OFF and shadow on the frozen build, turns 1..8. Writes gates.txt, decisions_<run>.tsv next to this file.
Usage: ua_gates.py"""
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

HERE = Path(__file__).parent
ATT = set(range(4, 21))
LAST = 8
SC = [("M6 s1", "d25_DO_M6_s1", "us5_QS_M6_s1", "d26_DN_M6_s1", "ra1_AN_M6_s1"), ("M3 s1", "d21_DO_M3_s1", "d22_DS_M3_s1", "d23_DN_M3_s1", None)]
TAGS = ("[AIDECIDE]", "[AIEXEC]", "[AISTATE]", "[AICASUALTY]", "[AIREC]", "[AIPANIC]", "[AIAFTER]", "[AIPOSTWALK]", "[AIEVENT]")
TIMING = re.compile(r" (?:\w*us|\w*ms|\w*_ns|t|ms)=[-0-9.]+")
CFG = re.compile(r'"cfg":"[0-9a-f]+",')
out = open(HERE / "gates.txt", "w", encoding="utf-8-sig")


def p(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    out.write(s + "\n")


sys.stdout.reconfigure(encoding="utf-8")


def stream(run):
    """Every decision of the AI side up to LAST, with its record's dice and its execution."""
    D = []
    recs = {}
    last = None
    for s in read(run):
        if s.startswith("[AIDECIDE]"):
            k = kv(s)
            last = None
            if k["side"] == "1" and int(k["turn"]) <= LAST:
                last = dict(k, rolled="-", ex=None)
                D.append(last)
        elif s.startswith("[AIREC]") and last is not None and "rec" not in last:
            try:
                j = json.loads(s[8:])
            except ValueError:
                continue
            last["rec"] = j["rec"]
            recs[j["rec"]] = last
            odds = (((j.get("base") or {}).get("reason") or {}).get("odds")) or []
            if odds:
                last["rolled"] = str(odds[-1].get("mode"))
            last["src"] = (j.get("base") or {}).get("src", "")
        elif s.startswith("[AIEXEC]"):
            try:
                j = json.loads(s[9:])
            except ValueError:
                continue
            if j["rec"] in recs:
                recs[j["rec"]]["ex"] = j
    return D


def measures(run):
    D = stream(run)
    M = Counter()
    by = defaultdict(list)
    seq = defaultdict(list)
    for d in D:
        a = int(d["act"])
        ex = d["ex"] or {}
        M["decisions"] += 1
        M["mode" + d["mode"]] += 1
        M["walk"] += a == 2
        M["attack"] += a in ATT
        M["attack_dmg"] += a in ATT and ex.get("dmg", 0) > 0
        M["dmg"] += ex.get("dmg", 0)
        M["downed"] += ex.get("downed", 0)
        M["fdmg"] += ex.get("fdmg", 0)
        M["fdowned"] += ex.get("fdowned", 0)
        M["rolled3"] += d["rolled"] == "3"
        M["rolled3_kept"] += d["rolled"] == "3" and d["mode"] == "3"
        M["mode3_not_rolled"] += d["mode"] == "3" and d["rolled"] != "3"
        M["empty_walk"] += a == 2 and ex.get("spent", 1) == 0
        M["spent"] += ex.get("spent", 0)
        if ex.get("seen", 0) > 0:
            M["seen_dec"] += 1
            M["seen_combat"] += d["mode"] == "2"
            M["seen_escape"] += d["mode"] == "3"
            M["seen_patrol"] += d["mode"] == "0"
            M["seen_attack"] += a in ATT
        by[(int(d["turn"]), d["unit"])].append(d)
        seq[d["unit"]].append(d["mode"])
    for k, ds in by.items():
        M["unit_turns"] += 1
        attacked = any(int(d["act"]) in ATT for d in ds)
        moved = any(d["act"] == "2" and (d["ex"] or {}).get("spent", 0) > 0 for d in ds)
        M["ut_attacked"] += attacked
        M["ut_moved"] += moved
        M["ut_nothing"] += not attacked and not moved
        if ds[-1]["act"] == "0":
            M["idle_tu"] += int(ds[-1]["tu"])
    for u, ms in seq.items():
        for a, b in zip(ms, ms[1:]):
            M["p_to_c"] += a == "0" and b == "2"
            M["c_to_p"] += a == "2" and b == "0"
            M["to_esc"] += a != "3" and b == "3"
    # who fell, once each
    lost = defaultdict(set)
    bturn = Counter()
    for s in read(run):
        if s.startswith("[AICASUALTY]"):
            k = kv(s)
            if int(k.get("turn", 0)) <= LAST:
                lost[k.get("vfaction")].add(k.get("victim"))
                if k.get("vfaction") == "1":
                    bturn[int(k["turn"])] += 0
    M["lost_hostile"] = len(lost["1"])
    M["lost_player"] = len(lost["0"])
    M["lost_civil"] = len(lost["2"])
    return M, D


def events(run):
    ev = defaultdict(list)
    for s in read(run):
        if s.startswith("[HIVEUA]"):
            k = kv(s)
            ev[k["event"]].append(k)
    return ev


def first_point(off, on):
    """The first differing journal line, and what the headquarters had just done in the ON run."""
    a = [(CFG.sub("", TIMING.sub("", s))) for s in read(off) if s.startswith(TAGS)]
    L = read(on)
    b = []
    for i, s in enumerate(L):
        if s.startswith(TAGS):
            b.append((CFG.sub("", TIMING.sub("", s)), i))
    for n, (x, (y, i)) in enumerate(zip(a, b)):
        if x != y:
            p(f"  first difference at journal line {n} of {min(len(a), len(b))}")
            p("   OFF", x[:190])
            p("   ON ", y[:190])
            prev = [s for s in L[max(0, i - 60):i] if s.startswith("[HIVEUA]") and ("event=CHOICE" in s or "event=KEPT_DROP" in s)]
            for s in prev[-3:]:
                p("   HQ ", s[:250])
            return n
    p("  no difference")
    return None


def feedback(run, ev):
    """RESULT against the engine's own [AIEXEC] spent, unit-turn by unit-turn; commanders changed and what became of their task."""
    D = stream(run)
    sp = Counter()
    for d in D:
        sp[(d["turn"], d["unit"])] += (d["ex"] or {}).get("spent", 0)
    eq = bad = 0
    for k in ev["RESULT"]:
        if int(k["turn"]) > LAST:
            continue
        if sp[(k["turn"], k["unit"])] == int(k["spent"]):
            eq += 1
        else:
            bad += 1
    p(f"  F6 RESULT spent = [AIEXEC] spent: {eq} equal, {bad} differ")
    area = {}
    lines = read(run)
    kept = lost = 0
    ch = []
    for s in lines:
        if s.startswith("[HIVEUA] event=REVIEW"):
            k = kv(s)
            if k["squad"] in area and area[k["squad"]][0] == "wait":
                was = area[k["squad"]][1]
                if was == k["area"].split(":")[0]:
                    kept += 1
                else:
                    lost += 1
                ch.append((k["squad"], was, k["area"]))
            area[k["squad"]] = ("had", k["area"].split(":")[0])
        elif s.startswith("[HIVECMD]"):
            k = kv(s)
            if k.get("new", "-1") != "-1" and k["squad"] in area:
                area[k["squad"]] = ("wait", area[k["squad"]][1])
    cmd = [kv(s) for s in lines if s.startswith("[HIVECMD]")]
    p(f"  F6 commanders changed {sum(c.get('new') != '-1' for c in cmd)}, all down {sum(c.get('new') == '-1' for c in cmd)}; task kind the same at the next review {kept}, other {lost}; merges {sum('merged=' in s for s in lines if s.startswith('[HIVESQUAD]'))}")


def inplace(ev):
    t = defaultdict(lambda: [0, 0])
    for k in ev["SQUADTURN"]:
        if int(k["turn"]) <= LAST:
            t[k["kind"]][0] += int(k["inside"])
            t[k["kind"]][1] += int(k["alive"])
    return {k: f"{v[0]}/{v[1]}={100 * v[0] // max(1, v[1])}%" for k, v in sorted(t.items())}


def visited(ev):
    v = {}
    for k in ev["SQUADTURN"]:
        if int(k["turn"]) <= LAST:
            v[int(k["turn"])] = k["visited"]
    return v


def plan(run):
    v = [int(kv(s)["us"]) for s in read(run) if s.startswith("[HIVEPERF]") and "phase=plan" in s]
    f = [int(kv(s)["floodUs"]) for s in read(run) if s.startswith("[HIVEPERF]") and "phase=turn" in s]
    return v, f


rows = []
for name, off, sh, on, ra in SC:
    p("=====", name, "OFF", off, "SHADOW", sh, "ON", on)
    evo = events(on)
    evs = events(sh)
    init = [s for s in read(on) if s.startswith("[HIVEINIT]")][0]
    k = kv(init)
    p(f"  F1 hostile {k['hostile']} managed {k['managed']} apart {k['apart']} squads {k['squads']} sectors {k['sectors']}; org {dict(Counter(x['area'].split(':')[0] for x in evo['ORG']))}")
    by = defaultdict(Counter)
    for x in evo["SQUADTURN"]:
        by[int(x["turn"])][x["kind"]] += 1
    full = [t for t, c in by.items() if len(c) == 3 and t <= LAST]
    p(f"  F2 turns with all three kinds at once: {sorted(full)}; by turn { {t: dict(c) for t, c in sorted(by.items())} }")
    wr = [x for x in evo["RESULT"] if x["changed"] == "1" and int(x["turn"]) <= LAST]
    good = [x for x in wr if x["moved"] == "1" and (x["inside"] == "1" or x["closer"] == "1")]
    p(f"  F3 unit-turns walking on a changed node {len(wr)}, of them moved and ending inside or closer {len(good)}, squads {len({x['squad'] for x in good})}, by kind {dict(Counter(x['kind'] for x in good))}")
    ch = [x for x in evo["CHOICE"] if int(x["turn"]) <= LAST]
    t1 = [x for x in ch if x["try"] == "1"]
    p(f"  choices {len(ch)}, first tries {len(t1)}: changed {sum(x['changed'] == '1' for x in t1)}, nothing fits {sum(x['fallback'] == '1' for x in t1)}; chosen inside {sum(x['inside'] == '1' for x in t1)} against free inside {sum(x['free_inside'] == '1' for x in t1)}; KEPT_DROP {len(evo['KEPT_DROP'])} KEPT_BACK {len(evo['KEPT_BACK'])}")
    dw = [x for x in evo["DECIDED"] if x["changed"] == "1" and int(x["turn"]) <= LAST]
    p(f"  walk decisions on a changed node {len(dw)}")
    p("  in place at turn's end, shadow (free soldiers, same rules of tasks):", inplace(evs))
    p("  in place at turn's end, ON:", inplace(evo))
    p("  nodes visited by turn, shadow:", visited(evs))
    p("  nodes visited by turn, ON:    ", visited(evo))
    Mo, _ = measures(off)
    Mn, Dn = measures(on)
    keys = ["decisions", "unit_turns", "mode0", "mode1", "mode2", "mode3", "walk", "attack", "attack_dmg", "dmg", "downed", "fdmg", "fdowned", "ut_attacked", "ut_moved", "ut_nothing", "idle_tu", "empty_walk", "spent", "rolled3", "rolled3_kept", "mode3_not_rolled", "seen_dec", "seen_combat", "seen_escape", "seen_patrol", "seen_attack", "p_to_c", "c_to_p", "to_esc", "lost_hostile", "lost_player", "lost_civil"]
    p("  measure: OFF -> ON")
    for key in keys:
        p(f"    {key}: {Mo[key]} -> {Mn[key]}")
        rows.append((name, key, Mo[key], Mn[key]))
    p("  T6")
    first_point(off, on)
    feedback(on, evo)
    p("  F5 returns:")
    for x in evo["RETURN"]:
        after = [y for y in evo["RESULT"] if y["squad"] == x["squad"] and int(y["turn"]) > int(x["turn"]) and y["changed"] == "1"]
        again = [y for y in evo["OBJECTIVE"] if y["squad"] == x["squad"] and int(y["turn"]) >= int(x["turn"])]
        p(f"    turn {x['turn']} squad {x['squad']} {x['from']} contact {x['contact']} since {x['since']} -> {x['task']} {x['objective']}; then walking on the task: {len(after)} unit-turns, {sum(y['closer'] == '1' or y['inside'] == '1' for y in after)} inside or closer; objective events {[(y['turn'], y['to'], y['why']) for y in again]}")
    v, f = plan(on)
    rv = plan(ra)[0] if ra else []
    p(f"  T9 plan us ON max {max(v) if v else None} sum {sum(v)}; flood us per side's turn max {max(f) if f else None} sum {sum(f)}; RA plan us max {max(rv) if rv else None} sum {sum(rv)}")
    p("  T7 lines with crash words:", sum(any(w in s for w in ("Segmentation", "FATAL", "assert")) for s in read(on)))
with open(HERE / "measures.tsv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f, delimiter="\t")
    w.writerow(["scen", "measure", "OFF", "ON"])
    w.writerows(rows)
out.close()
