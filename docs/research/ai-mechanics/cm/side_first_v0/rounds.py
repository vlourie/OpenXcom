"""SIDE-FIRST COMBAT V0.1: think rounds of one unit in one hostile turn, the director's own actions apart. D0 stops at 2 rounds a pass, 2 passes.
args: zip:label ... [--type SUBSTR]; prints per battle: unit-turns, think rounds per unit-turn, distribution, the max, and by type if asked."""
import gzip
import io
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
KV = re.compile(r"(\w+)=([^ ]*)")


def rounds(zp, label):
    z = zipfile.ZipFile(zp)
    raw = gzip.open(io.BytesIO(z.read(f"out/{label}/openxcom.log.gz")), "rt", encoding="utf-8", errors="replace").read().splitlines()
    scd = set()
    typ = {}
    think = Counter()
    direc = Counter()
    tu = Counter()
    pend = None
    for s in raw:
        s = s.split("\t")[-1]
        if s.startswith("[AISCD] "):
            j = json.loads(s[8:])
            if j.get("ev") == "act":
                scd.add(str(j["actor"]))
        elif s.startswith("[AISTATE] "):
            d = dict(KV.findall(s))
            if d.get("unit") and d.get("type"):
                typ[d["unit"]] = d["type"]
        elif s.startswith("[AIDECIDE] "):
            d = dict(KV.findall(s.split(" hu=")[0]))
            pend = None
            if d.get("side") != "1":
                continue
            k = (int(d["turn"]), d["unit"])
            if d["unit"] in scd:
                scd.discard(d["unit"])
                direc[k] += 1
            else:
                think[k] += 1
            pend = k
        elif s.startswith("[AIEXEC] ") and pend:
            tu[pend] += json.loads(s[9:]).get("spent") or 0
            pend = None
    return think, direc, tu, typ


def show(zp, label, want):
    think, direc, tu, typ = rounds(zp, label)
    keys = set(think) | set(direc)
    dist = Counter(think[k] for k in keys)
    print(f"{label}: юнит-ходов {len(keys)}, раундов think {sum(think.values())} ({sum(think.values()) / max(1, len(keys)):.2f} на юнит-ход), директор {sum(direc.values())}; распределение {sorted(dist.items())}; больше 4: {sum(v for r, v in dist.items() if r > 4)}")
    if want:
        by = defaultdict(lambda: [0, 0, 0, 0, 0])
        for k in keys:
            t = typ.get(k[1], "?")
            if want in t:
                b = by[t]
                b[0] += 1
                b[1] += think[k]
                b[2] += direc[k]
                b[3] += tu[k]
                b[4] = max(b[4], think[k])
        for t, b in sorted(by.items()):
            print(f"   {t}: юнит-ходов {b[0]}, think {b[1]}, директор {b[2]}, ОВ {b[3]}, макс. think {b[4]}")


if __name__ == "__main__":
    want = None
    args = sys.argv[1:]
    if "--type" in args:
        i = args.index("--type")
        want = args[i + 1]
        args = args[:i] + args[i + 2:]
    for a in args:
        zp, label = a.rsplit(":", 1)
        show(zp, label, want)
