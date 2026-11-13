"""Movement diagnosis: who closes each part. The part is the union of the engine's reachable lists of units standing in it right after the drop; an exit is an outside cell of an earlier
list started inside, with no cheaper outside neighbour; a closer is a unit on an exit with cells behind it. Complete means the union holds as many cells as the logged field (read only)."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from lib import Places, cells, kv, read, tup  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")


def nbrs(c):
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                if dx or dy or dz:
                    yield (c[0] + dx, c[1] + dy, c[2] + dz)


def analyse(run, window=140):
    L = read(run)
    P = Places(L)
    move = {}
    for s in L:
        if s.startswith("[HIVEUNIT]"):
            m = kv(s)
            move[int(m["id"])] = m["move"]
    lists = []
    frm = {}
    for i, s in enumerate(L):
        if s.startswith("[AIDECIDE]"):
            k = kv(s)
            frm[int(k["unit"])] = tup(k["from"])
        elif s.startswith("[AICAND] moves="):
            k = kv(s)
            u = int(k["unit"])
            if u in move and u in frm:
                lists.append((i, u, move[u], frm[u], cells(k["list"])))
    last = {}
    res = []
    for i, s in enumerate(L):
        if not s.startswith("[HIVEREACH]"):
            continue
        k = kv(s)
        key = (k["unit"], k["turn"], k["at"])
        t = int(k["tiles"])
        if key in last and last[key][0] >= 2 * t:
            u = int(k["unit"])
            here, gone = P.at(i)
            me = here[u]
            occ = {p: v for v, p in here.items() if v not in gone and v != u}
            mine = next((c for j, v, m, f, c in lists if i < j < i + 60 and v == u), None)
            if mine is None:
                res.append(dict(line=i, unit=u, note="no list after the flood"))
                last[key] = (t, i)
                continue
            R = set(mine) | {me}
            # lists of others just after, started in the part and not walking on a cell a unit stood on now: the same part seen from elsewhere
            for j, v, m, f, c in lists:
                if i < j < i + window and m == move[u] and v != u and f in R and not (set(c) & set(occ) - {f}):
                    R |= set(c) | {f}
            ring = {}
            used = 0
            for j, v, m, f, c in lists:
                if m != move[u] or f not in R:
                    continue
                O = {x: y for x, y in c.items() if x not in R}
                if not O:
                    continue
                used += 1
                for x, y in O.items():
                    if not any(n in O and O[n] < y for n in nbrs(x)):
                        behind = [n for n in nbrs(x) if n in O and O[n] > y and n not in occ]
                        ring.setdefault(x, set()).update(behind)
            hit = {g: occ[g] for g in ring if g in occ}
            closers = {g: occ[g] for g in hit if ring[g]}
            free = sorted(g for g in ring if g not in occ)
            before, gone0 = P.at(last[key][1])
            occ0 = {p: v for v, p in before.items() if v not in gone0 and v != u}
            res.append(dict(line=i, line0=last[key][1], turn=k["turn"], unit=u, move=move[u], at=me, big=last[key][0], small=t, part=len(R), complete=len(R) == t, lists=used, ring=len(ring), hit=hit, closers=closers, free=free, closed0={g: occ0[g] for g in closers if g in occ0}, players=[v for g, v in hit.items() if v < 1000000]))
        last[key] = (t, i)
    return L, res


def why_there(L, unit, line):
    """How the unit came to stand there: its last walk before the line."""
    for j in range(line, 0, -1):
        s = L[j]
        if s.startswith("[AIEXEC]") and f'"unit":{unit},' in s:
            d = json.loads(s[len("[AIEXEC] "):])
            trail = [x.split()[0].replace("walk.stop.", "") for x in d.get("trail", []) if x.startswith("walk.stop.")]
            for m in range(j, max(j - 8, 0), -1):
                if L[m].startswith("[AIDECIDE]") and f" unit={unit} " in L[m]:
                    k = kv(L[m])
                    return f"turn {k['turn']} mode {k['mode']} act {k['act']} to {k['to']} tu_left {d.get('tu')} stop {trail[-1] if trail else None}"
            return f"stop {trail}"
    return "stood there since the start"


if __name__ == "__main__":
    for run in ["hh4_JA_M6_s2", "hh3_JA_M6_s1", "hh6_JV_M3_s1"]:
        L, res = analyse(run)
        print("==", run)
        for r in res:
            if "note" in r:
                print(r)
                continue
            print(f" line {r['line']} turn {r['turn']} unit {r['unit']} move {r['move']} at {r['at']} {r['big']}->{r['small']} union {r['part']} complete={r['complete']} lists_inside {r['lists']} exits {r['ring']} free_exits {len(r['free'])} {r['free'][:8]}")
            print(f"   units on exits {r['hit']}")
            print(f"   with cells behind {r['closers']}; already there at the big flood {r['closed0']}; players {r['players']}")
            for g, v in r["closers"].items():
                if g not in r["closed0"]:
                    print(f"     came after the big flood: {v} at {g}: {why_there(L, v, r['line'])}")
