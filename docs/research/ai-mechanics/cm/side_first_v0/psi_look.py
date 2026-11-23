"""SIDE-FIRST COMBAT: what the log holds of a psi action and of the player's unit state around it. args: zip label"""
import gzip
import io
import re
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
z = zipfile.ZipFile(sys.argv[1])
raw = gzip.open(io.BytesIO(z.read(f"out/{sys.argv[2]}/openxcom.log.gz")), "rt", encoding="utf-8", errors="replace").read().splitlines()
ls = [s.split("\t")[-1] for s in raw]
n = 0
for i, s in enumerate(ls):
    if s.startswith("[AIDECIDE] ") and re.search(r" side=1 .* act=1[34] ", s):
        n += 1
        if n <= 3:
            print(s[:230])
            for t in ls[i + 1:i + 8]:
                if t.startswith(("[AIEXEC]", "[AICASUALTY]")) or "psi" in t.lower() or "mind" in t.lower():
                    print("   ", t[:380])
print("psi records", n)
st = [s for s in ls if s.startswith("[AISTATE] ") and " faction=0 " in s]
print(st[0][:420])
for w in ("aistart", "pstart", "before"):
    x = [s for s in st if s.startswith("[AISTATE] " + w)]
    print(w, len(x), x[10][:200] if len(x) > 10 else "")
same = [s for s in st if " unit=" in s and " turn=2 " in s]
print("\n".join(s[:150] for s in same[:6]))
