"""CONTACT_COORDINATION_V0: what a unit with kind=no_node did that turn, against the same unit-turn in the off run (read only). Usage: nonode.py <run> <off run>"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ATT = set(range(4, 21))


def dec(L):
    out = defaultdict(lambda: defaultdict(list))
    for s in L:
        if s.startswith("[AIDECIDE]"):
            k = kv(s)
            if k["side"] == "1":
                out[int(k["turn"])][int(k["unit"])].append(k)
    return out


def main():
    L, O = read(sys.argv[1]), read(sys.argv[2])
    d, d0 = dec(L), dec(O)
    orders = Counter()
    for s in L:
        if s.startswith("[HIVECC]") and "event=ORDER" in s and "kind=no_node" in s:
            k = kv(s)
            t, u = int(k["turn"]), int(k["unit"])
            ds = d[t].get(u, [])
            modes = Counter(x["mode"] for x in ds)
            acts = Counter(x["act"] for x in ds)
            first = int(ds[0]["tu"]) if ds else 0
            last = int(ds[-1]["tu"]) if ds else 0
            kind = "no decision" if not ds else ("walked" if acts.get("2") else ("attacked" if any(int(a) in ATT for a in acts) else "stood"))
            orders[(k["role"], kind)] += 1
            print(f"t{t} {k['role']} {u} decisions {len(ds)} modes {dict(modes)} acts {dict(acts)} tu {first}->{last}; off decisions {len(d0[t].get(u, []))}")
    print("sum", orders.most_common())


if __name__ == "__main__":
    main()
