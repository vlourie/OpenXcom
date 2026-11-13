"""UNIFIED ARMY CONTROL V0, read only: the remaining open points. Empty walks on the headquarters' node or not, escape without a rolled 3, RESULT against [AIEXEC] where they differ, unit-turns with nothing spent, what each task's soldiers did, time units never negative. Writes last.txt next to this file.
Usage: ua_last.py"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
LAST = 8
ATT = set(range(4, 21))
SC = [("M6 s1", "ua4_UO_M6_s1", "ua1_UN_M6_s1"), ("M3 s1", "ua6_UO_M3_s1", "ua2_UN_M3_s1"), ("M8 s1", "ua8_UO_M8_s1", "ua3_UN_M8_s1")]
out = open(HERE / "last.txt", "w", encoding="utf-8-sig")


def p(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    out.write(s + "\n")


def stream(run):
    D = []
    recs = {}
    last = None
    for s in read(run):
        if s.startswith("[AIDECIDE]"):
            k = kv(s)
            last = None
            if k["side"] == "1" and int(k["turn"]) <= LAST:
                last = dict(k, ex=None, rec=None, rolled="-", src="")
                D.append(last)
        elif s.startswith("[AIREC]") and last is not None and last["rec"] is None:
            try:
                j = json.loads(s[8:])
            except ValueError:
                continue
            last["rec"] = j["rec"]
            recs[j["rec"]] = last
            b = j.get("base") or {}
            odds = (b.get("reason") or {}).get("odds") or []
            if odds:
                last["rolled"] = str(odds[-1].get("mode"))
            last["src"] = b.get("src", "")
        elif s.startswith("[AIEXEC]"):
            try:
                j = json.loads(s[9:])
            except ValueError:
                continue
            if j["rec"] in recs:
                recs[j["rec"]]["ex"] = j
    return D


def share(a, b):
    return f"{a}/{b}={100 * a // max(1, b)}%"


for name, off, on in SC:
    p("=====", name)
    for run in (off, on):
        D = stream(run)
        neg = sum(int(d["tu"]) < 0 for d in D)
        e = [d for d in D if d["act"] == "2" and d["ex"] and d["ex"].get("spent", 1) == 0]
        tus = sorted(int(d["tu"]) for d in e)
        w = [d for d in D if d["act"] == "2"]
        wt = sorted(int(d["tu"]) for d in w)
        after = Counter()
        by = defaultdict(list)
        for d in D:
            by[(d["turn"], d["unit"])].append(d)
        for ds in by.values():
            had = any(int(d["act"]) in ATT for d in ds)
            for d in ds:
                if d in e:
                    after["after_attack" if had else "no_attack"] += 1
        p(f"  {run}: negative tu {neg}; empty walks {share(len(e), len(w))} of walks; median tu of empties {tus[len(tus) // 2] if tus else 0}, of all walks {wt[len(wt) // 2] if wt else 0}; soldier attacked that turn {dict(after)}")
        m3 = [d for d in D if d["mode"] == "3" and d["rolled"] != "3"]
        p(f"    escape without a rolled 3: {len(m3)}, rolled {dict(Counter(d['rolled'] for d in m3))}, src {dict(Counter(d['src'] for d in m3))}, acts {dict(Counter(d['act'] for d in m3))}")
        rolled = Counter(d["rolled"] for d in D)
        p(f"    rolled {dict(rolled)}; final mode for each roll {dict(Counter((d['rolled'], d['mode']) for d in D if d['rolled'] != '-'))}")
    L = read(on)
    ev = defaultdict(list)
    for s in L:
        if s.startswith("[HIVEUA]"):
            k = kv(s)
            ev[k["event"]].append(k)
    D = stream(on)
    sp = Counter()
    ex = defaultdict(list)
    for d in D:
        sp[(d["turn"], d["unit"])] += (d["ex"] or {}).get("spent", 0)
        ex[(d["turn"], d["unit"])].append(f"{d['act']}:{(d['ex'] or {}).get('spent', '-')}")
    n = 0
    for k in ev["RESULT"]:
        if int(k["turn"]) <= LAST and sp[(k["turn"], k["unit"])] != int(k["spent"]):
            n += 1
            if n <= 4:
                p(f"  differ: turn {k['turn']} unit {k['unit']} RESULT spent {k['spent']} tu {k['tu']} moved {k['moved']}; exec {sp[(k['turn'], k['unit'])]} acts {ex[(k['turn'], k['unit'])]}")
    # empty walks on the headquarters' node
    onnode = Counter()
    decided = {(k["turn"], k["unit"], k["tu"]): k for k in ev["DECIDED"]}
    for d in D:
        if d["act"] == "2" and d["ex"] and d["ex"].get("spent", 1) == 0:
            q = decided.get((d["turn"], d["unit"], d["tu"]))
            onnode["unmatched" if q is None else ("changed" if q["changed"] == "1" else "same_as_free")] += 1
    p("  empty walks by node:", dict(onnode))
    # nothing spent all turn
    by = defaultdict(list)
    for d in D:
        by[(d["turn"], d["unit"])].append(d)
    for key, ds in by.items():
        if all(d["act"] in ("0", "2") and (not d["ex"] or d["ex"].get("spent", 0) == 0) for d in ds):
            p(f"  nothing spent: turn {key[0]} unit {key[1]} tu {ds[0]['tu']} decisions {[(d['mode'], d['act'], d['from'], d['to']) for d in ds][:3]}")
    # by task
    role = {}
    for k in ev["RESULT"]:
        role[(k["turn"], k["unit"])] = k["kind"]
    t = defaultdict(Counter)
    for d in D:
        kind = role.get((d["turn"], d["unit"]), "?")
        c = t[kind]
        c["dec"] += 1
        c["mode" + d["mode"]] += 1
        c["att"] += int(d["act"]) in ATT
        c["att_dmg"] += int(d["act"]) in ATT and (d["ex"] or {}).get("dmg", 0) > 0
        c["dmg"] += (d["ex"] or {}).get("dmg", 0)
        c["downed"] += (d["ex"] or {}).get("downed", 0)
    for kind, c in sorted(t.items()):
        p(f"  task {kind}: {dict(c)}")
    t = defaultdict(Counter)
    for k in ev["RESULT"]:
        if int(k["turn"]) <= LAST:
            c = t[k["kind"]]
            c["unit_turns"] += 1
            c["moved"] += k["moved"] == "1"
            c["inside"] += k["inside"] == "1"
            c["closer"] += k["closer"] == "1"
            c["on_changed"] += k["changed"] == "1"
    for kind, c in sorted(t.items()):
        p(f"  result {kind}: {dict(c)}")
    for k in ev["REVIEW"][:0]:
        p(k)
    p("  objective reached by turn", sorted(Counter(int(k["turn"]) for k in ev["OBJECTIVE"] if k["why"] == "reached").items()))
    cmd = [s for s in L if s.startswith("[HIVECMD]")]
    p("  commander lines", [s[:150] for s in cmd[:2]])
out.close()
