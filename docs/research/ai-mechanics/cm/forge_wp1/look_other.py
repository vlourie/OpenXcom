"""AI FORGE WP1: the log lines no comparison covered: what they are and how two replays differ in them; and R6's canonical chain against R5's at n=889. args: none"""
import gzip
import re
import sys
from collections import Counter

sys.path.insert(0, __file__.rsplit("\\", 1)[0] if "\\" in __file__ else __file__.rsplit("/", 1)[0])
import AIForgeReplayRunner as rr
import scheduler_integrity_check as sic

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def others(r):
    return [s for s in sic.read_log(*rr.source_of(r)) if not s.startswith(("[AI", "[FORGE"))]


def shape(s):
    return re.sub(r"\d+", "#", s)[:70]


for a, b in (("R2", "R3"), ("P1", "R5")):
    oa, ob = others(a), others(b)
    print(a, b, "lines", len(oa), len(ob), "first 3 of a:", [x[:90] for x in oa[:3]])
    ca, cb = Counter(oa), Counter(ob)
    only_a = list((ca - cb).elements())
    only_b = list((cb - ca).elements())
    print(" only in", a, len(only_a), Counter(shape(x) for x in only_a).most_common(8))
    print(" only in", b, len(only_b), Counter(shape(x) for x in only_b).most_common(8))
    known = re.compile(r"^(HD stall:|HD frame:|User folder is:|Config folder is:|Scanning user mods in|scanModDir\()")
    print(" neither real-time report nor path:", [x[:120] for x in only_a + only_b if not known.match(x)])
rows = {}
for r in ("R5", "R6"):
    with gzip.open(rr.HERE / "chains" / f"chain_{r}.tsv.gz", "rt", encoding="utf-8") as z:
        rows[r] = [s.rstrip("\n").split("\t") for s in z][1:]
print("n=889", rows["R5"][888], rows["R6"][888])
print("canonical equal at every n to 889:", all(x[2] == y[2] for x, y in zip(rows["R5"], rows["R6"])), "raw equal:", sum(1 for x, y in zip(rows["R5"], rows["R6"]) if x[1] == y[1]))
fl = sic.read_log.__doc__
_, fp, _ = rr.prov(*rr.source_of("R3"))
print("fast flag", fp.get("OXCE_AI_FAST"), "realtime flag", fp.get("OXCE_AI_REALTIME"), "bot flags", {k: v for k, v in fp.items() if "FORGE" in k})
