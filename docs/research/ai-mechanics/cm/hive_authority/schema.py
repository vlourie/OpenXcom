"""AUTHORITY CONTRACT research: what the archives hold and how each log tag looks. Read only."""
import gzip
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
S = Path("C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad")
A = Path("E:/OXCE_AIWorker/battles_archive/side_turn_scheduler_pilot_2026-10-30")
for z in ("res_scpa.zip", "res_scpb.zip"):
    names = [n for n in zipfile.ZipFile(A / z).namelist() if n.endswith("log.gz")]
    print(z, len(names))
    print("  ", sorted(re.sub(r".*/", "", n.rsplit("/", 1)[0]) for n in names)[:70])
arch = Path("E:/OXCE_AIWorker/battles_archive")
print("archives:", sorted(p.name for p in arch.iterdir())[-40:])
with gzip.open(S / "hive/res/out/op2_OO_M3_s1/openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
    L = [x.rstrip("\n").split("\t")[-1] for x in f]
print(Counter(s.split(" ", 1)[0] for s in L if s.startswith("[")).most_common(40))
for tag, n, w in (("[AISTATE] aistart", 2, 450), ("[AISTATE] pstart", 1, 450), ("[AIDECIDE]", 1, 450), ("[AIEXEC]", 2, 500), ("[AIREC]", 1, 1200), ("[AICAND]", 1, 600), ("[AICASUALTY]", 1, 450), ("[AIEVENT]", 2, 300), ("[AISTATE] end", 1, 400), ("[AISTATE] before", 1, 400)):
    rows = [s for s in L if s.startswith(tag)]
    print(tag, len(rows))
    for s in rows[len(rows) // 2:len(rows) // 2 + n]:
        print("  ", s[:w])
