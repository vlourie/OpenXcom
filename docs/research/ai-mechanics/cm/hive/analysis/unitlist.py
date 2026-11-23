"""HIVE COMMAND gate: one D0 log (read only): the enemy at its first turn (type, place, TU, weapon, who it sees), the ruleset's rank and intelligence of each type, what each mode did on turns 1-6 and the first falls. Usage: unitlist.py <log.gz> <Piratez_Factions.rul>"""
import gzip
import re
import sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")
log, rul = sys.argv[1], sys.argv[2]
text = open(rul, encoding="utf-8-sig", errors="replace").read()
units = text[text.index("\nunits:"):]
info = {}
for b in re.split(r"(?m)^  - type: *", units)[1:]:
    name = b.split("\n", 1)[0].strip()
    g = lambda k: (re.search(rf"(?m)^    {k}: *(\S+)", b) or [None, "-"])[1]
    info.setdefault(name, (g("rank"), g("intelligence"), g("aggression"), g("sniper"), g("spotter")))
kv = re.compile(r"(\w+)=([^ ]*)")
start = {}
turn_modes = defaultdict(Counter)
turn_dist = defaultdict(list)
falls = []
players = {}
for line in gzip.open(log, "rt", encoding="utf-8", errors="replace"):
    p = line.rstrip("\n").split("\t")
    if len(p) < 3:
        continue
    m = p[2]
    if m.startswith("[AISTATE] aistart turn=1 "):
        k = dict(kv.findall(m))
        if k["faction"] == "1":
            start[k["unit"]] = k
        else:
            players[k["unit"]] = k
    elif m.startswith("[AIDECIDE]"):
        k = dict(kv.findall(m))
        if k.get("side") == "1" and int(k["turn"]) <= 6:
            turn_modes[int(k["turn"])][("mode" + k["mode"], "act" + k["act"])] += 1
    elif m.startswith("[AICASUALTY]"):
        k = dict(kv.findall(m))
        if int(k["turn"]) <= 6:
            falls.append((k["turn"], k["side"], k["victim"], k["type"][4:20], k["how"], k["killer"], k.get("weapon", "")[:22]))
print("players:", {u: (k["pos"], k["tu"], k.get("rh"), k.get("lh")) for u, k in players.items()})
for u, k in sorted(start.items(), key=lambda x: int(x[0])):
    print(u, k["type"][4:28], info.get(k["type"], "?"), k["pos"], "tu", k["tu"], "hp", k["hp"], "rh", k.get("rh", "-")[:24], "lh", k.get("lh", "-")[:18], "sees", k.get("sees"), "seenby", k.get("seenby"))
for t in sorted(turn_modes):
    print("turn", t, turn_modes[t].most_common(10))
print("falls t<=6:", len(falls))
for f in falls[:40]:
    print(f)
