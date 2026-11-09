"""SIDE-FIRST COMBAT V0.1, L8: the first hostile turn's decisions of the two types that ever used psi, in order: unit, time units, action, what it saw. args: zip label ..."""
import gzip
import io
import re
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
KV = re.compile(r"(\w+)=([^ ]*)")
TYPES = ("STR_ETHEREAL_COMMANDER", "STR_ETHEREAL_LEADER")
args = sys.argv[1:]
for zp, label in zip(args[0::2], args[1::2]):
    z = zipfile.ZipFile(zp)
    ls = [s.split("\t")[-1] for s in gzip.open(io.BytesIO(z.read(f"out/{label}/openxcom.log.gz")), "rt", encoding="utf-8", errors="replace").read().splitlines()]
    typ = {}
    print("---", label)
    for s in ls:
        if s.startswith("[AISTATE] "):
            d = dict(KV.findall(s))
            if d.get("unit") and d.get("type"):
                typ[d["unit"]] = d["type"]
        elif s.startswith("[AIDECIDE] "):
            d = dict(KV.findall(s.split(" hu=")[0]))
            if d.get("side") == "1" and d.get("turn") == "1" and typ.get(d["unit"]) in TYPES:
                print(f"  {typ[d['unit']][13:]} {d['unit']} n={d['n']} tu={d['tu']} act={d['act']} weapon={d.get('weapon')} seen={d.get('seen')}")
    print("  итог юнитов:", [(u, t[13:]) for u, t in typ.items() if t in TYPES])
