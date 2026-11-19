"""FIRST CONTACT SURVIVAL, stage 1: the chronology of every hostile loss from the existing D0 logs (read only).
For each loss: the phase (the player's turn, the start of the hostile side's own turn before any of its decisions, inside its turn), whether the unit ever got a decision of its own,
the last own decision, who was acting when it fell, what killed it, whether the killer was known to the side (spotted this turn at the unit's last decision, or ever before).
Usage: chrono.py <out tsv> <battle dir>...  Prints a summary per battle."""
import collections
import gzip
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")
POS = re.compile(r"(\w+)=\((-?\d+),(-?\d+),(-?\d+)\)")
COLS = ("battle turn side phase victim type how pos tu_at_loss seenby killer kfaction dist weapon hit terrain own_decisions own_turns own_spent cause "
        "actor actor_act actor_mode actor_is_victim last_turn last_mode last_act last_from last_to last_tu last_seen_n killer_seen_at_last killer_seen_before reaction_by_killer "
        "start_pos start_seenby moved cat").split()


def rows(d):
    with gzip.open(Path(d) / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for ln in f:
            yield ln.rstrip("\n").split("\t")[-1]


def kv(s):
    k = dict(KV.findall(s))
    for m in POS.finditer(s):
        k[m.group(1)] = f"{m.group(2)},{m.group(3)},{m.group(4)}"
    return k


def battle(d):
    name = Path(d).name
    out = []
    own = collections.defaultdict(list)  # the unit's decisions
    spent = collections.Counter()
    seen_ever = set()
    start = {}
    turn_has_dec = set()  # (turn) hostile decisions began
    actor = None
    last_react = None
    dec = None
    res = {}
    for s in rows(d):
        if s.startswith("[AISTATE] "):
            k = kv(s)
            if k.get("faction") == "1" and k["unit"] not in start and s.startswith("[AISTATE] before"):
                start[k["unit"]] = (k.get("pos"), k.get("seenby"))
        elif s.startswith("[AIDECIDE] "):
            k = kv(s)
            actor = k
            dec = k
            if k["side"] == "1":
                turn_has_dec.add(k["turn"])
                own[k["unit"]].append(k)
                if k.get("seen") and k["seen"] != "-":
                    seen_ever.update(k["seen"].split(","))
        elif s.startswith("[AIEXEC] ") and dec:
            try:
                x = json.loads(s[9:])
            except ValueError:
                x = {}
            if str(x.get("unit")) in own and dec["side"] == "1":
                spent[str(x["unit"])] += x.get("spent") or 0
            dec = None
        elif s.startswith("[AIEVENT] "):
            k = kv(s)
            if k.get("what") == "reaction":
                last_react = k
        elif s.startswith("[AIRESULT]"):
            res = kv(s)
        elif s.startswith("[AICASUALTY] "):
            k = kv(s)
            if k.get("vfaction") != "1":
                continue
            v = k["victim"]
            ds = own.get(v, [])
            last = ds[-1] if ds else {}
            if k["side"] == "0":
                phase = "player_turn"
            elif k["turn"] not in turn_has_dec:
                phase = "own_turn_start"
            else:
                phase = "inside_own_turn"
            kill = k.get("killer", "-1")
            react = bool(last_react and last_react.get("unit") == kill and last_react.get("turn") == k["turn"] and last_react.get("side") == k["side"])
            if k.get("kfaction") == "1":
                cause = "friendly"
            elif kill == "-1":
                cause = "no_killer"
            elif phase == "player_turn":
                cause = "direct_fire" if actor and actor.get("unit") == kill else "player_other"
            elif phase == "own_turn_start":
                cause = "turn_start_wounds_or_fire"
            else:
                cause = "reaction" if react else "own_turn_other"
            sn = last.get("seen", "-")
            moved = "-"
            st = start.get(v, ("-", "-"))
            if st[0] and k.get("pos"):
                moved = int(st[0] != k["pos"])
            row = dict(battle=name, turn=k["turn"], side=k["side"], phase=phase, victim=v, type=k.get("type", "")[4:], how=k.get("how"), pos=k.get("pos"), tu_at_loss=k.get("tu"), seenby=k.get("seenby"),
                       killer=kill, kfaction=k.get("kfaction"), dist=k.get("dist"), weapon=k.get("weapon"), hit=k.get("hit"), terrain=k.get("terrain"),
                       own_decisions=len(ds), own_turns=len({x["turn"] for x in ds}), own_spent=spent.get(v, 0), cause=cause,
                       actor=actor.get("unit") if actor else "-", actor_act=actor.get("act") if actor else "-", actor_mode=actor.get("mode") if actor else "-",
                       actor_is_victim=int(bool(actor and actor.get("unit") == v)), last_turn=last.get("turn", "-"), last_mode=last.get("mode", "-"), last_act=last.get("act", "-"),
                       last_from=last.get("from", "-"), last_to=last.get("to", "-"), last_tu=last.get("tu", "-"), last_seen_n=len(sn.split(",")) if sn != "-" and last else 0,
                       killer_seen_at_last=int(kill in sn.split(",")), killer_seen_before=int(kill in seen_ever), reaction_by_killer=int(react), start_pos=st[0], start_seenby=st[1], moved=moved)
            row["cat"] = "A" if not ds else "?"
            out.append(row)
    return name, out, res, start


def main():
    allrows = []
    for d in sys.argv[2:]:
        name, out, res, start = battle(d)
        allrows += out
        print(f'== {name}: end turn {res.get("turn")} hostile {res.get("hostile")} dead {res.get("hdead")}+{res.get("hout")} pdead {res.get("pdead")} (start states {len(start)})')
        c = collections.Counter((r["turn"], r["phase"], r["cause"], "acted" if r["own_decisions"] else "NEVER") for r in out)
        for key, n in sorted(c.items(), key=lambda a: (int(a[0][0]), a[0][1], a[0][2], a[0][3])):
            print(f"   t{key[0]:>2} {key[1]:16} {key[2]:26} {key[3]:6} {n}")
    with open(sys.argv[1], "w", encoding="utf-8-sig", newline="") as f:
        f.write("\t".join(COLS) + "\n")
        for r in allrows:
            f.write("\t".join(str(r.get(c, "")) for c in COLS) + "\n")
    print("rows", len(allrows))


main()
