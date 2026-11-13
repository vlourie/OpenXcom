"""Movement diagnosis, the remaining counts: replaced orders (same contact moved or another one, how far the target went, would the unit have come), the reserve (empty walks, walks cut short, full orders lost),
the deaths (whose turn, while doing what), the modes against what the unit could see, and the harm of a closed part in orders (read only)."""
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from classify import run_table  # noqa: E402
from lib import kv, tup  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
RUNS = ["hh4_JA_M6_s2", "hh6_JV_M3_s1"]


def dist(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def squad_turns(L):
    out = {}
    for i, s in enumerate(L):
        if s.startswith("[HIVESQUADTURN]"):
            k = kv(s)
            out[(int(k["squad"]), int(k["turn"]))] = k
    return out


def contact_of_task(L, o):
    """The squad's objective contact in the task line right before the order closed, and the one before that."""
    seen = []
    for j in range(o["line1"], max(o["line1"] - 2500, 0), -1):
        s = L[j]
        if s.startswith("[HIVETASK]") and f"squad={o['squad']} " in s:
            k = kv(s)
            if k.get("kind") == "contact" and "contact" in k:
                seen.append((j, int(k["turn"]), k["contact"], k.get("objective") or k.get("pos")))
            if len(seen) == 2:
                break
    return seen


def analyse(run):
    L, rows, decisions = run_table(run)
    print("==", run, "orders", len(rows))
    closed = [o for o in rows if "fate" in o]
    by_unit = {}
    for o in rows:
        by_unit.setdefault(o["unit"], []).append(o)
    for v in by_unit.values():
        v.sort(key=lambda x: x["line0"])
    # replaced
    rep = [o for o in closed if o.get("reason") == "replaced"]
    kinds = Counter()
    moved = []
    nearer = 0
    came = Counter()
    for o in rep:
        nxt = next((n for n in by_unit[o["unit"]] if n["line0"] >= o["line1"] - 3 and n["id"] != o["id"]), None)
        c = contact_of_task(L, o)
        if o["trigger"].startswith("contact"):
            if len(c) == 2 and c[0][2] == c[1][2]:
                kinds["тот же контакт, сдвинулся"] += 1
            elif len(c) == 2:
                kinds["другой контакт"] += 1
            else:
                kinds["первый контакт подразделения"] += 1
        else:
            kinds[o["trigger"] or "неизвестно"] += 1
        if nxt is not None:
            d = dist(o["target"], nxt["target"])
            moved.append(d)
            if dist(nxt["target"], o["end"]) < dist(o["target"], o["end"]):
                nearer += 1
        left = o["note"].get("path_tu", 0) - o["walk_tu"]
        if o["cause"] == "задача изменилась":
            came["всего"] += 1
            if o["note"].get("reach") == "full" or left <= o["tu0"]:
                came["хватило бы на ход"] += 1
            elif left <= 2 * o["tu0"]:
                came["хватило бы на два"] += 1
            else:
                came["дальше двух ходов"] += 1
    print(" replaced", len(rep), kinds.most_common())
    moved.sort()
    if moved:
        print(" new target from the old: median", moved[len(moved) // 2], "<=5:", sum(x <= 5 for x in moved), "<=10:", sum(x <= 10 for x in moved), "<=20:", sum(x <= 20 for x in moved), ">20:", sum(x > 20 for x in moved), "of", len(moved), "; new nearer the unit:", nearer)
    print(" cause=task changed, would the old target be in reach:", came.most_common())
    # the reserve
    walk = [(o, d) for o in rows for d in o["decs"] if d["act"] == 2 and d["to"] == o["target"]]
    res = [d for _, d in walk if d["stop"] == "reserve"]
    print(" walks on order", len(walk), "stopped by reserve", len(res), "of them spent 0:", sum(d["spent"] == 0 for d in res), "spent>0:", sum(d["spent"] > 0 for d in res), "; all spent 0 of any stop:", sum(d["spent"] == 0 for _, d in walk))
    print(" stops on order", Counter(d["stop"] for _, d in walk).most_common())
    full = [o for o in closed if o["note"].get("reach") == "full"]
    print(" reach=full", len(full), "arrived", sum(o["cause"] == "выполнен" for o in full), "causes", Counter(o["cause"] for o in full).most_common())
    fullres = [o for o in full if o["cause"] != "выполнен" and any(d["stop"] == "reserve" for d in o["decs"] if d["act"] == 2 and d["to"] == o["target"])]
    print(" reach=full, lost, with a reserve stop on the way:", len(fullres), Counter(o["cause"] for o in fullres).most_common())
    print(" all closed not arrived with a reserve stop as the last walk:", Counter(o["cause"] for o in closed if o["cause"] != "выполнен" and o["last_stop"] == "reserve").most_common())
    # time left: the last decision of the unit in a turn, while a walking order stands
    left = {}
    for o, d in walk:
        left[(o["unit"], d["turn"])] = (d, o)
    tu_left = []
    for (u, t), (d, o) in left.items():
        tu_left.append(max(d["tu"] - d["spent"], 0))
    tu_left.sort()
    if tu_left:
        print(" TU left after the last walk of a turn on order: median", tu_left[len(tu_left) // 2], "n", len(tu_left), ">=20:", sum(x >= 20 for x in tu_left), ">=40:", sum(x >= 40 for x in tu_left))
    # deaths
    cas = {}
    for i, s in enumerate(L):
        if s.startswith("[AICASUALTY]"):
            k = kv(s)
            cas.setdefault(int(k["victim"]), (i, int(k["turn"]), k["side"], k["how"], int(k.get("kfaction", -1)), int(k.get("dist", -1))))
    dead = [o for o in closed if o.get("reason") == "unit_out"]
    side = Counter()
    doing = Counter()
    ks = Counter()
    for o in dead:
        c = cas.get(o["unit"])
        if not c:
            side["нет строки потери"] += 1
            continue
        side["ход игрока" if c[2] == "0" else "свой ход"] += 1
        ks[c[3]] += 1
        ds = [d for d in decisions[o["unit"]] if d["line"] < c[0]]
        if not ds:
            doing["не ходил"] += 1
        else:
            d = ds[-1]
            doing["шёл по приказу" if d["act"] == 2 and d["to"] == o["target"] else ("режим %d" % d["mode"])] += 1
    print(" orders closed by death", len(dead), side.most_common(), ks.most_common(), "last decision:", doing.most_common())
    print(" of those, already walked on the order:", sum(o["walk_tu"] > 0 for o in dead), "gain>0:", sum(o.get("gain", 0) > 0 for o in dead), "turns alive after issue:", Counter(o.get("turn1", 0) - o["turn0"] for o in dead).most_common(4))
    # modes against what the unit sees, first decision of a turn with a walking order standing
    seen_mode = Counter()
    turn_first = {}
    for o in rows:
        for d in o["decs"]:
            key = (o["unit"], d["turn"])
            if key not in turn_first:
                turn_first[key] = d
    for d in turn_first.values():
        k = kv(L[d["line"]])
        vis = bool(k.get("seen") and k["seen"] != "-")
        lab = "видит врага" if vis else "не видит"
        seen_mode[(lab, "патруль" if d["mode"] == 0 else ("засада" if d["mode"] == 1 else ("бой" if d["mode"] == 2 else "побег")))] += 1
    print(" first decision of a unit's turn while an order stands, sees/mode:", sorted(seen_mode.items()))
    # the harm of a closed part in orders
    blocked = [o for o in rows if o["cause"] == "союзник закрыл проход"]
    route = [o for o in rows if o["cause"] == "маршрут стал недоступен"]
    locked = Counter()
    for s in L:
        if s.startswith("[HIVEORD]") and "state=CREATED" in s or (s.startswith("[HIVEORD]") and "state=VALIDATED" in s):
            k = kv(s)
            if k.get("kind") == "STAY":
                locked[k.get("why")] += 1
    print(" ally closed", len(blocked), [(o["id"], o["unit"], o["turn1"], o["note"].get("tiles")) for o in blocked][:10], "route", len(route))
    print(" STAY orders by why (unique creation lines):", locked.most_common(8))
    return rows


if __name__ == "__main__":
    for run in RUNS:
        analyse(run)
