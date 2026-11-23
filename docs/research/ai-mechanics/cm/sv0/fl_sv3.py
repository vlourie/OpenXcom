"""STRIKE-V0, the last checks: the end-of-action decisions in the shadow run, the order shots that hurt their own side, the unit-turn
with the most decisions in each battle with the order on against D0.

  py -3.13 -I fl_sv3.py <out dir> <D0 prefix> <shadow prefix> <on prefix>"""
import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")


def lines(d):
    for raw in gzip.open(d / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace"):
        yield raw.rstrip("\n").split("\t", 2)[-1]


out, pd, ps, pn = Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
none_cls = Counter()
none_shot = Counter()
none_mode = Counter()
for d in sorted(out.glob(f"{ps}_*")):
    for b in lines(d):
        if b.startswith("[AISTRIKE] kind=opp "):
            s = dict(KV.findall(b))
            if s["act"] == "0":
                none_cls[s["cls"]] += 1
                none_mode[s["mode"]] += 1
                if s["cls"] == "allowed":
                    none_shot[s["shot"]] += 1
print("end-of-action decisions (act 0), shadow, all 48 battles")
print("  by class: " + ", ".join(f"{k}={v}" for k, v in none_cls.most_common()))
print("  by mode: " + ", ".join(f"{k}={v}" for k, v in none_mode.most_common()))
print("  class allowed, by shot: " + ", ".join(f"{k}={v}" for k, v in none_shot.most_common()))

print("order shots that hurt their own side")
for d in sorted(out.glob(f"{pn}_*")):
    want = None
    pend = None
    for b in lines(d):
        if b.startswith("[AISTRIKE] kind=exec "):
            want = dict(KV.findall(b))
        elif b.startswith("[AIDECIDE] "):
            pend = dict(KV.findall(b.split(" hu=")[0]))
        elif b.startswith("[AIEXEC] ") and pend and want and pend["unit"] == want["unit"]:
            x = json.loads(b[9:])
            if str(x["unit"]) == pend["unit"]:
                if (x.get("fdmg") or 0) > 0 or (x.get("fdowned") or 0) > 0:
                    print(f"  {d.name} t{want['turn']} u{want['unit']} target{want['target']} weapon {pend.get('weapon')} type{want['type']}"
                          f" dmg {x.get('dmg')} fdmg {x.get('fdmg')} fdowned {x.get('fdowned')}")
                want = None

print("the unit-turn with the most decisions: acts with TU spent")


def most(d):
    per = defaultdict(list)
    orders = set()
    pend = None
    for b in lines(d):
        if b.startswith("[AISTRIKE] kind=exec "):
            s = dict(KV.findall(b))
            orders.add((int(s["turn"]), s["unit"]))
        elif b.startswith("[AIDECIDE] "):
            pend = dict(KV.findall(b.split(" hu=")[0]))
            if pend["side"] == "1":
                per[(int(pend["turn"]), pend["unit"])].append([pend["act"], None, pend["mode"]])
        elif b.startswith("[AIEXEC] ") and pend:
            x = json.loads(b[9:])
            if str(x["unit"]) == pend["unit"] and pend["side"] == "1":
                per[(int(pend["turn"]), pend["unit"])][-1][1] = x.get("spent")
            pend = None
    k = max(per, key=lambda q: len(per[q]))
    return k, per[k], k in orders, Counter(len(v) for v in per.values())


for nd in sorted(out.glob(f"{pn}_*")):
    dd = out / nd.name.replace(f"{pn}_", f"{pd}_", 1)
    k, v, by_order, hist = most(nd)
    k0, v0, _, hist0 = most(dd)
    big = sum(c for n, c in hist.items() if n >= 11)
    big0 = sum(c for n, c in hist0.items() if n >= 11)
    print(f"  {nd.name[len(pn) + 1:]:8s} on t{k[0]} u{k[1]} {len(v)} decisions, had an order shot: {int(by_order)}, zero-TU {sum(1 for a in v if not a[1])}:"
          f" {' '.join(f'{a[0]}/{a[1]}' for a in v)}")
    print(f"  {'':8s} D0 t{k0[0]} u{k0[1]} {len(v0)} decisions; unit-turns with 11+ decisions on {big} / D0 {big0}")
