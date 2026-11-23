"""Movement diagnosis: one final cause per walking order, by a fixed order of tests; prints the table and writes ledger_<run>.tsv (read only on the logs)."""
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from ledger import load, summarise  # noqa: E402
from lib import kv  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
CATS = ["выполнен", "погиб или выбыл", "переключился на бой", "задача изменилась", "закончились TU", "приблизился, не дошёл", "союзник закрыл проход", "маршрут стал недоступен", "не получил хода", "открыт на срезе боя"]


def replaced_trigger(o, L, tasks):
    """What changed the squad's task just before this order was replaced: the nearest squad line of the same turn."""
    prev = [(i, s) for i, s in tasks[o["squad"]] if i <= o["line1"] and f"turn={o['turn1']} " in s]
    for i, s in reversed(prev):
        if s.startswith("[HIVETASK]"):
            k = kv(s)
            if "kept" in k or "refused_contacts" in k:
                continue
            if "from" in k:
                return "из HOLD в SEARCH"
            if k.get("state") == "BLOCKED":
                return "цель снята: " + k.get("why", "?")
            if k.get("kind") == "contact":
                return "contact:" + k["contact"]
            if k.get("kind") == "sector_node":
                return "узел сектора"
        if s.startswith("[HIVEHOLD]"):
            return "HOLD заново"
    for j in range(o["line1"], max(o["line1"] - 400, 0), -1):
        s = L[j]
        if s.startswith("[HIVESQUAD]") and "merged=" in s and (f"into={o['squad']} " in s or f"merged={o['squad']} " in s):
            return "слияние подразделений"
    return "неизвестно"


def cause(o, L, tasks):
    if o.get("fate") == "ARRIVED":
        return "выполнен"
    if o.get("reason") == "unit_out":
        return "погиб или выбыл"
    if o.get("reason") in ("no_path_now", "no_progress"):
        return o["route"]
    if "fate" not in o:
        return "открыт на срезе боя"
    if o["own_tu"] > o["walk_tu"] or (o["walk_tu"] == 0 and (o["n_attack"] or o["n_ownwalk"])):
        return "переключился на бой"
    if o["walk_tu"] == 0 and o["own_tu"] == 0:
        return "задача изменилась" if o["reason"] == "replaced" else "не получил хода"
    if o["reason"] == "replaced":
        return "задача изменилась"
    if o["last_stop"] in ("tu", "reserve", "energy"):
        return "закончились TU"
    return "приблизился, не дошёл"


def route_cause(o, L):
    """A refusal: the same place and a field fallen at least by half is a part closed; anything else is the route itself."""
    k = None
    for j in range(o["line1"] - 1, max(o["line1"] - 4, 0), -1):
        if L[j].startswith("[HIVEREACH]"):
            k = kv(L[j])
            break
    plan = o["note"].get("tiles", -1)
    if k and plan > 0 and tuple(map(int, k["at"].strip("()").split(","))) == o["start"] and int(k["tiles"]) * 2 <= plan:
        return "союзник закрыл проход"
    return "маршрут стал недоступен"


def run_table(run):
    L, orders, decisions, tasks = load(run)
    rows = []
    for o in orders.values():
        summarise(o, decisions)
        if o.get("reason") in ("no_path_now", "no_progress"):
            o["route"] = route_cause(o, L)
        o["cause"] = cause(o, L, tasks)
        o["trigger"] = replaced_trigger(o, L, tasks) if o.get("reason") == "replaced" else ""
        rows.append(o)
    return L, rows, decisions


if __name__ == "__main__":
    for run in sys.argv[1:]:
        L, rows, decisions = run_table(run)
        c = Counter(o["cause"] for o in rows)
        n = len(rows)
        failed = n - c["выполнен"] - c["открыт на срезе боя"]
        print("==", run, "приказов", n, "не дошли, закрыты", failed)
        for x in CATS:
            print(f"  {x:28s} {c[x]:4d}  {100 * c[x] / n:5.1f}% всех  {100 * c[x] / failed if x not in ('выполнен', 'открыт на срезе боя') else 0:5.1f}% незавершённых")
        print("  по причине закрытия у 'переключился на бой':", Counter(o.get("reason") for o in rows if o["cause"] == "переключился на бой").most_common())
        print("  причины смены задачи (все replaced):", Counter(("contact" if o["trigger"].startswith("contact") else o["trigger"]) for o in rows if o.get("reason") == "replaced").most_common())
        print("  задача изменилась, сместились ближе:", sum(o["cause"] == "задача изменилась" and o.get("gain", 0) > 0 for o in rows), "не сдвинулись:", sum(o["cause"] == "задача изменилась" and o.get("fate") == "NOT_MOVED" for o in rows))
        print("  доля TU на приказ / своё по всем закрытым:", sum(o["walk_tu"] for o in rows), sum(o["own_tu"] for o in rows))
        print("  ходов до закрытия:", Counter(o.get("turn1", -1) - o["turn0"] for o in rows if "turn1" in o).most_common())
        print("  запас: приказ на 1 ход (reach=full)", sum(o["note"].get("reach") == "full" for o in rows), "на 2+ (partial)", sum(o["note"].get("reach") == "partial" for o in rows), "из partial дошли", sum(o["note"].get("reach") == "partial" and o["cause"] == "выполнен" for o in rows), "из full дошли", sum(o["note"].get("reach") == "full" and o["cause"] == "выполнен" for o in rows))
        with open(HERE / f"ledger_{run}.tsv", "w", encoding="utf-8-sig") as f:
            f.write("id\tunit\tsquad\ttask\twhy\tturn0\tturn1\tstart\ttarget\tend\tpath_tu\treach\ttiles\tfate\treason\tgain\twalk_tu\town_tu\tn_walk\tn_ownwalk\tn_attack\tlast_stop\tcause\ttrigger\n")
            for o in rows:
                f.write("\t".join(str(x) for x in (o["id"], o["unit"], o["squad"], o["task"], o["why"], o["turn0"], o.get("turn1", ""), o["start"], o["target"], o.get("end", ""), o["note"].get("path_tu", ""), o["note"].get("reach", ""), o["note"].get("tiles", ""), o.get("fate", "OPEN"), o.get("reason", "open"), o.get("gain", ""), o["walk_tu"], o["own_tu"], o["n_walk"], o["n_ownwalk"], o["n_attack"], o["last_stop"], o["cause"], o["trigger"])) + "\n")
        # the side's decisions while a walking order stands
        turns = {}
        for o in rows:
            for d in o["decs"]:
                key = (o["unit"], d["turn"])
                t = turns.setdefault(key, dict(first=None, order=0, own=0, tu0=d["tu"]))
                if t["first"] is None:
                    t["first"] = d
                on = d["act"] == 2 and d["to"] == o["target"]
                t["order" if on else "own"] += d["spent"]
        first = Counter(("патруль по приказу" if t["first"]["act"] == 2 and t["first"]["mode"] == 0 else "режим %d act %d" % (t["first"]["mode"], t["first"]["act"])) for t in turns.values())
        print("  ходов бойца с приказом на ходьбу:", len(turns), "первое решение:", first.most_common(8))
        print("  из них приказу досталось больше TU:", sum(t["order"] > t["own"] for t in turns.values()), "своему решению:", sum(t["own"] > t["order"] for t in turns.values()), "ни то ни другое:", sum(t["own"] == t["order"] for t in turns.values()))
