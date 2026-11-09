"""SIDE-FIRST COMBAT V0.1: why the first hostile turn visits low ids again. A "jump back" = the next unit decided has a lower id than the one before.
Its cause: the unit before went out (casualty between the two decisions) or not. Visits of the chrysalids and their rounds in a visit. args: zip:prefix:arm ... (M3 seeds 1-4)"""
import gzip
import io
import re
import sys
import zipfile
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
KV = re.compile(r"(\w+)=([^ ]*)")


def battle(z, label):
    raw = gzip.open(io.BytesIO(z.read(f"out/{label}/openxcom.log.gz")), "rt", encoding="utf-8", errors="replace").read().splitlines()
    c = Counter()
    typ = {}
    last = None
    out_since = set()
    visits = Counter()
    per_visit = Counter()
    cur = 0
    for s in raw:
        s = s.split("\t")[-1]
        if s.startswith("[AISTATE] "):
            d = dict(KV.findall(s))
            if d.get("unit") and d.get("type"):
                typ[d["unit"]] = d["type"]
        elif s.startswith("[AICASUALTY] "):
            d = dict(KV.findall(s))
            if d.get("turn") == "1" and d.get("side") == "1":
                out_since.add(d.get("victim"))
        elif s.startswith("[AIDECIDE] "):
            d = dict(KV.findall(s.split(" hu=")[0]))
            if d.get("side") != "1" or d.get("turn") != "1":
                continue
            u = d["unit"]
            if u != last:
                if "CHRYSSALID" in typ.get(last or "", ""):
                    per_visit[cur] += 1
                cur = 0
                if "CHRYSSALID" in typ.get(u, ""):
                    visits[u] += 1
                if last and int(u) < int(last):
                    c["jump_back"] += 1
                    c["jump_after_out" if last in out_since else "jump_other"] += 1
                    if last in out_since:
                        c["jump_after_out_to_low"] += 1 if int(u) <= 1000006 else 0
                last = u
            cur += 1
    c["chr_units"] = len(visits)
    c["chr_visits"] = sum(visits.values())
    c["chr_max_visits"] = max(visits.values()) if visits else 0
    c["own_out_t1"] = len(out_since)
    return c, per_visit


for a in sys.argv[1:]:
    zp, prefix, arm = a.rsplit(":", 2)
    z = zipfile.ZipFile(zp)
    tot = Counter()
    pv = Counter()
    for s_ in (1, 2, 3, 4):
        c, v = battle(z, f"{prefix}_{arm}_M3_s{s_}")
        print(f"  {prefix} {arm} s{s_}: прыжков назад {c['jump_back']} (после выбытия выбранного {c['jump_after_out']}, иначе {c['jump_other']}); хризалид {c['chr_units']}, заходов {c['chr_visits']}, макс. {c['chr_max_visits']}")
        tot.update({k: v_ for k, v_ in c.items() if k not in ("chr_max_visits",)})
        pv.update(v)
    print(f"{prefix} {arm}: прыжков назад {tot['jump_back']}, после выбытия {tot['jump_after_out']}, иначе {tot['jump_other']}; заходов хризалид {tot['chr_visits']} на {tot['chr_units']} юнитов; раундов за заход {sorted(pv.items())}")
