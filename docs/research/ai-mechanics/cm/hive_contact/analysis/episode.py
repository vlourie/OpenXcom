"""Contact coordination, the episode by a rule fixed before looking at any result. The log is the shadow run (behaviour of D0, the organization only written down).
Earliest enemy turn, at its plan, with a KNOWN contact where:
 A: a squad has a unit standing that the same side's turn attacks that contact (a shot or blow aimed at it) - it can attack lawfully;
 B: another squad, with no attack on that contact this turn, no unit of it attacking anything, at least two armed standing units, its nearest unit within CONTACT_REACH of the contact and a route: some unit's field at the plan or a walking order at its place, not locked;
 C: a third squad holding its sector or on a sector node, with no contact within HOLD_EXIT_RADIUS of its commander.
Prints all such turns, the earliest first; what the three squads did in that turn and the next two (read only)."""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import Places, kv, read, tup  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
REACH, NEAR = 24, 12
ATTACK = {4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20}


def dist(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def load(run):
    L = read(run)
    P = Places(L)
    weapon, squad_of = {}, {}
    plan = {}
    contacts = defaultdict(dict)
    sqturn = defaultdict(dict)
    dec = defaultdict(list)
    tiles = defaultdict(dict)
    hist = []
    for i, s in enumerate(L):
        if s.startswith("[HIVEUNIT]"):
            k = kv(s)
            weapon[int(k["id"])] = k.get("weapon", "-")
        elif s.startswith("[HIVESQUAD]"):
            k = kv(s)
            if "members" in k and "id" in k:
                for m in k["members"].split(","):
                    squad_of[int(m.rstrip("LSMA"))] = int(k["id"])
            elif "join" in k:
                squad_of[int(k["join"])] = int(k["squad"])
            elif "merged" in k:
                for u, q in list(squad_of.items()):
                    if q == int(k["merged"]):
                        squad_of[u] = int(k["into"])
        elif s.startswith("[HIVECONTACT]"):
            k = kv(s)
            if "event" not in k:
                contacts[int(k["turn"])][int(k["target"])] = (tup(k["pos"]), k["cls"], int(k.get("age", 0)))
        elif s.startswith("[HIVEPERF]") and "phase=plan" in s:
            k = kv(s)
            plan[int(k["turn"])] = (i, dict(squad_of))
        elif s.startswith("[HIVESQUADTURN]"):
            k = kv(s)
            sqturn[int(k["turn"])][int(k["squad"])] = k
        elif s.startswith("[AIDECIDE]"):
            k = kv(s)
            if k["side"] == "1":
                dec[int(k["turn"])].append((i, k))
        elif s.startswith("[HIVEREACH]"):
            k = kv(s)
            tiles[int(k["turn"])][int(k["unit"])] = int(k["tiles"])
    return L, P, weapon, plan, contacts, sqturn, dec, tiles


def rule(run):
    L, P, weapon, plan, contacts, sqturn, dec, tiles = load(run)
    print("==", run, "enemy turns with a plan", sorted(plan))
    found = []
    for turn in sorted(plan):
        line, so = plan[turn]
        here, gone = P.at(line)
        members = defaultdict(list)
        for u, q in so.items():
            if u in here and u not in gone:
                members[q].append(u)
        attacks = defaultdict(set)
        anyatt = Counter()
        for i, k in dec[turn]:
            a = int(k["act"])
            if a in ATTACK:
                q = so.get(int(k["unit"]))
                anyatt[q] += 1
                aim = int(k.get("aim", -1))
                attacks[aim].add(q)
        for c, (pc, cls, age) in contacts[turn].items():
            if cls != "KNOWN" or c < 0:
                continue
            A = {q for q in attacks.get(c, set()) if q is not None}
            if not A:
                continue
            B = []
            for q, ms in members.items():
                if q in A or anyatt[q]:
                    continue
                armed = [u for u in ms if weapon.get(u, "-") not in ("-", "NONE")]
                d = min((dist(here[u], pc) for u in ms), default=999)
                route = [u for u in ms if tiles[turn].get(u, 0) >= 30]
                if len(armed) >= 2 and d <= REACH and route:
                    B.append((q, d, len(ms), len(route)))
            C = []
            for q, ms in members.items():
                if q in A or q in [b[0] for b in B] or q not in sqturn[turn]:
                    continue
                k = sqturn[turn][q]
                own = k["task"] == "HOLD" or k.get("objective") not in {str(v[0]).replace(" ", "") for v in contacts[turn].values()}
                near = min((dist(here[int(k["commander"])], v[0]) for v in contacts[turn].values()), default=999) if int(k["commander"]) in here else 999
                if own and near > NEAR:
                    C.append((q, k["task"], k.get("hold"), near))
            if B and C:
                found.append((turn, c, pc, sorted(A), sorted(B, key=lambda x: x[1]), C))
    for f in found[:8]:
        print("  turn", f[0], "contact", f[1], f[2], "A", f[3], "B (squad, dist, units, with field)", f[4], "C", f[5])
    print("  turns matching:", sorted({f[0] for f in found}))
    return L, P, weapon, plan, contacts, sqturn, dec, tiles, found


def look(run, res, tn=3):
    L, P, weapon, plan, contacts, sqturn, dec, tiles, found = res
    if not found:
        return
    turn, c, pc, A, B, C = found[0]
    line, so = plan[turn]
    print(" episode: turn", turn, "contact", c, pc, "squads", A, B[0][0], [x[0] for x in C])
    for t in range(turn, turn + tn):
        print(" -- turn", t)
        for q in sorted(set(A) | {B[0][0]} | {x[0] for x in C}):
            ks = sqturn[t].get(q)
            row = Counter()
            towards = []
            for i, k in dec[t]:
                u = int(k["unit"])
                if so.get(u) != q:
                    continue
                row[("mode", k["mode"], "act", k["act"])] += 1
            print(f"   squad {q}:", {x: ks.get(x) for x in ("task", "hold", "alive", "tuPct", "shots", "saw", "objective")} if ks else None)
            print("      decisions", row.most_common(6))


if __name__ == "__main__":
    for run in sys.argv[1:]:
        res = rule(run)
        look(run, res)
