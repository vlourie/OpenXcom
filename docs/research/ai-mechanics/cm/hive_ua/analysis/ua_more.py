"""UNIFIED ARMY CONTROL V0, read only: what the first difference consists of, one decision followed from the headquarters to the map, empty walks, casualty lines against victims, how each battle ended, RESPOND's turns. Writes more.txt next to this file.
Usage: ua_more.py"""
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
LAST = 8
SC = [("M6 s1", "ua4_UO_M6_s1", "ua1_UN_M6_s1"), ("M3 s1", "ua6_UO_M3_s1", "ua2_UN_M3_s1"), ("M8 s1", "ua8_UO_M8_s1", "ua3_UN_M8_s1")]
TAGS = ("[AIDECIDE]", "[AIEXEC]", "[AISTATE]", "[AICASUALTY]", "[AIREC]", "[AIPANIC]", "[AIAFTER]", "[AIPOSTWALK]", "[AIEVENT]")
TIMING = re.compile(r" (?:\w*us|\w*ms|\w*_ns|t|ms)=[-0-9.]+")
CFG = re.compile(r'"cfg":"[0-9a-f]+",')
out = open(HERE / "more.txt", "w", encoding="utf-8-sig")


def p(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    out.write(s + "\n")


def fields(s):
    return dict(re.findall(r"(\w+)=(\S+)", s))


def first_fields(off, on):
    a = [CFG.sub("", TIMING.sub("", s)) for s in read(off) if s.startswith(TAGS)]
    b = [CFG.sub("", TIMING.sub("", s)) for s in read(on) if s.startswith(TAGS)]
    for n, (x, y) in enumerate(zip(a, b)):
        if x != y:
            fa, fb = fields(x), fields(y)
            d = {k: (fa.get(k), fb.get(k)) for k in set(fa) | set(fb) if fa.get(k) != fb.get(k)}
            p(f"  first difference at line {n}, {x.split()[0]}: fields {d}")
            hr = [(u, v) for u, v in zip(a[:n], b[:n]) if u.startswith("[AIDECIDE]")]
            p(f"  decisions before it {len(hr)}, all equal including hr: {all(u == v for u, v in hr)}")
            # the next lines, until the decisions part
            for j in range(n + 1, min(n + 8, len(a), len(b))):
                if a[j] != b[j]:
                    p("   next OFF", a[j][:170])
                    p("   next ON ", b[j][:170])
                    break
            return


def chain(on, off):
    """One changed choice: the choice, the engine's decision, what became of it, and the same soldier on the same turn without headquarters."""
    L = read(on)
    ch = [kv(s) for s in L if s.startswith("[HIVEUA] event=CHOICE") and "changed=1" in s]
    dec = defaultdict(list)
    for s in L:
        if s.startswith("[AIDECIDE]"):
            k = kv(s)
            dec[(k["turn"], k["unit"])].append(k)
    res = {(k["turn"], k["unit"]): k for k in (kv(s) for s in L if s.startswith("[HIVEUA] event=RESULT"))}
    offd = defaultdict(list)
    for s in read(off):
        if s.startswith("[AIDECIDE]"):
            k = kv(s)
            offd[(k["turn"], k["unit"])].append(k)
    shown = 0
    for c in ch:
        key = (c["turn"], c["unit"])
        r = res.get(key)
        ds = dec[key]
        if not r or r["moved"] != "1" or r["inside"] != "1" or c["free_inside"] != "0" or not any(d["to"] == c["chosen"] and d["mode"] == "0" for d in ds):
            continue
        if shown == 2:
            break
        shown += 1
        p(f"  turn {c['turn']} soldier {c['unit']} squad {c['squad']} task {c['kind']} area center {c['center']} r {c['radius']}: free node {c['free']}, chosen {c['chosen']}")
        for d in ds[:4]:
            p(f"    ON  n={d['n']} from {d['from']} mode {d['mode']} act {d['act']} to {d['to']} tu {d['tu']}")
        for d in offd[key][:4]:
            p(f"    OFF n={d['n']} from {d['from']} mode {d['mode']} act {d['act']} to {d['to']} tu {d['tu']}")
        p(f"    result start {r['start']} end {r['end']} spent {r['spent']} inside {r['inside']} closer {r['closer']}")


def empties(run):
    """Walk decisions with nothing spent: where they point, and what the soldier did next."""
    L = read(run)
    D = []
    last = None
    import json
    recs = {}
    for s in L:
        if s.startswith("[AIDECIDE]"):
            k = kv(s)
            last = None
            if k["side"] == "1" and int(k["turn"]) <= LAST:
                last = dict(k, ex=None, rec=None)
                D.append(last)
        elif s.startswith("[AIREC]") and last is not None and last["rec"] is None:
            try:
                j = json.loads(s[8:])
            except ValueError:
                continue
            last["rec"] = j["rec"]
            recs[j["rec"]] = last
        elif s.startswith("[AIEXEC]"):
            try:
                j = json.loads(s[9:])
            except ValueError:
                continue
            if j["rec"] in recs:
                recs[j["rec"]]["ex"] = j
    c = Counter()
    by = defaultdict(list)
    for d in D:
        by[(d["turn"], d["unit"])].append(d)
    for key, ds in by.items():
        for i, d in enumerate(ds):
            if d["act"] != "2" or not d["ex"] or d["ex"].get("spent", 1) != 0:
                continue
            c["empty"] += 1
            c["mode" + d["mode"]] += 1
            c["self" if d["to"] == d["from"] else "elsewhere"] += 1
            nxt = ds[i + 1] if i + 1 < len(ds) else None
            if nxt is None:
                c["last_of_turn"] += 1
                c["left_tu"] += int(d["tu"])
            elif int(nxt["act"]) in range(4, 21):
                c["then_attack"] += 1
            elif nxt["act"] == "2":
                c["then_walk"] += 1
            else:
                c["then_other"] += 1
    # a soldier's turn all of empties and nothing else
    for key, ds in by.items():
        if all(d["act"] in ("0", "2") and (not d["ex"] or d["ex"].get("spent", 0) == 0) for d in ds):
            c["turns_nothing_spent"] += 1
            c["turns_nothing_spent_tu"] += int(ds[-1]["tu"])
    c["unit_turns"] = len(by)
    return c


def casualties(run):
    per = Counter()
    typ = {}
    how = Counter()
    bt = defaultdict(lambda: defaultdict(set))
    for s in read(run):
        if s.startswith("[AICASUALTY]"):
            k = kv(s)
            per[(k.get("vfaction"), k["victim"])] += 1
            typ[k["victim"]] = k.get("type")
            how[(k.get("vfaction"), k.get("how"))] += 1
            bt[k.get("vfaction")][int(k["turn"])].add(k["victim"])
    p(f"  {run}: lines {sum(per.values())}, victims {len(per)}, most lines {[(v[1], typ[v[1]], n) for v, n in per.most_common(3)]}, how {dict(how)}")
    seen = set()
    for f in sorted(bt):
        line = []
        for t in sorted(bt[f]):
            new = bt[f][t] - seen
            seen |= new
            line.append(f"{t}:{len(new)}")
        p(f"    side {f} new victims by turn: {' '.join(line)}")
    tt = Counter(typ[v[1]] for v in per if v[0] == "1")
    p(f"    side 1 by type: {tt.most_common(8)}")


def ending(run):
    L = read(run)
    tags = Counter(s.split()[0] for s in L if s.startswith("["))
    turns = [int(kv(s)["turn"]) for s in L if s.startswith("[AIDECIDE]")]
    ends = [s for s in L if re.match(r"\[(AIEND|AIBATTLE|BATTLEEND|AIRESULT|AIOUTCOME|HIVEEND|AIBENCH|CMEND)", s)]
    p(f"  {run}: last turn {max(turns)}; lines of ending {ends[-2:] if ends else '-'}")
    st = [s for s in L if s.startswith("[AISTATE]")]
    if st:
        p("    last state", st[-1][:260])
    return tags


def respond(run):
    ev = defaultdict(list)
    for s in read(run):
        if s.startswith("[HIVEUA]"):
            k = kv(s)
            ev[k["event"]].append(k)
    p(f"  {run}: objective why {dict(Counter(k['why'] for k in ev['OBJECTIVE']))}")
    tr = defaultdict(list)
    for k in ev["SQUADTURN"]:
        tr[k["squad"]].append(f"{k['turn']}{k['kind'][:3]}{k['alive']}/{k['inside']}")
    for sq, v in sorted(tr.items(), key=lambda x: int(x[0])):
        p(f"    squad {sq}: {' '.join(v)}")


for name, off, on in SC:
    p("=====", name)
    first_fields(off, on)
    chain(on, off)
    p("  empty walks OFF", dict(empties(off)))
    p("  empty walks ON ", dict(empties(on)))
    casualties(off)
    casualties(on)
    tags = ending(off)
    ending(on)
    respond(on)
p("tags", sorted(tags))
out.close()
