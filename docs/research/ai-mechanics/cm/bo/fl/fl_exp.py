"""TACTICAL STAGE 2: the A/B/C/D runs of M3 seed 1 - identity before the first changed decision, enemy turn 2 and the player's
turn 3 per run, the four shooters' action sequences, the battle's outcome.

  py -3.13 -I fl_exp.py <ref label>=<log> <label>=<log> ...   (log: openxcom.log or .gz; the first one is A, the reference)

Identity: the record lines ([AI*], timestamps cut) are compared with A's up to the run's first [AIORDER] that changed an action
(status shot or nil_attack); lines that carry the configuration or the clock are left out ([AIRECHEAD], [AIPROBE] closed,
[AILIGHT], [AIREUSE], [AIRESULT]; the cfg hash in [AIREC]). A repeat of the same arm is compared whole.
Turn 2 numbers (hostile side): attacks executed at 520 (the [AIDECIDE] target cell is 520's cell), damage they did (the
[AIEXEC] dmg) and useful damage (capped by 520's health left), the player's HP lost over the turn (aistart turn 2 to pstart
turn 3, a dead unit counts all; bleeding included, the same in every arm for the living), reactions of tank 444 and of all,
hostile units down in their own turn, TU the hostile side spent; then the player's turn 3: units down per side."""
import gzip
import json
import re
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")
CFG = re.compile(r'"cfg":"[0-9a-f]+",')
SKIP = ("[AIRECHEAD]", "[AIPROBE] closed", "[AILIGHT]", "[AIREUSE]", "[AIRESULT]", "[AIORDER]")
SHOOTERS = ["1000028", "1000042", "1000055", "1000057"]
WATCH = SHOOTERS + ["1000036", "1000051"]
ATT = {6, 7, 8, 9, 10, 12}
T = 2


def lines_of(path):
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if body.startswith("[AI"):
                yield body


def norm(lines):
    return [CFG.sub("", l) for l in lines if not l.startswith(SKIP)]


def analyse(lines):
    r = {"orders": [], "seq": defaultdict(list), "react444": 0, "react_all": 0, "hdown": [], "p3down": [], "h3down": [],
         "tu": 0, "tu4": 0, "att520": 0, "dmg520": 0, "useful520": 0, "result": ""}
    hp0, hp1, st = {}, {}, {}
    pos520 = None
    pend = None
    cur = None
    for l in lines:
        if l.startswith("[AISTATE] aistart ") and f" turn={T} " in l:
            d = dict(KV.findall(l))
            if d["faction"] == "0":
                hp0[d["unit"]] = int(d["hp"].split("/")[0])
            if d["unit"] == "520":
                pos520 = d["pos"]
                r["hp520"] = hp0["520"]
        elif l.startswith("[AISTATE] pstart ") and f" turn={T + 1} " in l:
            d = dict(KV.findall(l))
            if d["faction"] == "0":
                hp1[d["unit"]] = int(d["hp"].split("/")[0])
                st[d["unit"]] = d
        elif l.startswith("[AIORDER] ") and f" turn={T} " in l:
            d = dict(KV.findall(l))
            r["orders"].append(d)
            r["seq"][d["unit"]].append(f"  [order {d['arm']} {d['status']} idx={d['idx']} type={d['type']} cost={d['cost']} "
                                       f"tu={d['tu']} since={d['since']} d0act={d['d0act']} d0to={d['d0to']}]")
        elif l.startswith("[AIDECIDE] "):
            d = dict(KV.findall(l.split(" hu=")[0]))
            pend = d if int(d["turn"]) == T and d["side"] == "1" else None
            cur = None
        elif l.startswith("[AIEXEC] ") and pend:
            x = json.loads(l[9:])
            if str(x["unit"]) != pend["unit"]:
                continue
            u, act = pend["unit"], int(pend["act"])
            spent = x.get("spent") or 0
            r["tu"] += spent
            if u in SHOOTERS:
                r["tu4"] += spent
            at = act in ATT and spent > 0 and not x.get("walk")
            to = pend["to"]
            if at and to == pos520:
                r["att520"] += 1
                dm = x.get("dmg") or 0
                r["dmg520"] += dm
                use = min(dm, max(0, r["hp520"]))
                r["useful520"] += use
                r["hp520"] -= use
            cur = {"u": u, "react": []}
            if u in WATCH:
                cur["text"] = (f"  n={pend['n']} act={act} to={to} aim={pend['aim']} w={pend['weapon'][:18]} spent={spent} "
                               f"walk={1 if x.get('walk') else 0} dmg={x.get('dmg') or 0} pos={x.get('pos')} tu={x.get('tu')} "
                               f"spotted={x.get('spotted')}")
                r["seq"][u].append(cur)
            pend = None
        elif l.startswith("[AIEVENT] ") and " what=reaction " in l:
            d = dict(KV.findall(l))
            if int(d["turn"]) == T and d["side"] == "1":
                r["react_all"] += 1
                r["react444"] += d.get("unit") == "444"
                if cur is not None:
                    cur["react"].append(d.get("unit"))
        elif l.startswith("[AICASUALTY] "):
            d = dict(KV.findall(l))
            tt, side = int(d["turn"]), d["side"]
            if tt == T and side == "1" and d["vfaction"] == "1":
                r["hdown"].append(f"{d['victim']}({d['how']} by {d['killer']} {d['weapon'][:16]})")
            if tt == T + 1 and side == "0":
                lst = r["p3down"] if d["vfaction"] == "0" else r["h3down"]
                if not any(e.startswith(d["victim"] + "(") for e in lst):
                    lst.append(f"{d['victim']}({d['how']} by {d['killer']})")
            if tt == T and side == "1" and d["vfaction"] == "0":
                r.setdefault("pdown2", []).append(f"{d['victim']}({d['how']} by {d['killer']} {d['weapon'][:16]})")
        elif l.startswith("[AIRESULT] "):
            d = dict(KV.findall(l))
            r["result"] = " ".join(f"{k}={d.get(k)}" for k in ("how", "turn", "player", "pdead", "livesoldiers", "hostile",
                                                              "hdead", "hleft", "phplost"))
    r["plost"] = sum(hp0[u] - hp1.get(u, 0) for u in hp0)
    r["s520"] = f"hp {st['520']['hp']} status {st['520']['status']}" if "520" in st else "down"
    r["s444"] = f"hp {st['444']['hp']} status {st['444']['status']}" if "444" in st else "down"
    return r


def first_change(lines):
    for i, l in enumerate(lines):
        if l.startswith("[AIORDER] ") and (" status=shot " in l or " status=nil_attack " in l):
            return i
    return None


def main():
    runs = [a.split("=", 1) for a in sys.argv[1:]]
    # X~Y: a repeat - its whole log (the orders' lines included, the clock and configuration left out) against Y's
    pairs = [lab.split("~") for lab, _ in runs if "~" in lab]
    runs = [(lab.split("~")[0], p) for lab, p in runs]
    data = {lab: list(lines_of(p)) for lab, p in runs}
    ref_lab = runs[0][0]
    ref = norm(data[ref_lab])
    print("== identity")
    whole = lambda ls: [CFG.sub("", l) for l in ls if not l.startswith(SKIP[:-1])]
    for x, y in pairs:
        same = whole(data[x]) == whole(data[y])
        print(f"{x} vs {y}: whole log, orders included: {'IDENTICAL' if same else 'DIFFERENT'}")
    for lab, _ in runs[1:]:
        ls = data[lab]
        fc = first_change(ls)
        n = norm(ls if fc is None else ls[:fc])
        same = n == ref[:len(n)]
        upto = "whole log" if fc is None else f"{len(n)} lines before the first changed decision"
        if fc is None:
            same = n == ref
        print(f"{lab} vs {ref_lab}: {upto}: {'IDENTICAL' if same else 'DIFFERENT'}")
        if not same:
            for k, (a, b) in enumerate(zip(n, ref)):
                if a != b:
                    print(f"   first difference at line {k}:\n   {lab}: {a[:300]}\n   {ref_lab}: {b[:300]}")
                    break
            else:
                print(f"   lengths {len(n)} vs {len(ref)}")
        if fc is not None:
            print(f"   first change: {ls[fc][:260]}")
            nxt = next((l for l in ls[fc:] if l.startswith("[AIDECIDE] ")), "")
            m = dict(KV.findall(nxt))
            key = (m.get("turn"), m.get("unit"), m.get("n"))
            refd = next((l for l in data[ref_lab] if l.startswith("[AIDECIDE] ") and
                         (dict(KV.findall(l)).get("turn"), dict(KV.findall(l)).get("unit"), dict(KV.findall(l)).get("n")) == key
                         and l.split(" hu=")[1].split()[0] == nxt.split(" hu=")[1].split()[0]), "")
            hk = ("hu", "hi", "ho", "hm", "hr", "hr0", "ha0")
            mr = dict(KV.findall(refd))
            print(f"   state hashes of that decision vs A's: " + " ".join(f"{k}={'=' if m.get(k) == mr.get(k) else 'DIFF'}" for k in hk)
                  + f"; act {m.get('act')} vs A {mr.get('act')}")
    print("\n== turn 2 (hostile) and turn 3 (player)")
    cols = ["att520", "dmg520", "useful520", "plost", "react444", "react_all", "tu", "tu4"]
    res = {lab: analyse(data[lab]) for lab, _ in runs}
    print(f"{'run':<10} " + " ".join(f"{c:>9}" for c in cols) + "  hostile down own turn | 520 after | 444 after")
    for lab, _ in runs:
        r = res[lab]
        print(f"{lab:<10} " + " ".join(f"{r[c]:>9}" for c in cols) + f"  {len(r['hdown'])}: {', '.join(r['hdown'])} | {r['s520']} | {r['s444']}")
    print()
    for lab, _ in runs:
        r = res[lab]
        print(f"{lab}: player down in turn 2: {', '.join(r.get('pdown2', [])) or '-'}; turn 3 player down {len(r['p3down'])}: "
              f"{', '.join(r['p3down']) or '-'}; hostile down {len(r['h3down'])}: {', '.join(r['h3down']) or '-'}")
        print(f"   orders: " + (", ".join(f"{o['unit']}:{o['status']}" for o in r["orders"]) or "-"))
        print(f"   result: {r['result']}")
    print("\n== the shooters' turn 2")
    for lab, _ in runs:
        print(f"-- {lab}")
        for u in WATCH:
            print(f" {u}")
            for e in res[lab]["seq"].get(u, []):
                if isinstance(e, str):
                    print(e)
                else:
                    print(e["text"] + (f" reactions={','.join(e['react'])}" if e["react"] else ""))


main()
