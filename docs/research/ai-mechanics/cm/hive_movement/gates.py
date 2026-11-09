"""Movement diagnosis: the way out of each closed part, proved from the engine's own lists.
A list started inside the part and reaching outside it shows the exits: an outside cell with no outside neighbour cheaper than itself was entered from the part.
The part is closed at the drop if every such exit has a unit on it then, and it was open before if the same exit was free at the big flood (read only)."""
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from lib import Places, cells, kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")


def nbrs(c):
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                if dx or dy or dz:
                    yield (c[0] + dx, c[1] + dy, c[2] + dz)


def analyse(run):
    L = read(run)
    P = Places(L)
    move = {}
    for s in L:
        if s.startswith("[HIVEUNIT]"):
            m = kv(s)
            move[int(m["id"])] = m["move"]
    # every list with where it started
    lists = []
    last_from = {}
    for i, s in enumerate(L):
        if s.startswith("[AIDECIDE]"):
            k = kv(s)
            last_from[int(k["unit"])] = (i, k["from"])
        elif s.startswith("[AICAND] moves="):
            k = kv(s)
            u = int(k["unit"])
            if u in move and u in last_from:
                f = last_from[u][1].strip("()").split(",")
                lists.append((i, u, move[u], tuple(map(int, f)), cells(k["list"])))
    last = {}
    out = []
    for i, s in enumerate(L):
        if not s.startswith("[HIVEREACH]"):
            continue
        k = kv(s)
        key = (k["unit"], k["turn"], k["at"])
        t = int(k["tiles"])
        if key in last and last[key][0] >= 2 * t:
            u = int(k["unit"])
            lst = next((c for j, v, m, f, c in lists if j > i and j < i + 60 and v == u), None)
            if lst is None:
                out.append(dict(run=run, line=i, unit=u, note="no list"))
                last[key] = (t, i)
                continue
            here, gone = P.at(i)
            me = here[u]
            R = set(lst) | {me}
            alive = {p: v for v, p in here.items() if v not in gone and v != u}
            gates = {}
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
                        gates[x] = gates.get(x, 0) + 1
            hit = {g: alive[g] for g in gates if g in alive}
            free = [g for g in gates if g not in alive]
            before, _ = P.at(last[key][1])
            alive0 = {p: v for v, p in before.items() if v not in gone and v != u}
            hit0 = {g: alive0[g] for g in gates if g in alive0}
            out.append(dict(run=run, line=i, line0=last[key][1], turn=k["turn"], unit=u, move=move[u], at=me, big=last[key][0], small=t, part=len(R), lists=used, gates=gates, hit=hit, free=free, hit0=hit0))
        last[key] = (t, i)
    return out


if __name__ == "__main__":
    for run in ["hh4_JA_M6_s2", "hh3_JA_M6_s1", "hh6_JV_M3_s1"]:
        print("==", run)
        for r in analyse(run):
            if "note" in r:
                print(r)
                continue
            print(f" line {r['line']} turn {r['turn']} unit {r['unit']} move {r['move']} at {r['at']} {r['big']}->{r['small']} part {r['part']} lists_from_inside {r['lists']}")
            print(f"   exits seen {len(r['gates'])}; with a unit at the drop {r['hit']}; free at the drop {len(r['free'])} {sorted(r['free'])[:10]}; with a unit at the big flood {r['hit0']}")
