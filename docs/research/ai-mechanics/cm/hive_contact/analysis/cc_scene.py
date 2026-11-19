"""CONTACT_COORDINATION_V0: results and unique casualties per run; one turn told as a scene: the decision, who sees the role contact, the helper's orders and acts, who else hit that contact, the guards, the feedback; a squad's units in the baseline; guards' distance by turn (read only).
Usage: cc_scene.py sum <run> ... | cc_scene.py scene <run> <base> <turn> <squad> | cc_scene.py guards <run>"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from cc_eval import ATT, damage, side_dec  # noqa: E402
from lib import kv, read, tup  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")


def summary(run):
    L = read(run)
    rows = [kv(s) for s in L if s.startswith("[AICASUALTY]")]
    res = [s for s in L if s.startswith("[AIRESULT]")]
    r = kv(res[-1]) if res else {}
    dec = side_dec(L)
    uniq = defaultdict(dict)
    how = Counter()
    for k in rows:
        if int(k["turn"]) <= 8:
            side = "enemy" if k.get("vfaction") == "1" else ("player" if k.get("vfaction") == "0" else "neutral " + k.get("vfaction", "?"))
            uniq[side][k["victim"]] = k["how"]
            how[(side, k["how"])] += 1
    print(run, "result", {x: r.get(x) for x in ("how", "turn", "livealiens", "livesoldiers", "pdead", "phplost")}, "units deciding per turn", [len(dec[t]) for t in sorted(dec) if t <= 8])
    print("   unique victims", {s: len(v) for s, v in uniq.items()}, "rows by how", how.most_common(8))


def scene(run, base, turn, squad):
    L = read(run)
    B = read(base)
    dec, dec0 = side_dec(L), side_dec(B)
    dmg, dmg0 = damage(L), damage(B)
    cc = [(s, kv(s)) for s in L if s.startswith("[HIVECC]")]
    print("== scene", run, "turn", turn, "squad", squad)
    for s, k in cc:
        if k["event"] == "DECISION" and int(k["turn"]) == turn:
            print("  ", s[9:][:300])
    contact = None
    for s, k in cc:
        if k["event"] == "ASSIGN" and int(k["turn"]) == turn:
            print("  ", s[9:][:170])
            if k["squad"] == str(squad) and k["to"] == "REINFORCE":
                contact = k["contact"]
        if k["event"] == "REINFORCE_CHECK" and int(k["turn"]) == turn:
            print("  ", s[9:][:170])
    print(" contact records", [s[:140] for s in L if s.startswith("[HIVEFAIR]") and kv(s).get("turn") == str(turn) and kv(s).get("target") == contact][:4])
    roles = {}
    for s, k in cc:
        if k["event"] == "EXEC" and int(k["turn"]) == turn:
            roles[int(k["unit"])] = (k["squad"], k["role"])
    for s, k in cc:
        if k["event"] == "ORDER" and int(k["turn"]) == turn and k["squad"] == str(squad):
            u = int(k["unit"])
            ds = dec[turn].get(u, [])
            ds0 = dec0[turn].get(u, [])
            print(f"   {u} {k['kind']} {k.get('at')} -> {k.get('target')}: acts {[d['act'] for d in ds]} aims {[d['aim'] for d in ds if int(d['act']) in ATT]} ends {ds[-1]['to'] if ds else '-'} dmg {dmg.get((turn, u), Counter())['dmg']} | baseline acts {[d['act'] for d in ds0]} aims {[d['aim'] for d in ds0 if int(d['act']) in ATT]} dmg {dmg0.get((turn, u), Counter())['dmg']}")
    print(" everyone who attacked the contact", contact, "this turn:")
    who = Counter()
    for u, ds in dec[turn].items():
        for d in ds:
            if int(d["act"]) in ATT and d["aim"] == contact:
                who[(roles.get(u, ("?", "?")), u)] += 1
    print("  ", who.most_common())
    by_role = Counter()
    for u, ds in dec[turn].items():
        for d in ds:
            if int(d["act"]) in ATT:
                by_role[roles.get(u, ("?", "?"))] += 1
    print(" attacks by squad and role", sorted(by_role.items()))
    print(" contact in the baseline: attacks on it", sum(1 for ds in dec0[turn].values() for d in ds if int(d["act"]) in ATT and d["aim"] == contact), "side attacks", sum(1 for ds in dec0[turn].values() for d in ds if int(d["act"]) in ATT))
    for s, k in cc:
        if k["event"] == "FEEDBACK" and int(k["turn"]) == turn + 1 and k["squad"] == str(squad):
            print("  ", s[9:][:170])
    print(" contact's state next rows:", [s[:150] for s in L if s.startswith("[AICASUALTY]") and kv(s).get("victim") == contact][:2])
    # the squad's fate against the baseline
    us = sorted({int(k["unit"]) for s, k in cc if k["event"] == "ORDER" and k["squad"] == str(squad) and int(k["turn"]) == turn})
    def fate(LL):
        out = {}
        for s in LL:
            if s.startswith("[AICASUALTY]"):
                k = kv(s)
                if k["victim"].isdigit() and int(k["victim"]) in us:
                    out.setdefault(int(k["victim"]), (int(k["turn"]), k["how"]))
        return out
    print(" units", us, "fall on", fate(L), "base", fate(B))


def guards(run):
    L = read(run)
    dec = side_dec(L)
    holds = {}
    for s in L:
        if s.startswith("[HIVEHOLD]"):
            k = kv(s)
            holds.setdefault(int(k["squad"]), k)
    mem = defaultdict(set)
    role = defaultdict(dict)
    for s in L:
        if s.startswith("[HIVECC]") and "event=EXEC" in s:
            k = kv(s)
            mem[int(k["squad"])].add(int(k["unit"]))
            role[int(k["squad"])][int(k["turn"])] = k["role"][0]
    print("==", run, "guards: by turn, role and median distance of the living from the anchor")
    for sq, h in sorted(holds.items()):
        a = tup(h["anchor"])
        row = []
        for t in sorted(dec):
            ds = []
            for u in mem[sq]:
                if u in dec[t]:
                    p = tup(dec[t][u][0]["from"])
                    ds.append(max(abs(p[0] - a[0]), abs(p[1] - a[1])))
            if ds:
                row.append(f"t{t}{role[sq].get(t, '-')}{sorted(ds)[len(ds) // 2]}")
        print("   squad", sq, a, " ".join(row))


if __name__ == "__main__":
    if sys.argv[1] == "sum":
        for r in sys.argv[2:]:
            summary(r)
    elif sys.argv[1] == "scene":
        scene(sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5]))
    else:
        guards(sys.argv[2])
