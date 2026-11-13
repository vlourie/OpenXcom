"""Movement diagnosis: where the headquarters is born in the log relative to the spawn, the first turn and the first decisions of either side, and the fate of the saved orders after a load (read only)."""
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")


def first(L, tag, n=1):
    out = []
    for i, s in enumerate(L):
        if s.startswith(tag):
            out.append((i, s[:200]))
            if len(out) >= n:
                break
    return out


for run in ["hh4_JA_M6_s2", "hh6_JV_M3_s1", "hh1_JO_M6_s1", "hh2_JS_M6_s1"]:
    L = read(run)
    print("==", run, "lines", len(L))
    print("  tags before the first decision:", Counter(s.split(" ")[0] for s in L[: next(i for i, s in enumerate(L) if s.startswith("[AIDECIDE]"))] if s.startswith("[")).most_common(16))
    for tag in ("[AIPROBE]", "[HIVEINIT]", "[AICASUALTY]", "[HIVEUNIT]", "[HIVETURN]", "[AIDECIDE]", "[HIVEFIRST]", "[HIVEPLAN]", "[HIVEGO]", "[HIVEORDER]"):
        print("  ", tag, first(L, tag))
    d0 = next(kv(s) for s in L if s.startswith("[AIDECIDE]"))
    print("   first decision side", d0.get("side"), "turn", d0.get("turn"), "unit", d0.get("unit"))
    d1 = next((i, kv(s)) for i, s in enumerate(L) if s.startswith("[AIDECIDE]") and " side=1 " in s)
    print("   first enemy decision line", d1[0], "turn", d1[1].get("turn"), "unit", d1[1].get("unit"))
    print("   casualties before the first enemy decision:", [s[:120] for i, s in enumerate(L[: d1[0]]) if s.startswith("[AICASUALTY]")][:6])


def saved_orders(text):
    """Order records of the hive text: O,<fields>."""
    return [x for x in text.split(";") if x.startswith("O,")]


A = read("hh6_JV_M3_s1")
B = read("hh7_HL_M3_s1")
save = next(s for s in A if s.startswith("[HIVESAVE]"))
load = next(s for s in B if s.startswith("[HIVELOAD]"))
t_a = save[save.index("text=") + 5 :]
t_b = load[load.index("text=") + 5 :]
print("== hive text same in save and load:", t_a == t_b, len(t_a), len(t_b))
print("   record kinds:", Counter(x.split(",")[0] for x in t_a.split(";")).most_common())
print("   sample:", [x[:120] for x in t_a.split(";")[:8]])
for tag in ("[HIVESAVE]", "[HIVELOAD]", "[HIVEDUMP]", "[HIVECHECK]", "[HIVERESTORE]"):
    print("  ", tag, "A", sum(s.startswith(tag) for s in A), "B", sum(s.startswith(tag) for s in B))
print("tags in B around the load:")
i0 = next(i for i, s in enumerate(B) if s.startswith("[HIVELOAD]"))
for s in B[i0 - 2 : i0 + 6]:
    print("   ", s[:170])
print("first hive lines of B after the load:")
n = 0
for i, s in enumerate(B[i0 + 2 :], i0 + 2):
    if s.startswith("[HIVE"):
        print("   ", i, s[:190])
        n += 1
        if n > 14:
            break
tags = Counter(s.split(" ")[0] for s in B if s.startswith("[HIVE"))
print("hive tags in B", tags.most_common())
print("save turn hash lines in A:", [(i, s[:100]) for i, s in enumerate(A) if s.startswith("[HIVESAVE]")][:4])
print(re.findall(r"nextOrder\w*", t_a)[:2])
