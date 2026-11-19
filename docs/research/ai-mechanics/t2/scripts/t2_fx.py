"""AI-T2: the real effect of the executed shots by t2Retarget's verdict (why) and expected damage (ev10 = tenths of HP), and
which fields changed; the alternatives of the useless shots (best expected damage among the other lawful targets).

  py -3.13 t2_fx.py <out dir> <prefix>"""
import gzip
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT, PRE = Path(sys.argv[1]), sys.argv[2]
KV = re.compile(r"(\w+)=(\([^)]*\)|\S+)")
SHOT = {7, 8, 9}
NAMES = ("hp", "stun", "morale", "tu", "energy", "wounds", "fire", "armF", "armL", "armR", "armRear", "armU")
grp = defaultdict(Counter)
alt_best = Counter()
alt_why = Counter()
alt_fac = Counter()


def bucket(ev10):
    return "ev<0.5" if ev10 < 5 else "ev0.5-3" if ev10 < 30 else "ev>=3"


for d in sorted(OUT.glob(f"{PRE}_*")):
    pend = {}
    last = None
    with gzip.open(d / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if body.startswith("[AIT2] "):
                k = dict(KV.findall(body))
                pend[k["unit"]] = k
                if k["useless"] == "1" and k["n"] != "0":
                    best = 0
                    for a in k.get("alts", "").split(";"):
                        if a:
                            i, fac, dist, ev10, w = a.split(":")
                            best = max(best, int(ev10))
                            alt_why[w] += 1
                            alt_fac[fac] += 1
                    alt_best["0" if best == 0 else "0.1-0.9" if best < 10 else "1-2.9" if best < 30 else ">=3"] += 1
            elif body.startswith("[AIT2FX] "):
                k = dict(KV.findall(body))
                if last and last[0] == k["unit"] and k["later"] == "0":
                    g = grp[last[1]]
                    dd = [int(x) for x in k["d"].split(",")]
                    g["n"] += 1
                    a, b = k["st"].split(">")
                    ch = []
                    if dd[0] < 0: ch.append("hp")
                    if dd[1] > 0: ch.append("stun")
                    if dd[2] < 0: ch.append("morale")
                    if dd[4] < 0: ch.append("energy")
                    if dd[5] > 0: ch.append("wounds")
                    if dd[6] > 0: ch.append("fire")
                    if any(x < 0 for x in dd[7:]): ch.append("armour")
                    if a != b: ch.append("status")
                    g["any"] += bool(ch)
                    g["dmg"] += any(x in ch for x in ("hp", "stun", "wounds", "armour", "status", "fire"))
                    for x in ch:
                        g[x] += 1
                    g["hp_lost"] += -dd[0] if dd[0] < 0 else 0
                    g["armour_lost"] += -sum(x for x in dd[7:] if x < 0)
                last = None
            elif body.startswith("[AIDECIDE] ") and " side=1 " in body:
                k = dict(KV.findall(body))
                p = pend.pop(k["unit"], None)
                last = None
                if p and int(k["act"]) in SHOT and k.get("aim") == p["target"]:
                    last = (k["unit"], f"{p['why']:12s} {bucket(int(p['ev10']))}")
print("executed shots by verdict and expected damage: n, with any change, with damage-like change (hp/stun/wounds/armour/fire/status)")
for key, g in sorted(grp.items()):
    extra = {x: g[x] for x in ("hp", "stun", "morale", "energy", "wounds", "fire", "armour", "status") if g[x]}
    print(f"  {key}  n={g['n']:5d} any={g['any']:4d} dmg={g['dmg']:4d} ({100 * g['dmg'] / max(1, g['n']):.0f}%) "
          f"hp_lost={g['hp_lost']} armour_lost={g['armour_lost']} {extra}")
print("useless shots with other lawful targets: best alternative expected HP", dict(alt_best))
print("  alternatives' verdict:", dict(alt_why), "faction:", dict(alt_fac))
