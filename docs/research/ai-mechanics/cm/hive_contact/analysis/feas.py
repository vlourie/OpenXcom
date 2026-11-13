"""Contact coordination, feasibility of the episode M6 s1 turn 1: who sees what at the plan; the means of squad B; what each squad did turn by turn in the shadow run (D0 behaviour) and in the active run of HH on the same seed; how long a squad sent to a contact takes to shoot (read only)."""
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import Places, kv, read, tup  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
SHOT = {7, 8, 9}
ATT = {4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20}


def dist(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def parse(run):
    L = read(run)
    units, so, fair, contacts, sqt, dec, dead, kills, reach = {}, {}, defaultdict(list), defaultdict(dict), defaultdict(dict), defaultdict(list), {}, defaultdict(list), defaultdict(dict)
    so_turn = {}
    tasks = defaultdict(list)
    for i, s in enumerate(L):
        if s.startswith("[HIVEUNIT]"):
            k = kv(s)
            units[int(k["id"])] = k
        elif s.startswith("[HIVESQUAD]"):
            k = kv(s)
            if "members" in k and "id" in k:
                for m in k["members"].split(","):
                    so[int(m.rstrip("LSMA"))] = int(k["id"])
            elif "join" in k:
                so[int(k["join"])] = int(k["squad"])
            elif "merged" in k:
                for u, q in list(so.items()):
                    if q == int(k["merged"]):
                        so[u] = int(k["into"])
        elif s.startswith("[HIVEFAIR]"):
            k = kv(s)
            fair[int(k["turn"])].append((int(k["observer"]), int(k["target"]), tup(k["pos"]), so.get(int(k["observer"]))))
        elif s.startswith("[HIVECONTACT]"):
            k = kv(s)
            if "event" not in k:
                contacts[int(k["turn"])][int(k["target"])] = (tup(k["pos"]), k["cls"])
        elif s.startswith("[HIVEPERF]") and "phase=plan" in s:
            so_turn[int(kv(s)["turn"])] = dict(so)
        elif s.startswith("[HIVESQUADTURN]"):
            k = kv(s)
            sqt[int(k["turn"])][int(k["squad"])] = k
        elif s.startswith("[HIVETASK]"):
            k = kv(s)
            tasks[int(k["turn"])].append(k)
        elif s.startswith("[HIVEREACH]"):
            k = kv(s)
            reach[int(k["turn"])][int(k["unit"])] = k
        elif s.startswith("[AIDECIDE]"):
            k = kv(s)
            if k["side"] == "1":
                dec[int(k["turn"])].append(k)
        elif s.startswith("[AICASUALTY]"):
            k = kv(s)
            t = int(k["turn"])
            if k.get("vfaction") == "1":
                dead[int(k["victim"])] = (t, k["side"], k.get("how"))
            if k.get("kfaction") == "1" and k.get("killer", "-").isdigit():
                kills[t].append((int(k["killer"]), int(k["victim"]) if k["victim"].isdigit() else k["victim"], k.get("how")))
    return dict(L=L, units=units, so_turn=so_turn, fair=fair, contacts=contacts, sqt=sqt, dec=dec, dead=dead, kills=kills, reach=reach, tasks=tasks)


def squad_rows(d, q, last=8):
    print(f"  squad {q}")
    so1 = d["so_turn"].get(1, {})
    for t in range(1, last + 1):
        so = d["so_turn"].get(t, so1)
        ms = {u for u, x in so.items() if x == q}
        ks = d["sqt"][t].get(q)
        modes, shots, aims = Counter(), 0, Counter()
        mind, walked = 999, Counter()
        cs = d["contacts"][t]
        for k in d["dec"][t]:
            u = int(k["unit"])
            if u not in ms:
                continue
            modes[k["mode"]] += 1
            a = int(k["act"])
            if a in ATT:
                shots += 1
                aims[k["aim"]] += 1
            p = tup(k["from"])
            for v in cs.values():
                if v[1] == "KNOWN":
                    mind = min(mind, dist(p, v[0]))
        dead_now = [u for u in ms if d["dead"].get(u, (0,))[0] == t]
        kl = [x for x in d["kills"][t] if x[0] in ms]
        task = (ks["task"], ks.get("hold"), ks.get("objective")) if ks else None
        print(f"    t{t} task {task} alive {ks and ks['alive']} tuPct {ks and ks.get('tuPct')} modes {dict(modes)} attacks {shots} {dict(aims.most_common(3))} nearestKNOWN {mind} lost {len(dead_now)} kills {len(kl)}")


def shot_ranges(d):
    r = defaultdict(list)
    pos = {}
    for t in d["dec"]:
        cs = d["contacts"][t]
        for k in d["dec"][t]:
            if int(k["act"]) in SHOT and k["aim"].isdigit() and int(k["aim"]) in cs:
                r[k["weapon"]].append(dist(tup(k["from"]), cs[int(k["aim"])][0]))
    return r


def main():
    hh2, hh3 = parse("hh2_JS_M6_s1"), parse("hh3_JA_M6_s1")
    print("== turn 1 at the plan: contacts by squad that sees them (shadow)")
    seers = defaultdict(set)
    for o, c, p, q in hh2["fair"][1]:
        seers[(c, p)].add(q)
    for c, qs in sorted(seers.items()):
        print("  ", c, sorted(x for x in qs if x is not None))
    print("== squad 0 at the plan of turn 1")
    so = hh2["so_turn"][1]
    for u, q in sorted(so.items()):
        if q == 0:
            k = hh2["units"][u]
            r = hh2["reach"][1].get(u, {})
            ds = sorted((dist(tup(r["at"]), v[0]), c) for c, v in hh2["contacts"][1].items() if v[1] == "KNOWN") if r else []
            print(f"   {u} {k['type']} rank {k['rank']} weapon {k['weapon']} aggr {k['aggr']} int {k['int']} tu {r.get('tu')} at {r.get('at')} tiles {r.get('tiles')} nearest {ds[:2]} dead {hh2['dead'].get(u)}")
    print("== shadow M6 s1 (D0 behaviour)")
    for q in (0, 1, 5, 7, 8):
        squad_rows(hh2, q)
    print("== active HH M6 s1, same seed")
    for q in (0, 1, 5, 7, 8):
        squad_rows(hh3, q)
    print("== attacks at a KNOWN contact, distance by weapon, all three runs")
    r = defaultdict(list)
    for d in (hh2, hh3, parse("hh4_JA_M6_s2")):
        for w, v in shot_ranges(d).items():
            r[w] += v
    for w, v in sorted(r.items(), key=lambda x: -len(x[1]))[:10]:
        v = sorted(v)
        print(f"   {w} n={len(v)} median {v[len(v)//2]} max {v[-1]}")


if __name__ == "__main__":
    main()
