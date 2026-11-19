"""COUNTERFIRE: the record lines of one unit's decisions in a turn and everything logged until the next other unit's decision
(reactions, casualties, exec), trimmed.

  py -3.13 -I fl_window.py <log (timestamps cut)> <turn> <unit> [width]
"""
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")
T, U = sys.argv[2], sys.argv[3]
W = int(sys.argv[4]) if len(sys.argv) > 4 else 330
on = False
for l in open(sys.argv[1], encoding="utf-8", errors="replace"):
    l = l.rstrip("\n")
    if l.startswith("[AIDECIDE] "):
        d = dict(KV.findall(l.split(" hu=")[0]))
        on = d.get("turn") == T and d.get("side") == "1" and d.get("unit") == U
    if on and not l.startswith(("[AILIGHT]", "[AIREUSE]")):
        print(l[:W])
