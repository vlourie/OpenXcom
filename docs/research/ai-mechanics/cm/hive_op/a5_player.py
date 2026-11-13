"""COORDINATED OPERATION, phase A, point 6: what the player could do to the staged fighters between the turns in M3 s1 D0. Each event, reaction and casualty on turns 4 (AI side) and 5 (both sides) in the log's order, with the decisions of the player's bot on turn 5 by tank 470. Read only."""
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "oi"))
sys.path.insert(0, str(HERE.parent / "mc"))
from lib import kv  # noqa: E402
from oilib import Battle  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
b = Battle("scpa_D_M3_s1")
turn = side = None
for s in b.L:
    if s.startswith(("[AIEVENT]", "[AICASUALTY]", "[AIDECIDE]")):
        k = kv(s)
        t = int(k.get("turn", -1))
        if s.startswith("[AIEVENT]") and t in (4, 5) and k.get("what") == "reaction":
            print("reaction t", t, "side", k.get("side"), "unit", k.get("unit"), "at", k.get("pos"), s[:150])
        if s.startswith("[AICASUALTY]") and t in (4, 5, 6) and k.get("how") == "dead":
            print("dead t", t, "side", k.get("side"), k.get("victim"), k.get("type", "")[4:16], k.get("pos"), "by", k.get("killer"), k.get("weapon"), "dist", k.get("dist"))
        if s.startswith("[AIDECIDE]") and k.get("side") == "0" and t == 5 and k.get("unit") == "470":
            print("bot 470 t5:", k.get("from"), "tu", k.get("tu"), "mode", k.get("mode"), "act", k.get("act"), "to", k.get("to"), "aim", k.get("aim"), "weapon", k.get("weapon"), "seen", k.get("seen"))
