"""RESTORE COMBAT AUTONOMY, stage 2 static check over the archive (no battle): what the proposed rule answers on every held decision, by squad task and why. Guard stays (task HOLD with a guard's reason): stand without escape. Everything else: free choice. Dice escapes and attacks do not change. Read only.
Usage: static.py <run> ... (needs chain.py's decisions_<run>.tsv)"""
import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
ART = {"art_esc_stand", "art_esc_walk", "held_patrol_stand"}
NOT_GUARD = {"nothing_known", "nothing_reachable"}


def task_map(run):
    """(turn, unit, order why) -> the squad's task, from the order's own line."""
    out = {}
    for s in read(run):
        if s.startswith("[HIVEORD]") and " task=" in s:
            k = kv(s)
            out[(k["turn"], k["unit"])] = k.get("task")
    return out


tot = Counter()
for run in sys.argv[1:]:
    rows = list(csv.DictReader(open(HERE / f"decisions_{run}.tsv", encoding="utf-8-sig"), delimiter="\t"))
    tasks = task_map(run)
    c = Counter()
    w = Counter()
    for d in rows:
        if not d["hold"]:
            continue
        guard = d["task"] == "HOLD" and d["why"] not in NOT_GUARD
        ans = "STAND" if guard else "FREE"
        c[ans + ":" + d["cls"]] += 1
        if d["cls"] in ART:
            w[ans + ":" + d["label"] + ":" + (d["hold"].split(":")[-1])] += 1
    print("==", run)
    print("  ", dict(c.most_common()))
    print("   artificial:", dict(w.most_common()))
    tot.update(k.split(":")[0] for k, v in w.items() for _ in range(v))
print("total artificial decisions", dict(tot))
