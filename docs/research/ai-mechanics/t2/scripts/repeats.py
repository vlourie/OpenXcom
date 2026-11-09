"""Cycles (pv_analyze hrepeat: the same hostile unit, same turn, the same decision from/tu/act/to right after itself) by act,
and how many of them come right after a target switch ([AITARGETSET] of that unit before the decision); per turn.

  py -3.13 repeats.py <battle dir> [<battle dir> ...]"""
import gzip
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\([^)]*\)|\S+)")
for arg in sys.argv[1:]:
    d = Path(arg)
    last = {}
    rep = Counter()
    after_sw = Counter()
    sw = set()
    turns = 0
    with gzip.open(d / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if body.startswith("[AITARGETSET] "):
                sw.add(dict(KV.findall(body))["unit"])
            elif body.startswith("[AIDECIDE] ") and " side=1 " in body:
                k = dict(KV.findall(body))
                turns = max(turns, int(k["turn"]))
                key = (k["turn"], k["from"], k["tu"], k["act"], k["to"])
                was_sw = k["unit"] in sw
                sw.discard(k["unit"])
                if last.get(k["unit"]) == key:
                    rep[k["act"]] += 1
                    after_sw[k["act"]] += was_sw
                last[k["unit"]] = key
    print(f"{d.name}: turns {turns} repeats {sum(rep.values())} ({sum(rep.values()) / max(1, turns):.1f}/turn) by act {dict(rep)} "
          f"right after a switch {dict(after_sw)}")
