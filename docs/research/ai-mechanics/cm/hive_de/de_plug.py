"""DECISION ENGINE FOUNDATION, read only, over the 48 D0 battles: a comrade as the plug of a pocket.
A whole unit-turn lost (B). Pocket: the farthest tile of B's reach cost under half of B's time units. Plug: a live comrade A not in the reach, next to a tile of it, with a tile past A that B walked to or could walk to at some other decision of this battle and that is not in the reach now.
For every plug: when A decided against B on this turn, what A did, did A arrive there this turn; what filled A's slots; what B did over the next two turns.
Reach comes by hash from the AIREC: a list is logged once per battle."""
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
ATT = {5, 6, 7, 8, 9, 10, 11, 12}


def kv(s):
    return dict(KV.findall(s))


zf = zipfile.ZipFile(A)
C = Counter()
per = Counter()
perTu = Counter()
what = Counter()
samples = []
for n in sorted(x for x in zf.namelist() if x.endswith("openxcom.log.gz")):
    name = n.split("/")[-2].replace("scpa_D_", "")
    L = [x.rstrip("\n").split("\t")[-1] for x in gzip.open(io.BytesIO(zf.read(n)), "rt", encoding="utf-8", errors="replace")]
    moves = {}
    for s in L:
        m = re.match(r"\[AICAND\] moves=(\w+) unit=\d+ list=(.*)", s)
        if m:
            d = {}
            for c in m.group(2).split(";"):
                if ":" in c:
                    a, tu = c.split(":")
                    # tu -1 is a tile beyond this turn's reach, listed as where the soldier may head (AiCandidates::addMoves)
                    if int(tu) >= 0:
                        d[tuple(int(v) for v in a.split("."))] = int(tu)
            moves[m.group(1)] = d
    pos = {}
    side1 = set()
    out = set()
    D = []
    for i, s in enumerate(L):
        if s.startswith("[AISTATE] before"):
            k = kv(s)
            m = POS.match(k.get("pos", ""))
            if m:
                pos[k["unit"]] = tuple(int(v) for v in m.groups())
            if k.get("faction") == "1":
                side1.add(k["unit"])
        elif s.startswith("[AIDECIDE]"):
            k = kv(s)
            m = POS.match(k.get("from", ""))
            if m:
                pos[k["unit"]] = tuple(int(v) for v in m.groups())
            if k.get("side") == "1":
                side1.add(k["unit"])
            D.append({"i": i, "k": k, "pos": dict(pos), "out": set(out)})
        elif s.startswith("[AIREC]") and D and '"base"' in s:
            try:
                j = json.loads(s[8:])
            except json.JSONDecodeError:
                continue
            D[-1]["b"] = j.get("base") or {}
            D[-1]["c"] = j.get("cand") or {}
            D[-1]["slots"] = sorted({p.get("s") for p in ((j.get("base") or {}).get("reason", {}).get("props") or [])} | {(j.get("base") or {}).get("slot")} - {None})
        elif s.startswith("[AIEXEC]"):
            j = json.loads(s[9:])
            u = str(j.get("unit"))
            if j.get("pos"):
                pos[u] = tuple(j["pos"])
            if D and D[-1]["k"]["unit"] == u:
                D[-1]["ex"] = j
        elif s.startswith("[AICASUALTY]"):
            out.add(kv(s).get("victim"))
    H = [d for d in D if d["k"].get("side") == "1" and d.get("b")]
    ut = defaultdict(list)
    ever = defaultdict(set)
    for d in H:
        ut[(int(d["k"]["turn"]), d["k"]["unit"])].append(d)
        ever[d["k"]["unit"]] |= set(moves.get(d["c"].get("moves"), {}))
    for (t, u), v in ut.items():
        tu = int(v[0]["k"]["tu"])
        if sum(x.get("ex", {}).get("spent", 0) for x in v) or not tu:
            continue
        C["lost"] += 1
        C["lost tu"] += tu
        C[f"lost mode {v[0]['k'].get('mode')}"] += 1
        r = moves.get(v[0]["c"].get("moves"), {})
        far = max(r.values(), default=0)
        here = v[0]["pos"].get(u)
        cells = set(r) | ({here} if here else set())
        if far * 2 >= tu:
            continue
        C["pocket"] += 1
        C["pocket tu"] += tu
        com = {w: p for w, p in v[0]["pos"].items() if w in side1 and w != u and w not in v[0]["out"]}
        plugs = []
        for w, p in com.items():
            if p in cells or not any(abs(p[0] - c[0]) <= 1 and abs(p[1] - c[1]) <= 1 and p[2] == c[2] for c in cells):
                continue
            past = [q for q in ever[u] if q not in cells and abs(p[0] - q[0]) <= 1 and abs(p[1] - q[1]) <= 1 and abs(p[2] - q[2]) <= 1]
            if past or p in ever[u]:
                plugs.append(w)
        if not plugs:
            continue
        C["plugged pocket"] += 1
        C["plugged tu"] += tu
        per[name] += 1
        perTu[name] += tu
        # the plug's decisions on this turn, earlier than B's first
        best = None
        for w in plugs:
            early = [d for d in ut.get((t, w), []) if d["i"] < v[0]["i"]]
            late = [d for d in ut.get((t, w), []) if d["i"] > v[0]["i"]]
            if early:
                moved = sum(1 for d in early if d.get("ex", {}).get("spent", 0) > 0 and d["k"].get("act") == "2")
                shot = sum(1 for d in early if d["b"].get("t") in ATT and d.get("ex", {}).get("spent", 0) > 0)
                src = [d["b"].get("src") for d in early if d.get("ex", {}).get("spent", 0) > 0]
                kind = "earlier: walked here" if moved else ("earlier: fired from here" if shot else "earlier: spent nothing")
                best = best or (kind, w, src, early[0].get("slots"), early[0]["k"].get("mode"), int(early[0]["k"]["tu"]))
            elif late and best is None:
                best = None
        kind = best[0] if best else "plug decides later or not at all"
        what[kind] += 1
        what[kind + " tu"] += tu
        if best and best[0] == "earlier: walked here":
            what["walked by " + str(best[2][0] if best[2] else "?")] += 1
        if best:
            what["A slots " + "".join(best[3] or [])] += 1
        # B over the next two turns
        nxt = [d for tt in (t + 1, t + 2) for d in ut.get((tt, u), [])]
        hit = sum(d.get("ex", {}).get("dmg", 0) for d in nxt)
        att = sum(1 for d in nxt if d["b"].get("t") in ATT and d.get("ex", {}).get("spent", 0) > 0)
        C["B later fired"] += 1 if att else 0
        C["B later dmg"] += hit
        if best and len(samples) < 30:
            samples.append(dict(b=name, t=t, B=u, tu=tu, far=far, nreach=len(r), mode=v[0]["k"].get("mode"), A=best[1], kind=best[0], Asrc=best[2], Aslots=best[3], Amode=best[4], Atu=best[5], seen=len([x for x in v[0]["k"].get("seen", "").split(",") if x.isdigit() and int(x) < 1000000]), next_att=att, next_dmg=hit))
print(dict(C))
print(dict(what))
print("by battle", per.most_common(), "tu", perTu.most_common(8))
for s in samples:
    print(" ", s)
