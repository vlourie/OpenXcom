"""TACTICAL STAGE 2: the hostile decisions of a turn in two runs side by side - unit, n, act, target cell and the state hashes
(hu units, hi items, ho ?, hm map, hr RNG, hr0, ha0) - to see what made a later decision differ after the first changed one.

  py -3.13 -I fl_hash.py <log A> <log X> [turn]
"""
import gzip
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")
HK = ("hu", "hi", "ho", "hm", "hr", "hr0", "ha0")


def decs(path, turn):
    out = []
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if body.startswith("[AIDECIDE] "):
                d = dict(KV.findall(body))
                if d.get("turn") == str(turn) and d.get("side") == "1":
                    out.append(d)
    return out


def main():
    turn = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    a, x = decs(sys.argv[1], turn), decs(sys.argv[2], turn)
    for i in range(max(len(a), len(x))):
        da = a[i] if i < len(a) else {}
        dx = x[i] if i < len(x) else {}
        sa = f"{da.get('unit')} n={da.get('n')} act={da.get('act')} to={da.get('to')}" if da else "-"
        sx = f"{dx.get('unit')} n={dx.get('n')} act={dx.get('act')} to={dx.get('to')}" if dx else "-"
        same = " ".join(k if da.get(k) == dx.get(k) else k.upper() for k in HK) if da and dx else ""
        print(f"{i:>3} A: {sa:<42} X: {sx:<42} {same}")


main()
