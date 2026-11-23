"""All fields of one unit across saves, the ones that differ from the first save marked:
py -3.13 unit_all.py <id> <sav> [sav ...]"""
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from cmp_b0 import state

uid = int(sys.argv[1])
us = [(p.replace("\\", "/").rsplit("/", 2)[-2], state(p)["byid"].get(uid) or {}) for p in sys.argv[2:]]
base = us[0][1]
print(us[0][0], {k: v for k, v in base.items() if k not in ("tags", "currStats", "inventory", "scriptValues")})
for name, u in us[1:]:
    print(name, {k: (base.get(k), u.get(k)) for k in sorted(set(base) | set(u)) if base.get(k) != u.get(k)})
