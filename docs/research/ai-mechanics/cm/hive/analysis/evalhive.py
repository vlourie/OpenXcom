"""HIVE COMMAND CORE V0: one active battle against its D0 journal (read only). The first difference and whether the order explains it; orders by state and real result, per task; how many units ended near the order's target; commander changes; contact fairness against the sides' own [AISTATE] lines; the measure at the limit. Usage: evalhive.py <active dir> <D0 dir> <turn limit>"""
import gzip
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
kv = re.compile(r"(\w+)=([^ ]*)")
limit = int(sys.argv[3])


def read(d):
    with gzip.open(Path(d) / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        return [ln.rstrip("\n").split("\t")[-1] for ln in f]


def pos(s):
    return tuple(int(v) for v in s.strip("()").split(","))


def dist(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1])) + 2 * abs(a[2] - b[2])


def summary(lines):
    dec = defaultdict(lambda: defaultdict(int))
    out = {"pfall": [], "hfall": [], "turn_shots": Counter(), "tu": defaultdict(list), "result": {}, "walk": 0, "pat": Counter(), "patwalk": Counter(), "patstop": Counter()}
    for s in lines:
        if s.startswith("[AIDECIDE]"):
            k = dict(kv.findall(s))
            if k.get("side") != "1" or int(k["turn"]) > limit:
                continue
            t = int(k["turn"])
            if k["act"] in ("6", "7", "8", "9", "10", "11", "12"):
                out["turn_shots"][t] += 1
            if k["mode"] == "0":
                out["pat"][t] += 1
                if k["act"] == "2":
                    out["patwalk"][t] += 1
                elif k["act"] == "0":
                    out["patstop"][t] += 1
        elif s.startswith("[AICASUALTY]"):
            k = dict(kv.findall(s))
            if int(k["turn"]) > limit:
                continue
            (out["pfall"] if k.get("vfaction") == "0" else out["hfall"]).append((int(k["turn"]), k["victim"], k.get("how"), k.get("killer")))
        elif s.startswith("[AISTATE] pstart "):
            k = dict(kv.findall(s))
            if k.get("faction") == "1" and k.get("status") not in ("6", "7") and int(k["turn"]) <= limit + 1:
                out["tu"][int(k["turn"]) - 1].append(int(k["tu"]) * 100 // max(1, int(k.get("tumax", 1))))
        elif s.startswith("[AIRESULT]"):
            out["result"] = dict(kv.findall(s))
    return out


def state_at_limit(lines):
    php, hhp = {}, {}
    for s in lines:
        if s.startswith("[AISTATE] pstart ") or s.startswith("[AISTATE] aistart "):
            k = dict(kv.findall(s))
            if int(k["turn"]) > limit + 1:
                continue
            if k.get("faction") == "0":
                php[k["unit"]] = (int(k["hp"].split("/")[0]), k.get("status"))
            elif k.get("faction") == "1":
                hhp[k["unit"]] = (int(k["hp"].split("/")[0]), k.get("status"))
    return php, hhp


a = read(sys.argv[1])
d = read(sys.argv[2])
TAGS = ("[AIDECIDE]", "[AICASUALTY]", "[AISTATE]", "[AIEXEC]", "[AIEVENT]")
fa = [s for s in a if s.startswith(TAGS)]
fd = [s for s in d if s.startswith(TAGS)]
n = min(len(fa), len(fd))
first = next((i for i in range(n) if fa[i] != fd[i]), None)
print("identical lines before the first difference:", first if first is not None else n)
if first is not None:
    print(" active:", fa[first][:190])
    print(" D0    :", fd[first][:190])
    k = dict(kv.findall(fa[first]))
    u = k.get("unit")
    t = k.get("turn")
    before = [s for s in a if s.startswith("[HIVEORD]") and f" unit={u} " in s and f"turn={t} " in s]
    print(" orders of that unit that turn:")
    for s in before[:5]:
        print("   ", s[:210])

orders = defaultdict(dict)
states = Counter()
own = Counter()
for s in a:
    if s.startswith("[HIVEORD]"):
        k = dict(kv.findall(s))
        if "own" in k:
            own[k["own"]] += 1
            continue
        if "id" not in k:
            states["NONE"] += 1
            continue
        o = orders[k["id"]]
        o.update({"unit": k["unit"], "task": k["task"], "kind": k["kind"], "target": k["target"], "turn0": o.get("turn0", int(k["turn"])), "why": k["why"], "squad": k["squad"]})
        o.setdefault("trail", []).append(k["state"])
        o["last"] = k["state"]
        o["at"] = k["at"]
        o["note"] = k.get("note")
        o["lastturn"] = int(k["turn"])
print("orders:", len(orders), "last state:", Counter(o["last"] for o in orders.values()).most_common())
print("by kind and result:")
tab = Counter((o["task"], o["kind"], o["why"], o["last"]) for o in orders.values())
for key, v in sorted(tab.items()):
    print("  ", key, v)
print("the units' own decisions over an order, by action type:", own.most_common())
go = [o for o in orders.values() if o["kind"] == "GO"]
done = [o for o in go if o["last"] == "COMPLETED"]
print("GO orders:", len(go), "completed:", len(done), "by distinct units:", len({o["unit"] for o in done}), "by distinct squads:", len({o["squad"] for o in done}), "of tasks:", Counter(o["task"] for o in done))
near = sum(dist(pos(o["at"]), pos(o["target"])) <= 2 for o in done)
print(" of the completed, the unit really within 2 tiles of the target at the last record:", near)
print("commander changes:")
for s in a:
    if s.startswith("[HIVECMD]"):
        print("  ", s[:170])
print("task changes:", sum(s.startswith("[HIVETASK]") and " to=" in s for s in a), "| objectives set:", sum(s.startswith("[HIVETASK]") and " objective=" in s for s in a))
print("squad events:", sum(s.startswith("[HIVESQUAD] turn=") for s in a))

# fairness: each [HIVEFAIR] pair of the first turn's opening against what the observer's own aistart line says it sees, when one was written that turn
sees = {}
fair = bad = 0
for s in a:
    if s.startswith("[AISTATE] aistart "):
        k = dict(kv.findall(s))
        if k.get("faction") == "1":
            sees[(k["turn"], k["unit"])] = set(k.get("sees", "-").split(","))
    elif s.startswith("[HIVEFAIR]"):
        k = dict(kv.findall(s))
        got = sees.get((k["turn"], k["observer"]))
        if got is not None:
            fair += 1
            if k["target"] not in got:
                bad += 1
print("contact records with the observer's own line for that turn:", fair, "target not in its sees at the start of the side's turn (may have come into sight since):", bad, "of all", sum(s.startswith("[HIVEFAIR]") for s in a))

sa, sd = summary(a), summary(d)
pa, ha = state_at_limit(a)
pd, hd = state_at_limit(d)
for name, s, p, h in (("active", sa, pa, ha), ("D0", sd, pd, hd)):
    # no live or hp here: a unit's last line stays after it falls and counted the fallen as live; curve.py counts them turn by turn
    print(f"{name}: player falls {len({x[1] for x in s['pfall']})}, hostile down {len({x[1] for x in s['hfall']})}, shots {sum(s['turn_shots'].values())}")
print("per turn: patrol decisions (walks, stops) | shots | TU% left at the player's turn; active / D0")
for t in range(1, limit + 1):
    fmt = lambda s: f"{s['pat'][t]}({s['patwalk'][t]},{s['patstop'][t]}) {s['turn_shots'][t]} {sum(s['tu'].get(t, [0])) // max(1, len(s['tu'].get(t, [0])))}"
    print(f"  {t:2d}: {fmt(sa)}  /  {fmt(sd)}")
print("result:", {k: sa["result"].get(k) for k in ("how", "turn", "phplost", "pdead", "hdead", "hattacks", "pattacks", "livesoldiers", "livealiens", "ms")})
for s in a:
    if s.startswith("[HIVETURN]"):
        print("  ", s[:330])
print("plan, us:", [dict(kv.findall(s)).get("us") for s in a if s.startswith("[HIVEPERF]")])
