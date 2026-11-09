"""OPERATIONAL INTELLIGENCE: the full list of kills by tank 470 in M3 s1 D0, per turn, without truncation; the same fields for the mean damage of one melee blow in the chain of 1000000 at t5. Read only."""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from oilib import Battle  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
b = Battle("scpa_D_M3_s1")
k = [(c["turn"], c["victim"]) for c in b.casualties if c.get("killer") == "470" and c.get("how") == "dead"]
print("kills by 470:", len(k), k)
print("per turn:", sorted(Counter(t for t, _ in k).items(), key=lambda x: int(x[0])))
for u in ("1000000", "1000005"):
    print(u, "decisions on t4, spent:", [(d["from"], d["to"], d.get("src"), (d.get("exec") or {}).get("spent")) for d in b.decisions if d["unit"] == u and d["turn"] == "4"])
print("Chryssalids alive at aistart by turn:", [(t, sum(1 for s in b.state[t].values() if "CHRYSSALID" in s.get("type", "") and int(s.get("status", 0)) < 6)) for t in sorted(b.state)][:12])
