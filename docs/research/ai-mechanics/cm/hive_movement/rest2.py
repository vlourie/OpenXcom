"""Movement diagnosis, second part of the counts: how far the contact really moved against how far the unit's target moved; the rule a stable order would need, in orders; STAY locked against the unit's own earlier field;
longer windows for the partial cases of a closed part; the loose exit (27,15,0); the first enemy decision of the two loads (read only)."""
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from classify import run_table  # noqa: E402
from closers import analyse as closers_analyse  # noqa: E402
from lib import Places, kv, read, tup  # noqa: E402
from rest import contact_of_task, dist  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")


def objective_at(L, o):
    """The squad's objective in its turn line before the order closed and in the one before the order was issued."""
    before = after = None
    for j in range(o["line1"], 0, -1):
        s = L[j]
        if s.startswith("[HIVESQUADTURN]") and f"squad={o['squad']} " in s:
            k = kv(s)
            if "objective" in k:
                if int(k["turn"]) >= o["turn0"]:
                    after = after or tup(k["objective"])
                    before = tup(k["objective"])
                if int(k["turn"]) < o["turn0"]:
                    break
    return before, after


def stable(run):
    L, rows, decisions = run_table(run)
    by_unit = {}
    for o in rows:
        by_unit.setdefault(o["unit"], []).append(o)
    for v in by_unit.values():
        v.sort(key=lambda x: x["line0"])
    print("==", run)
    rep = [o for o in rows if o.get("reason") == "replaced"]
    table = Counter()
    shift, tshift = [], []
    goal_near = 0
    other_kind = Counter()
    for o in rep:
        c = contact_of_task(L, o)
        same = o["trigger"].startswith("contact") and len(c) == 2 and c[0][2] == c[1][2]
        kind = "тот же контакт" if same else ("другой контакт" if o["trigger"].startswith("contact") and len(c) == 2 else o["trigger"] or "неизвестно")
        o["kind"] = kind
        if o["cause"] == "задача изменилась":
            left = o["note"].get("path_tu", 0) - o["walk_tu"]
            reach = "один ход" if o["note"].get("reach") == "full" or left <= o["tu0"] else ("два хода" if left <= 2 * o["tu0"] else "дальше")
            table[(kind, reach)] += 1
        other_kind[(kind, o["cause"])] += 1
        if same:
            b, a = objective_at(L, o)
            nxt = next((n for n in by_unit[o["unit"]] if n["line0"] >= o["line1"] - 3 and n["id"] != o["id"]), None)
            if b and a and nxt:
                shift.append(dist(b, a))
                tshift.append(dist(o["target"], nxt["target"]))
                if dist(nxt["target"], a) <= dist(o["target"], a):
                    goal_near += 1
    print(" replaced, kind and cause:", sorted(other_kind.items()))
    print(" task changed, kind and how far the old target was:", sorted(table.items()))
    shift.sort()
    tshift.sort()
    if shift:
        print(f" same contact: contact moved median {shift[len(shift) // 2]} (min {shift[0]} max {shift[-1]}), the unit's target moved median {tshift[len(tshift) // 2]}, n {len(shift)}; the new target is nearer the contact in {goal_near}; contact moved <=10: {sum(x <= 10 for x in shift)}; target moved more than the contact: {sum(t > s for s, t in zip(shift, tshift))} (independently sorted, for scale)")
    chains = Counter(len(v) for v in by_unit.values())
    print(" walking orders per unit in the battle:", sorted(chains.items()))
    # STAY locked and the unit's own earlier field
    L2 = L
    lock = Counter()
    seen = set()
    best = {}
    for i, s in enumerate(L2):
        if s.startswith("[HIVEREACH]"):
            k = kv(s)
            u = int(k["unit"])
            best[u] = max(best.get(u, 0), int(k["tiles"]))
            last_tiles = (u, int(k["tiles"]))
        elif s.startswith("[HIVEORD]") and "kind=STAY" in s and "why=locked" in s:
            k = kv(s)
            if k.get("id") in seen:
                continue
            seen.add(k.get("id"))
            u = int(k["unit"])
            t = None
            for j in range(i, max(i - 40, 0), -1):
                if L2[j].startswith("[HIVEREACH]") and f"unit={u} " in L2[j]:
                    t = int(kv(L2[j])["tiles"])
                    break
            lab = "нет поля рядом" if t is None else ("поле было вдвое больше" if best.get(u, 0) >= 2 * t else "поле всегда такое")
            lock[(lab, int(k["turn"]))] += 1
    print(" STAY locked by turn and own earlier field:", sorted(lock.items()))


for run in ["hh4_JA_M6_s2", "hh6_JV_M3_s1"]:
    stable(run)

print("== longer windows for the partial parts")
for run in ["hh3_JA_M6_s1", "hh4_JA_M6_s2", "hh6_JV_M3_s1"]:
    for w in (140, 300, 600):
        L, res = closers_analyse(run, window=w)
        print(" ", run, "window", w, [(r["line"], r["small"], r["part"], r.get("complete")) for r in res if "note" not in r])

L = read("hh4_JA_M6_s2")
P = Places(L)
here, gone = P.at(3053)
print("== (27,15,0) at line 3053: units nearby", {u: p for u, p in here.items() if u not in gone and abs(p[0] - 27) <= 3 and abs(p[1] - 15) <= 3})
print("   gone nearby", {u: p for u, p in here.items() if u in gone and abs(p[0] - 27) <= 3 and abs(p[1] - 15) <= 3})
for j in range(3053, 2500, -1):
    if "(27,15,0)" in L[j] and L[j].startswith(("[AIDECIDE]", "[AICASUALTY]", "[AIEXEC]")):
        print("   last mention", j, L[j][:170])
        break

B = read("hh7_HL_M3_s1")
C = read("hh8_HL_M3_s1")
db = [(i, kv(s)) for i, s in enumerate(B) if s.startswith("[AIDECIDE]")]
dc = [(i, kv(s)) for i, s in enumerate(C) if s.startswith("[AIDECIDE]")]
print("== decisions 14..17 of the two loads")
for n in range(14, 18):
    for name, d in (("hive", db), ("none", dc)):
        i, k = d[n]
        print("  ", name, n, "line", i, "side", k["side"], "unit", k["unit"], "mode", k["mode"], "act", k["act"], "to", k.get("to"), "ha0", k["ha0"][:8], "hr0", k["hr0"][:8], "hr", k["hr"][:8])
print("players' decisions before the first enemy one:", sum(1 for _ in __import__("itertools").takewhile(lambda x: x[1]["side"] == "0", db)))
for name, X in (("hive", B), ("none", C)):
    i0 = next(i for i, s in enumerate(X) if s.startswith("[AIDECIDE]") and " side=1 " in s)
    print(name, "before the first enemy decision:", Counter(s.split(" ")[0] for s in X[i0 - 40 : i0] if s.startswith("[")).most_common(6))
    u = int(kv(X[i0])["unit"])
    print("   orders for it:", [s[:150] for s in X[: i0 + 1] if s.startswith("[HIVEORD]") and f"unit={u} " in s and "turn=5" in s][-3:])
