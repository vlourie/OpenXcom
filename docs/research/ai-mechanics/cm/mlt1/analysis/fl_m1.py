"""MISSION-LEVEL TACTICS: a base defense battle by its [AIMISSION] lines: is the record the same as D0's, what the task is made of (facilities,
module tiles, target nodes, who can do it) and what came of it (aims, where the shots landed, the module map by turn).

  py -3.13 -I fl_m1.py <D0 battle dir> <probe battle dir>"""
import gzip
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")
TAGS = ("[AIDECIDE] ", "[AISTATE] ", "[AICASUALTY] ", "[AIRESULT] ")
TIME = re.compile(r" v?ms=\d+")


def body(d):
    with gzip.open(Path(d) / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            yield raw.rstrip("\n").split("\t", 2)[-1]


def record(d):
    return [TIME.sub("", s) for s in body(d) if s.startswith(TAGS)]


a, b = record(sys.argv[1]), record(sys.argv[2])
first = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), None)
print(f"identity with D0: lines {len(a)} / {len(b)}, " + ("the same" if first is None and len(a) == len(b) else f"FIRST DIFFERENCE at {first}"))
if first is not None:
    print(" D0:", a[first][:300])
    print(" ML:", b[first][:300])
res = [s for s in b if s.startswith("[AIRESULT]")]
print(res[-1][:300] if res else "no result")

m = []
for s in body(sys.argv[2]):
    if s.startswith("[AIMISSION] "):
        d = dict(KV.findall(s))
        d["_"] = s
        m.append(d)
print("lines by kind:", Counter(d["what"] for d in m).most_common())
start = next((d for d in m if d["what"] == "start"), None)
print("start:", start["_"] if start else None)
print("facilities:", " ".join(f"{d['at']}:{d['type'].replace('STR_', '')}" for d in m if d["what"] == "fac"))
mt = [d for d in m if d["what"] == "mtile"]
print(f"module tiles {len(mt)}; by z:", sorted(Counter(d['at'].split(',')[2] for d in mt).items()), "by armor:", sorted(Counter(int(d['armor']) for d in mt).items()))
print("target nodes:", " ".join(f"{d['at']}(left {d['left']})" for d in m if d["what"] == "node"))
un = [d for d in m if d["what"] == "unit"]
print(f"hostile units {len(un)}, protocol {sum(d['protocol'] == '1' for d in un)}")
print(" weapons of protocol units:", Counter((d["weapon"], d["power"], d["totile"], d["method"]) for d in un if d["protocol"] == "1").most_common(12))
print(" others:", Counter((d["weapon"], d["size"]) for d in un if d["protocol"] != "1").most_common(10))
aims = [d for d in m if d["what"] == "aim"]
print(f"aims {len(aims)}; by (from z, lof, line):", Counter((d["from"].split(",")[2], d["lof"], d["line"]) for d in aims).most_common(12))
print(" impact tile == target:", sum(d["impact"] == d["target"] for d in aims), "of", len(aims), "; targets:", Counter(d["target"] for d in aims).most_common(12))
print(" with tu < cost:", sum(int(d["tu"]) < int(d["cost"]) for d in aims), "units:", len({d["unit"] for d in aims}))
hits = [d for d in m if d["what"] == "hit" and d["side"] == "1"]
print(f"hostile tile hits {len(hits)}; (part, module):", Counter((d["part"], d["module"]) for d in hits).most_common(10))
oh = [d for d in hits if d["module"] == "1" and d["part"] == "3"]
print(" on a module object: tdmg", sorted(int(d["tdmg"]) for d in oh)[:30], "armor", Counter(d["partarmor"] for d in oh).most_common(5), "broke", sum(int(d["tdmg"]) >= int(d["partarmor"]) for d in oh))
print(" tiles hit by side 1 with part<=3:", Counter(d["tile"] for d in hits if int(d["part"]) in range(0, 4)).most_common(12))
ph = [d for d in m if d["what"] == "hit" and d["side"] != "1" and d["module"] == "1" and d["part"] == "3"]
print(" other sides on module objects:", len(ph), "blasts:", sum(d["what"] == "blast" for d in m))
print("nomodule:", Counter(d["from"] for d in m if d["what"] == "nomodule").most_common(10))
print("walks to nodes:", Counter(d["node"] for d in m if d["what"] == "walk").most_common(12))
print("units walking:", len({d["unit"] for d in m if d["what"] == "walk"}))
print("module map:")
last = None
for d in m:
    if d["what"] == "grid":
        s = d["_"].split("left: ")[-1]
        if s != last:
            print(f"  turn {d['turn']} {d['when']}: {s}")
            last = s
