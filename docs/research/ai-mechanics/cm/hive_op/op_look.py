"""COORDINATED OPERATION, phase C: one run read in full. All [HIVEOP] lines in order, the decisions and execution of the operation's fighters on the operation's turns, reactions and casualties of those turns, the target's state lines. Usage: op_look.py <run dir name> [short]"""
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "oi"))
sys.path.insert(0, str(HERE.parent / "mc"))
from lib import kv  # noqa: E402
from oilib import Battle  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
run = sys.argv[1]
b = Battle(run)
lines = [s for s in b.L if s.startswith("[HIVEOP]")]
print("== HIVEOP lines:", len(lines))
said = set()
for s in lines:
    if s in said:  # sideEnds comes many times with the same state on the bot's turn
        continue
    said.add(s)
    print(" ", s[9:300])
fighters, target, turns = set(), None, set()
for s in lines:
    k = kv(s)
    if k.get("event") == "ASSIGN":
        fighters.add(k["unit"])
        turns.add(int(k["turn"]))
        turns.add(int(k["turn"]) + 1)
    if k.get("event") == "PROPOSED":
        target = k.get("target")
print("== fighters", sorted(fighters), "target", target, "turns", sorted(turns))
print("== decisions")
for d in b.decisions:
    if d["unit"] in fighters and int(d["turn"]) in turns:
        e = d.get("exec") or {}
        print(" ", d["turn"], d["unit"], d["from"], "tu", d["tu"], "mode", d["mode"], "src", d.get("src"), "act", d.get("act"), "to", d["to"], "aim", d["aim"], "seen", d.get("seen"), "spent", e.get("spent"), "dmg", e.get("dmg"))
print("== state lines")
for s in b.L:
    if s.startswith("[AISTATE]"):
        k = kv(s)
        if int(k.get("turn", 0)) in turns and k.get("unit") in fighters | {target}:
            print(" ", s.split(" ", 2)[1], "t", k["turn"], k["unit"], "pos", k["pos"], "dir", k["dir"], "tu", k["tu"], "hp", k["hp"], "status", k.get("status"), "sees", k.get("sees"), "seenby", k.get("seenby"))
print("== reactions and casualties on these turns")
for s in b.L:
    if s.startswith("[AIEVENT]") or s.startswith("[AICASUALTY]"):
        k = kv(s)
        if int(k.get("turn", -1)) in turns and (s.startswith("[AICASUALTY]") or k.get("what") == "reaction"):
            print(" ", s[:210])
ends = [s for s in b.L if s.startswith("[AIRESULT]")]
print("== result:", ends[-1][:240] if ends else "no AIRESULT")
