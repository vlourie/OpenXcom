"""HIVE hardening: every GO order of the V0 logs with one closing reason, and the same refusal repeated (read only). Usage: fate_v0.py <dir>..."""
import gzip
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
kv = re.compile(r"(\w+)=([^ ]*)")
tot = Counter()
rep_all = rep_sum = rep_pairs = 0
for d in sys.argv[1:]:
    orders = {}
    with gzip.open(Path(d) / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for ln in f:
            s = ln.rstrip("\n").split("\t")[-1]
            if not s.startswith("[HIVEORD]"):
                continue
            k = dict(kv.findall(s))
            if "id" not in k or "state" not in k or k.get("kind") != "GO":
                continue
            o = orders.setdefault(k["id"], {"unit": k["unit"], "target": k["target"], "trail": [], "at0": k["at"]})
            o["trail"].append(k["state"])
            o["last"] = k["state"]
            o["note"] = k.get("note", "")
            o["at"] = k["at"]
    c = Counter()
    rep = Counter()
    for o in orders.values():
        ex = "EXECUTING" in o["trail"]
        moved = o["at"] != o["at0"]
        c[("walk" if ex else "nowalk") + ("+moved" if moved else "+still") + ":" + o["last"] + ":" + o["note"].split(" ")[0][:22]] += 1
        if o["last"] == "BLOCKED" and o["note"] == "no_path":
            rep[(o["unit"], o["target"])] += 1
    print(Path(d).name, "GO", len(orders))
    for k, v in c.most_common():
        print("   ", v, k)
    print("    no_path repeated for the same unit+target:", sum(v for v in rep.values() if v > 1), "of", sum(rep.values()), "pairs", len(rep))
    rep_all += sum(v for v in rep.values() if v > 1)
    rep_sum += sum(rep.values())
    rep_pairs += len(rep)
    tot.update(c)
print("ALL", sum(tot.values()), "no_path total", rep_sum, "pairs", rep_pairs, "in repeated pairs", rep_all)
for k, v in tot.most_common():
    print("  ", v, k)
