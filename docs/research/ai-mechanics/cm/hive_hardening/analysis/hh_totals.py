"""HIVE hardening: the report's tables from the journals (read only). Usage: hh_totals.py <hive/res/out>"""
import gzip
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
kv = re.compile(r"(\w+)=([^ ]*)")
out = Path(sys.argv[1])
RUNS = ["hh3_JA_M6_s1", "hh4_JA_M6_s2", "hh5_JA_M6_s2", "hh6_JV_M3_s1", "hh7_HL_M3_s1", "hh8_HL_M3_s1"]
V0 = ["hv6_HA_M6_s1", "hv8_HA_M6_s2", "hv9_HA_L6_s1", "hv10_HA_L6_s2", "hv11_HA_L7_s1"]


def read(n):
    with gzip.open(out / n / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        return [ln.rstrip("\n").split("\t")[-1] for ln in f]


print("run | GO | closed | ARRIVED walked | ARRIVED no step | closer | not closer | not moved | open | BLOCKED | repeats same conditions | same unit+target | locked STAY | no_closer STAY | HOLD STAY | why")
for n in RUNS:
    L = read(n)
    go = {}
    stay = Counter()
    for s in L:
        if s.startswith("[HIVEORD]") and "state=CREATED" in s:
            k = dict(kv.findall(s))
            if k["kind"] == "GO":
                go[k["id"]] = k
            else:
                stay[k["why"]] += 1
    fate = [dict(kv.findall(s)) for s in L if s.startswith("[HIVEFATE]")]
    c = Counter(k["fate"] for k in fate)
    blocked = [dict(kv.findall(s)) for s in L if s.startswith("[HIVEORD]") and "state=BLOCKED" in s]
    tiles = [re.search(r"tiles=(\d+)", s).group(1) if "tiles=" in s else "-" for s in L if s.startswith("[HIVEORD]") and "state=BLOCKED" in s]
    same = Counter((b["unit"], b["target"], b["at"], t) for b, t in zip(blocked, tiles))
    pair = Counter((b["unit"], b["target"]) for b in blocked)
    walked = sum(k["fate"] == "ARRIVED" and k["decided_walk"] == "1" for k in fate)
    print(n, len(go), len(fate), c["ARRIVED"], f"(by its walk order {walked})", c["ARRIVED_NO_STEP"], c["MOVED_CLOSER"], c["MOVED_NOT_CLOSER"], c["NOT_MOVED"], len(go) - len(fate), len(blocked),
          sum(v for v in same.values() if v > 1), sum(v for v in pair.values() if v > 1), stay["locked"], stay["no_closer_node"] + stay["post_too_far"], stay["guard_sector"] + stay["nothing_known"] + stay["nothing_reachable"], Counter(k["why"] for k in go.values()).most_common())
    print("   reasons", Counter(k["reason"] for k in fate).most_common())
print()
print("V0 refusals etc by battle")
for n in V0:
    L = read(n)
    st = {}
    first = {}
    for s in L:
        if s.startswith("[HIVEORD]") and "kind=GO" in s and "state=" in s:
            k = dict(kv.findall(s))
            st.setdefault(k["id"], []).append(k["state"])
            first.setdefault(k["id"], k)
    print(n, "GO", len(st), "last BLOCKED", sum(v[-1] == "BLOCKED" for v in st.values()), "COMPLETED", sum(v[-1] == "COMPLETED" for v in st.values()))
print()
print("HOLD: every stretch by squad, what ended it")
for n in RUNS:
    L = read(n)
    print(n)
    print("  results", Counter(dict(kv.findall(s))["result"] for s in L if s.startswith("[HIVEREVIEW]")).most_common())
    print("  hold lines", Counter((dict(kv.findall(s))["event"], dict(kv.findall(s))["why"], dict(kv.findall(s))["from"]) for s in L if s.startswith("[HIVEHOLD]")).most_common())
    rows = defaultdict(list)
    for s in L:
        if s.startswith("[HIVEREVIEW]"):
            k = dict(kv.findall(s))
            if k["task"] == "HOLD" or k["result"].startswith(("exit", "no_task")):
                rows[k["squad"]].append((k["turn"], k["shots"], k["reactions"], k["hurt"], k["saw"], k["idle"], k["result"]))
    for q, r in sorted(rows.items(), key=lambda e: int(e[0])):
        print("   squad", q, " ".join(f"t{t}:{a}/{b}/{c}/{d}i{e}{'' if f == 'stay' else ':' + f}" for t, a, b, c, d, e, f in r))
    idle = [dict(kv.findall(s)) for s in L if s.startswith("[HIVEREVIEW]") and " shots=0 reactions=0 hurt=0 saw=0 " in s]
    print("  reviews with nothing", len(idle), "of", sum(s.startswith("[HIVEREVIEW]") for s in L), Counter(k["task"] for k in idle).most_common())
print()
print("what fell and who took over, final build")
for n in RUNS[1:4]:
    L = read(n)
    cmd = [dict(kv.findall(s)) for s in L if s.startswith("[HIVECMD]")]
    print(n, "changes", len(cmd), "new commander", sum(c["new"] != "-1" for c in cmd), "squad finished", sum(c["new"] == "-1" for c in cmd), "kept", sum(c["kept"] == "1" for c in cmd))
    print("  perf plan max us", max(int(dict(kv.findall(s))["us"]) for s in L if s.startswith("[HIVEPERF]")), "sum us", sum(int(dict(kv.findall(s))["us"]) for s in L if s.startswith("[HIVEPERF]")), "flood us", sum(int(dict(kv.findall(s))["floodUs"]) for s in L if s.startswith("[HIVEPERF]")), "floods", sum(int(dict(kv.findall(s))["floods"]) for s in L if s.startswith("[HIVEPERF]")))
print()
print("task 5, M6 s2 (run 4): squads 0 and 3")
L = read("hh4_JA_M6_s2")
for s in L:
    if s.startswith(("[HIVEHOLD]", "[HIVETASK]", "[HIVECMD]", "[HIVEREVIEW]", "[HIVESQUADTURN]")) or s.startswith("[HIVESQUAD] id="):
        k = dict(kv.findall(s))
        if (k.get("squad") or k.get("id")) in ("0", "3") and int(k.get("turn", 0)) <= 7:
            print("  ", s[:230])
print("  fates of squads 0 and 3 up to turn 7")
for s in L:
    if s.startswith("[HIVEFATE]"):
        k = dict(kv.findall(s))
        if k["squad"] in ("0", "3") and int(k["turn"]) <= 7:
            print("  ", k["turn"], "squad", k["squad"], "unit", k["unit"], k["task"], k["fate"], k["reason"], k["why"], k["start"], "->", k["end"], "target", k["target"], "path", k["path_tu"], "gain", k["gain"])
print("  merged", [s[12:80] for s in L if s.startswith("[HIVESQUAD] turn=") and "merged" in s])
