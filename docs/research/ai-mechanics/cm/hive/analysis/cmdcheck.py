"""HIVE COMMAND CORE V0: commander changes checked apart from the code's own kept=1 (read only). Was the new one a member of the squad at the start, was the old one really out by the unit's own records, did the squad's orders before and after carry the same task and objective. Prints the first change in full as an example. Usage: cmdcheck.py <dir>"""
import gzip
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
kv = re.compile(r"(\w+)=([^ ]*)")
lines = [ln.rstrip("\n").split("\t")[-1] for ln in gzip.open(Path(sys.argv[1]) / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace")]

members = {}
for s in lines:
    if s.startswith("[HIVESQUAD] id="):
        k = dict(kv.findall(s))
        members[k["id"]] = {re.sub(r"\D", "", m) for m in k["members"].split(",")}
    elif s.startswith("[HIVESQUAD] turn=") and " merged=" in s:
        k = dict(kv.findall(s))
        members.setdefault(k["into"], set()).update(members.get(k["merged"], set()))
    elif s.startswith("[HIVESQUAD] turn=") and " join=" in s:
        k = dict(kv.findall(s))
        members.setdefault(k["squad"], set()).add(k["join"])

falls = {}
for s in lines:
    if s.startswith("[AICASUALTY]"):
        k = dict(kv.findall(s))
        falls.setdefault(k["victim"], (int(k["turn"]), k.get("how")))


def orders(squad, turn):
    c = Counter()
    for s in lines:
        if s.startswith("[HIVEORD]") and f" squad={squad} " in s and f" turn={turn} " in s and " state=CREATED" in s:
            k = dict(kv.findall(s))
            c[(k["task"], k["kind"], k["target"])] += 1
    return c


def tasks(squad, upto):
    out = []
    for s in lines:
        if s.startswith("[HIVETASK]") and f" squad={squad} " in s:
            k = dict(kv.findall(s))
            if int(k["turn"]) <= upto:
                out.append(k)
    return out


rows = 0
good = Counter()
first = True
for s in lines:
    if not s.startswith("[HIVECMD]"):
        continue
    k = dict(kv.findall(s))
    rows += 1
    t, sq, old, new = int(k["turn"]), k["squad"], k["old"], k["new"]
    good["new_was_member"] += new in members.get(sq, set())
    good["old_fell_in_records"] += old in falls and falls[old][0] <= t
    before = {x[0] for x in orders(sq, t - 1)}
    after = {x[0] for x in orders(sq, t)}
    good["same_task_in_orders"] += (not before or not after or before == after)
    good["new_has_order_or_acts"] += any(f" unit={new} " in o and f" turn={t} " in o for o in lines if o.startswith("[HIVEORD]"))
    if first:
        first = False
        print("example:", s[:150])
        print("  the old one's fall:", falls.get(old))
        print("  squad's orders, turn", t - 1, dict(orders(sq, t - 1).most_common(6)))
        print("  squad's orders, turn", t, dict(orders(sq, t).most_common(6)))
        tk = tasks(sq, t)
        print("  squad's objectives so far:", [(x["turn"], x.get("objective"), x.get("contact")) for x in tk][-4:])
print("changes", rows, dict(good))
