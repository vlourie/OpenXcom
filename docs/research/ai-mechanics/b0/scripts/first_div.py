"""First AI decision that differs between two stand logs ([AIDECIDE] lines, timestamps dropped).

  py -3.13 first_div.py <a/openxcom.log> <b/openxcom.log> [context]

The choice is what comes before the state hashes (turn, side, unit, n, from, tu, mode, act, to, run, kneel, aim, weapon,
seen); the hashes after it (hu units, hi items, ho/hou others, hm map, hr/hr0 RNG, ha/ha0 action) tell where the state the
decision saw began to differ. Prints the first decision whose state hashes differ and the first whose choice differs."""
import re
import sys

KEEP = re.compile(r"\[AIDECIDE\] (.*)")
HASH = re.compile(r"\s(h[a-z]*\d?)=([0-9a-f]+)")


def decisions(p):
    out = []
    for line in open(p, encoding="utf-8", errors="replace"):
        m = KEEP.search(line)
        if m:
            d = m.group(1).strip()
            cut = d.find(" hu=")
            out.append((d[:cut] if cut >= 0 else d, dict(HASH.findall(d[cut:])) if cut >= 0 else {}))
    return out


def first(a, b, key):
    n = 0
    while n < min(len(a), len(b)) and key(a[n]) == key(b[n]):
        n += 1
    return n


a, b = decisions(sys.argv[1]), decisions(sys.argv[2])
ctx = int(sys.argv[3]) if len(sys.argv) > 3 else 1
nh = first(a, b, lambda d: d)
nc = first(a, b, lambda d: d[0])
print(f"decisions A {len(a)} B {len(b)}; same state and choice from the start {nh}; same choice from the start {nc}")
if nh < min(len(a), len(b)):
    diff = [k for k in sorted(set(a[nh][1]) | set(b[nh][1])) if a[nh][1].get(k) != b[nh][1].get(k)]
    print(f"  first state difference at #{nh}: {a[nh][0][:120]} ... hashes differ: {','.join(diff)}")
if nc < max(len(a), len(b)):
    for k in range(max(0, nc - ctx), nc):
        print("  same ", a[k][0][:220])
    print("  A    ", a[nc][0][:220] if nc < len(a) else "-")
    print("  B    ", b[nc][0][:220] if nc < len(b) else "-")
