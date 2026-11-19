"""UNIFIED ARMY SAFETY, read only: the three guards walk by walk and on whose node; who stood on their nodes; fall-backs the condition turns into a patrol; free tries lost to the condition; time by parts on one measure. Writes more.txt next to this file. Usage: us_more.py"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read, victims  # noqa: E402

HERE = Path(__file__).parent
NONE = "(-1,-1,-1)"
out = open(HERE / "more.txt", "w", encoding="utf-8-sig")
sys.stdout.reconfigure(encoding="utf-8")


def p(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    out.write(s + "\n")


G = ("1000021", "1000038", "1000039")
p("===== the guards: OFF us4, V0 ON ua1, ON us1")
for run in ("us4_QO_M6_s1", "ua1_UN_M6_s1", "us1_QN_M6_s1"):
    L = read(run)
    v = victims(L)
    for u in G:
        d = [kv(s) for s in L if s.startswith("[AIDECIDE]") and f" unit={u} " in s]
        ex = {}
        for s in L:
            if s.startswith("[AIEXEC]"):
                j = json.loads(s[9:])
                if str(j.get("unit")) == u:
                    ex[j["rec"]] = j
        spent = sum(j.get("spent", 0) for j in ex.values())
        dmg = sum(j.get("dmg", 0) for j in ex.values())
        att = sum(4 <= int(x["act"]) <= 20 for x in d)
        turns = sorted({int(x["turn"]) for x in d})
        p(run, u, "decisions", len(d), "turns", turns[0] if turns else "-", "..", turns[-1] if turns else "-", "places", len({x["from"] for x in d}), "modes", dict(Counter(x["mode"] for x in d)), "attacks", att, "dmg", dmg, "spent", spent, "fell", any(u in str(w) for w in v.get("1", ())))

p("===== ON us1: each patrol walk of the guards against the choice just before it")
L = read("us1_QN_M6_s1")
last = {}
for s in L:
    if s.startswith("[HIVEUA] event=CHOICE"):
        k = kv(s)
        if k["unit"] in G:
            last[k["unit"]] = k
    elif s.startswith("[AIDECIDE]"):
        k = kv(s)
        if k["unit"] in G and k["act"] == "2":
            c = last.get(k["unit"], {})
            who = "kept" if not c or c.get("turn") != k["turn"] else ("chosen" if k["to"] == c.get("chosen") else "free" if k["to"] == c.get("free") else "other")
            p(k["unit"], "t", k["turn"], "mode", k["mode"], k["from"], "->", k["to"], "node of:", who, "scout", c.get("scout"), "from", c.get("from"), "free", c.get("free"), "fl", c.get("free_linked"), "chosen", c.get("chosen"), "cl", c.get("chosen_linked"), "try", c.get("try"))

p("===== who stands on what the guards were after, by turn (first decision of each unit at that place)")
want = {"(8,23,1)", "(8,15,1)", "(8,18,1)", "(6,19,2)", "(8,21,2)", "(10,19,2)", "(7,17,2)"}
for run in ("us4_QO_M6_s1", "us1_QN_M6_s1"):
    seen = defaultdict(set)
    for s in read(run):
        if s.startswith("[AIDECIDE]"):
            k = kv(s)
            if k["from"] in want and k["side"] == "1" and int(k["turn"]) <= 4:
                seen[(int(k["turn"]), k["from"])].add(k["unit"])
    p(run, {f"t{t} {w}": sorted(u) for (t, w), u in sorted(seen.items())})

p("===== the choices of one think: all tries failed, and what the condition had; fall-back to the mode's own course")
for run in ("us5_QS_M6_s1", "us1_QN_M6_s1", "us2_QN_M3_s1", "us3_QN_M8_s1"):
    seq = []
    cur = None
    for s in read(run):
        if s.startswith("[HIVEUA] event=CHOICE"):
            k = kv(s)
            if k["try"] == "0" or k["try"] == "1" or cur is None or cur[-1]["unit"] != k["unit"] or int(k["try"]) <= int(cur[-1]["try"]):
                cur = []
                seq.append(cur)
            cur.append(k)
    full = [q for q in seq if len(q) == 5]
    had = [q for q in full if any(c["chosen"] != NONE for c in q)]
    only_free_short = [q for q in full if any(c["chosen"] != NONE for c in q[:3])]
    p(run, "thinks with a choice", len(seq), "all five tried", len(full), "of them with a node from the condition", len(had), "by scout", dict(Counter(q[0]["scout"] for q in had)), "first tries with no path by length", dict(Counter(len(q) for q in seq)))
    # shadow: the condition's node exists where the free node's five paths failed: what active would turn into a patrol
    # active: free search had only tries 4 and 5 after the condition's own node failed
    lost = sum(all(c["chosen"] != NONE for c in q[:3]) for q in full)
    p("   five tried and all three first on the condition's node:", lost)
    p("   length of the sequences where try 1 is the condition's:", dict(Counter(len(q) for q in seq if q[0]["chosen"] != NONE)), "free's:", dict(Counter(len(q) for q in seq if q[0]["chosen"] == NONE)))

p("===== time: one measure on all the builds; per side's turn; ms")
for run in ("ra1_AN_M6_s1", "ra2_AN_M6_s2", "ua1_UN_M6_s1", "ua10_UN_M6_s1", "us1_QN_M6_s1", "us6_QN_M6_s1", "us5_QS_M6_s1", "ua2_UN_M3_s1", "us2_QN_M3_s1", "ua3_UN_M8_s1", "us3_QN_M8_s1"):
    L = read(run)
    plan = [int(kv(s)["us"]) for s in L if s.startswith("[HIVEPERF]") and "phase=plan" in s]
    planflood = [kv(s).get("floodUs") for s in L if s.startswith("[HIVEPERF]") and "phase=plan" in s]
    rows = [kv(s) for s in L if s.startswith("[HIVEPERF]") and "phase=turn" in s]
    res = [kv(s) for s in L if s.startswith("[AIRESULT]")]
    p(run, "plan", [round(x / 1000, 1) for x in plan], "floods", [int(r.get("floods", 0)) for r in rows], "floodMs", [round(int(r.get("floodUs", 0)) / 1000) for r in rows], "battle ms", res[-1].get("ms") if res else "-", "planflood", planflood[:2])

p("===== time by parts, us1 and us2, us3")
for run in ("us1_QN_M6_s1", "us6_QN_M6_s1", "us2_QN_M3_s1", "us3_QN_M8_s1"):
    L = read(run)
    plan = [kv(s) for s in L if s.startswith("[HIVEPERF]") and "phase=plan" in s]
    rows = [kv(s) for s in L if s.startswith("[HIVEPERF]") and "phase=turn" in s]
    p(run)
    for i, r in enumerate(rows):
        P = int(plan[i]["us"]) if i < len(plan) else 0
        F = int(r["floodUs"])
        IF = int(r["intentFloodUs"])
        pf = int(r["floods"]) - int(r["intentFloods"])
        pfl = max(0, F - IF)
        T = int(r["thinkUs"])
        hive = T + IF + int(r["stepsUs"])
        p(f"  t{r['turn']} total_hq {hive / 1000:.1f} | plan {P / 1000:.1f}: fields {pf} {pfl / 1000:.1f}, areas {max(0, P - pfl) / 1000:.2f} | update without plan {max(0, T - P) / 1000:.2f} | fields on the choice {r['intentFloods']} {IF / 1000:.1f} | max field {int(r['maxFloodUs']) / 1000:.1f} | free search {r['searches']} {int(r['freeUs']) / 1000:.2f} | steps {int(r['stepsUs']) / 1000:.2f} | max choice {int(r['maxChoiceUs']) / 1000:.2f} | the engine's paths {r['paths']} fails {r['pathFails']} {int(r['pathUs']) / 1000:.1f}")
    # how many of the fields are repeats of the same unit in that turn
    per = defaultdict(Counter)
    tiles = []
    for s in L:
        if s.startswith("[HIVEREACH]"):
            k = kv(s)
            per[k.get("turn")][k.get("unit")] += 1
            tiles.append(int(k.get("tiles", 0)))
    p("  fields per turn, distinct units:", {t: (sum(c.values()), len(c), max(c.values())) for t, c in sorted(per.items(), key=lambda x: int(x[0]))}, "tiles max", max(tiles) if tiles else None)
out.close()
