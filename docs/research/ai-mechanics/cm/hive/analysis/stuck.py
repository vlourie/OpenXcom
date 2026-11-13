"""HIVE COMMAND CORE V0: the units refused 'no path' most often: where they stood and walked here and in D0, and what they were refused (read only). Also the oddities: an order with two ends; a STAY unit that patrol-walked. Usage: stuck.py <active dir> <D0 dir> <n units>"""
import gzip
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
kv = re.compile(r"(\w+)=([^ ]*)")


def read(d):
    with gzip.open(Path(d) / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        return [ln.rstrip("\n").split("\t")[-1] for ln in f]


a = read(sys.argv[1])
d = read(sys.argv[2])
n = int(sys.argv[3])

ref = Counter()
targets = defaultdict(Counter)
at = defaultdict(Counter)
for s in a:
    if s.startswith("[HIVEORD]") and "state=BLOCKED" in s and "note=no_path" in s:
        k = dict(kv.findall(s))
        ref[k["unit"]] += 1
        targets[k["unit"]][k["target"]] += 1
        at[k["unit"]][k["at"]] += 1
info = {}
for s in a:
    if s.startswith("[HIVEUNIT]"):
        k = dict(kv.findall(s))
        info[k["id"]] = f"{k['type']} move={k['move']} size={k['size']} start={k['pos']}"


def walks(lines, u, last):
    out = []
    for s in lines:
        if s.startswith("[AIDECIDE]") and f" unit={u} " in s:
            k = dict(kv.findall(s))
            if int(k["turn"]) > last:
                break
            out.append(f"t{k['turn']} {k['from']} m{k['mode']} a{k['act']}" + (f">{k['to']}" if k["act"] == "2" else ""))
    return out


for u, c in ref.most_common(n):
    print(f"--- {u} refused {c}: {info.get(u)}")
    print("   refused while at:", at[u].most_common(5))
    print("   refused targets:", targets[u].most_common(5))
    wa = walks(a, u, 12)
    wd = walks(d, u, 12)
    print("   active:", " | ".join(wa[:14]))
    print("   D0    :", " | ".join(wd[:14]))
    print("   D0 walks to another floor or far:", sum("a2>" in x for x in wd), "of", len(wd))

chain = defaultdict(list)
for s in a:
    if s.startswith("[HIVEORD]"):
        k = dict(kv.findall(s))
        if "id" in k and "state" in k:
            chain[k["id"]].append((k["turn"], k["state"], k.get("kind"), k.get("why"), k.get("note", "")))
OPEN = {"CREATED", "ASSIGNED", "VALIDATED", "EXECUTING"}
for i, c in chain.items():
    if sum(x[1] not in OPEN for x in c) > 1:
        print("two ends:", i, c)

stay = set()
for s in a:
    if s.startswith("[HIVEORD]"):
        k = dict(kv.findall(s))
        if k.get("turn") == "1" and k.get("kind") == "STAY" and k.get("state") == "VALIDATED":
            stay.add(k["unit"])
for s in a:
    if s.startswith("[AIDECIDE]"):
        k = dict(kv.findall(s))
        if k.get("side") == "1" and k["turn"] == "1" and k["mode"] == "0" and k["act"] == "2" and k["unit"] in stay:
            print("STAY unit walked on patrol:", s[:150])
            for o in a:
                if o.startswith("[HIVEORD]") and " turn=1 " in o and f" unit={k['unit']} " in o:
                    print("    ", o[:175])
