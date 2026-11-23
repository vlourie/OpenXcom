"""COORDINATED OPERATION, phase A: the stricter search for a repeat. A chance counts only if at least two fighters able to land K blows in a full turn have nothing to charge now: every player's unit known to the side stands more than 20 tiles from each (meleeAction refuses it, AIModule.cpp:4927), the target is reachable within two turns by the engine's list, and D0 did not land a melee blow on the target by both on t or t+1. The outcome in D0 is added: who hit the target on t+1 and how the target's HP changed. Also the player's events around the source episode. Read only.
Usage: a4_strict.py <archive dir>"""
import gzip
import io
import json
import math
import re
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=([^ ]*)")
K = 6
ARM = {"444", "448", "470", "545"}
PL = ARM | {"454", "503", "520", "543"}
RUNS = ["M3_s1", "M3_s2", "M11_s1", "M11_s2", "M2_s1", "M2_s2"]


def pos(p):
    return tuple(int(x) for x in p.strip("()").split(","))


def d2(a, b):
    return int(round(math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)))


def moves(s):
    out = {}
    for c in s.split(" list=", 1)[1].split(";"):
        try:
            p, tu = c.split(":")
            x, y, z = p.split(".")
            out[(int(x), int(y), int(z))] = int(tu)
        except ValueError:
            pass
    return out


def read(zf, name):
    with gzip.open(io.BytesIO(zf.read(name)), "rt", encoding="utf-8", errors="replace") as h:
        return [ln.rstrip("\n").split("\t")[-1] for ln in h]


root = Path(sys.argv[1])
for z in sorted(root.glob("res_*.zip")):
    zf = zipfile.ZipFile(z)
    for name in zf.namelist():
        m = re.search(r"scpa_D_((M3|M11|M2)_s\d+)/.*log\.gz$", name)
        if not m or m.group(1) not in RUNS:
            continue
        L = read(zf, name)
        state = defaultdict(dict)
        first = defaultdict(dict)
        decs = []
        cur = mv = None
        recs = {}
        for s in L:
            if s.startswith("[AISTATE] aistart"):
                k = dict(KV.findall(s))
                state[int(k["turn"])][k["unit"]] = k
            elif s.startswith("[AIDECIDE]"):
                cur = dict(KV.findall(s))
                mv = None
            elif s.startswith("[AICAND] moves=") and cur:
                mv = s
            elif s.startswith("[AICAND] acts=") and cur:
                t, u = int(cur["turn"]), cur["unit"]
                if cur.get("side") == "1" and u not in first[t] and mv:
                    try:
                        acts = json.loads(s.split(" list=", 1)[1])
                    except (IndexError, ValueError):
                        acts = []
                    w = {}
                    for a in acts:
                        if a.get("k") == "a" and a.get("t") == 10:
                            w[a["w"]] = a["tu"]
                    first[t][u] = (moves(mv), w, pos(cur["from"]), int(cur["tu"]))
            elif s.startswith("[AIREC]") and cur:
                try:
                    j = json.loads(s[8:])
                    cur["src"] = (j.get("base") or {}).get("src")
                    recs[j["rec"]] = cur
                except ValueError:
                    pass
            elif s.startswith("[AIEXEC]"):
                try:
                    j = json.loads(s[9:])
                except ValueError:
                    continue
                d = recs.get(j["rec"])
                if d and d.get("side") == "1":
                    d["exec"] = j
                    decs.append(d)
        found = 0
        print("=====", m.group(1))
        for t in sorted(first):
            known = {u: pos(k["pos"]) for u, k in state[t].items() if u in PL and k.get("spotted") == "0" and int(k.get("status", 0)) < 6}
            for tid in sorted(ARM & set(known)):
                st = state[t][tid]
                tp = known[tid]
                near = [(tp[0] + x, tp[1] + y, tp[2]) for x in range(-1, 3) for y in range(-1, 3) if not (0 <= x < 2 and 0 <= y < 2)]
                can = []
                for u, (mm, w, fr, tu) in first[t].items():
                    if not w:
                        continue
                    c = min(w.values())
                    tumax = int(state[t].get(u, {}).get("tumax", tu))
                    if tumax < K * c:
                        continue
                    if min(d2(fr, q) for q in known.values()) <= 20:
                        continue
                    ways = [mm[q] for q in near if q in mm and mm[q] >= 0]
                    if not ways or min(ways) > tu + tumax - K * c:
                        continue
                    can.append((u, state[t].get(u, {}).get("type", "")[4:16], "tu", tu, "way", min(ways), "hp", state[t].get(u, {}).get("hp"), "dist", d2(fr, tp)))
                if len(can) < 2:
                    continue
                ids = {x[0] for x in can}
                hits = []
                for d in decs:
                    if int(d["turn"]) in (t, t + 1) and d["unit"] in ids and (d.get("exec") or {}).get("dmg", 0) > 0:
                        p = state[int(d["turn"])].get(tid)
                        q = pos(d["to"])
                        if p and max(abs(q[0] - pos(p["pos"])[0]), abs(q[1] - pos(p["pos"])[1])) <= 2:
                            hits.append((d["turn"], d["unit"], d["exec"].get("dmg")))
                found += 1
                print(f"  t{t} target {tid} {st['pos']} dir {st['dir']} hp {st['hp']}; capable: {can}")
                print("     D0 melee on it t,t+1:", hits, "hp at t+1, t+2:", state.get(t + 1, {}).get(tid, {}).get("hp"), state.get(t + 2, {}).get(tid, {}).get("hp"))
        print("  strict chances:", found)
