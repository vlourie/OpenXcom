"""Read only: one enemy turn of one battle in order, for the units named: each decision, its source and slots, what it did, attacks at hand with a line of fire, reach near the tile, casualties. args: battle turn unit [unit...]"""
import gzip
import io
import json
import re
import sys
import zipfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
A = Path("E:/OXCE_AIWorker/battles_archive/side_turn_scheduler_pilot_2026-10-30/res_scpa.zip")
b, t = sys.argv[1:3]
units = set(sys.argv[3:])
zf = zipfile.ZipFile(A)
L = [x.rstrip("\n").split("\t")[-1] for x in gzip.open(io.BytesIO(zf.read(f"out/scpa_D_{b}/openxcom.log.gz")), "rt", encoding="utf-8", errors="replace")]
KV = re.compile(r"(\w+)=([^ ]*)")
moves, acts = {}, {}
for s in L:
    m = re.match(r"\[AICAND\] moves=(\w+) unit=\d+ list=(.*)", s)
    if m:
        moves[m.group(1)] = m.group(2)
    m = re.match(r"\[AICAND\] acts=(\w+) unit=\d+ list=(.*)", s)
    if m:
        try:
            acts[m.group(1)] = json.loads(m.group(2))
        except json.JSONDecodeError:
            pass
cur = None
for i, s in enumerate(L):
    if s.startswith("[AIDECIDE]"):
        k = dict(KV.findall(s))
        cur = k if k.get("turn") == t else None
        if cur and (not units or k["unit"] in units):
            print(f'{i} DEC u={k["unit"]} n={k.get("n")} from={k.get("from")} tu={k.get("tu")} mode={k.get("mode")} act={k.get("act")} to={k.get("to")} w={k.get("weapon")} seen={k.get("seen")}')
    elif s.startswith("[AIREC]") and cur and (not units or cur["unit"] in units) and '"base"' in s:
        r = json.loads(s[8:])
        bb = r["base"]
        print("   src", bb.get("src"), "slot", bb.get("slot"), "props", [(p["s"], p["src"], p["sc"], p["t"], p["to"]) for p in (bb.get("reason", {}).get("props") or [])], "trail", (bb.get("reason", {}).get("trail") or [])[:8])
        al = [(c["u"], c["to"], c["t"], c["w"], c["tu"], c["p"], c["d"]) for c in acts.get(r["cand"]["acts"], []) if c.get("k") == "a" and c.get("lof") == 1 and c.get("tu", 0) <= int(cur["tu"])]
        print("   attacks with a line", al[:14])
        mv = moves.get(r["cand"]["moves"], "")
        real = [x for x in mv.split(";") if ":" in x and not x.endswith(":-1")]
        print("   reach", len(real), real[:30])
    elif s.startswith("[AIEXEC]") and cur and (not units or cur["unit"] in units):
        j = json.loads(s[9:])
        print("   EXEC", {k: j.get(k) for k in ("unit", "walk", "pos", "tu", "spent", "hp", "dmg", "fdmg", "fdowned", "downed")})
    elif s.startswith("[AICASUALTY]") and f"turn={t} " in s:
        print("   CAS", s[:230])
