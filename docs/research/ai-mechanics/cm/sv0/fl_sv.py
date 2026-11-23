"""STRIKE-V0, shadow analysis: the 746 historical 'none' unit-turns of D0 (fl_focus2.py: possible shooter, no attack in its turn)
split at the moment of decision by the prototype's own checks, written by the shadow run (OXCE_AI_STRIKE=1: nothing changed).

  py -3.13 -I fl_sv.py <out dir> <D0 prefix> <shadow prefix>

For every hostile decision the shadow run wrote [AISTRIKE] kind=opp: the decision's class (attack, escape, ambush, status,
charging, tu_changed, combat_move, mission, other_act, allowed) and the best shot the unit had then at a target known to the
side now (ok, or why not: no_target, no_weapon, no_mode, no_tu, no_ammo, no_lof, no_estimate, low_effect)."""
import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")
FIRE = {7, 8, 9}
ATT = {6, 7, 8, 9, 10, 12, 13, 14}


def none_units(d):
    """The possible-shooter unit-turns with no attack in their turn (fl_focus2.py's 'none')."""
    snap = defaultdict(dict)
    acts, first = {}, {}
    dec = []
    pend = None
    for raw in gzip.open(d / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace"):
        body = raw.rstrip("\n").split("\t", 2)[-1]
        if body.startswith("[AISTATE] aistart "):
            s = dict(KV.findall(body))
            snap[int(s["turn"])][s["unit"]] = s
        elif body.startswith("[AICAND] acts="):
            acts[body.split()[1].split("=")[1]] = body.split(" list=", 1)[1]
        elif body.startswith("[AIREC] "):
            r = json.loads(body[8:])
            k = (r["turn"], str(r["unit"]))
            if k not in first:
                first[k] = (r["state"]["tu"], r["cand"]["acts"])
        elif body.startswith("[AIDECIDE] "):
            pend = dict(KV.findall(body.split(" hu=")[0]))
        elif body.startswith("[AIEXEC] ") and pend:
            x = json.loads(body[9:])
            if str(x["unit"]) == pend["unit"] and pend["side"] == "1":
                if int(pend["act"]) in ATT and (x.get("spent") or 0) > 0 and not x.get("walk"):
                    dec.append((int(pend["turn"]), pend["unit"]))
            pend = None
    shooters = defaultdict(set)
    for (t, u), (tu, h) in first.items():
        if t not in snap or snap[t].get(u, {}).get("faction") != "1":
            continue
        a = acts.get(h, "[]")
        for x in (json.loads(a) if a.startswith("[") else []):
            e = str(x.get("u"))
            ev = snap[t].get(e)
            if (x.get("k") == "a" and x.get("t") in FIRE and x.get("lof") == 1 and (x.get("tu") or 999) <= tu and ev
                    and ev["faction"] == "0" and ev["spotted"] == "0" and not ev["weapon"].startswith("AUX_")):
                shooters[(t, e)].add(u)
    units = set()
    for (t, e), g in shooters.items():
        if len(g) >= 3:
            units |= {(t, u) for u in g}
    done = set(dec)
    return {k for k in units if k not in done}


def shadow(d):
    """Per hostile unit-turn: its kind=opp lines in order, and whether the shadow coordinator would have fired it."""
    opp = defaultdict(list)
    would = set()
    alone = set()
    for raw in gzip.open(d / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace"):
        body = raw.rstrip("\n").split("\t", 2)[-1]
        if body.startswith("[AISTRIKE] kind=opp "):
            s = dict(KV.findall(body))
            opp[(int(s["turn"]), s["unit"])].append(s)
        elif body.startswith("[AISTRIKE] kind=exec "):
            s = dict(KV.findall(body))
            would.add((int(s["turn"]), s["unit"]))
        elif body.startswith("[AISTRIKE] kind=noorder "):
            s = dict(KV.findall(body))
            alone.add((int(s["turn"]), s["unit"]))
    return opp, would, alone


GROUP = {"escape": "2 escape/panic/mission", "status": "2 escape/panic/mission", "mission": "2 escape/panic/mission",
         "charging": "2 escape/panic/mission",
         "ambush": "3 ambush/conscious choice", "combat_move": "3 ambush/conscious choice",
         "tu_changed": "3 ambush/conscious choice", "other_act": "3 ambush/conscious choice", "no_ai": "3 ambush/conscious choice"}


def main():
    out, pd, ps = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    total = Counter()
    cross = defaultdict(Counter)
    groups = Counter()
    why5 = Counter()
    order = Counter()
    allcls = Counter()
    allok = Counter()
    per_scen = []
    missing = 0
    for dd in sorted(out.glob(f"{pd}_*")):
        sd = out / dd.name.replace(f"{pd}_", f"{ps}_", 1)
        if not (sd / "openxcom.log.gz").exists():
            print("no shadow log for", dd.name)
            continue
        keys = none_units(dd)
        opp, would, alone = shadow(sd)
        for lines in opp.values():
            for s in lines:
                allcls[s["cls"]] += 1
                if s["cls"] == "allowed":
                    allok[s["shot"]] += 1
        n_allowed = 0
        for k in sorted(keys):
            lines = opp.get(k)
            if not lines:
                missing += 1
                groups["? no decision logged"] += 1
                continue
            total["unit-turns"] += 1
            ok_allowed = [s for s in lines if s["cls"] == "allowed" and s["shot"] == "ok"]
            first = lines[0]
            cross[first["cls"]][first["shot"] if first["shot"] == "ok" else "no"] += 1
            if ok_allowed:
                groups["1 allowed at decision time"] += 1
                n_allowed += 1
                order["would fire by order" if k in would else ("no shared target (fewer than 2 shooters)" if k in alone
                                                                else "other (order elsewhere, used)")] += 1
            elif first["cls"] in GROUP:
                groups[GROUP[first["cls"]]] += 1
            else:
                groups["5 shot not confirmed"] += 1
                why5[first["shot"]] += 1
        per_scen.append((dd.name, len(keys), n_allowed))
    n = total["unit-turns"]
    print(f"historical 'none' unit-turns with shadow decisions: {n} (no decision logged: {missing})")
    for g, c in sorted(groups.items()):
        print(f"  {g:45s} {c:5d}")
    print("  of group 5 (first decision allowed by class, no useful legal shot now): " +
          ", ".join(f"{w}={c}" for w, c in why5.most_common()))
    print("  of group 1, what the shadow coordinator did: " + ", ".join(f"{w}={c}" for w, c in order.most_common()))
    print("first decision class x useful legal shot now (group 4 = column ok):")
    for c, cc in sorted(cross.items()):
        print(f"  {c:12s} ok={cc['ok']:4d} no={cc['no']:4d}")
    print("all hostile decisions of the shadow run, by class: " + ", ".join(f"{w}={c}" for w, c in allcls.most_common()))
    print("  class allowed, by shot: " + ", ".join(f"{w}={c}" for w, c in allok.most_common()))
    print("per battle: none / allowed")
    for name, a, b in per_scen:
        print(f"  {name:22s} {a:4d} {b:4d}")


main()
