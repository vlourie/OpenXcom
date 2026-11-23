"""HIVE hardening: one journal against the conditions (read only). Usage: hh_eval.py <out dir> [--chain]"""
import gzip
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
kv = re.compile(r"(\w+)=([^ ]*)")
chain = "--chain" in sys.argv
d = Path(sys.argv[1])
with gzip.open(d / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
    lines = [ln.rstrip("\n").split("\t")[-1] for ln in f]


def tag(t):
    return [(i, dict(kv.findall(s))) for i, s in enumerate(lines) if s.startswith(t)]


print("==", d.name, "lines", len(lines))
errs = [s for s in lines if "[ERROR]" in s or "[FATAL]" in s or "Exception" in s or s.startswith("[HIVELOAD] parsed=0")]
print("errors", len(errs), [e[:140] for e in errs[:4]])
inits = tag("[HIVEINIT]")
print("inits", [(k.get("origin"), "turn", k.get("turn"), "side", k.get("side"), "squads", k.get("squads"), "managed", k.get("managed"), "us", k.get("us")) for _, k in inits])
firstTask = next((i for i, s in enumerate(lines) if s.startswith("[HIVEORD]")), None)
print("first order line", firstTask, "init line", inits[0][0] if inits else None)
for _, k in tag("[HIVEFIRST]"):
    print("first plan", k)
for s in lines:
    if s.startswith("[HIVESQUAD] id="):
        print("  ", s[:210])

# double assignment
member = Counter()
for s in lines:
    if s.startswith("[HIVESQUAD] id="):
        for m in re.findall(r"(\d+)[MSLA]", dict(kv.findall(s))["members"]):
            member[m] += 1
print("double assigned", [m for m, c in member.items() if c > 1])

# the orders
fate = tag("[HIVEFATE]")
c = Counter(k["fate"] for _, k in fate)
print("GO closed", len(fate), dict(c))
print("  by reason", Counter(k["fate"] + ":" + k["reason"] for _, k in fate).most_common(14))
created = {}
state = {}
for _, k in tag("[HIVEORD]"):
    if "id" in k and "kind" in k:
        o = created.setdefault(k["id"], {"kind": k["kind"], "unit": k["unit"], "target": k["target"], "why": k["why"], "turn": k["turn"], "at": k["at"]})
        o["state"] = k["state"]
go = {i: o for i, o in created.items() if o["kind"] == "GO"}
stay = {i: o for i, o in created.items() if o["kind"] == "STAY"}
closed = {k["id"] for _, k in fate}
print("GO orders", len(go), "open at the end", len([i for i in go if i not in closed]), "STAY", len(stay))
print("  GO why", Counter(o["why"] for o in go.values()).most_common(), " STAY why", Counter(o["why"] for o in stay.values()).most_common())
ex = 0
for _, k in tag("[HIVEFATE]"):
    ex += k["decided_walk"] == "1"
print("decided to walk (closed)", ex)

# refused
blocked = []
for s in lines:
    if s.startswith("[HIVEORD]") and "state=BLOCKED" in s:
        k = dict(kv.findall(s))
        blocked.append((k["unit"], k["target"], k["at"], k.get("note", ""), re.search(r"tiles=(\d+)", s).group(1) if "tiles=" in s else "-", k["turn"]))
print("BLOCKED", len(blocked), Counter(b[3] for b in blocked).most_common(5))
same = Counter((b[0], b[1], b[2], b[4]) for b in blocked)
print("same unit+target+at+tiles repeated", sum(v for v in same.values() if v > 1), [k for k, v in same.items() if v > 1][:5])
pair = Counter((b[0], b[1]) for b in blocked)
print("same unit+target at all", sum(v for v in pair.values() if v > 1))

# holds and tasks
print("HIVEHOLD", Counter((k["event"], k["why"], k.get("from")) for _, k in tag("[HIVEHOLD]")).most_common())
rev = tag("[HIVEREVIEW]")
print("reviews", len(rev), Counter(k["result"] for _, k in rev).most_common())
turns = defaultdict(dict)
for _, k in tag("[HIVESQUADTURN]"):
    turns[int(k["turn"])][k["squad"]] = (k["task"], k["hold"], k["objective"], k["alive"], k["tuPct"], k["shots"], k["saw"])
run = defaultdict(int)
mx = defaultdict(int)
for t in sorted(turns):
    for q, v in turns[t].items():
        run[q] = run[q] + 1 if v[0] == "HOLD" else 0
        mx[q] = max(mx[q], run[q])
print("longest HOLD run by squad", dict(mx))
for t in sorted(turns):
    print("  t", t, " ".join(f"{q}:{v[0][0]}{'/' + v[1] if v[0] == 'HOLD' else ''}{v[2] if v[0] != 'HOLD' else ''} a{v[3]} tu{v[4]} sh{v[5]} saw{v[6]}" for q, v in sorted(turns[t].items(), key=lambda e: int(e[0]))))
print("commanders", [(k["turn"], k["squad"], k["old"], k["new"], k["why"], k["task"]) for _, k in tag("[HIVECMD]")])
print("merged", [s[12:90] for s in lines if s.startswith("[HIVESQUAD] turn=") and "merged" in s])
print("task lines", Counter(k.get("state") or ("to=" + k["to"] if "to" in k else "new") for _, k in tag("[HIVETASK]")))
print("reactions", len(tag("[HIVEREACT]")))
sc = tag("[HIVESAVECHECK]")
print("savecheck", len(sc), "parsed", sum(k["parsed"] == "1" for _, k in sc), "same", sum(k["same"] == "1" for _, k in sc), "maxbytes", max([int(k["bytes"]) for _, k in sc] or [0]), "maxus", max([int(k["us"]) for _, k in sc] or [0]))
print("save", [(k["turn"], k["side"], k["hash"], k["bytes"]) for _, k in tag("[HIVESAVE]")], "load", [(k.get("parsed"), k.get("same"), k.get("hash"), k.get("mid_side_turn")) for _, k in tag("[HIVELOAD]")])
perf = tag("[HIVEPERF]")
print("plan us", [int(k["us"]) for _, k in perf], "floods", [int(k["floods"]) for _, k in perf])
tt = tag("[HIVETURN]")
print("thinks", [int(k["thinks"]) for _, k in tt], "thinkUs", [int(k["thinkUs"]) for _, k in tt], "alive", [int(k["alive"]) for _, k in tt])
print("fair lines", len(tag("[HIVEFAIR]")), "reach lines", len(tag("[HIVEREACH]")))
print("capped", Counter(k["capped"] for _, k in tag("[HIVEREACH]")), "min tiles", min([int(k["tiles"]) for _, k in tag("[HIVEREACH]")] or [0]))
if chain:
    for s in lines:
        if s.startswith(("[HIVETASK]", "[HIVEHOLD]", "[HIVECMD]", "[HIVEREVIEW]")):
            print("   ", s[:200])
