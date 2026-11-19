"""Movement diagnosis: the walkable graph of one battle rebuilt from the engine's own candidate lists, one per move type.
Two free neighbours are linked if no list contradicts a step between them: a real step of cost w means the two costs differ by at most w in every list holding both.
The graph is trusted only as far as it reproduces the logged field sizes: an uncapped flood is the size of the part containing its start, so the check is exact (read only)."""
import sys
from collections import defaultdict, deque
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from lib import Places, cells, kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
OFFS = [(dx, dy, dz) for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1) if (dx, dy, dz) > (0, 0, 0)]
WMAX = 12


def lists_of(L):
    move, size = {}, {}
    for s in L:
        if s.startswith("[HIVEUNIT]"):
            m = kv(s)
            move[int(m["id"])] = m["move"]
            size[int(m["id"])] = m["size"]
    frm = {}
    out = defaultdict(list)
    for i, s in enumerate(L):
        if s.startswith("[AIDECIDE]"):
            k = kv(s)
            frm[int(k["unit"])] = tuple(map(int, k["from"].strip("()").split(",")))
        elif s.startswith("[AICAND] moves="):
            k = kv(s)
            u = int(k["unit"])
            if u in move and u in frm and size[u] == "1":
                c = cells(k["list"])
                c[frm[u]] = 0
                out[move[u]].append((i, u, c))
    return move, out


def build(lists):
    """Neighbours seen together, and the largest difference any list gives them."""
    spread = {}
    for _, _, c in lists:
        for a, ca in c.items():
            for d in OFFS:
                b = (a[0] + d[0], a[1] + d[1], a[2] + d[2])
                cb = c.get(b)
                if cb is None:
                    continue
                key = (a, b)
                delta = abs(ca - cb)
                if delta > spread.get(key, -1):
                    spread[key] = delta
    adj = defaultdict(set)
    for (a, b), delta in spread.items():
        if delta <= WMAX:
            adj[a].add(b)
            adj[b].add(a)
    return adj


def flood(adj, start, blocked):
    seen = {start}
    q = deque([start])
    while q:
        a = q.popleft()
        for b in adj.get(a, ()):
            if b not in seen and b not in blocked:
                seen.add(b)
                q.append(b)
    return seen


if __name__ == "__main__":
    for run in ["hh4_JA_M6_s2", "hh3_JA_M6_s1", "hh6_JV_M3_s1"]:
        L = read(run)
        P = Places(L)
        move, lists = lists_of(L)
        graphs = {m: build(v) for m, v in lists.items()}
        print("==", run, {m: (len(v), len(graphs[m])) for m, v in lists.items()})
        good = bad = 0
        misses = []
        for i, s in enumerate(L):
            if s.startswith("[HIVEREACH]") and " capped=0 " in s:
                k = kv(s)
                u = int(k["unit"])
                t = int(k["tiles"])
                here, out = P.at(i)
                ally = {p for v, p in here.items() if v >= 1000000 and v not in out and v != u}
                got = flood(graphs[move[u]], here[u], ally)
                if len(got) == t:
                    good += 1
                else:
                    bad += 1
                    misses.append((i, u, t, len(got)))
        print("  uncapped floods reproduced exactly", good, "not", bad, "first misses", misses[:12])
