"""SIDE_TURN_ACTION_SCHEDULER stage 3, step 1: the queue after a load in the middle of the hostile turn. The save run (arm V)
gives the hostile turn's activations before [AISCHEDSAVE] and the whole turn without a load; each load run (ai_probe on the
save: S with the scheduler, Q without) gives the activations of the same turn after the load. Per unit: activations in the turn
without a load vs before the save + after the load; which units acted before the save and act again after it, and
whether an AI decision was made for a player unit in the hostile turn.

  py -3.13 -I sc_load.py <out dir> <save run label> <load label> [<load label> ...]"""
import gzip
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT = Path(sys.argv[1])
KV = re.compile(r"(\w+)=(\S+)")


def acts(label, turn, stop_at_save=False):
    """[(unit, n of the first decision, decisions)] of the hostile side in that turn, activation by activation; the AI decisions
    for player units in the hostile turn; the [AISCHED] lines of the turn."""
    seq, foreign, sched, saved = [], [], [], False
    with gzip.open(OUT / label / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if body.startswith("[AISCHEDSAVE] "):
                saved = True
                if stop_at_save:
                    break
            elif body.startswith("[AISCHED] "):
                d = dict(KV.findall(body))
                if int(d["turn"]) == turn and d["side"] == "1":
                    sched.append(d)
            elif body.startswith("[AIDECIDE] "):
                d = dict(KV.findall(body.split(" hu=")[0]))
                if int(d["turn"]) != turn or d["side"] != "1":
                    continue
                if int(d["unit"]) < 1000000:
                    foreign.append(d)
                if not seq or seq[-1][0] != d["unit"] or d["n"] == "1":
                    seq.append([d["unit"], d["n"], 0])
                seq[-1][2] += 1
    return seq, foreign, sched, saved


base, label_loads = sys.argv[2], sys.argv[3:]
whole, _, wsched, _ = acts(base, 1)
before, _, bsched, saved = acts(base, 1, stop_at_save=True)
print(f"save run {base}: hostile turn 1 without a load - activations {len(whole)}, units {len(set(u for u, *_ in whole))}; "
      f"before the save {len(before)}: {' '.join(u for u, *_ in before)} (saved: {saved})")
cw = Counter(u for u, *_ in whole)
cb = Counter(u for u, *_ in before)
print(f"  activations per unit without a load: {dict(sorted(Counter(cw.values()).items()))} (activations: units)")
for lab in label_loads:
    after, foreign, sched, _ = acts(lab, 1)
    ca = Counter(u for u, *_ in after)
    tot = cb + ca
    more = sorted((u for u in tot if tot[u] > cw.get(u, 0)), key=int)
    again = [u for u in cb if u in ca]
    first_after = [u for u, *_ in after[:8]]
    print(f"== {lab}: activations after the load {len(after)}, first ones: {' '.join(first_after)}")
    if sched:
        s0 = sched[0]
        print(f"  first scheduler pick after the load: pick {s0['pick']} site {s0['site']} left {s0['left']} chosen {s0['chosen']} "
              f"why {s0['why']}")
    print(f"  units active before the save that act again after the load: {len(again)} of {len(cb)}: {' '.join(again)}")
    print(f"  units with more activations in the turn than without a load: {len(more)}; activations before+after vs without: "
          + ", ".join(f"{u}:{cb.get(u, 0)}+{ca.get(u, 0)}/{cw.get(u, 0)}" for u in more[:12]) + (" ..." if len(more) > 12 else ""))
    print(f"  activations in the turn, before+after the load: {sum(tot.values())} vs {sum(cw.values())} without a load")
    if foreign:
        f0 = foreign[0]
        print(f"  AI decisions for player units in the hostile turn: {len(foreign)}, first unit {f0['unit']} act {f0['act']} "
              f"tu {f0['tu']}")
    else:
        print("  AI decisions for player units in the hostile turn: 0")
