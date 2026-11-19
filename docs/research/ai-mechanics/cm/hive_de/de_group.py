"""DECISION ENGINE FOUNDATION, read only, over the 48 D0 battles.
BLOCK: each whole unit-turn lost (time units, nothing spent): its reach, a comrade on the edge of the reach, what that comrade decided this turn before the soldier, the reach on a later turn when the comrade had gone.
FF: each own soldier downed by an own soldier's action: where victim, shooter and target stood, did the victim walk there this turn, by what source."""
import gzip
import io
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
A = Path("E:/OXCE_AIWorker/battles_archive/side_turn_scheduler_pilot_2026-10-30/res_scpa.zip")
KV = re.compile(r"(\w+)=([^ ]*)")
POS = re.compile(r"\((-?\d+),(-?\d+),(-?\d+)\)")


def kv(s):
    return dict(KV.findall(s))


def tup(p):
    m = POS.match(p or "")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def line_dist(a, b, p):
    ax, ay = a[0], a[1]
    bx, by = b[0] - ax, b[1] - ay
    px, py = p[0] - ax, p[1] - ay
    n = bx * bx + by * by
    if not n:
        return 99, 0
    t = (px * bx + py * by) / n
    dx, dy = px - t * bx, py - t * by
    return (dx * dx + dy * dy) ** 0.5, t


zf = zipfile.ZipFile(A)
block_rows = []
bc = Counter()
fc = Counter()
ff_rows = []
for n in sorted(x for x in zf.namelist() if x.endswith("openxcom.log.gz")):
    name = n.split("/")[-2].replace("scpa_D_", "")
    L = [x.rstrip("\n").split("\t")[-1] for x in gzip.open(io.BytesIO(zf.read(n)), "rt", encoding="utf-8", errors="replace")]
    pos = {}
    out = set()
    hostile = set()
    D = []
    cand = {}
    reach_by = defaultdict(dict)  # unit -> turn -> reach size
    for i, s in enumerate(L):
        if s.startswith("[AISTATE] before"):
            k = kv(s)
            p = tup(k.get("pos"))
            if p:
                pos[k["unit"]] = p
            if k.get("faction") == "1":
                hostile.add(k["unit"])
        elif s.startswith("[AICAND]"):
            k = kv(s)
            # written after its [AIDECIDE]: moves, then the attacks the bench's own enumeration holds legal
            if "moves" in k and D and D[-1]["k"]["unit"] == k["unit"] and not D[-1]["reach"]:
                D[-1]["reach"] = [c.split(":")[0] for c in k.get("list", "").split(";") if re.fullmatch(r"\d+\.\d+\.\d+:\d+", c)]
                reach_by[k["unit"]].setdefault(int(D[-1]["k"]["turn"]), len(D[-1]["reach"]))
        elif s.startswith("[AIDECIDE]"):
            k = kv(s)
            p = tup(k.get("from"))
            if p:
                pos[k["unit"]] = p
            if k.get("side") == "1":
                hostile.add(k["unit"])
            d = {"i": i, "k": k, "reach": [], "pos": dict(pos), "out": set(out)}
            D.append(d)
        elif s.startswith("[AIREC]"):
            if D and '"base"' in s:
                try:
                    j = json.loads(s[8:])
                    b = j.get("base") or {}
                    D[-1]["src"] = b.get("src")
                    D[-1]["slots"] = sorted({p.get("s") for p in (b.get("reason", {}).get("props") or [])} | {b.get("slot")} - {None})
                except json.JSONDecodeError:
                    pass
        elif s.startswith("[AIEXEC]"):
            j = json.loads(s[9:])
            u = str(j.get("unit"))
            if j.get("pos"):
                pos[u] = tuple(j["pos"])
            if D and D[-1]["k"]["unit"] == u:
                D[-1]["ex"] = j
                D[-1]["after"] = dict(pos)
        elif s.startswith("[AICASUALTY]"):
            k = kv(s)
            if k.get("how") == "dead" or True:
                out.add(k["victim"])
            if k.get("vfaction") == "1" and k.get("kfaction") == "1" and k.get("victim") != k.get("killer"):
                # the killer's last decision, the victim's walks this turn
                kd = next((d for d in reversed(D) if d["k"]["unit"] == k.get("killer")), None)
                vd = [d for d in D if d["k"]["unit"] == k["victim"] and d["k"]["turn"] == k["turn"] and d.get("ex", {}).get("spent", 0) > 0 and d["k"].get("act") == "2"]
                vp = tup(k.get("pos"))
                sp = tup(kd["k"].get("from")) if kd else None
                tp = tup(kd["k"].get("to")) if kd else None
                row = {"b": name, "t": k["turn"], "v": k["victim"], "how": k.get("how"), "w": kd["k"].get("weapon") if kd else "", "act": kd["k"].get("act") if kd else "", "src": kd.get("src") if kd else "", "walked": len(vd), "vsrc": vd[-1].get("src") if vd else ""}
                if vp and sp and tp:
                    ld, t = line_dist(sp, tp, vp)
                    dt = max(abs(vp[0] - tp[0]), abs(vp[1] - tp[1]))
                    row.update(lane=round(ld, 1), along=round(t, 2), to_target=dt, to_shooter=max(abs(vp[0] - sp[0]), abs(vp[1] - sp[1])))
                ff_rows.append(row)
    # BLOCK
    ut = defaultdict(list)
    for d in D:
        if d["k"].get("side") == "1":
            ut[(int(d["k"]["turn"]), d["k"]["unit"])].append(d)
    order = {}
    for key, v in ut.items():
        if sum(x.get("ex", {}).get("spent", 0) for x in v) or not int(v[0]["k"]["tu"]):
            continue
        t, u = key
        d0 = v[0]
        r = set(d0["reach"])
        here = tup(d0["k"]["from"])
        cells = set()
        for c in r:
            a = c.split(".")
            cells.add((int(a[0]), int(a[1]), int(a[2])))
        cells.add(here)
        edge = []
        for w, p in d0["pos"].items():
            if w == u or w in d0["out"] or w not in hostile:
                continue
            if any(abs(p[0] - c[0]) <= 1 and abs(p[1] - c[1]) <= 1 and p[2] == c[2] for c in cells) and p not in cells:
                edge.append(w)
        later = [(tt, s) for tt, s in reach_by[u].items() if tt > t]
        grow = max([s for _, s in later], default=0)
        before = [d for d in D if d["i"] < d0["i"] and d["k"].get("turn") == str(t) and d["k"].get("side") == "1" and d["k"]["unit"] in edge]
        moved_before = {d["k"]["unit"] for d in before}
        rec = dict(b=name, t=t, u=u, reach=len(cells), later=grow, edge=edge, acted=sorted(moved_before), mode=d0["k"]["mode"], act=d0["k"]["act"], tu=int(d0["k"]["tu"]), seen=len([x for x in d0["k"].get("seen", "").split(",") if x.isdigit() and int(x) < 1000000]), slots=[d.get("slots") for d in before][-1:] )
        block_rows.append(rec)
        bc["lost"] += 1
        bc["tu"] += rec["tu"]
        if edge:
            bc["comrade on the edge"] += 1
        if len(cells) <= 80:
            bc["reach<=80"] += 1
            if edge:
                bc["reach<=80, comrade on the edge"] += 1
                bc["tu reach<=80, comrade on the edge"] += rec["tu"]
                if moved_before:
                    bc["...the comrade decided before him"] += 1
                if grow > 3 * len(cells):
                    bc["...later reach 3x"] += 1
                    if moved_before:
                        bc["...later reach 3x, comrade decided before"] += 1
print("BLOCK", dict(bc))
by = Counter()
for r in block_rows:
    if r["reach"] <= 80 and r["edge"] and r["later"] > 3 * r["reach"] and r["acted"]:
        by[r["b"]] += 1
print(" by battle", by.most_common())
for r in [r for r in block_rows if r["reach"] <= 80 and r["edge"] and r["later"] > 3 * r["reach"] and r["acted"]][:25]:
    print("  ", r)
print("FF rows", len(ff_rows))
real = [r for r in ff_rows if r["how"] == "dead"]
print(" dead", len(real), "walked before", sum(r["walked"] > 0 for r in real), "by weapon", Counter(r["w"] for r in real).most_common(12))
print(" by source of the shooter", Counter(r["src"] for r in real).most_common(), "victim walked by", Counter(r["vsrc"] for r in real).most_common())
geo = [r for r in real if "lane" in r]
print(" with geometry", len(geo), "next to the target (<=1)", sum(r["to_target"] <= 1 for r in geo), "<=2", sum(r["to_target"] <= 2 for r in geo), "in the lane (<=1.5, between)", sum(r["lane"] <= 1.5 and 0 < r["along"] < 1 for r in geo), "next to the shooter", sum(r["to_shooter"] <= 1 for r in geo))
for r in geo[:15]:
    print("  ", r)
