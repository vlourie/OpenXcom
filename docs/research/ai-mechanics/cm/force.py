"""How the hostile side spends its force in archived battles (D0 logs): per hostile unit - did it ever see a player unit, ever
attack, how it ended; how alone it was when it fell; how many attackers a hostile turn brings; how long battles run and when
cheatTurn (all player units known) starts.

  py -3.13 -I force.py <out dir> <prefix> [per-battle tsv]"""
import gzip
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT, PRE = Path(sys.argv[1]), sys.argv[2]
TSV = Path(sys.argv[3]) if len(sys.argv) > 3 else None
KV = re.compile(r"(\w+)=(\([^)]*\)|\S+)")
ATT = {6, 7, 8, 9, 10, 12, 13, 14}


def pos(t):
    return tuple(int(x) for x in t.strip("()").split(","))


tot = Counter()
alone = Counter()
turn_att = Counter()
end_turns = []
cheat = Counter()
first_att = Counter()
per = []
for d in sorted(OUT.glob(f"{PRE}_*")):
    units = {}  # id -> dict(faction, saw, att, end, end_turn, pos)
    where = {}  # id -> last known pos
    alive = {}  # id -> faction, alive now
    res = None
    att_turn = defaultdict(set)
    tgt_turn = defaultdict(Counter)
    hostile_alive_by_turn = {}
    with gzip.open(d / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if body.startswith("[AISTATE] "):
                k = dict(KV.findall(body))
                if "unit" not in k or "pos" not in k:
                    continue
                u = k["unit"]
                fac = int(k["faction"])
                if u not in units:
                    units[u] = {"fac": fac, "saw": False, "att": 0, "end": None, "turn": None, "type": k.get("type", "?")}
                where[u] = pos(k["pos"])
                if k["status"] in ("0", "1", "2", "3") and units[u]["end"] is None:
                    alive[u] = fac
                if fac == 1 and k.get("sees", "-") != "-":
                    units[u]["saw"] = True
                if body.startswith("[AISTATE] aistart"):
                    t = int(k["turn"])
                    hostile_alive_by_turn[t] = sum(1 for x, fa in alive.items() if fa == 1 and units[x]["end"] is None)
            elif body.startswith("[AIDECIDE] "):
                k = dict(KV.findall(body))
                u = k["unit"]
                if k.get("from"):
                    where[u] = pos(k["from"])
                if k.get("side") == "1" and u in units:
                    if k.get("seen", "-") not in ("-", ""):
                        units[u]["saw"] = True
                    if int(k["act"]) in ATT:
                        units[u]["att"] += 1
                        t = int(k["turn"])
                        att_turn[t].add(u)
                        tgt_turn[t][k.get("aim", "?")] += 1
                        if units[u]["att"] == 1:
                            units[u]["first"] = t
            elif body.startswith("[AICASUALTY] "):
                k = dict(KV.findall(body))
                v = k["victim"]
                if v not in units:
                    units[v] = {"fac": int(k["vfaction"]), "saw": False, "att": 0, "end": None, "turn": None, "type": k.get("type", "?")}
                if units[v]["end"] is None:
                    units[v]["end"] = k["how"]
                    units[v]["turn"] = int(k["turn"])
                    units[v]["side"] = k["side"]
                    p = pos(k["pos"])
                    if units[v]["fac"] == 1:
                        near = sum(1 for x, fa in alive.items() if fa == 1 and x != v and units[x]["end"] is None and x in where
                                   and max(abs(where[x][0] - p[0]), abs(where[x][1] - p[1])) <= 5 and abs(where[x][2] - p[2]) <= 1)
                        units[v]["near"] = near
                    alive.pop(v, None)
            elif body.startswith("[AIRESULT] "):
                res = dict(KV.findall(body))
    if not res:
        continue
    hs = [u for u in units.values() if u["fac"] == 1]
    b = Counter()
    for u in hs:
        b["hostile"] += 1
        b["saw"] += u["saw"]
        b["attacked"] += u["att"] > 0
        b["fell"] += u["end"] is not None
        b["fell_no_attack"] += u["end"] is not None and u["att"] == 0
        b["fell_never_saw"] += u["end"] is not None and not u["saw"]
        b["never_saw_alive_at_end"] += u["end"] is None and not u["saw"]
        if u["end"] is not None and "near" in u:
            alone["0" if u["near"] == 0 else "1" if u["near"] == 1 else "2-3" if u["near"] <= 3 else "4+"] += 1
            alone["fell_on_" + ("player_turn" if u["side"] == "0" else "own_turn")] += 1
        if "first" in u:
            first_att[min(u["first"], 21)] += 1
    for t, us in att_turn.items():
        turn_att["turns_with_attack"] += 1
        turn_att["attackers"] += len(us)
        turn_att["solo_turns"] += len(us) == 1
        turn_att["focus_turns"] += any(c >= 2 for c in tgt_turn[t].values())
    et = int(res["turn"])
    end_turns.append(et)
    ct = next((t for t in sorted(hostile_alive_by_turn) if (t > 10 and hostile_alive_by_turn[t] <= 2) or t > 20), None)
    cheat["battles"] += 1
    cheat["cheat_reached"] += ct is not None
    cheat["cheat_by_over20"] += ct is not None and ct > 20
    for k, v in b.items():
        tot[k] += v
    won = int(res["livealiens"]) == 0
    per.append((d.name, et, ct if ct else "-", b["hostile"], b["saw"], b["attacked"], b["fell"], b["fell_no_attack"], res["pdead"],
                res["phplost"], "player_won" if won else "other"))
print("battles", len(per), "end turn: median", sorted(end_turns)[len(end_turns) // 2], "max", max(end_turns),
      " >10:", sum(t > 10 for t in end_turns), " >20:", sum(t > 20 for t in end_turns))
print("cheatTurn reached (turn>20, or turn>10 with <=2 hostiles alive):", dict(cheat))
print("hostile units:", dict(tot))
h = tot["hostile"]
print(f"  saw a player unit {100 * tot['saw'] / h:.0f}%, ever attacked {100 * tot['attacked'] / h:.0f}%, "
      f"fell {100 * tot['fell'] / h:.0f}%, fell without one attack {100 * tot['fell_no_attack'] / max(1, tot['fell']):.0f}% of the fallen")
print("allies within 5 tiles (same level +-1) when a hostile fell:", dict(alone))
print("hostile turns with attacks:", dict(turn_att), f"attackers per such turn {turn_att['attackers'] / max(1, turn_att['turns_with_attack']):.2f}")
print("turn of a hostile's first attack (21 = later):", dict(sorted(first_att.items())))
if TSV:
    with open(TSV, "w", encoding="utf-8-sig", newline="\n") as f:
        f.write("battle\tend_turn\tcheat_turn\thostile\tsaw\tattacked\tfell\tfell_no_attack\tpdead\tphplost\tresult\n")
        for r in per:
            f.write("\t".join(map(str, r)) + "\n")
