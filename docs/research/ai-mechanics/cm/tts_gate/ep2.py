"""NATURAL GATE: L9_s2 turn 2-3 around T 571: order of everything between B's blocked list and B's open list, T's health, what T did afterwards (read only)."""
import gzip
import io
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import gate_lib as G

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ARC = "E:/OXCE_AIWorker/battles_archive/side_turn_scheduler_pilot_2026-10-30/res_scpa.zip"
with zipfile.ZipFile(ARC) as z:
    raw = z.read("out/scpa_D_L9_s2/openxcom.log.gz")
L = [s.rstrip("\n").split("\t")[-1] for s in gzip.open(io.BytesIO(raw), "rt", encoding="utf-8", errors="replace")]
b = G.Battle(L)
print("== every decision and exec between lines 1298 and 1425, unit, cell, action, damage")
for i in range(1298, 1430):
    s = L[i]
    if s.startswith("[AIDECIDE]"):
        k = G.kv(s)
        print(i, "DEC", k["unit"], k["from"], "tu", k["tu"], "act", k["act"], "to", k["to"], "aim", k.get("aim"), "w", k.get("weapon"))
    elif s.startswith("[AIEXEC]"):
        j = json.loads(s[9:])
        print(i, "  EX", j["unit"], j.get("pos"), "tu", j.get("tu"), "sp", j.get("spent"), "dmg", j.get("dmg"), "f", j.get("fdmg"))
    elif s.startswith("[AICASUALTY]"):
        print(i, s[:170])
print("\n== T 571 health and acts through the battle")
for i, s in enumerate(L):
    if s.startswith("[AISTATE]") and " unit=571 " in s:
        k = G.kv(s)
        print(i, s.split(" ")[1], "turn", k["turn"], "pos", k["pos"], "tu", k["tu"], "hp", k["hp"], "stun", k["stun"], "morale", k.get("morale"), "wounds", k.get("wounds"), "sees", k.get("sees"), "seenby", k.get("seenby"))
    elif s.startswith("[AIDECIDE]") and " unit=571 " in s:
        k = G.kv(s)
        print(i, "DEC", "turn", k["turn"], "from", k["from"], "tu", k["tu"], "act", k["act"], "to", k["to"], "w", k.get("weapon"))
    elif s.startswith("[AIEXEC]") and '"unit":571,' in s:
        j = json.loads(s[9:])
        print(i, "  EX", j.get("pos"), "tu", j.get("tu"), "sp", j.get("spent"), "dmg", j.get("dmg"), "stunned", j.get("stunned"), "downed", j.get("downed"), "hp", j.get("hp"), "lost", j.get("hp_lost"))
    elif s.startswith("[AICASUALTY]") and ("victim=571 " in s or "killer=571 " in s):
        print(i, s[:190])
print("\n== B after the turn and the side's losses")
for s in L:
    if s.startswith("[AISTATE]") and " unit=1000014 " in s:
        k = G.kv(s)
        print(s.split(" ")[1], "turn", k["turn"], "pos", k["pos"], "tu", k["tu"], "hp", k["hp"], "weapon", k.get("weapon"), "ammo", k.get("ammo"), "spare", k.get("spare"))
print("\n== the side's casualties in turns 2-4")
for s in L:
    if s.startswith("[AICASUALTY]"):
        k = G.kv(s)
        if 2 <= int(k["turn"]) <= 4:
            print(s[:170])
