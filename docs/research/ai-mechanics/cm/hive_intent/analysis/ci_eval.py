"""HIVE COMBAT INTENT V0, the main check, read only: what the soldiers answered at each place they choose a target, and the causal chain of each changed decision: CHOICE -> [AIDECIDE] aim -> DECIDED -> RESULT, with the time units against [AIEXEC].
Usage: ci_eval.py <run> [<run>...]"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ATT = set(range(4, 21))


def scan(run):
    lines = read(run)
    print("==", run, "lines", len(lines))
    events = Counter(kv(s).get("event") for s in lines if s.startswith("[HIVEINTENT]"))
    print("  events", dict(events))
    print("  issued", dict(Counter(kv(s).get("type") for s in lines if s.startswith("[HIVEINTENT] event=ISSUE"))))
    print("  closed", dict(Counter(kv(s).get("status") for s in lines if s.startswith("[HIVEINTENT] event=CLOSE"))))
    sites, nos = Counter(), Counter()
    per = defaultdict(Counter)
    for s in lines:
        if s.startswith("[HIVEINTENT] event=CHOICE"):
            k = kv(s)
            sites[k["site"]] += 1
            nos[k["no"]] += 1
            per[k["site"]][k["no"] if k["no"] != "-" else ("TAKES" if k["changed"] == "1" else "WOULD")] += 1
    print("  choice by site", {a: dict(b.most_common()) for a, b in per.items()})
    print("  no", dict(nos.most_common()))
    print("  result kinds", dict(Counter(kv(s)["kind"] for s in lines if s.startswith("[HIVEINTENT] event=RESULT"))))
    print("  result kinds, changed", dict(Counter(kv(s)["kind"] for s in lines if s.startswith("[HIVEINTENT] event=RESULT") and " changed=1" in s)))
    print("  own", dict(Counter(kv(s).get("own") for s in lines if s.startswith("[HIVEINTENT] event=DECIDED"))))

    # the chain
    last_choice = {}
    last_dec = None
    rec_of = {}
    spent_of = {}
    chains = []
    pending = None
    for s in lines:
        if s.startswith("[HIVEINTENT] event=CHOICE"):
            k = kv(s)
            last_choice[k["unit"]] = k
        elif s.startswith("[AIDECIDE]"):
            last_dec = kv(s)
        elif s.startswith("[AIREC]") and last_dec is not None and "rec_" not in last_dec:
            try:
                last_dec["rec_"] = json.loads(s[8:]).get("rec")
            except ValueError:
                last_dec["rec_"] = None
        elif s.startswith("[AIEXEC]"):
            try:
                j = json.loads(s[9:])
                spent_of[str(j.get("rec"))] = j.get("spent")
            except ValueError:
                pass
        elif s.startswith("[HIVEINTENT] event=DECIDED"):
            k = kv(s)
            if k.get("squad") == "-1":
                continue
            pending = dict(dec=k, ai=last_dec, choice=last_choice.pop(k["unit"], None))
        elif s.startswith("[HIVEINTENT] event=RESULT") and pending:
            k = kv(s)
            pending["res"] = k
            chains.append(pending)
            pending = None
    ch = [c for c in chains if c["dec"].get("changed") == "1"]
    bad = 0
    tu_same = tu_diff = tu_none = 0
    for c in chains:
        a = c["ai"] or {}
        rec = str(a.get("rec_"))
        if isAttack(c["dec"]["act"]) and rec in spent_of:
            if str(spent_of[rec]) == c["res"]["tu_spent"]:
                tu_same += 1
            else:
                tu_diff += 1
        elif isAttack(c["dec"]["act"]):
            tu_none += 1
    print(f"  chains {len(chains)} changed {len(ch)}; tu against AIEXEC: same {tu_same} differ {tu_diff} no exec record {tu_none}")
    turns = defaultdict(list)
    for c in ch:
        a, d, r, cho = c["ai"], c["dec"], c["res"], c["choice"] or {}
        ok = a and a.get("unit") == d["unit"] and cho.get("contact") == d["contact"] and (not isAttack(d["act"]) or (a.get("aim") == d["contact"] and r["kind"] == "ATTACKED_CONTACT" and int(r["tu_spent"]) > 0))
        bad += not ok
        turns[int(d["turn"])].append(f"{d['unit']} sq{d['squad']} {cho.get('site')} {cho.get('own')}->{d['contact']} act{d['act']} aim={a.get('aim') if a else None} {r['kind']} tu={r['tu_spent']} hit={r['hit']} down={r['down']}{'' if ok else ' !!'}")
    print("  changed decisions whose chain is not whole:", bad)
    for t in sorted(turns)[:3]:
        print(f"  turn {t}:")
        for x in turns[t][:14]:
            print("    ", x)
    # shared attacks: at least two fighters on one aim in a turn
    atk = defaultdict(lambda: defaultdict(set))
    for s in lines:
        if s.startswith("[AIDECIDE]"):
            k = kv(s)
            if k["side"] == "1" and int(k["turn"]) <= 8 and int(k["act"]) in ATT and k["aim"] != "-1":
                atk[int(k["turn"])][k["aim"]].add(k["unit"])
    print("  fighters per aim, turn: ", {t: sorted((len(v) for v in a.values()), reverse=True)[:5] for t, a in sorted(atk.items())})


def isAttack(a):
    return int(a) in ATT


for r in sys.argv[1:]:
    scan(r)
