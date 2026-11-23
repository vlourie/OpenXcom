"""SIDE-FIRST COMBAT V0.1, L8: what psi and capture did. For each psi action the target's morale, faction and tile at its last [AISTATE] before and first after; decisions of hostile side by units that belong to the player (a capture that took);
for the units able to use psi (their decisions carry a psi candidate): decisions, those with a psi candidate, those that used it, and the time units they had. Also the record of unit 91 around an attack_on_out, and over-spent records against [AIEXEC] tu.
args: zip:prefix:arm ..."""
import gzip
import io
import json
import re
import sys
import zipfile
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
KV = re.compile(r"(\w+)=([^ ]*)")
PSI = {"13": "psi", "14": "mc"}


def battle(z, label):
    raw = gzip.open(io.BytesIO(z.read(f"out/{label}/openxcom.log.gz")), "rt", encoding="utf-8", errors="replace").read().splitlines()
    ls = [s.split("\t")[-1] for s in raw]
    c = Counter()
    states = {}
    for i, s in enumerate(ls):
        if s.startswith("[AISTATE] "):
            d = dict(KV.findall(s))
            if "unit" in d and "morale" in d:
                states.setdefault(d["unit"], []).append((i, s.split(" ", 2)[1], int(d["turn"]), d["faction"], int(d["morale"]), d["hp"], d["tu"]))
    acts = []
    last_cand = {}
    cand_units = set()
    for i, s in enumerate(ls):
        if s.startswith("[AICAND] "):
            m = re.search(r"unit=(\d+)", s)
            if m and ('"t":13' in s or '"t":14' in s):
                cand_units.add(m.group(1))
                last_cand[m.group(1)] = i
        elif s.startswith("[AIDECIDE] "):
            d = dict(KV.findall(s.split(" hu=")[0]))
            if d.get("side") != "1":
                continue
            if int(d["unit"]) < 1000000:
                c["hostile_decisions_by_player_units"] += 1
                c["captured_unit_" + d["unit"]] = 1
            if d.get("act") in PSI:
                acts.append((i, d))
    for i, d in acts:
        a = d.get("aim")
        h = states.get(a, [])
        b = [x for x in h if x[0] < i][-1:]
        f = [x for x in h if x[0] > i][:1]
        print(f"   ход {d['turn']} {PSI[d['act']]} -> {a}: до {b[0][1:] if b else '-'} после {f[0][1:] if f else '-'}")
    psi_dec = Counter()
    for s in ls:
        if s.startswith("[AIDECIDE] "):
            d = dict(KV.findall(s.split(" hu=")[0]))
            if d.get("side") == "1" and d["unit"] in cand_units:
                psi_dec["decisions"] += 1
                psi_dec["used"] += 1 if d.get("act") in PSI else 0
                psi_dec["seen_some"] += 1 if d.get("seen") not in (None, "-", "") else 0
    print(f"  {label}: юнитов с пси-кандидатом {len(cand_units)}; их решений {psi_dec['decisions']}, с видимой целью {psi_dec['seen_some']}, пси применено {psi_dec['used']}; решений врага бойцами игрока {c['hostile_decisions_by_player_units']}, таких бойцов {sum(v for k, v in c.items() if k.startswith('captured_unit_'))}")
    for s in ls:
        if s.startswith("[AISCD] ") and '"turn_end"' in s:
            j = json.loads(s[8:])
            print(f"     ход {j['turn']}: consults {j.get('consults')} special {j.get('special')} thinks {j.get('thinks')}")
    return c


def show_target(z, label, unit):
    raw = gzip.open(io.BytesIO(z.read(f"out/{label}/openxcom.log.gz")), "rt", encoding="utf-8", errors="replace").read().splitlines()
    for s in raw:
        s = s.split("\t")[-1]
        if s.startswith("[AISTATE] ") and f" unit={unit} " in s:
            print("   ", s[:125])
        elif s.startswith("[AICASUALTY] ") and f"victim={unit} " in s:
            print("   ", s[:170])
        elif s.startswith("[AISCD] ") and f'"target":{unit},' in s and '"tOut"' in s:
            print("   ", s[8:240])


for a in sys.argv[1:]:
    zp, prefix, arm = a.rsplit(":", 2)
    z = zipfile.ZipFile(zp)
    for s_ in (1, 2, 3, 4):
        battle(z, f"{prefix}_{arm}_L8_s{s_}")
    if prefix == "sfI":
        print("цель attack_on_out, 91 в s4:")
        show_target(z, "sfI_XN_L8_s4", 91)
    if prefix == "sfF" and arm == "XN":
        print("цель attack_on_out, 157 в s4:")
        show_target(z, "sfF_XN_L8_s4", 157)
