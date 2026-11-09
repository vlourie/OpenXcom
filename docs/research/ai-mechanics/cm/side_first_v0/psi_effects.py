"""SIDE-FIRST COMBAT V0.1, L8: psi by the engine's numbers (RuleItem.h: BA_MINDCONTROL = 13, BA_PANIC = 14). Per arm: done per turn; capture attempts and the turns that ended with the target on the hostile side; what captured soldiers did; the share of decisions of psi-capable units that had a target in sight; morale, stun and wounds of the player per unit-turn in hostile turns.
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
KIND = {"13": "mc", "14": "panic"}


def battle(z, label):
    ls = [s.split("\t")[-1] for s in gzip.open(io.BytesIO(z.read(f"out/{label}/openxcom.log.gz")), "rt", encoding="utf-8", errors="replace").read().splitlines()]
    c = Counter()
    start = {}
    fac = {}
    cand = set()
    pend = None
    targets = Counter()
    for s in ls:
        if s.startswith("[AICAND] "):
            m = re.search(r"unit=(\d+)", s)
            if m and ('"t":13' in s or '"t":14' in s):
                cand.add(m.group(1))
    for s in ls:
        if s.startswith("[AISTATE] "):
            kind = s.split(" ", 2)[1]
            d = dict(KV.findall(s))
            if "unit" not in d or "hp" not in d or int(d["unit"]) >= 1000000:
                continue
            u = d["unit"]
            if fac.get(u) == "0" and d.get("faction") == "1":
                c["captured_seen"] += 1
            fac[u] = d.get("faction")
            st = (int(d["morale"]), int(d["stun"]), int(d.get("wounds") or 0))
            if kind == "aistart":
                start[(int(d["turn"]), u)] = st
            elif kind == "pstart" and (int(d["turn"]) - 1, u) in start:
                b = start[(int(d["turn"]) - 1, u)]
                c["unit_turns"] += 1
                c["morale_lost"] += max(0, b[0] - st[0])
                c["stun_added"] += max(0, st[1] - b[1])
                c["wounds_added"] += max(0, st[2] - b[2])
                c["morale_zero"] += 1 if st[0] == 0 and b[0] > 0 else 0
        elif s.startswith("[AIDECIDE] "):
            d = dict(KV.findall(s.split(" hu=")[0]))
            if d.get("side") != "1":
                pend = None
                continue
            pend = d
            if d["unit"] in cand:
                c["cand_dec"] += 1
                c["cand_seen"] += 1 if d.get("seen") not in (None, "-", "") else 0
            if d.get("act") in KIND:
                targets[d.get("aim")] += 1
        elif s.startswith("[AIEXEC] ") and pend:
            x = json.loads(s[9:])
            d, pend = pend, None
            if str(x.get("unit")) != d["unit"]:
                continue
            spent = x.get("spent") or 0
            if d.get("act") in KIND and spent > 0:
                c[KIND[d["act"]]] += 1
                c["psi_tu"] += spent
            if int(d["unit"]) < 1000000:
                c["cap_dec"] += 1
                c["cap_spent"] += spent
                c["cap_fdmg"] += x.get("fdmg") or 0
                c["cap_dmg"] += x.get("dmg") or 0
        elif s.startswith("[AIRESULT] "):
            c["turns"] = int(dict(KV.findall(s)).get("turn") or 0)
    return c, targets


for a in sys.argv[1:]:
    zp, prefix, arm = a.rsplit(":", 2)
    z = zipfile.ZipFile(zp)
    tot = Counter()
    for s_ in (1, 2, 3, 4):
        c, t = battle(z, f"{prefix}_{arm}_L8_s{s_}")
        tot.update(c)
        print(f"  {prefix} {arm} s{s_}: ходов {c['turns']}, захват {c['mc']}, паника {c['panic']}, на ход {(c['mc'] + c['panic']) / max(1, c['turns']):.2f}, цели {dict(t)}, боец у врага {c['captured_seen']}, решений захваченных {c['cap_dec']}")
    n = max(1, tot["unit_turns"])
    print(f"{prefix} {arm} L8: ходов {tot['turns']}, захват {tot['mc']}, паника {tot['panic']}, всего {tot['mc'] + tot['panic']}, на ход {(tot['mc'] + tot['panic']) / max(1, tot['turns']):.2f}; ОВ {tot['psi_tu']}; боец у врага на конец хода {tot['captured_seen']}; решений захваченных {tot['cap_dec']}, их ОВ {tot['cap_spent']}, урон {tot['cap_dmg']}, по своим врага {tot['cap_fdmg']}; решений пси-способных {tot['cand_dec']}, с видимой целью {tot['cand_seen']} = {100 * tot['cand_seen'] / max(1, tot['cand_dec']):.1f} %; юнит-ходов игрока {tot['unit_turns']}: потеря морали {tot['morale_lost']} ({tot['morale_lost'] / n:.1f} на юнит-ход), мораль до 0 {tot['morale_zero']}, оглушение +{tot['stun_added']} ({tot['stun_added'] / n:.2f}), раны +{tot['wounds_added']} ({tot['wounds_added'] / n:.2f})")
