"""COUNTERFIRE: every new hostile loss to one player weapon (default AUX_TANK_CANNON) in hostile turns, by the hostile decision
in whose window it happened: an attack at the vehicle carrying that weapon, an attack at another target, a walk, other.
A unit already down (unconscious, not up since) hit again is not a new loss.

  py -3.13 -I fl_cannon.py <out dir> <label prefix> [weapon]
"""
import gzip
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")
ATT = {6, 7, 8, 9, 10, 12}


def main():
    out, pre = Path(sys.argv[1]), sys.argv[2]
    wpn = sys.argv[3] if len(sys.argv) > 3 else "AUX_TANK_CANNON"
    tot, by_kind, rows = Counter(), Counter(), []
    for p in sorted(out.iterdir()):
        if not p.name.startswith(pre + "_") or not (p / "openxcom.log.gz").exists():
            continue
        down, carrier, dec = set(), set(), None
        with gzip.open(p / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
            for raw in f:
                l = raw.rstrip("\n").split("\t", 2)[-1]
                if l.startswith("[AISTATE] aistart "):
                    d = dict(KV.findall(l))
                    if d.get("status") == "0":
                        down.discard(d["unit"])
                    if wpn in l and d.get("faction") == "0":
                        carrier.add(d["unit"])
                elif l.startswith("[AIDECIDE] "):
                    d = dict(KV.findall(l.split(" hu=")[0]))
                    down.discard(d["unit"])
                    dec = d if d.get("side") == "1" else None
                elif l.startswith("[AICASUALTY] "):
                    c = dict(KV.findall(l))
                    new = c["victim"] not in down
                    down.add(c["victim"])
                    if not new or c.get("vfaction") != "1" or not c.get("weapon", "").startswith(wpn) or c.get("side") != "1":
                        continue
                    if dec is None:
                        k = "no hostile decision"
                    elif int(dec["act"]) in ATT:
                        k = "attack at the carrier" if dec["aim"] in carrier else "attack at another"
                    elif dec["act"] == "2":
                        k = "walk"
                    else:
                        k = f"act {dec['act']}"
                    by_kind[k] += 1
                    tot[p.name] += 1
                    rows.append(f"{p.name} t{c['turn']} {c['victim']} {c['how']} | during {dec['unit'] if dec else '-'} "
                                f"act={dec['act'] if dec else '-'} aim={dec['aim'] if dec else '-'} -> {k}")
    print(f"new hostile losses to {wpn} in hostile turns: {sum(by_kind.values())}")
    for k, n in by_kind.most_common():
        print(f"  {k}: {n}")
    print("per battle: " + ", ".join(f"{k[len(pre) + 1:]} {n}" for k, n in sorted(tot.items())))
    print()
    print("\n".join(rows))


main()
