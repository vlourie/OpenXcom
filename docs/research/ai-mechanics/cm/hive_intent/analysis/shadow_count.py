"""HIVE COMBAT INTENT V0, R-617: in a shadow run, which fighting choices would the intent replace, per turn, contact and refusal; only those at sniper and shot sites, as those are the attacks. Read only.
Usage: shadow_count.py <run> [<turn to list>]"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
run = sys.argv[1]
want = int(sys.argv[2]) if len(sys.argv) > 2 else 1
lines = read(run)
per = defaultdict(Counter)
contacts = Counter()
seen = Counter()
for s in lines:
    if s.startswith("[HIVEINTENT] event=CHOICE") and "site=firepoint" not in s:
        k = kv(s)
        t = int(k["turn"])
        no = k["no"] if k["no"] != "-" else "TAKES"
        per[t][no] += 1
        contacts[(k["contact"], no)] += 1
        if t == want:
            print(s[:200])
    elif s.startswith("[HIVEINTENT] event=PRIORITY") or s.startswith("[HIVEINTENT] event=SKIP"):
        if int(kv(s)["turn"]) <= 3:
            print(s[:120])
    elif s.startswith("[AIEXEC]"):
        seen["exec"] += 1
        if seen["exec"] <= 2:
            print(s[:200])
print("by turn", {t: dict(c.most_common()) for t, c in sorted(per.items())})
print("by contact", sorted(contacts.items()))
