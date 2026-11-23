"""RESTORE COMBAT AUTONOMY: hostile=70 in CC and 64 in RA on M3: is the start the same, and who are the rest? Units of the AI side by the turn they first show, start lists of the pair compared. Read only."""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
TRIPLES = [("cc3_CO_M6_s1", "cc8_CC_M6_s1", "ra1_AN_M6_s1"), ("scpa_D_M6_s2", "cc5_CC_M6_s2", "ra2_AN_M6_s2"), ("scpa_D_M3_s1", "cc6_CV_M3_s1", "ra3_AV_M3_s1")]


def units(run):
    first = {}
    typ = {}
    result = ""
    for s in read(run):
        if s.startswith("[AISTATE]") or s.startswith("[AIDECIDE]"):
            k = kv(s)
            u = k.get("unit") or k.get("id")
            if not u or k.get("faction", k.get("side")) != "1":
                continue
            t = int(k.get("turn", 0))
            first.setdefault(u, t)
            if k.get("type"):
                typ[u] = k["type"]
        elif s.startswith("[AICASUALTY]"):
            k = kv(s)
            if k.get("vfaction") == "1":
                first.setdefault(k["victim"], int(k["turn"]))
                typ[k["victim"]] = k.get("type", "")
        elif s.startswith("[AIRESULT]"):
            k = kv(s)
            result = {x: k.get(x) for x in ("hostile", "hdead", "hout", "hleft", "livealiens", "turn")}
    return first, typ, result


for triple in TRIPLES:
    base = None
    for run in triple:
        first, typ, result = units(run)
        at = Counter(first.values())
        early = {u for u, t in first.items() if t <= 1}
        print(run, "units", len(first), "by first turn", dict(sorted(at.items())), result)
        late = sorted((t, u, typ.get(u, "")) for u, t in first.items() if t > 1)
        print("   late", late[:30])
        if base is None:
            base = early
        else:
            print("   start list against the first of the triple: only here", sorted(early - base)[:20], "only there", sorted(base - early)[:20])
