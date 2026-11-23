"""TACTICAL STAGE 2: the player's units over hostile turn 2 per run - HP at aistart turn 2 and at pstart turn 3 (status), and
who hit them in that turn ([AIEXEC] of hostile attacks whose target cell is the unit's cell).

  py -3.13 -I fl_plost.py <label>=<log> ...
"""
import gzip
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")


def run(path):
    hp0, hp1 = {}, {}
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if body.startswith("[AISTATE] aistart ") and " turn=2 " in body:
                d = dict(KV.findall(body))
                if d["faction"] == "0":
                    hp0[d["unit"]] = (d["hp"], d["pos"])
            elif body.startswith("[AISTATE] pstart ") and " turn=3 " in body:
                d = dict(KV.findall(body))
                if d["faction"] == "0":
                    hp1[d["unit"]] = (d["hp"], d.get("status"))
    return hp0, hp1


def main():
    for arg in sys.argv[1:]:
        lab, path = arg.split("=", 1)
        hp0, hp1 = run(path)
        print(f"== {lab}")
        tot = 0
        for u, (h, pos) in hp0.items():
            a = int(h.split("/")[0])
            b = int(hp1[u][0].split("/")[0]) if u in hp1 else 0
            if a != b:
                tot += a - b
                print(f"  {u} {pos} hp {h} -> {hp1[u][0] + ' status ' + hp1[u][1] if u in hp1 else 'gone'}  lost {a - b}")
        print(f"  total {tot}")


main()
