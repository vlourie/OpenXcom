"""Movement diagnosis: a field depends on the start, the move type, the map and who stands where. For every drop on one place: did the map fingerprint change between the two floods, and which units moved (read only)."""
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from lib import Places, kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
for run in ["hh4_JA_M6_s2", "hh3_JA_M6_s1", "hh6_JV_M3_s1"]:
    L = read(run)
    P = Places(L)
    dec = [(i, kv(s)["hm"]) for i, s in enumerate(L) if s.startswith("[AIDECIDE]")]
    last = {}
    print("==", run)
    for i, s in enumerate(L):
        if not s.startswith("[HIVEREACH]"):
            continue
        k = kv(s)
        key = (k["unit"], k["turn"], k["at"])
        t = int(k["tiles"])
        if key in last and last[key][0] >= 2 * t:
            i0 = last[key][1]
            inside = [h for j, h in dec if i0 <= j <= i]
            after = next((h for j, h in dec if j > i0), None)
            before = next((h for j, h in reversed(dec) if j < i), None)
            h0, g0 = P.at(i0)
            h1, g1 = P.at(i)
            moved = sorted(u for u in h1 if u >= 1000000 and h0.get(u) != h1[u] and u not in g1 and u != int(k["unit"]))
            out = sorted(u for u in g1 if u not in g0)
            print(f" {i0}->{i} turn {k['turn']} unit {k['unit']} {last[key][0]}->{t} decisions {len(inside)} map fingerprints {len(set(inside))} same_ends {after == before} allies moved {len(moved)} fell {len(out)} player moved {sum(1 for u in h1 if u < 1000000 and h0.get(u) != h1[u])}")
        last[key] = (t, i)
