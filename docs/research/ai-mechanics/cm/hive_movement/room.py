"""Movement diagnosis: draws one closed part level by level from the unit's own candidate list: # part, + walked by units of the same move type at any time in the battle, letters units then (read only).
Usage: room.py <run> <flood line> <x0> <x1> <y0> <y1>"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from lib import Places, cells, kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
run, line = sys.argv[1], int(sys.argv[2])
x0, x1, y0, y1 = map(int, sys.argv[3:7])
L = read(run)
P = Places(L)
k = kv(L[line])
u = int(k["unit"])
here, out = P.at(line)
moves = {}
for s in L:
    if s.startswith("[HIVEUNIT]"):
        m = kv(s)
        moves[int(m["id"])] = m["move"]
inside = {}
for j in range(line, min(line + 60, len(L))):
    if L[j].startswith("[AICAND] moves=") and f" unit={u} " in L[j]:
        inside = cells(kv(L[j])["list"])
        break
known = set()
for s in L:
    if s.startswith("[AICAND] moves="):
        m = kv(s)
        if moves.get(int(m["unit"])) == moves[u]:
            known |= set(cells(m["list"]))
print(L[line][:120], "move", moves[u], "list", len(inside), "known cells", len(known))
letters = {}
abc = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
for v, p in sorted(here.items()):
    if v not in out:
        letters[p] = v
names = {}
for z in range(0, 5):
    rows = []
    for y in range(y0, y1 + 1):
        row = ""
        for x in range(x0, x1 + 1):
            p = (x, y, z)
            if p in letters:
                v = letters[p]
                names.setdefault(v, abc[len(names) % len(abc)])
                row += names[v]
            elif p in inside:
                row += "#"
            elif p in known:
                row += "+"
            else:
                row += " "
        rows.append(f"{y:3d} {row}")
    if any(("#" in r or any(c in abc for c in r[4:])) for r in rows):
        print("z", z, "x from", x0)
        print("\n".join(rows))
print({names[v]: (v, p) for p, v in letters.items() if v in names})
