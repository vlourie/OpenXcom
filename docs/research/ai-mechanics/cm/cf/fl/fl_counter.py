"""TACTICAL COUNTERFIRE: hostile attacks that drew player reaction fire with hostile losses, over saved battle logs.

For every executed hostile attack ([AIDECIDE] side=1, act throw/auto/snap/aimed/melee/launch, [AIEXEC] spent > 0) the window
up to the next decision: player reactions ([AIEVENT] what=reaction), hostile units down in it by a player killer
([AICASUALTY] vfaction=1, kfaction=0) and the attack's own effect ([AIEXEC] dmg - all units it hurt, downed - enemies it put
down). Losses are counted per unit (a stun then a death is one). The target's kind is its main weapon at the turn's aistart
(AUX_* = a player vehicle). Signs the AI had at the decision, from the record: the shooter's distance to the target (cells),
own units within 3 cells of the shooter (aistart positions of the turn, the shooter's own from the decision), whether the
shooter was spotted after its previous action this turn (unknown for a first action).

  py -3.13 -I fl_counter.py <out dir> <label prefix,...> [min losses]   (logs: <out dir>/<label>/openxcom.log.gz)
"""
import gzip
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")
ATT = {6: "throw", 7: "auto", 8: "snap", 9: "aimed", 10: "melee", 12: "launch"}
P3 = re.compile(r"\((-?\d+),(-?\d+),(-?\d+)\)")


def xyz(s):
    m = P3.search(s or "")
    return tuple(int(v) for v in m.groups()) if m else None


def cells(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1])) if a and b else -1


def scan(path, label, rows, stat):
    kind, pos, fac, down = {}, {}, {}, set()
    cur, spotted = None, {}

    def close():
        if cur and cur["exec"]:
            stat["att"] += 1
            if cur["react"]:
                stat["att_react"] += 1
            n = len(cur["lost"])
            if n:
                stat["att_loss1"] += 1
            if n >= 2:
                stat["att_loss2"] += 1
            rows.append(cur)

    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            l = raw.rstrip("\n").split("\t", 2)[-1]
            if l.startswith("[AISTATE] aistart "):
                d = dict(KV.findall(l))
                kind[d["unit"]] = d.get("weapon", "")
                pos[d["unit"]] = xyz(d.get("pos"))
                fac[d["unit"]] = d.get("faction")
                if d.get("status") == "0":
                    down.discard(d["unit"])
                spotted = {}
            elif l.startswith("[AIDECIDE] "):
                close()
                cur = None
                d = dict(KV.findall(l.split(" hu=")[0]))
                down.discard(d["unit"])
                if d.get("side") == "1" and int(d["act"]) in ATT:
                    me = xyz(d.get("from"))
                    near = sum(1 for u, p in pos.items() if fac.get(u) == "1" and u != d["unit"] and cells(p, me) in range(0, 4))
                    cur = {"label": label, "turn": d["turn"], "unit": d["unit"], "n": d["n"], "act": ATT[int(d["act"])],
                           "w": d.get("weapon", ""), "aim": d.get("aim"), "akind": kind.get(d.get("aim"), ""),
                           "dist": cells(me, xyz(d.get("to"))), "near": near, "pre_spotted": spotted.get(d["unit"]),
                           "exec": False, "dmg": 0, "downed": 0, "react": [], "lost": {}}
            elif l.startswith("[AIEXEC] "):
                x = json.loads(l[9:])
                u = str(x["unit"])
                if cur and u == cur["unit"] and not cur["exec"]:
                    cur["exec"] = (x.get("spent") or 0) > 0 and not x.get("walk")
                    cur["dmg"] = x.get("dmg") or 0
                    cur["downed"] = x.get("downed") or 0
                    cur["post_spotted"] = x.get("spotted")
                spotted[u] = x.get("spotted")
            elif cur and l.startswith("[AIEVENT] ") and " what=reaction " in l:
                cur["react"].append(dict(KV.findall(l)).get("unit"))
            elif l.startswith("[AICASUALTY] "):
                c = dict(KV.findall(l))
                # a unit already down (unconscious, not up since) hit again is not a new loss
                new = c["victim"] not in down
                down.add(c["victim"])
                if cur and new and c.get("vfaction") == "1" and c.get("kfaction") == "0":
                    cur["lost"].setdefault(c["victim"], f"{c['victim']}({c['how']} by {c['killer']} {c['weapon'][:16]} d{cells(xyz(c.get('pos')), pos.get(cur['unit']))})")
        close()


def main():
    out = Path(sys.argv[1])
    prefixes = sys.argv[2].split(",")
    mn = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    rows, stat = [], Counter()
    logs = sorted(p for p in out.iterdir() if p.is_dir() and any(p.name.startswith(x + "_") for x in prefixes))
    for p in logs:
        g = p / "openxcom.log.gz"
        if g.exists():
            stat["battles"] += 1
            scan(g, p.name, rows, stat)
    print(f"battles {stat['battles']}, hostile attacks executed {stat['att']}, with player reactions {stat['att_react']}, "
          f"with >=1 hostile loss to the player in the window {stat['att_loss1']}, with >=2 {stat['att_loss2']}")
    big = [r for r in rows if len(r["lost"]) >= mn]
    print(f"\n== attacks with >= {mn} hostile losses in their window")
    for r in big:
        tk = "VEHICLE" if r["akind"].startswith("AUX_") else r["akind"][:18]
        print(f"{r['label']} t{r['turn']} {r['unit']} n={r['n']} {r['act']} {r['w'][:16]} -> {r['aim']} ({tk}) dist={r['dist']} "
              f"near3={r['near']} pre_spotted={r['pre_spotted']} post_spotted={r.get('post_spotted')} dmg={r['dmg']} "
              f"downed={r['downed']} reactions={','.join(r['react']) or '-'}\n    lost {len(r['lost'])}: {', '.join(r['lost'].values())}")
    # the shape of the losing attacks against the rest
    for name, sel in (("all executed", rows), (">=1 loss", [r for r in rows if r["lost"]]), (">=2 losses", big)):
        if not sel:
            continue
        veh = sum(r["akind"].startswith("AUX_") for r in sel)
        avgnear = sum(r["near"] for r in sel) / len(sel)
        nod = sum(1 for r in sel if not r["downed"])
        print(f"{name}: {len(sel)}; at a vehicle {veh} ({100 * veh / len(sel):.0f}%); own units within 3 cells avg {avgnear:.2f}; "
              f"target not downed {nod} ({100 * nod / len(sel):.0f}%)")
    # by the target's weapon: how often an attack at it is answered with losses
    print("\n== by the target's main weapon (attacks, with reactions, with >=1 loss, losses, losses per 100 attacks)")
    by = {}
    for r in rows:
        k = r["akind"] if r["akind"].startswith("AUX_") else ("player soldier" if r["aim"] and r["aim"].isdigit()
                                                              and int(r["aim"]) < 1000000 else "other/none")
        b = by.setdefault(k, Counter())
        b["n"] += 1
        b["react"] += bool(r["react"])
        b["l1"] += bool(r["lost"])
        b["lost"] += len(r["lost"])
        b["dmg"] += r["dmg"]
        b["zero"] += not r["dmg"]
        b["downed"] += r["downed"]
    for k, b in sorted(by.items(), key=lambda kv: -kv[1]["n"]):
        print(f"  {k[:28]:<28} {b['n']:>5} {b['react']:>5} {b['l1']:>5} {b['lost']:>5} {100 * b['lost'] / b['n']:>6.1f}"
              f"   dmg/attack {b['dmg'] / b['n']:>5.1f} no-dmg {100 * b['zero'] / b['n']:>3.0f}% enemies downed {b['downed']}")
    if len(sys.argv) > 4:
        # every attack at a target of this main weapon, with its signs and outcome
        sel = [r for r in rows if r["akind"] == sys.argv[4]]
        print(f"\n== all {len(sel)} attacks at {sys.argv[4]}")
        for r in sel:
            print(f"  {r['label'][7:]:<8} t{r['turn']:<3} {r['unit']} {r['act']:<6} {r['w'][:16]:<16} dist={r['dist']:<3} near3={r['near']} "
                  f"pre={r['pre_spotted']} post={r.get('post_spotted')} dmg={r['dmg']:<4} react={len(r['react'])} lost={len(r['lost'])}")
        for lab, f in (("near3>=1", lambda r: r["near"] >= 1), ("near3==0", lambda r: r["near"] == 0),
                       ("dist<=6", lambda r: 0 <= r["dist"] <= 6), ("dist>6", lambda r: r["dist"] > 6),
                       ("melee/throw", lambda r: r["act"] in ("melee", "throw")), ("fire", lambda r: r["act"] in ("auto", "snap", "aimed"))):
            s = [r for r in sel if f(r)]
            if s:
                print(f"  {lab:<12} attacks {len(s):>3}  with loss {sum(bool(r['lost']) for r in s):>2}  losses {sum(len(r['lost']) for r in s):>2}"
                      f"  per 100 {100 * sum(len(r['lost']) for r in s) / len(s):.0f}")
    killers = Counter()
    for r in rows:
        for v in r["lost"].values():
            killers[v.split(" by ")[1].split(" d")[0].split(" ", 1)[1] if " by " in v else "?"] += 1
    print("\n== who killed in those windows (weapon):", ", ".join(f"{k} {n}" for k, n in killers.most_common(8)))


main()
