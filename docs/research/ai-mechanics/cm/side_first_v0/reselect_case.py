"""SIDE-FIRST COMBAT: every log line of one unit in one turn, to read a case of the director acting after the mark by eye, and every walk that began marked. args: zip label turn unit"""
import gzip
import io
import re
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
zp, label, turn, unit = sys.argv[1:5]
z = zipfile.ZipFile(zp)
ls = [s.split("\t")[-1] for s in gzip.open(io.BytesIO(z.read(f"out/{label}/openxcom.log.gz")), "rt", encoding="utf-8", errors="replace").read().splitlines()]
for s in ls:
    if not s.startswith(("[AIPOSTWALK]", "[AISCD]", "[AIDECIDE]", "[AIEXEC]")):
        continue
    if unit not in s:
        continue
    if re.search(rf'turn"?[=:]{turn}\b', s) or s.startswith("[AIEXEC]"):
        print(s[:300])
print("--- шаги, начатые при метке")
for m in ("M3",):
    for s_ in (1, 2, 3, 4):
        lb = f"sfH_XN_{m}_s{s_}"
        if lb + "/" not in " ".join(z.namelist()):
            continue
        for s in gzip.open(io.BytesIO(z.read(f"out/{lb}/openxcom.log.gz")), "rt", encoding="utf-8", errors="replace"):
            s = s.split("\t")[-1]
            if s.startswith("[AIPOSTWALK]") and " resel0=0" in s:
                print(lb, s[:230].strip())
