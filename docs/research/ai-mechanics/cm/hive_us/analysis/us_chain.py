"""UNIFIED ARMY SAFETY, read only: why the guards could walk in ON and not in OFF (who stood on their nodes, on whose node he left); idle unit-turns, unit by unit, against OFF; the thinks where the condition's node took the free tries; to-and-fro walks; repeats of fields. Writes chain.txt next to this file. Usage: us_chain.py"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
sys.path.insert(0, str(Path(__file__).parent.parent / "ua"))
from lib import kv, read  # noqa: E402

HERE = Path(__file__).parent
NONE = "(-1,-1,-1)"
ATT = set(range(4, 21))
LAST = 8
out = open(HERE / "chain.txt", "w", encoding="utf-8-sig")
sys.stdout.reconfigure(encoding="utf-8")


def p(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    out.write(s + "\n")


def decisions(run):
    D = []
    recs = {}
    for s in read(run):
        if s.startswith("[AIDECIDE]"):
            k = kv(s)
            if k["side"] == "1" and int(k["turn"]) <= LAST:
                k["ex"] = None
                D.append(k)
                cur = k
            else:
                cur = None
        elif s.startswith("[AIEXEC]"):
            try:
                j = json.loads(s[9:])
            except ValueError:
                continue
            for d in reversed(D[-3:]):
                if str(j.get("unit")) == d["unit"] and d["ex"] is None:
                    d["ex"] = j
                    break
    return D


p("===== place of the unit at each decision: nodes the guards were after")
N = {"(8,23,1)": "1000038 wants", "(6,19,2)": "1000021 wants", "(8,21,2)": "1000039 wants"}
for run in ("us4_QO_M6_s1", "us1_QN_M6_s1"):
    D = decisions(run)
    for node, what in N.items():
        by = defaultdict(set)
        for d in D:
            if d["from"] == node:
                by[int(d["turn"])].add(d["unit"])
        p(run, node, what, {t: sorted(u) for t, u in sorted(by.items())})

p("===== ON us1: the first walks off those nodes; whose node")
L = read("us1_QN_M6_s1")
last = {}
for s in L:
    if s.startswith("[HIVEUA] event=CHOICE"):
        k = kv(s)
        last[k["unit"]] = k
    elif s.startswith("[AIDECIDE]"):
        k = kv(s)
        if k["from"] in N and k["act"] == "2" and k["side"] == "1" and int(k["turn"]) <= 3 and k["unit"] not in ("1000021", "1000038", "1000039"):
            c = last.get(k["unit"], {})
            p(" t", k["turn"], k["unit"], "mode", k["mode"], k["from"], "->", k["to"], "free", c.get("free"), "chosen", c.get("chosen"), "scout", c.get("scout"), "kind", c.get("kind"), "squad", c.get("squad"), "changed", c.get("changed"))
p("===== OFF us4: those same units, by turn")
Do = decisions("us4_QO_M6_s1")
for u in ("1000031", "1000015"):
    p(u, [(d["turn"], d["from"], "m" + d["mode"], "a" + d["act"], d["to"]) for d in Do if d["unit"] == u][:12])
Dn = decisions("us1_QN_M6_s1")
for u in ("1000031", "1000015"):
    p(u, "ON", [(d["turn"], d["from"], "m" + d["mode"], "a" + d["act"], d["to"]) for d in Dn if d["unit"] == u][:12])

p("===== who idles: a unit-turn with no attack and nothing spent")
for name, off, v0, on in (("M6", "us4_QO_M6_s1", "ua1_UN_M6_s1", "us1_QN_M6_s1"), ("M3", "ua6_UO_M3_s1", "ua2_UN_M3_s1", "us2_QN_M3_s1"), ("M8", "ua8_UO_M8_s1", "ua3_UN_M8_s1", "us3_QN_M8_s1")):
    res = {}
    for label, run in (("OFF", off), ("V0", v0), ("ON", on)):
        by = defaultdict(list)
        for d in decisions(run):
            by[(int(d["turn"]), d["unit"])].append(d)
        idle = Counter()
        tus = Counter()
        for (t, u), ds in by.items():
            att = any(int(d["act"]) in ATT for d in ds)
            mv = any(d["act"] == "2" and (d["ex"] or {}).get("spent", 0) > 0 for d in ds)
            if not att and not mv:
                idle[u] += 1
                tus[u] += int(ds[-1]["tu"])
        res[label] = (idle, tus, len(by), max(t for t, u in by))
        p(name, label, run, "unit-turns", len(by), "last turn", res[label][3], "idle", sum(idle.values()), dict(idle), "by turn up to 5:", sum(n for u, n in idle.items()) if False else "")
    new = set(res["ON"][0]) - set(res["OFF"][0])
    p("  idle in ON and not in OFF:", sorted(new))
    L = read(on)
    for u in sorted(new)[:6]:
        ch = [kv(s) for s in L if s.startswith("[HIVEUA] event=CHOICE") and f" unit={u} " in s]
        ds = [d for d in decisions(on) if d["unit"] == u]
        by = defaultdict(list)
        for d in ds:
            by[int(d["turn"])].append((d["from"], "m" + d["mode"], "a" + d["act"]))
        p("  ", u, "scout", dict(Counter(c["scout"] for c in ch)), "chosen", sum(c["chosen"] != NONE for c in ch), "of", len(ch), "paths of decisions", dict(list(by.items())[:3]))
        p("      OFF", [(d["turn"], d["from"], "m" + d["mode"], "a" + d["act"]) for d in decisions(off) if d["unit"] == u][:6])

p("===== the thinks where the first three tries went to the condition's node, the path failed, all five failed")
for run in ("us2_QN_M3_s1",):
    L = read(run)
    seq = []
    cur = None
    for s in L:
        if s.startswith("[HIVEUA] event=CHOICE"):
            k = kv(s)
            if k["try"] == "1" or cur is None or cur[-1]["unit"] != k["unit"] or int(k["try"]) <= int(cur[-1]["try"]):
                cur = []
                seq.append(cur)
            cur.append(k)
    for q in seq:
        if len(q) == 5 and any(c["chosen"] != NONE for c in q):
            p(run, "t", q[0]["turn"], q[0]["unit"], "kind", q[0]["kind"], "at", q[0]["at"], "scout", q[0]["scout"], "tries", [(c["chosen"], c["free"]) for c in q])

p("===== to and fro: a patrol walk back to where the same unit walked from, in that turn")
for run in ("us4_QO_M6_s1", "ua1_UN_M6_s1", "us1_QN_M6_s1", "ua6_UO_M3_s1", "ua2_UN_M3_s1", "us2_QN_M3_s1", "ua8_UO_M8_s1", "ua3_UN_M8_s1", "us3_QN_M8_s1"):
    D = decisions(run)
    prev = {}
    tf = Counter()
    pw = 0
    for d in D:
        if d["act"] != "2" or d["mode"] != "0":
            continue
        pw += 1
        u = d["unit"]
        if u in prev and prev[u][0] == d["turn"] and prev[u][2] == d["from"] and prev[u][1] == d["to"]:
            tf[u] += 1
        prev[u] = (d["turn"], d["from"], d["to"])
    p(run, "patrol walks", pw, "back again", sum(tf.values()), "units", len(tf), "most", tf.most_common(3))

p("===== fields: on all the turns, repeats of a unit within its turn; tiles")
for run in ("ua1_UN_M6_s1", "us1_QN_M6_s1", "ua2_UN_M3_s1", "us2_QN_M3_s1", "ua3_UN_M8_s1", "us3_QN_M8_s1"):
    per = Counter()
    tiles = []
    for s in read(run):
        if s.startswith("[HIVEREACH]"):
            k = kv(s)
            per[(k["turn"], k["unit"])] += 1
            tiles.append(int(k["tiles"]))
    tiles.sort()
    p(run, "fields", sum(per.values()), "unit-turns with a field", len(per), "repeats", sum(per.values()) - len(per), "tiles median", tiles[len(tiles) // 2] if tiles else None, "max", tiles[-1] if tiles else None)

p("===== scout=1 on M3: what gives it (fromNode rank); by scenario")
for run in ("us1_QN_M6_s1", "us2_QN_M3_s1", "us3_QN_M8_s1"):
    ch = [kv(s) for s in read(run) if s.startswith("[HIVEUA] event=CHOICE")]
    p(run, Counter((c["scout"], c["from_rank"]) for c in ch).most_common(8), "cheating lines", sum("cheating" in s.lower() for s in read(run)))

p("===== RESULT spent differs on M8, which")
L = read("us3_QN_M8_s1")
sp = Counter()
for d in decisions("us3_QN_M8_s1"):
    sp[(d["turn"], d["unit"])] += (d["ex"] or {}).get("spent", 0)
di = [kv(s) for s in L if s.startswith("[HIVEUA] event=RESULT")]
di = [(k["turn"], k["unit"], k["spent"], sp[(k["turn"], k["unit"])]) for k in di if int(k["turn"]) <= LAST and sp[(k["turn"], k["unit"])] != int(k["spent"])]
p("differ", len(di), di[:10])
out.close()
