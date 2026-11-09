"""Each mode 3 decision of the AI side: was it the dice (odds mode=3) or the fall back COMBAT/PATROL -> AMBUSH -> ESCAPE, and what order stood over the unit that turn. Read only.
Usage: rollback.py run ...; run without HIVECC lines counts as order 'none'."""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ATT = set(range(4, 21))


def one(run, last=8):
    L = read(run)
    ord_, hold = {}, {}
    pend = {}
    tally = defaultdict(Counter)
    samples = []
    for s in L:
        if s.startswith("[HIVECC]"):
            k = kv(s)
            if k["event"] == "ORDER":
                ord_[(int(k["turn"]), int(k["unit"]))] = k
        elif s.startswith("[AIREC]"):
            try:
                j = json.loads(s[8:])
            except ValueError:
                continue
            pend[(j["turn"], j["unit"], j["n"])] = j
        elif s.startswith("[AIDECIDE]"):
            k = kv(s)
            if k["side"] != "1":
                continue
            t, u, n = int(k["turn"]), int(k["unit"]), int(k["n"])
            if t > last:
                continue
            o = ord_.get((t, u))
            label = (o["role"] + ":" + o["kind"]) if o else "none"
            j = pend.get((t, u, n)) or {}
            b = j.get("base") or {}
            odds = (b.get("reason") or {}).get("odds") or []
            dice = odds[-1]["mode"] if odds else "-"
            act = int(k["act"])
            fin = k["mode"]
            what = "attack" if act in ATT else "walk" if act == 2 else "none"
            kind = "other"
            if fin == "3":
                kind = "esc_dice" if dice == 3 else "esc_kept" if dice == "-" else "esc_rollback"
            elif fin == "1":
                kind = "amb_dice" if dice == 1 else "amb_kept" if dice == "-" else "amb_rollback"
            elif fin == "0":
                kind = "pat"
            elif fin == "2":
                kind = "combat"
            tally[label][kind + "/" + what] += 1
            tally[label]["_decisions"] += 1
            if kind == "esc_rollback" and len(samples) < 6:
                samples.append((t, u, n, label, what, b.get("src"), b.get("src_rec"), odds[-1:], b.get("to")))
    print("==", run)
    keys = sorted({x for c in tally.values() for x in c if x != "_decisions"})
    print("order\tdecisions\t" + "\t".join(keys))
    for lab in sorted(tally):
        print(lab + "\t" + str(tally[lab]["_decisions"]) + "\t" + "\t".join(str(tally[lab][x]) for x in keys))
    for x in samples:
        print("  ", x)


for r in sys.argv[1:]:
    one(r)
