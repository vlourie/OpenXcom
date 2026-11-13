"""SIDE-FIRST COMBAT V0.1: the M3 gate. The first hostile turn by unit: think rounds, runs of decisions, the time units left. "No second pass" = a unit the director did not lead,
alive, with more than 5 time units left at the end of the turn, whose decisions make one run. args: zip:prefix:arm ... (seeds 1-4 of M3, or --mission)"""
import gzip
import io
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
KV = re.compile(r"(\w+)=([^ ]*)")
TYPES = ("CHRYSSALID", "SILACOID")


def turn1(z, label, turn=1):
    raw = gzip.open(io.BytesIO(z.read(f"out/{label}/openxcom.log.gz")), "rt", encoding="utf-8", errors="replace").read().splitlines()
    typ, runs, rounds, spent, attacks, left, led, out = {}, Counter(), Counter(), Counter(), Counter(), {}, set(), set()
    last = None
    pend = None
    scd = set()
    for s in raw:
        s = s.split("\t")[-1]
        if s.startswith("[AISCD] "):
            j = json.loads(s[8:])
            if j.get("turn") == turn and j.get("ev") == "act":
                scd.add(str(j["actor"]))
                led.add(str(j["actor"]))
        elif s.startswith("[AISTATE] "):
            d = dict(KV.findall(s))
            if d.get("unit") and d.get("type"):
                typ[d["unit"]] = d["type"]
                if s.startswith("[AISTATE] aistart") and d.get("turn") == str(turn) and d.get("faction") == "1":
                    left.setdefault(d["unit"], int(d.get("tu") or 0))
        elif s.startswith("[AICASUALTY] "):
            d = dict(KV.findall(s))
            if d.get("turn") == str(turn):
                out.add(d.get("victim"))
        elif s.startswith("[AIDECIDE] "):
            d = dict(KV.findall(s.split(" hu=")[0]))
            pend = None
            if d.get("side") != "1" or d.get("turn") != str(turn):
                continue
            u = d["unit"]
            if u != last:
                runs[u] += 1
            last = u
            if u in scd:
                scd.discard(u)
            else:
                rounds[u] += 1
            pend = (u, d.get("act"))
        elif s.startswith("[AIEXEC] ") and pend:
            x = json.loads(s[9:])
            u, act = pend
            pend = None
            spent[u] += x.get("spent") or 0
            left[u] = x.get("tu") if x.get("tu") is not None else left.get(u, 0)
            if act in ("6", "7", "8", "9", "10") and (x.get("spent") or 0) > 0:
                attacks[u] += 1
    return typ, runs, rounds, spent, attacks, left, led, out


def report(z, prefix, arm, mission, seeds=(1, 2, 3, 4)):
    tot = defaultdict(Counter)
    for s_ in seeds:
        typ, runs, rounds, spent, attacks, left, led, out = turn1(z, f"{prefix}_{arm}_{mission}_s{s_}")
        c = Counter()
        for u in runs:
            t = typ.get(u, "?")
            for w in TYPES:
                if w in t:
                    tot[w]["units"] += 1
                    tot[w]["rounds"] += rounds[u]
                    tot[w]["tu"] += spent[u]
                    tot[w]["attacks"] += attacks[u]
                    tot[w]["seed%d" % s_] += rounds[u]
                    tot[w]["max"] = max(tot[w]["max"], rounds[u])
            if u in led or u in out:
                continue
            c["think_led"] += 1
            if runs[u] == 1 and (left.get(u) or 0) > 5:
                c["no_second"] += 1
                if any(w in t for w in TYPES):
                    tot["chr_sil"]["no_second"] += 1
        tot["all"].update(c)
        tot["seed_no_second"]["s%d" % s_] = c["no_second"]
        tot["seed_led"]["s%d" % s_] = c["think_led"]
    a = tot["all"]
    print(f"{prefix} {arm} {mission}: без директора {a['think_led']}, один проход с остатком ОВ {a['no_second']} ({100 * a['no_second'] / max(1, a['think_led']):.0f} %), из них хризалид и силакоидов {tot['chr_sil']['no_second']}; по сидам {dict(tot['seed_no_second'])} из {dict(tot['seed_led'])}")
    for w in TYPES:
        t = tot[w]
        print(f"   {w}: юнитов {t['units']}, раундов {t['rounds']} {[t['seed%d' % s] for s in seeds]}, макс. {t['max']}, ОВ {t['tu']}, атак {t['attacks']}")


if __name__ == "__main__":
    mission = "M3"
    for a in sys.argv[1:]:
        if a.startswith("--mission="):
            mission = a.split("=")[1]
            continue
        zp, prefix, arm = a.rsplit(":", 2)
        report(zipfile.ZipFile(zp), prefix, arm, mission)
