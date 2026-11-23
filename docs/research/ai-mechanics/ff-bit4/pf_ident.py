"""Pilot: battles where PF made no ff veto must play as PE - all streams compared without the header line (the config hash
and the env list differ by the flags) and without the blast record. usage: pf_ident.py <dir> <pf_battles.tsv>"""
import gzip
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
D = Path(sys.argv[1])
BT = [l.split("\t") for l in Path(sys.argv[2]).read_text(encoding="utf-8-sig").splitlines()[1:] if l.strip()]
CFG = re.compile(r'"cfg":"[0-9a-f]*",')
DROP = ("[AIRECHEAD]", "[AIBLAST]", "[AIBHIT]", "[AIEFF]")


def lines(p):
    if not p.exists():
        return None
    op = gzip.open if p.suffix == ".gz" else open
    with op(p, "rt", encoding="utf-8-sig", errors="replace") as f:
        # every record line carries the config hash ("cfg"), which the flags change
        return [CFG.sub("", l) for l in f.read().splitlines() if not any(t in l for t in DROP)]


for b in BT:
    a, f = f"pf_PE_{b[0]}", f"pf_PF_{b[0]}"
    rec = lines(D / f"{f}.rec.gz") or []
    veto = sum(1 for l in rec if '"ff.sec' in l)
    res = "IDENTICAL"
    n = 0
    for s in (".rec.gz", ".decide.gz", ".cand.gz", ".casualties.txt"):
        la, lb = lines(D / (a + s)), lines(D / (f + s))
        if la is None and lb is None:
            continue
        if la != lb:
            i = next((i for i, (x, y) in enumerate(zip(la or [], lb or [])) if x != y), min(len(la or []), len(lb or [])))
            res = f"DIFF {s} line {i}"
            break
        n += len(la)
    print(f"{b[0]}\tveto lines {veto}\t{res}" + (f" ({n} lines)" if res == "IDENTICAL" else ""))
