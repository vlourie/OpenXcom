"""AI FORGE WP1: each fall of time units past the hooks, with the unit's tu/hp/stun as every kind of line shows them
between the last forge line and this one. Also counts rises past the hooks. args: run"""
import re
import sys
from collections import Counter

sys.path.insert(0, __file__.rsplit("\\", 1)[0] if "\\" in __file__ else __file__.rsplit("/", 1)[0])
import AIForgeReplayRunner as rr
import scheduler_integrity_check as sic

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
lines = sic.read_log(*rr.source_of(sys.argv[1]))
NUM = re.compile(r"\b(tu|hp|stun)[=\":]+(\d+)")


def seen_state(s, u):
    """the unit's tu/hp/stun if this line is about that unit, else None"""
    if s.startswith("[FORGEDUMP] ") and f" u={u} " in s:
        pass
    elif s.startswith("[AISTATE] ") and f" unit={u} " in s:
        pass
    elif s.startswith("[AIEXEC] ") and f'"unit":{u},' in s:
        pass
    else:
        return None
    return {k: int(v) for k, v in NUM.findall(s)}


last = {}
at = {}
falls = 0
rises = Counter()
classes = Counter()
for i, s in enumerate(lines):
    if not s.startswith("[FORGE] "):
        continue
    d = dict(sic.KV.findall(s))
    u, ev = d.get("unit"), d.get("ev")
    if not u or u == "-1" or "tu" not in d:
        continue
    shown = int(d["was"]) if ev == "tu" else int(d["tu"])
    if u in last and shown != last[u]:
        seq = [x for x in (seen_state(y, u) for y in lines[at[u] + 1:i]) if x]
        kinds = Counter(y.split(" ", 1)[0] for y in lines[at[u] + 1:i] if f"unit={u} " in y and y.startswith("[AIEVENT]"))
        hits = [y for y in lines[at[u] + 1:i] if y.startswith("[AIEVENT]") and f"unit={u} " in y and "what=explosion" in y]
        hps = [x["hp"] for x in seq if "hp" in x]
        stuns = [x["stun"] for x in seq if "stun" in x]
        changed = len(set(hps)) > 1 or len(set(stuns)) > 1
        if shown > last[u]:
            rises[d["ev"]] += 1
        else:
            falls += 1
            cls = "hp_or_stun_moved" if changed else ("no_state_lines" if len(seq) < 2 else "no_hp_stun_move")
            classes[cls] += 1
            print(f"#{falls} n={d['n']} t={d['t']} s={d['s']} u={u} fall={last[u] - shown} {cls} tu={[x.get('tu') for x in seq][:6]} hp={hps[:6]} stun={stuns[:6]}")
    last[u] = int(d["now"]) if ev == "tu" else shown
    at[u] = i
print("falls", falls, dict(classes))
print("rises past the hooks by event", dict(rises), "total", sum(rises.values()))
