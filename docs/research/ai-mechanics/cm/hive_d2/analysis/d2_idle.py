"""HIVE D2 CORRECTION, read only: (1) unit-turns with nothing spent, ON against OFF, and why; (2) empty walks with no stop reason: whose node they go to; (3) fields by unit and place: how many a key of unit+place+turn or unit+place would have answered, against the exact state."""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
PAIRS = [("d21_DO_M3_s1", "d23_DN_M3_s1"), ("d25_DO_M6_s1", "d26_DN_M6_s1")]


def turns(L):
    d = defaultdict(list)
    ex = {}
    for i, s in enumerate(L):
        if s.startswith("[AIDECIDE]"):
            k = kv(s)
            if k.get("side") == "1":
                d[(k["turn"], k["unit"])].append((i, k))
        elif s.startswith("[AIEXEC]"):
            j = json.loads(s[9:])
            ex[(str(j.get("turn", "")), str(j.get("unit")), j.get("rec"))] = j
    return d


for off, on in PAIRS:
    for run in (off, on):
        L = read(run)
        print("=====", run)
        recs = []
        seq = []
        for i, s in enumerate(L):
            if s.startswith("[AIDECIDE]"):
                seq.append((i, kv(s)))
            elif s.startswith("[AIEXEC]"):
                j = json.loads(s[9:])
                if seq and str(j.get("unit")) == seq[-1][1]["unit"]:
                    recs.append((seq[-1][0], seq[-1][1], j))
        ut = defaultdict(list)
        for i, k, j in recs:
            if k.get("side") == "1" and int(k["turn"]) <= 8:
                ut[(int(k["turn"]), k["unit"])].append((i, k, j))
        ends = defaultdict(list)
        offers = {}
        for i, s in enumerate(L):
            if s.startswith("[HIVEUA] event=PATROLEND"):
                e = kv(s)
                ends[(int(e["turn"]), e["unit"])].append(e)
        nothing = [(t, u) for (t, u), v in ut.items() if sum(x[2].get("spent", 0) for x in v) == 0]
        print(" unit-turns with nothing spent:", len(nothing))
        for t, u in sorted(nothing):
            v = ut[(t, u)]
            print("   t", t, u, [(k["from"], "m" + k["mode"], "a" + k["act"], k.get("to")) for _, k, _ in v][:3], "ends", [(e["tries"], e["refused"], e["end"]) for e in ends[(t, u)]][:3])
        # empty walks without a stop reason
        last_end = {}
        empty = Counter()
        ex = []
        for i, k, j in sorted(recs, key=lambda r: r[0]):
            pass
        pos = 0
        cur = {}
        order = sorted(recs, key=lambda r: r[0])
        ends_lines = [(i, kv(s)) for i, s in enumerate(L) if s.startswith("[HIVEUA] event=PATROLEND")]
        p = 0
        for i, k, j in order:
            while p < len(ends_lines) and ends_lines[p][0] < i:
                cur[ends_lines[p][1]["unit"]] = ends_lines[p][1]
                p += 1
            if k.get("side") != "1" or k["act"] != "2" or j.get("spent", 0) != 0:
                continue
            tr = j.get("trail") or []
            if tr:
                continue
            e = cur.get(k["unit"])
            what = "no patrol end yet" if not e else ("this turn: to the node of the last choice, " + ("offer" if int(e["taken"]) else "free")) if e["end"] == k.get("to") and e["turn"] == k["turn"] else ("older node: kept" if e else "")
            empty[what + " mode" + k["mode"]] += 1
            if len(ex) < 6:
                ex.append((k["turn"], k["unit"], k["from"], k.get("to"), "tu", k["tu"], "mode", k["mode"], "walk", j.get("walk")))
        print(" empty walks, no stop reason:", dict(empty))
        for x in ex:
            print("    ", x)
        # fields
        fl = [kv(s) for s in L if s.startswith("[HIVEREACH]")]
        by_all = Counter()
        same_place = same_place_turn = same_tiles = 0
        seen = {}
        seen_t = set()
        for f in fl:
            key = (f["unit"], f["at"])
            if key in seen:
                same_place += 1
                if seen[key] == f["tiles"]:
                    same_tiles += 1
            if key + (f["turn"],) in seen_t:
                same_place_turn += 1
            seen[key] = f["tiles"]
            seen_t.add(key + (f["turn"],))
        if fl:
            print(" fields", len(fl), "same unit and place before:", same_place, "and the same tile count:", same_tiles, "same unit, place and turn:", same_place_turn)
