"""OPERATIONAL INTELLIGENCE, step 3: two checks on the D0 logs. (a) M6 s1, turn 1: the flechette attack with damage 239: which unit, cell, how far from tank 444, the reaction of 444, who was hit and from what. All player's losses caused by the player's own weapons in the three D0 battles. (b) M3 s1: every decision of Chryssalid 1000005 with damage, its last decisions and how it ended. Read only."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from oilib import Battle, kv, pos  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
PL = {"444", "448", "470", "545", "454", "503", "520", "543"}
b = Battle("cc3_CO_M6_s1")
for d in b.attacks:
    if (d.get("exec") or {}).get("dmg", 0) > 100:
        print("big:", d["turn"], d["unit"], d["from"], d["to"], d["weapon"], d.get("target"), (d.get("exec") or {}).get("dmg"), "line", d["line"])
        for s in b.L[d["line"]:d["line"] + 60]:
            if s.startswith("[AIEVENT]") and "reaction" in s or s.startswith("[AICASUALTY]") and "how=dead" in s:
                print("   ", s[:170])
st = b.state[1]
print("player's units at aistart t1:", {u: (st[u]["pos"], st[u]["dir"], st[u]["hp"]) for u in PL if u in st})
for run in ("cc3_CO_M6_s1", "scpa_D_M6_s2", "scpa_D_M3_s1"):
    b = Battle(run)
    own = [c for c in b.casualties if c.get("victim") in PL and c.get("killer") in PL and c.get("how") == "dead"]
    allp = [c for c in b.casualties if c.get("victim") in PL and c.get("how") == "dead"]
    print(run, "player's dead", len({c['victim'] for c in allp}), "by own side", [(c["turn"], c["victim"], c["killer"], c.get("weapon"), c.get("dist")) for c in own])
b = Battle("scpa_D_M3_s1")
ds = [d for d in b.decisions if d["unit"] == "1000005"]
print("1000005 decisions", len(ds), "with damage", [(d["turn"], (d.get("exec") or {}).get("dmg")) for d in ds if (d.get("exec") or {}).get("dmg", 0) > 0], "last", ds[-1]["turn"], ds[-1]["from"], ds[-1]["tu"], ds[-1]["hp"])
print("casualty lines:", [{k: c.get(k) for k in ("turn", "how", "killer", "weapon", "dist")} for c in b.casualties if c.get("victim") == "1000005"][:4])
print("t7 onward states:", [(t, b.state.get(t, {}).get("1000005", {}).get("hp"), b.state.get(t, {}).get("1000005", {}).get("status")) for t in range(6, 13)])
print("result", {k: b.result.get(k) for k in ("how", "turn", "pdead", "hdead")})
print("alive of AI side by turn:", [(t, sum(1 for k in b.state[t].values() if k.get("faction") == "1" and int(k.get("status", 0)) < 6)) for t in sorted(b.state)][:14])
