"""SIDE-FIRST COMBAT: what the friendly damage recorded on non-attack records is (M8 act 0, walks). args: zip prefix"""
import gzip
import io
import json
import re
import sys
import zipfile
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
KV = re.compile(r"(\w+)=([^ ]*)")
z = zipfile.ZipFile(sys.argv[1])
P = sys.argv[2]
for m, arm, acts in (("M8", "XN", ("0",)), ("M8", "XN", ("2",)), ("M3", "D", ("2",))):
    c = Counter()
    shown = 0
    for s_ in (1, 2, 3, 4):
        raw = gzip.open(io.BytesIO(z.read(f"out/{P}_{arm}_{m}_s{s_}/openxcom.log.gz")), "rt", encoding="utf-8", errors="replace").read().splitlines()
        raw = [s.split("\t")[-1] for s in raw]
        pend = None
        for i, s in enumerate(raw):
            if s.startswith("[AIDECIDE] "):
                pend = dict(KV.findall(s.split(" hu=")[0]))
            elif s.startswith("[AIEXEC] ") and pend:
                x = json.loads(s[9:])
                d, pend = pend, None
                if d.get("side") != "1" or d.get("act") not in acts or not x.get("fdmg"):
                    continue
                c["records"] += 1
                c["fdmg"] += x["fdmg"]
                c["reacted" if x.get("react") or x.get("reactions") else "no react field"] += 1
                if shown < 2:
                    shown += 1
                    print(f"{m} {arm} act {acts} s{s_}:", s[:420])
                    print("   decide:", {k: d.get(k) for k in ("turn", "unit", "act", "weapon", "aim", "tu")})
                    between = [t[:170] for t in raw[max(0, i - 12):i] if t.startswith(("[AICASUALTY]", "[AISCD]"))]
                    print("   before:", between[-3:])
    print(f"{m} {arm} act {acts}:", dict(c))
