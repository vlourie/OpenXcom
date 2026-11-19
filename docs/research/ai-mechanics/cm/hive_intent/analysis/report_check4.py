"""HIVE COMBAT INTENT V0: attacks that asked no question (own_other): had their squad a contact at all, which intent type. Read only."""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
for run in ("ci5_IA_M6_s1", "ci6_IA_M6_s2", "ci7_IV_M3_s1"):
    L = read(run)
    issue = {}
    c = Counter()
    for s in L:
        if s.startswith("[HIVEINTENT] event=ISSUE"):
            k = kv(s)
            issue[(k["turn"], k["squad"])] = k["type"]
        elif s.startswith("[HIVEINTENT] event=DECIDED"):
            k = kv(s)
            if k.get("own") == "own_other":
                c[(issue.get((k["turn"], k["squad"]), "none"), "contact" if k["contact"] != "-1" else "no_contact")] += 1
    print(run, sorted(c.items(), key=lambda x: -x[1]))
