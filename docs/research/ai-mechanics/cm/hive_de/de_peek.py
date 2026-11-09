"""Read only: the lines of one battle round a unit's decision, cut short. args: battle unit turn [count]"""
import gzip
import io
import sys
import zipfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
A = Path("E:/OXCE_AIWorker/battles_archive/side_turn_scheduler_pilot_2026-10-30/res_scpa.zip")
b, u, t = sys.argv[1:4]
cnt = int(sys.argv[4]) if len(sys.argv) > 4 else 6
zf = zipfile.ZipFile(A)
L = [x.rstrip("\n").split("\t")[-1] for x in gzip.open(io.BytesIO(zf.read(f"out/scpa_D_{b}/openxcom.log.gz")), "rt", encoding="utf-8", errors="replace")]
hit = [i for i, s in enumerate(L) if s.startswith("[AIDECIDE]") and f"unit={u} " in s and f"turn={t} " in s]
print(len(L), hit[:8])
for i in hit[:1]:
    for j in range(max(0, i - cnt), min(len(L), i + cnt)):
        print(j, L[j][:240])
print("AICAND lines of the unit:", sum(s.startswith("[AICAND]") and f"unit={u} " in s for s in L))
for s in [s for s in L if s.startswith("[AICAND]")][:400:80]:
    print(s[:100])
print("no list:", sum(s.startswith("[AICAND]") and " list=" not in s for s in L), "of", sum(s.startswith("[AICAND]") for s in L))
print("empty/short lists:", sum(s.startswith("[AICAND]") and len(s.split(" list=")[-1]) < 8 for s in L))
