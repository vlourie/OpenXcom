"""Start check: the battle line and the first [AISTATE] before / first [AIDECIDE] of D0 and D1, each scenario-seed.

  py -3.13 start_diff.py <out dir> <scen.tsv>"""
import gzip
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT, SCEN = Path(sys.argv[1]), Path(sys.argv[2])
ids = [l.split("\t")[0] for l in SCEN.read_text(encoding="utf-8-sig").splitlines()[1:] if l.strip()]


def head(p):
    battle, before, first = "", [], None
    with gzip.open(p, "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if body.startswith("[AIPROBE] battle"):
                battle = body
            elif body.startswith("[AISTATE] before turn=1 "):
                before.append(body)
            elif body.startswith("[AIDECIDE] ") and first is None:
                first = body
                break
    return battle, before, first


def strip_threat(line):
    return " ".join(w for w in line.split() if not w.startswith(("threat=", "reach=")))


for sid in ids:
    for k in (1, 2):
        a = head(OUT / f"D0_{sid}_s{k}" / "openxcom.log.gz")
        b = head(OUT / f"D1_{sid}_s{k}" / "openxcom.log.gz")
        if a == b:
            continue
        print(f"== {sid} s{k}: battle {'=' if a[0] == b[0] else '!='}, before {len(a[1])}/{len(b[1])} "
              f"{'=' if a[1] == b[1] else '!='}, before w/o threat {'=' if [strip_threat(x) for x in a[1]] == [strip_threat(x) for x in b[1]] else '!='}")
        for x, y in zip(a[1], b[1]):
            if x != y:
                print("  D0", x[:400])
                print("  D1", y[:400])
                break
        da = dict(w.split("=", 1) for w in (a[2] or "").split()[1:] if "=" in w)
        db = dict(w.split("=", 1) for w in (b[2] or "").split()[1:] if "=" in w)
        print("  first decision differs in:", [key for key in da if da.get(key) != db.get(key)])
