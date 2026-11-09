"""AI_TACTICAL_DIRECTOR_V1 diagnostics: (1) unit-turns with the most director orders (the lines), (2) what the units with role S
were told, first order of each unit-turn and all orders.

  py -3.13 -I td_peek.py <out dir> <prefix>"""
import gzip
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT, P = Path(sys.argv[1]), sys.argv[2]
KV = re.compile(r"(\w+)=(\([^)]*\)|\S+)")
first_s, all_s = Counter(), Counter()
worst = []
for d in sorted(OUT.glob(f"{P}_*")):
    f = d / "openxcom.log.gz"
    if not f.exists():
        continue
    per = defaultdict(list)
    with gzip.open(f, "rt", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if body.startswith("[AIPROBE] td turn="):
                k = dict(KV.findall(body))
                per[(int(k["turn"]), k["unit"])].append((k["role"], k["order"], k.get("why", ""), body))
    for key, lst in per.items():
        n = sum(1 for _, o, _, _ in lst if o not in ("KEEP", "FREE", "HOLD"))
        worst.append((n, d.name, key, lst))
        if lst[0][0] == "S":
            first_s[lst[0][1] + ":" + lst[0][2].split(" ")[0]] += 1
            for r, o, w, _ in lst:
                all_s[o] += 1
worst.sort(key=lambda x: -x[0])
for n, name, key, lst in worst[:2]:
    print(f"== {name} turn {key[0]} unit {key[1]}: {n} orders")
    for *_, body in lst:
        print("  ", body[18:230])
print("S first order:", dict(first_s.most_common()))
print("S all orders:", dict(all_s.most_common()))
