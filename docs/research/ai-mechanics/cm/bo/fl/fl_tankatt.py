"""TACTICAL STAGE 2: every hostile attack at a player vehicle (main weapon AUX_*) in one hostile turn of a D0 log, and what came
of it - damage, the reactions fired before the next decision (and by whom), the actor's death in them.

The candidates for arm C (a confirmed useless attack at a tank that draws reaction fire) are among these rows.

  py -3.13 -I fl_tankatt.py <log> <turn>"""
import json
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")
T = int(sys.argv[2])
ATT = {6: "throw", 7: "auto", 8: "snap", 9: "aimed", 10: "melee", 12: "launch"}
kind, pos = {}, {}
rows, cur = [], None
for l in open(sys.argv[1], encoding="utf-8", errors="replace"):
    l = l.rstrip("\n")
    if l.startswith("[AISTATE] aistart ") and f" turn={T} " in l:
        d = dict(KV.findall(l))
        if d["faction"] == "0":
            kind[d["unit"]] = d["weapon"]
        pos[d["unit"]] = d["pos"]
    elif l.startswith("[AIDECIDE] "):
        d = dict(KV.findall(l.split(" hu=")[0]))
        cur = None
        if int(d["turn"]) == T and d["side"] == "1" and int(d["act"]) in ATT and kind.get(d["aim"], "").startswith("AUX_"):
            cur = {"unit": d["unit"], "act": ATT[int(d["act"])], "w": d["weapon"], "aim": d["aim"], "from": d.get("from"),
                   "dmg": None, "react": [], "spotted": None}
            rows.append(cur)
    elif l.startswith("[AIEXEC] ") and cur and cur["dmg"] is None:
        x = json.loads(l[9:])
        if str(x["unit"]) == cur["unit"]:
            cur["dmg"] = x.get("dmg")
            cur["spotted"] = x.get("spotted")
            cur["exec"] = (x.get("spent") or 0) > 0
    elif l.startswith("[AIEVENT] ") and " what=reaction " in l and cur:
        d = dict(KV.findall(l))
        if int(d["turn"]) == T:
            cur["react"].append(d.get("unit"))
    elif l.startswith("[AICASUALTY] ") and cur:
        d = dict(KV.findall(l))
        if int(d["turn"]) == T and d["victim"] == cur["unit"]:
            cur["died"] = d.get("killer")
for r in rows:
    print(f"{r['unit']} {r['act']:<6} {r['w'][:20]:<20} -> {r['aim']} ({kind[r['aim']][:22]}) from {r['from']} exec={r.get('exec')} "
          f"dmg={r['dmg']} spotted_after={r['spotted']} reactions={','.join(r['react']) or '-'} died_by={r.get('died', '-')}")
