"""COUNTERFIRE V0: one battle, D0 (A, the saved log) against the counterfire run (C) of the same exe base, mission and seed.

  py -3.13 -I fl_cf.py <A log.gz> <C log.gz> [<C2 log.gz>]   (C2: a repeat of C, compared whole)

1. Identity: the record lines ([AI*], timestamps cut; lines with the configuration or the clock and every [AIORDER] left out)
   of C up to its first [AIORDER] status=cf_cancel against A's; the state hashes of that decision against A's.
2. The rule's lines in C ([AIORDER] arm=cf): every cancel and every kept attack at a vehicle with a blast counter, why.
3. Per cancel: what the same decision did in A (the attack, its damage, reactions in its window, hostile units newly down in it
   and who downed them) - exact for the first cancel only, the state is the same there; later ones are in a battle that has
   already gone apart and are marked so. What the unit did next in C in that turn (its remaining decisions, TU).
4. The window of the first change: the hostile turn T and the player's turn T+1 in A and in C - hostile units newly down (by
   the counter vehicle and by anyone), split by the hostile decision in whose window it happened (attack at the vehicle, other
   attack, walk); player HP lost and player units down; the vehicle's reactions; TU the hostile side spent; hostile units able
   to act at the start of turn T+2 (aistart status 0).
5. Rules: cancels per unit per turn (a repeat beyond the second pass is a loop), TU of a unit never rising within a turn
   (no TU given back), every cancel followed by the unit's [AIDECIDE] act=0 (no action made in its place).
6. The battle's result line in A and in C.
"""
import gzip
import json
import re
import sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")
CFG = re.compile(r'"cfg":"[0-9a-f]+",')
SKIP = ("[AIRECHEAD]", "[AIPROBE] closed", "[AILIGHT]", "[AIREUSE]", "[AIRESULT]", "[AIORDER]")
ATT = {6, 7, 8, 9, 10, 12}


def lines_of(path):
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rt", encoding="utf-8", errors="replace") as f:
        return [b for b in (raw.rstrip("\n").split("\t", 2)[-1] for raw in f) if b.startswith("[AI")]


def norm(lines):
    return [CFG.sub("", l) for l in lines if not l.startswith(SKIP)]


def dec_of(l):
    return dict(KV.findall(l.split(" hu=")[0]))


def windows(lines):
    """Every hostile decision with its window: exec, reactions (unit ids), hostile units newly down (victim, killer, weapon),
    player units newly down; also aistart states per turn and the result."""
    out, down, cur = [], set(), None
    aist = defaultdict(dict)
    result = ""
    for i, l in enumerate(lines):
        if l.startswith("[AISTATE] aistart "):
            d = dict(KV.findall(l))
            aist[int(d["turn"])][d["unit"]] = d
            if d.get("status") == "0":
                down.discard(d["unit"])
        elif l.startswith("[AIDECIDE] "):
            d = dec_of(l)
            down.discard(d["unit"])
            cur = {"i": i, "d": d, "x": None, "react": [], "hlost": [], "plost": []}
            out.append(cur)
        elif l.startswith("[AIEXEC] ") and cur and cur["x"] is None:
            x = json.loads(l[9:])
            if str(x["unit"]) == cur["d"]["unit"]:
                cur["x"] = x
        elif l.startswith("[AIEVENT] ") and " what=reaction " in l and cur:
            cur["react"].append(dict(KV.findall(l)).get("unit"))
        elif l.startswith("[AICASUALTY] "):
            c = dict(KV.findall(l))
            new = c["victim"] not in down
            down.add(c["victim"])
            if new and cur:
                (cur["hlost"] if c.get("vfaction") == "1" else cur["plost"]).append(c)
        elif l.startswith("[AIRESULT] "):
            d = dict(KV.findall(l))
            result = " ".join(f"{k}={d.get(k)}" for k in ("how", "turn", "player", "pdead", "livesoldiers", "hostile", "hdead",
                                                          "hleft", "phplost"))
    return out, aist, result


def kind(w, vehicles):
    a = int(w["d"]["act"])
    spent = (w["x"] or {}).get("spent") or 0
    if a in ATT and spent > 0 and not (w["x"] or {}).get("walk"):
        return "attack at the vehicle" if w["d"].get("aim") in vehicles else "other attack"
    if a == 2:
        return "walk"
    return f"act {a}" if a else "none"


def turn_sum(ws, aist, T, vehicles):
    s = Counter()
    by = Counter()
    lost_units = []
    for w in ws:
        t, side = int(w["d"]["turn"]), w["d"]["side"]
        if t == T and side == "1":
            s["tu_spent"] += (w["x"] or {}).get("spent") or 0
            s["att_vehicle"] += kind(w, vehicles) == "attack at the vehicle"
            s["dmg"] += (w["x"] or {}).get("dmg") or 0
            s["veh_react"] += sum(1 for r in w["react"] if r in vehicles)
            for c in w["hlost"]:
                s["h_lost_T"] += 1
                if c.get("killer") in vehicles:
                    s["h_lost_T_vehicle"] += 1
                    by[kind(w, vehicles)] += 1
                lost_units.append(f"{c['victim']}({c['how']} by {c['killer']} {c.get('weapon', '')[:16]}; during {w['d']['unit']} "
                                  f"{kind(w, vehicles)})")
            s["p_lost_T"] += len(w["plost"])
        if t == T + 1 and side == "0":
            s["h_lost_T1"] += len(w["hlost"])
            s["p_lost_T1"] += len(w["plost"])
    st = aist.get(T + 2, {})
    s["h_able_T2"] = sum(1 for d in st.values() if d.get("faction") == "1" and d.get("status") == "0")
    s["p_able_T2"] = sum(1 for d in st.values() if d.get("faction") == "0" and d.get("status") == "0")
    return s, by, lost_units


def main():
    A, C = lines_of(sys.argv[1]), lines_of(sys.argv[2])
    C2 = lines_of(sys.argv[3]) if len(sys.argv) > 3 else None
    cf = [dict(KV.findall(l)) | {"i": i} for i, l in enumerate(C) if l.startswith("[AIORDER] ") and " arm=cf " in l]
    cancels = [o for o in cf if o["status"] == "cf_cancel"]
    print("== 1. identity")
    if C2 is not None:
        whole = lambda ls: [CFG.sub("", l) for l in ls if not l.startswith(SKIP[:-1])]
        print(f"repeat vs C, whole log with the rule's lines: {'IDENTICAL' if whole(C) == whole(C2) else 'DIFFERENT'}")
    fc = cancels[0]["i"] if cancels else None
    nC, nA = norm(C if fc is None else C[:fc]), norm(A)
    same = nC == (nA[:len(nC)] if fc is not None else nA)
    print(f"C vs A: {'whole log' if fc is None else f'{len(nC)} lines before the first cancel'}: {'IDENTICAL' if same else 'DIFFERENT'}")
    if not same:
        for k, (a, b) in enumerate(zip(nC, nA)):
            if a != b:
                print(f"   first difference at line {k}:\n   C: {a[:300]}\n   A: {b[:300]}")
                break
    wa, aistA, resA = windows(A)
    wc, aistC, resC = windows(C)
    vehicles = {o["target"] for o in cf}
    if fc is not None:
        nxt = next(l for l in C[fc:] if l.startswith("[AIDECIDE] "))
        m = dec_of(nxt)
        key = (m["turn"], m["unit"], m["n"])
        hk = ("hu", "hi", "ho", "hm", "hr", "hr0", "ha0")
        refd = next((l for l in A if l.startswith("[AIDECIDE] ") and (dec_of(l)["turn"], dec_of(l)["unit"], dec_of(l)["n"]) == key), "")
        mc, mr = dict(KV.findall(nxt)), dict(KV.findall(refd))
        print(f"   first cancel: {C[fc][:330]}")
        print(f"   its decision vs A's (turn {key[0]} unit {key[1]} n={key[2]}): " + " ".join(
            f"{k}={'=' if mc.get(k) == mr.get(k) else 'DIFF'}" for k in hk) + f"; act C {mc.get('act')} vs A {mr.get('act')}")
    print("\n== 2. the rule's lines in C (every attack at a vehicle with a blast counter)")
    print("statuses: " + ", ".join(f"{k} {n}" for k, n in Counter(o["status"] for o in cf).most_common()))
    print("kept for 'other': " + ", ".join(f"{k} {n}" for k, n in Counter(o["other"] for o in cf if o["status"] == "cf_keep.other").most_common()))
    for o in cf:
        print(f"  t{o['turn']} {o['unit']} n={o['n']} {o['status']:<22} type={o['type']} w={o['weapon'][:18]} target={o['target']} "
              f"power={o['power']} shots={o['shots']} est={o['est']} maxhp={o['maxhp']} side={o['side']} armorloss={o['armorloss']} "
              f"other={o['other']} tu={o['tu']}")
    print("\n== 3. per cancel: the same decision in A, and what the unit did next in C")
    diverged_at = fc
    for k, o in enumerate(cancels):
        key = (o["turn"], o["unit"], o["n"])
        wA = next((w for w in wa if (w["d"]["turn"], w["d"]["unit"], w["d"]["n"]) == key), None)
        tag = "exact (state identical)" if k == 0 else "battle already apart - indicative only"
        print(f"-- cancel {k + 1}: t{o['turn']} unit {o['unit']} n={o['n']} at {o['target']} ({tag})")
        if wA:
            x = wA["x"] or {}
            print(f"   A: act={wA['d']['act']} aim={wA['d']['aim']} w={wA['d']['weapon'][:18]} spent={x.get('spent')} dmg={x.get('dmg')} "
                  f"downed={x.get('downed')} reactions={','.join(wA['react']) or '-'} (vehicle {sum(1 for r in wA['react'] if r in vehicles)})")
            print(f"      hostile newly down in its window: {len(wA['hlost'])}: " + (", ".join(
                f"{c['victim']}({c['how']} by {c['killer']} {c.get('weapon', '')[:16]})" for c in wA["hlost"]) or "-"))
        else:
            print("   A: no decision with this key")
        mine = [w for w in wc if w["d"]["turn"] == o["turn"] and w["d"]["side"] == "1" and w["d"]["unit"] == o["unit"] and w["i"] > o["i"]]
        for w in mine:
            x = w["x"] or {}
            print(f"   C next: n={w['d']['n']} act={w['d']['act']} mode={w['d'].get('mode')} tu={w['d']['tu']} to={w['d']['to']} "
                  f"spent={x.get('spent')} dmg={x.get('dmg')} reactions={','.join(w['react']) or '-'} hostile down {len(w['hlost'])}")
    if fc is not None:
        T = int(cancels[0]["turn"])
        print(f"\n== 4. the window of the first change: hostile turn {T}, player turn {T + 1}, able to act at turn {T + 2}")
        sa, ba, la = turn_sum(wa, aistA, T, vehicles)
        sc, bc, lc = turn_sum(wc, aistC, T, vehicles)
        keys = ["att_vehicle", "veh_react", "h_lost_T", "h_lost_T_vehicle", "p_lost_T", "dmg", "tu_spent", "h_lost_T1", "p_lost_T1",
                "h_able_T2", "p_able_T2"]
        print(f"{'':<18}" + "".join(f"{k:>17}" for k in keys))
        print(f"{'A (D0)':<18}" + "".join(f"{sa[k]:>17}" for k in keys))
        print(f"{'C (CF)':<18}" + "".join(f"{sc[k]:>17}" for k in keys))
        print(f"A: hostile lost to the vehicle in turn {T} by window: " + (", ".join(f"{k} {n}" for k, n in ba.items()) or "-"))
        print(f"C: hostile lost to the vehicle in turn {T} by window: " + (", ".join(f"{k} {n}" for k, n in bc.items()) or "-"))
        print(f"A lost in turn {T}: " + ("; ".join(la) or "-"))
        print(f"C lost in turn {T}: " + ("; ".join(lc) or "-"))
    print("\n== 5. rules")
    per = Counter((o["turn"], o["unit"]) for o in cancels)
    print(f"cancels {len(cancels)}; most per unit per turn {max(per.values()) if per else 0}"
          + ("" if not per or max(per.values()) <= 2 else "  <-- LOOP?"))
    tu_up = []
    last = {}
    for w in wc:
        d = w["d"]
        if d["side"] != "1":
            continue
        k = (d["turn"], d["unit"])
        tu = int(d["tu"])
        if k in last and tu > last[k]:
            tu_up.append(f"t{d['turn']} {d['unit']} n={d['n']} {last[k]}->{tu}")
        last[k] = tu
    print(f"TU rising within a turn for a hostile unit: {len(tu_up)} " + " ".join(tu_up[:10]))
    bad = 0
    for o in cancels:
        nxt = next((dec_of(l) for l in C[o["i"]:] if l.startswith("[AIDECIDE] ")), None)
        if not nxt or nxt["unit"] != o["unit"] or nxt["act"] != "0":
            bad += 1
            print(f"   cancel not followed by its own act=0: {o['turn']} {o['unit']} -> {nxt}")
    print(f"cancels followed by the unit's act=0 decision: {len(cancels) - bad} of {len(cancels)}")
    print("\n== 6. result")
    print(f"A: {resA}\nC: {resC}")


main()
