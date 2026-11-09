"""Read only: one lost unit-turn, its AIREC cand fields against the moves list of that hash. args: battle unit turn"""
import gzip
import io
import json
import re
import sys
import zipfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
A = Path("E:/OXCE_AIWorker/battles_archive/side_turn_scheduler_pilot_2026-10-30/res_scpa.zip")
b, u, t = sys.argv[1:4]
zf = zipfile.ZipFile(A)
L = [x.rstrip("\n").split("\t")[-1] for x in gzip.open(io.BytesIO(zf.read(f"out/scpa_D_{b}/openxcom.log.gz")), "rt", encoding="utf-8", errors="replace")]
moves = {}
for s in L:
    m = re.match(r"\[AICAND\] moves=(\w+) unit=(\d+) list=(.*)", s)
    if m:
        moves[m.group(1)] = (m.group(2), m.group(3).split(";"))
print("lists", len(moves), "sizes", sorted(len(v[1]) for v in moves.values())[:10], "...", sorted(len(v[1]) for v in moves.values())[-10:])
hit = [i for i, s in enumerate(L) if s.startswith("[AIDECIDE]") and f"unit={u} " in s and f"turn={t} " in s]
for i in hit[:4]:
    print(L[i][:200])
    for j in range(i + 1, i + 12):
        s = L[j]
        if s.startswith("[AIREC]"):
            r = json.loads(s[8:])
            c = r["cand"]
            print("  cand", c, "state.tu", r["state"]["tu"], "pos", r["state"]["pos"], "base", {k: r["base"].get(k) for k in ("k", "t", "to", "src", "mode", "slot", "exp")})
            mv = moves.get(c["moves"])
            if mv:
                print("  list of the hash: logged for unit", mv[0], "n", len(mv[1]), "head", mv[1][:6], "max tu", max(int(x.split(":")[1]) for x in mv[1] if ":" in x and not x.endswith(":-1")))
            break
        print("  ", s[:110])
