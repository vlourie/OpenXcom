"""SIDE-FIRST COMBAT V0.1: the check of the repeated pass on every hostile turn of every battle given. Per unit-turn from the decisions: visits (runs of decisions in a row), time units never growing between records of one unit in one hostile turn ([AIDECIDE] tu); a jump back = the next unit decided has a lower id than the one before, and whether the one before went out in between.
A repeated finished action = an attack or a walk logged with spent 0 and repeated, or a record of a unit with no time units left. args: zip:prefix:arm:mission ..."""
import gzip
import io
import json
import re
import sys
import zipfile
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
KV = re.compile(r"(\w+)=([^ ]*)")


def battle(z, label):
    raw = gzip.open(io.BytesIO(z.read(f"out/{label}/openxcom.log.gz")), "rt", encoding="utf-8", errors="replace").read().splitlines()
    c = Counter()
    visits = Counter()
    tu = {}
    turn = None
    last = None
    out = set()
    open_rec = None
    for s in raw:
        s = s.split("\t")[-1]
        if s.startswith("[AICASUALTY] "):
            d = dict(KV.findall(s))
            if d.get("side") == "1":
                out.add(d.get("victim"))
        elif s.startswith("[AIDECIDE] "):
            d = dict(KV.findall(s.split(" hu=")[0]))
            if d.get("side") != "1":
                continue
            if d["turn"] != turn:
                turn = d["turn"]
                last = None
                out = set()
                c["turns"] += 1
            u = d["unit"]
            c["decisions"] += 1
            t = int(d.get("tu") or 0)
            k = (turn, u)
            if k in tu and t > tu[k]:
                c["tu_grew"] += 1
                print("   ОВ выросли:", s[:160])
            tu[k] = t
            if u != last:
                visits[k] += 1
                if last and int(u) < int(last):
                    c["jump_back"] += 1
                    c["jump_after_out" if last in out else "jump_other"] += 1
                last = u
            open_rec = d
        elif s.startswith("[AIEXEC] ") and open_rec:
            x = json.loads(s[9:])
            d, open_rec = open_rec, None
            if str(x.get("unit")) != d["unit"]:
                continue
            c["records"] += 1
            spent = x.get("spent") or 0
            if d.get("act") not in ("0", "1", None) and spent == 0:
                c["acted_spent_0"] += 1
            if spent > int(d.get("tu") or 0) + 8:
                c["spent_over_tu"] += 1
                print("   потрачено больше ОВ:", spent, s[:60], d.get("tu"))
    c["unit_turns"] = len(visits)
    c["visits"] = sum(visits.values())
    c["extra_visits"] = sum(v - 1 for v in visits.values())
    c["max_visits"] = max(visits.values()) if visits else 0
    return c


for a in sys.argv[1:]:
    zp, prefix, arm, mission = a.rsplit(":", 3)
    z = zipfile.ZipFile(zp)
    tot = Counter()
    mx = 0
    for s_ in (1, 2, 3, 4):
        c = battle(z, f"{prefix}_{arm}_{mission}_s{s_}")
        mx = max(mx, c["max_visits"])
        tot.update({k: v for k, v in c.items() if k != "max_visits"})
    print(f"{prefix} {arm} {mission}: юнит-ходов {tot['unit_turns']}, заходов {tot['visits']}, дополнительных заходов {tot['extra_visits']}, макс. за ход {mx}; прыжков назад {tot['jump_back']} (после выбытия выбранного {tot['jump_after_out']}, иначе {tot['jump_other']}); рост ОВ {tot['tu_grew']}; потрачено больше ОВ {tot['spent_over_tu']}; действие без траты ОВ {tot['acted_spent_0']} из {tot['records']}")
