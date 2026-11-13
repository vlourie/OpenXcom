"""NATURAL GATE: the numbers of the report that no earlier script prints. Base rate of a wound per plain shot, the same-turn openings with the range drop, own cell against A's step on M10, who knew T in M10 no. 19. Args: zip, cands.jsonl, M10 log, Piratez root."""
import gzip
import io
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import gate_lib as G

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RULES = (Path(sys.argv[4]) / "user" / "mods" / "Piratez" / "Ruleset" / "Piratez.rul").read_text(encoding="utf-8", errors="replace").splitlines()
RK = re.compile(r"^\s+(aimRange|snapRange|autoRange|dropoff):\s*(\S+)")


def weapon(name):
    out = {"aimRange": 200, "autoRange": 7, "snapRange": 15, "dropoff": 2}
    for i, s in enumerate(RULES):
        if re.match(r"^\s*- type: " + re.escape(name) + r"\s*$", s):
            for t in RULES[i + 1:i + 90]:
                if re.match(r"^\s*- type: ", t) or re.match(r"^\S", t):
                    break
                m = RK.match(t)
                if m:
                    out[m.group(1)] = int(m.group(2))
            break
    return out


def p_drop(s):
    w = weapon(s["w"])
    up = {7: w["autoRange"], 8: w["snapRange"], 9: w["aimRange"]}[s["mode"]]
    return s["p"] - max(0, s["d"] - up) * w["dropoff"]


base = Counter()
with zipfile.ZipFile(sys.argv[1]) as z:
    for n in sorted(x for x in z.namelist() if x.endswith("openxcom.log.gz")):
        L = [s.rstrip("\n").split("\t")[-1] for s in gzip.open(io.BytesIO(z.read(n)), "rt", encoding="utf-8", errors="replace")]
        b = G.Battle(L)
        for d in b.dec:
            if d["side"] == 1 and d["t"] in G.SHOT:
                e = b.exec.get(d["rec"]) or {}
                base["acts"] += 1
                base["wounding"] += 1 if (e.get("dmg") or 0) > 0 else 0
                base["own_fire"] += 1 if (e.get("fdmg") or 0) > 0 else 0
print("plain shots of the side, 48 battles:", dict(base))

print("\nsame-turn openings that pass the conditions, accuracy with the range drop at the blocked cell:")
for s in Path(sys.argv[2]).open(encoding="utf-8"):
    r = json.loads(s)
    for c in r["cands"]:
        sh = c["shot"]
        for f in c["flips"]:
            if not (f["after"] and f["turn"] == c["turn"]):
                continue
            walked = [x for x in f["comrades"] if not x["out"] and x["now"] != x["was"]]
            left = [x for x in f["comrades"] if x["out"] or x["now"] != x["was"]]
            if not left:
                continue
            if walked and f["tu"] >= sh["tu"] and c["hurtT"] and not c["other_lof"]:
                print(r["name"], "t", c["turn"], "B", c["B"]["id"], c["B"]["pos"], "tu", c["B"]["tu"], "T", c["T"]["id"], c["T"]["pos"], "d", sh["d"], sh["w"], "m", sh["mode"], sh["tu"], "TU p", sh["p"], "p_d", p_drop(sh), "shots", c["B"]["tu"] // sh["tu"], "walked", len(walked), "then t", f["did"]["t"], "u", f["did"]["u"], "dmg", f["did"]["dmg"], "f", f["did"]["fdmg"])
            break

L = [s.rstrip("\n").split("\t")[-1] for s in open(sys.argv[3], encoding="utf-8", errors="replace")]
b = G.Battle(L)
o = Counter()
rows = []
for no, (i, j) in enumerate([x for x in b.tts if x[1].get("ev") == "cand"], 1):
    Bx, Tx = j["B"], j["T"]
    d0 = [d for d in b.by_unit.get(Bx["id"], []) if d["turn"] == j["turn"] and d["side"] == 1 and d["i"] > i][0]
    s = G.shots_by_target(b.acts(d0["acts"]))[Tx["id"]]
    o["why " + j["why"]] += 1
    if s["lof"]:
        o["not blocked"] += 1
        continue
    o["blocked"] += 1
    if j["why"] != "b_own_cell":
        continue
    o["blocked, own cell by the engine"] += 1
    com = b.comrades(d0["i"], d0["unit"])
    taken = {a[0] for a in com.values()} | {d0["pos"]}
    best = None
    for c, cost in b.moves(d0["moves"]).items():
        if cost > d0["tu"] or c in taken or any(p != c and G.near_line(p, c, s["to"]) for p in taken if p != d0["pos"]):
            continue
        if best is None or cost < best:
            best = cost
    if best is None:
        o["  no flat cell in the moves, cost unknown"] += 1
    elif d0["tu"] // s["tu"] > (d0["tu"] - best) // s["tu"]:
        o["  flat: own move costs at least a shot"] += 1
    else:
        o["  flat: own move costs no shot"] += 1
for k in sorted(o):
    print(f"{o[k]:3d}  {k}")

print("\nno. 19 at the side's turn start:")
for s in L:
    if s.startswith("[AISTATE] aistart") and (" turn=6 " in s) and any(f" unit={u} " in s for u in (1000034, 1000047, 115)):
        k = G.kv(s)
        print(k["unit"], k["pos"], "tu", k["tu"], "hp", k["hp"], "weapon", k.get("weapon"), "sees", k.get("sees"), "known", k.get("known"))
