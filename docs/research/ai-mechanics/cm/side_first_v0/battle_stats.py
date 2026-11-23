"""SIDE-FIRST COMBAT: one battle read from its log. stats(zip, label) -> dict; run as a script it prints battles side by side. args: zip:label [zip:label ...]

From the record lines only: [AIRESULT] the battle's totals; [AIDECIDE] + [AIEXEC] per hostile action (type, time units, damage to other factions, friendly damage, units down);
[AICASUALTY] who brought whom down, in whose turn; [AISCD] the director's own actions, its forecast against the fact, vetoes, time.
Turn of a casualty: "how" is not used for the turn owner; the [AISTATE] aistart/pstart lines mark whose turn is running."""
import gzip
import io
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
KV = re.compile(r"(\w+)=([^ ]*)")
NAMES = {2: "walk", 6: "throw", 7: "auto", 8: "snap", 9: "aim", 10: "hit", 13: "psi", 14: "mc", 0: "none", 15: "rethink", 3: "turn"}
ATT = {6, 7, 8, 9, 10, 13, 14}


def lines(zip_path, label):
    with zipfile.ZipFile(zip_path) as z:
        raw = gzip.open(io.BytesIO(z.read(f"out/{label}/openxcom.log.gz")), "rt", encoding="utf-8", errors="replace").read().splitlines()
    return [s.split("\t")[-1] for s in raw]


def stats(zip_path, label):
    st = Counter()
    by = defaultdict(Counter)
    src = Counter()
    wfr = Counter()
    res = {}
    pend = None
    cur_side = None
    scd = []
    last_turn_end = None
    weapon_w = {}
    for s in lines(zip_path, label):
        if s.startswith("[AIDECIDE] "):
            d = dict(KV.findall(s.split(" hu=")[0]))
            pend = (d.get("side"), d.get("unit"), int(d.get("act", 0)))
            if d.get("side") == "1":
                cur_side = "1"
                st["dec"] += 1
                by[NAMES.get(pend[2], str(pend[2]))]["dec"] += 1
            elif d.get("side") == "0":
                cur_side = "0"
        elif s.startswith("[AIEXEC] ") and pend:
            x = json.loads(s[9:])
            side, u, act = pend
            pend = None
            if side != "1" or str(x.get("unit")) != u:
                continue
            spent = x.get("spent") or 0
            n = NAMES.get(act, str(act))
            c = by[n]
            c["n"] += 1
            c["spent"] += spent
            c["dmg"] += x.get("dmg") or 0
            c["fdmg"] += x.get("fdmg") or 0
            c["down"] += x.get("downed") or 0
            c["fdown"] += x.get("fdowned") or 0
            c["stun"] += x.get("stunned") or 0
            if (x.get("dmg") or 0) > 0:
                c["hitacts"] += 1
            st["spent"] += spent
            st["dmg"] += x.get("dmg") or 0
            st["fdmg"] += x.get("fdmg") or 0
            st["hp_lost_walk"] += (x.get("hp_lost") or 0) if act == 2 else 0
            if act in ATT and spent > 0:
                st["attacks"] += 1
                st["att_spent"] += spent
                if (x.get("dmg") or 0) > 0:
                    st["att_hit"] += 1
                if (x.get("fdmg") or 0) > 0:
                    st["att_ff"] += 1
        elif s.startswith("[AICASUALTY] "):
            d = dict(KV.findall(s))
            vf = d.get("vfaction")
            kf = d.get("kfaction")
            side = d.get("side")
            key = f"v{vf}_k{kf}_t{side}"
            st[key] += 1
            if vf == "1" and kf == "1":
                wfr[d.get("weapon", "?")] += 1
        elif s.startswith("[AIREC] "):
            j = json.loads(s[8:])
            if j.get("side") == 1:
                b = j.get("base") or {}
                src[str(b.get("src"))] += 1
        elif s.startswith("[AISCD] "):
            j = json.loads(s[8:])
            scd.append(j)
            if j.get("ev") == "turn_end":
                last_turn_end = j
        elif s.startswith("[AIRESULT] "):
            res = dict(KV.findall(s))
    return {"st": st, "by": by, "res": res, "scd": scd, "src": src, "wfr": wfr, "end": last_turn_end}


def director(b):
    out = Counter()
    pend = {}
    per = defaultdict(Counter)
    for j in b["scd"]:
        e = j.get("ev")
        if e == "act":
            out["act_" + j["kind"]] += 1
            pend[j["actor"]] = j
        elif e == "result":
            k = j["kind"]
            out["res_" + k] += 1
            out["spent_" + k] += j.get("spent", 0)
            out["ownLoss_" + k] += j.get("ownLoss", 0)
            out["ownDown_" + k] += j.get("ownDown", 0)
            out["actorOut_" + k] += j.get("actorOut", 0)
            if k in ("A", "T"):
                p = pend.get(j["actor"]) or {}
                out["eff_sum"] += j.get("eff", 0)
                out["ff_sum"] += j.get("ff", 0)
                out["tDmg"] += j.get("tDmg", 0)
                out["tStun"] += j.get("tStun", 0)
                out["tHit"] += j.get("tHit", 0)
                out["tOut"] += j.get("tOut", 0)
                out["atk"] += 1
                per[p.get("w", "?")]["n"] += 1
                per[p.get("w", "?")]["eff"] += j.get("eff", 0)
                per[p.get("w", "?")]["dmg"] += j.get("tDmg", 0)
                per[p.get("w", "?")]["hit"] += j.get("tHit", 0)
        elif e in ("veto", "special", "rng_touched", "would"):
            out[e] += 1
    return out, per


def show(b, label):
    r = b["res"]
    st = b["st"]
    print(f"\n=== {label}: turn {r.get('turn')}, player {r.get('player')}, pdead {r.get('pdead')}, pout {r.get('pout')}, phplost {r.get('phplost')}; hostile {r.get('hostile')}, hdead {r.get('hdead')}, hout {r.get('hout')}; live soldiers {r.get('livesoldiers')}")
    print(f"  decisions {st['dec']}, TU spent {st['spent']}, attacks {st['attacks']}, with damage {st['att_hit']}, with friendly damage {st['att_ff']}, dmg {st['dmg']}, friendly dmg {st['fdmg']}")
    print("  " + "  ".join(f"{k}:{v}" for k, v in sorted(st.items()) if k.startswith("v")))
    print(f"  {'action':<8}{'n':>6}{'spent':>8}{'dmg':>7}{'fdmg':>7}{'hit':>6}{'down':>6}{'fdown':>6}{'stun':>6}")
    for k, c in sorted(b["by"].items(), key=lambda kv_: -kv_[1]["n"]):
        print(f"  {k:<8}{c['n']:>6}{c['spent']:>8}{c['dmg']:>7}{c['fdmg']:>7}{c['hitacts']:>6}{c['down']:>6}{c['fdown']:>6}{c['stun']:>6}")
    if b["src"]:
        print("  src: " + " ".join(f"{k}:{v}" for k, v in b["src"].most_common(12)))
    if b["wfr"]:
        print("  own killed by own weapon: " + " ".join(f"{k}:{v}" for k, v in b["wfr"].most_common(6)))
    if b["scd"]:
        o, per = director(b)
        print("  director: " + " ".join(f"{k}:{round(v, 1)}" for k, v in sorted(o.items())))
        print("  forecast vs fact by weapon (n, eff sum, damage, hits): " + " | ".join(f"{w} {c['n']} {c['eff']:.0f} {c['dmg']} {c['hit']}" for w, c in sorted(per.items(), key=lambda kv_: -kv_[1]["n"])[:10]))
        if b["end"]:
            print("  last turn_end: " + json.dumps(b["end"]))


if __name__ == "__main__":
    for a in sys.argv[1:]:
        z, l = a.rsplit(":", 1)
        show(stats(z, l), l)
