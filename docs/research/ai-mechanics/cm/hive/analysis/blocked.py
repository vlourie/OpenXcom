"""HIVE COMMAND CORE V0: what stands behind the BLOCKED orders of one battle, and the units' decisions around one of them (read only). Usage: blocked.py <dir>"""
import gzip
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
kv = re.compile(r"(\w+)=([^ ]*)")
lines = [ln.rstrip("\n").split("\t")[-1] for ln in gzip.open(Path(sys.argv[1]) / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace")]
why = Counter()
samples = []
for i, s in enumerate(lines):
    if s.startswith("[HIVEORD]") and "state=BLOCKED" in s:
        k = dict(kv.findall(s))
        why[(k.get("note"), k["why"])] += 1
        if len(samples) < 40:
            samples.append(i)
print(why.most_common())
tu = Counter()
for i in samples:
    k = dict(kv.findall(lines[i]))
    tu[int(k["tu"]) // 20 * 20] += 1
print("TU at the block, by 20:", sorted(tu.items()))
shown = 0
for i in samples:
    k = dict(kv.findall(lines[i]))
    if k.get("note") == "no_progress" and shown < 4:
        shown += 1
        print("---", lines[i][:200])
        u = k["unit"]
        got = [s for s in lines[max(0, i - 200):i + 1] if f"unit={u} " in s and (s.startswith("[AIDECIDE]") or s.startswith("[AIEXEC]") or s.startswith("[HIVEORD]") or s.startswith("[AIEVENT]"))]
        for s in got[-9:]:
            print("   ", s[:170])
shown = 0
for i in samples:
    k = dict(kv.findall(lines[i]))
    if k.get("note") == "no_path" and shown < 4:
        shown += 1
        print("=== no_path", lines[i][:200])
print("kinds of AIDECIDE with act=0 by mode:", Counter(dict(kv.findall(s)).get("mode") for s in lines if s.startswith("[AIDECIDE]") and " side=1 " in s and " act=0 " in s).most_common())
print("stays recorded:", sum(1 for s in lines if s.startswith("[HIVEORD]") and "note=stays" in s))
