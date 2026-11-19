"""COMBAT INTENT V0, feasibility from the archives, read only: on each turn of a RA battle, attacks by aim; which of the shooters could also have fired at another contact (AICAND lines of the same record); turns where two or more fighters split though a shared target was open to them.
Usage: episodes.py <run> [<run>...]"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ATT = set(range(4, 21))


def scan(run):
    lines = read(run)
    sample = [s for s in lines if s.startswith("[AICAND]")][:2]
    print(run, "AICAND lines", sum(s.startswith("[AICAND]") for s in lines))
    for s in sample:
        print("   sample", s[:500])
    squad = {}
    for s in lines:
        if s.startswith("[HIVESQUAD]") and "members=" in s:
            k = kv(s)
            for m in k["members"].replace(",", ":").split(":"):
                if m:
                    squad[m] = k.get("squad") or k.get("id")
    turns = defaultdict(list)
    last = None
    for s in lines:
        if s.startswith("[AIDECIDE]"):
            k = kv(s)
            last = None
            if k["side"] == "1" and int(k["turn"]) <= 8 and int(k["act"]) in ATT:
                last = dict(k, rec=None, tg=None)
                turns[int(k["turn"])].append(last)
        elif s.startswith("[AIREC]") and last is not None and last["rec"] is None:
            try:
                j = json.loads(s[8:])
            except ValueError:
                continue
            last["rec"] = j
    total = Counter()
    for t in sorted(turns):
        by = Counter(d["aim"] for d in turns[t])
        units = defaultdict(set)
        for d in turns[t]:
            units[d["aim"]].add(d["unit"])
        all_units = {d["unit"] for d in turns[t]}
        total["attacks"] += len(turns[t])
        total["shooters"] += len(all_units)
        total["aims"] += len(by)
        total["turns_split"] += len(all_units) >= 2 and len(by) >= 2
        print(f"  turn {t}: attacks {len(turns[t])} shooters {len(all_units)} aims " + ", ".join(f"{a}:{n}/{len(units[a])}" for a, n in by.most_common()))
    print("  total", dict(total))
    for d in (turns.get(1) or [])[:1]:
        print("   rec keys", list((d["rec"] or {}).keys()), "base", json.dumps((d["rec"] or {}).get("base"))[:400])


for r in sys.argv[1:]:
    scan(r)
