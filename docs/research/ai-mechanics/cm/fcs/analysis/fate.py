"""FIRST CONTACT SURVIVAL V0, stage 4: every unit the rule moved: its fate in D0 and with the rule, the attacks it made after the change; the first difference's hashes; the raw lines of one execution (read only).
Usage: fate.py <d0 dir> <rule dir> [<d0 dir> <rule dir>]..."""
import gzip
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")
ATTACK = {"6", "7", "8", "9"}
LAST = 4


def read(d):
    with gzip.open(Path(d) / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        return [ln.rstrip("\n").split("\t")[-1] for ln in f]


def cas(lines):
    r = {}
    for s in lines:
        if s.startswith("[AICASUALTY] "):
            k = dict(KV.findall(s))
            if k.get("vfaction") == "1" and int(k["turn"]) <= LAST:
                r.setdefault(k["victim"], k)
    return r


def decs(lines, unit):
    return [k for k in (dict(KV.findall(s)) for s in lines if s.startswith("[AIDECIDE] ")) if k["unit"] == unit and k["side"] == "1" and int(k["turn"]) <= LAST]


tot = dict(units=0, d0_past=0, rule_past=0, att_after=0, d0_att_after=0)
args = sys.argv[1:]
for i in range(0, len(args), 2):
    a, b = read(args[i]), read(args[i + 1])
    ca, cb = cas(a), cas(b)
    print("==", Path(args[i + 1]).name)
    seen = {}
    for s in b:
        if s.startswith("[FCSACT]"):
            k = dict(KV.findall(s))
            if k["new"] != "-":
                seen.setdefault(k["unit"], k)
    for u, k in seen.items():
        t = int(k["turn"])
        fa, fb = ca.get(u), cb.get(u)
        fmt = lambda f: f"t{f['turn']}s{f['side']} at {f['pos']} by {f['killer']} d{f.get('dist')} {f.get('weapon', '')[:18]}" if f else "alive at the limit"
        past = lambda f: f is None or int(f["turn"]) > t + 1 or (int(f["turn"]) == t + 1 and f["side"] == "1")
        after_b = [x for x in decs(b, u) if int(x["turn"]) > t]
        after_a = [x for x in decs(a, u) if int(x["turn"]) > t]
        ab = sum(x["act"] in ATTACK for x in after_b)
        aa = sum(x["act"] in ATTACK for x in after_a)
        print(f"  {u} t{t}: D0 {fmt(fa)} | rule {fmt(fb)} | past the next player turn D0 {int(past(fa))} rule {int(past(fb))} | attacks later D0 {aa} rule {ab}")
        tot["units"] += 1
        tot["d0_past"] += past(fa)
        tot["rule_past"] += past(fb)
        tot["att_after"] += ab
        tot["d0_att_after"] += aa
    fa = [s for s in a if s.startswith("[AIDECIDE]")]
    fb = [s for s in b if s.startswith("[AIDECIDE]")]
    j = next((x for x in range(min(len(fa), len(fb))) if fa[x] != fb[x]), None)
    if j is not None:
        da, db = dict(KV.findall(fa[j])), dict(KV.findall(fb[j]))
        print("  first differing decision: fields that differ:", [x for x in da if da[x] != db.get(x)])
print(tot)
print()
b = read(args[1])
for j, s in enumerate(b):
    if s.startswith("[FCSACT]") and "unit=1000026" in s:
        for t in b[j:j + 30]:
            if '"unit":1000026' in t or "unit=1000026" in t and t.startswith(("[AIDECIDE]", "[FCSACT]", "[AISTATE]")):
                print(t[:330])
        break
