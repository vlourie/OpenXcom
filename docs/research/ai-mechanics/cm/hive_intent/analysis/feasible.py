"""COMBAT INTENT V0, feasibility from the RA archives, read only. For every attack of the AI side: the branch that made it, and whether the squad's contact of that turn was open to the same weapon by the journal's own candidates. Then pairs: two shooters with a line to one contact and different aims.
Usage: feasible.py <run> [<run>...]"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ATT = set(range(4, 21))
ROLE_MAP = {}


def scan(run):
    lines = read(run)
    acts = {}
    roles = {}
    seers = defaultdict(lambda: defaultdict(int))
    squad = {}
    C = Counter()
    src = Counter()
    atk = []
    last = None
    pos = {}
    for s in lines:
        if s.startswith("[HIVESQUAD]") and "members=" in s:
            k = kv(s)
            for m in k["members"].split(","):
                squad[m.rstrip("SLA")] = k["id"]
        elif s.startswith("[HIVESQUAD]") and "join=" in s:
            k = kv(s)
            squad[k["join"]] = k["squad"]
        elif s.startswith("[HIVECC] event=DECISION"):
            turn = int(kv(s)["turn"])
            part = s.split("squads:")[1].split()
            roles[turn] = {p.split("=")[0]: p.split("=")[1].split(":") for p in part}
        elif s.startswith("[HIVECC] event=CONTACT"):
            k = kv(s)
            seers[int(k["turn"])][k["target"]] = len([x for x in k["seen_by"].split(":") if x])
        elif s.startswith("[AICAND] acts="):
            k = s.split()
            h = k[1].split("=")[1]
            try:
                acts[h] = json.loads(s.split("list=", 1)[1])
            except ValueError:
                pass
        elif s.startswith("[AIDECIDE]"):
            k = kv(s)
            last = None
            if k["side"] == "1" and int(k["turn"]) <= 8 and int(k["act"]) in ATT:
                last = dict(k, rec=None)
                atk.append(last)
        elif s.startswith("[AIREC]") and last is not None and last["rec"] is None:
            try:
                last["rec"] = json.loads(s[8:])
            except ValueError:
                pass
    for d in atk:
        rec = d["rec"] or {}
        base = rec.get("base") or {}
        src[str(base.get("src"))] += 1
        C["act_" + d["act"]] += 1
        cand = acts.get((rec.get("cand") or {}).get("acts"), [])
        d["open"] = {str(c["u"]) for c in cand if c.get("k") == "a" and c.get("lof") and c.get("tu", 10**6) <= int(d["tu"])}
        d["all"] = {str(c["u"]) for c in cand if c.get("k") == "a"}
        t = int(d["turn"])
        sq = squad.get(d["unit"])
        role, contact = (roles.get(t, {}).get(sq) or ["?", "-1"])
        C["attacks"] += 1
        C["role_" + role] += 1
        d["role"] = role
        d["contact"] = contact
        d["squad"] = sq
        if contact in ("-1", "?"):
            C["no_contact"] += 1
            continue
        if d["aim"] == contact:
            C["aim_is_contact"] += 1
        elif contact in d["open"]:
            C["contact_open_other_aim"] += 1
        else:
            C["contact_not_open"] += 1
        # civilians: the aim's id is of the AI's own id range
    C["aim_civilian_or_other"] = sum(1 for d in atk if int(d["aim"]) >= 1000000)
    print("==", run)
    print("  by branch", dict(src.most_common()))
    print("  counts", dict(sorted(C.items())))
    # turns: the contact with most shooters open, and pairs that split
    pairs = []
    by = defaultdict(lambda: defaultdict(dict))
    for d in atk:
        by[int(d["turn"])][d["unit"]].setdefault("first", d)
    for t in sorted(by):
        units = [v["first"] for v in by[t].values()]
        open_for = Counter()
        for d in units:
            for x in d["open"]:
                if int(x) < 1000000:
                    open_for[x] += 1
        if not open_for:
            continue
        top, n = open_for.most_common(1)[0]
        aimed = sum(1 for d in units if d["aim"] == top)
        print(f"  turn {t}: shooters {len(units)} best contact {top}: open to {n}, first shot at it {aimed}; seen by squads {seers[t].get(top)}; first aims {Counter(d['aim'] for d in units).most_common(6)}")
        split = [d for d in units if top in d["open"] and d["aim"] != top]
        with_it = [d for d in units if d["aim"] == top]
        if len(split) >= 2 or (split and with_it):
            pairs.append((t, top, [(d["unit"], d["squad"], d["role"], d["contact"], d["aim"], d["tu"], d["act"]) for d in split[:5]], [(d["unit"], d["squad"]) for d in with_it[:4]]))
    print("  pairs that split:")
    for p in pairs[:6]:
        print("   ", p)


for r in sys.argv[1:]:
    scan(r)
