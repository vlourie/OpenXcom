"""AI_TACTICAL_DIRECTOR_V1: the flag-off arm (O) must repeat D0. Compares the [AIDECIDE] and [AIEXEC] lines of each O battle
with the same battle of the D0 control (a longer run: its first turns are the same battle), up to the last turn both reached.

  py -3.13 -I td_ident.py <out dir> <prefix O> <prefix D0>"""
import gzip
import hashlib
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT, PO, PD = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
TURN = re.compile(r"turn=(\d+)")


def lines(d):
    out = []
    with gzip.open(d / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        t = 0
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if body.startswith("[AIDECIDE] "):
                t = int(TURN.search(body).group(1))
                out.append((t, body))
            elif body.startswith("[AIEXEC] ") or body.startswith("[AICASUALTY] "):
                out.append((t, body))
    return out


bad = 0
for d in sorted(OUT.glob(f"{PO}_*")):
    key = "_".join(d.name.split("_")[2:])
    c = [x for x in OUT.glob(f"{PD}_*_{key}") if (x / "openxcom.log.gz").exists()]
    if not (d / "openxcom.log.gz").exists() or not c:
        print(f"{key}: no pair")
        continue
    a, b = lines(d), lines(c[0])
    tmax = min(a[-1][0], b[-1][0]) - 1 if a and b else 0  # the last turn of the shorter run may be cut
    a = [x for x in a if x[0] <= tmax]
    b = [x for x in b if x[0] <= tmax]
    ha = hashlib.md5("\n".join(s for _, s in a).encode()).hexdigest()
    hb = hashlib.md5("\n".join(s for _, s in b).encode()).hexdigest()
    same = ha == hb
    bad += not same
    first = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), None)
    print(f"{key}: turns<={tmax} lines {len(a)}/{len(b)} {'IDENTICAL' if same else 'DIFF at line ' + str(first)}")
    if not same and first is not None:
        print("   O :", a[first][1][:200])
        print("   D0:", b[first][1][:200])
print("OFF == D0" if bad == 0 else f"OFF differs in {bad}")
