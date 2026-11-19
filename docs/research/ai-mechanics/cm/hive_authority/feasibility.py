"""AUTHORITY CONTRACT, part 3: what a headquarters can know before it assigns an operation, measured on the archive only. 48 D0 battles (no HQ code at all), read only, nothing is run.
Order of a turn: player's turn t, then AI's turn t. pstart t+1 stands right after the AI's turn t, aistart t+1 right after the player's turn t+1.
Parts: A survival over the player's turn by what is on record at the end of the AI's turn (legal: distance to a player unit the side sees; hidden: seenby of the unit); B a cell somebody already survived on; C the target over the player's turn (moved, turned, still seen, alive); D full TU on the next turn; E walks reached their cell; F the mode against an attack already on the table; G calculated chance against the result; H two fighters and one target over the player's turn.
Battles are clusters: each share is given with the range over battles (10th and 90th percentile)."""
import gzip
import io
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
A = Path("E:/OXCE_AIWorker/battles_archive/side_turn_scheduler_pilot_2026-10-30/res_scpa.zip")
KV = re.compile(r"(\w+)=([^ ]*)")
POS = re.compile(r"\((-?\d+),(-?\d+),(-?\d+)\)")


def kv(s):
    return dict(KV.findall(s))


def tup(p):
    m = POS.match(p or "")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def d2(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def pct(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, int(q * len(v)))] if v else 0


class Share:
    """A share over all cases, and its spread over battles."""

    def __init__(self):
        self.by = defaultdict(lambda: [0, 0])

    def add(self, battle, yes):
        self.by[battle][0] += 1 if yes else 0
        self.by[battle][1] += 1

    def text(self):
        y = sum(a for a, _ in self.by.values())
        n = sum(b for _, b in self.by.values())
        sh = [100 * a / b for a, b in self.by.values() if b >= 5]
        return f"{y}/{n} = {100 * y / n:.1f}% (battles {len(sh)} with 5+: p10 {pct(sh, .1):.0f}, p90 {pct(sh, .9):.0f})" if n else "0/0"


def dist_bin(x):
    if x is None:
        return "none seen"
    return "<=5" if x <= 5 else "6-10" if x <= 10 else "11-20" if x <= 20 else ">20"


army = Counter()
zf = zipfile.ZipFile(A)
names = sorted(n for n in zf.namelist() if n.endswith("log.gz") and "scpa_D_" in n)
surv_seen = defaultdict(Share)
surv_legal = defaultdict(Share)
surv_cross = defaultdict(Share)
surv_all = Share()
cell_old = Share()
cell_new = Share()
t_moved = defaultdict(Share)
t_stats = defaultdict(lambda: Counter())
t_seen_next = defaultdict(Share)
t_alive = defaultdict(Share)
t_dir = defaultdict(Share)
tu_full = Share()
tu_full_hit = Share()
walk = defaultdict(Share)
walk_why = Counter()
mode_all = Counter()
attack_taken = Share()
attack_taken_mode = Counter()
evaluated = Share()
calib = defaultdict(Share)
pair_alive = Share()
pair_alive_exp = []
pair_full = Share()
pair_tgt = Share()
turns_seen = Counter()
deaths_side = Counter()
for n in names:
    battle = re.search(r"scpa_D_(\w+)/", n).group(1)
    L = [x.split("\t")[-1] for x in gzip.open(io.BytesIO(zf.read(n)), "rt", encoding="utf-8", errors="replace").read().split("\n")]
    pstart = defaultdict(dict)
    aistart = defaultdict(dict)
    out = defaultdict(dict)
    for s in L:
        if s.startswith("[AISTATE] pstart"):
            k = kv(s)
            pstart[int(k["turn"])][k["unit"]] = k
        elif s.startswith("[AISTATE] aistart"):
            k = kv(s)
            aistart[int(k["turn"])][k["unit"]] = k
        elif s.startswith("[AICASUALTY]"):
            k = kv(s)
            if k.get("how") in ("dead", "stun"):
                out[k["victim"]].setdefault((int(k["turn"]), int(k.get("side", -1))), k)
    last = max(aistart) if aistart else 0
    # was a unit put out inside this player's turn (side 0 of that turn)
    downed = lambda u, t: (t, 0) in out.get(u, {})
    cells_ok = {}
    for t in sorted(pstart):
        P = pstart[t]
        if t not in aistart:
            continue  # the battle ended in this player's turn
        seen_pl = [k for k in P.values() if k["faction"] == "0" and int(k["status"]) < 6 and int(k.get("seenby", 0)) > 0]
        ai = [k for k in P.values() if k["faction"] == "1" and int(k["status"]) < 6]
        for k in ai:
            u = k["unit"]
            dead = downed(u, t)
            sb = int(k.get("seenby", 0))
            at = tup(k["pos"])
            near = min((d2(at, tup(e["pos"])) for e in seen_pl), default=None)
            surv_all.add(battle, dead)
            surv_seen["0" if sb == 0 else "1" if sb == 1 else "2+"].add(battle, dead)
            surv_legal[dist_bin(near)].add(battle, dead)
            surv_cross[("seenby 0" if sb == 0 else "seenby 1+", dist_bin(near))].add(battle, dead)
            # a cell somebody already stood on through an earlier player's turn in this battle and was not put out
            (cell_old if at in cells_ok else cell_new).add(battle, dead)
            if not dead:
                cells_ok[at] = True
            if not dead and u in aistart[t]:
                b = aistart[t][u]
                full = b["tu"] == b.get("tumax")
                tu_full.add(battle, full)
                if b["hp"] != k["hp"]:
                    tu_full_hit.add(battle, full)
        # the target: a player's unit the side sees at the end of its turn, and over the player's turn
        for k in seen_pl:
            u = k["unit"]
            big = "tank" if k.get("type", "").startswith(("STR_TANK", "AUX_TANK", "TANK")) or u in () else "other"
            cls = k.get("type", "?")
            size = "vehicle" if "SOLDIER" not in cls else "soldier"
            t_alive[size].add(battle, not downed(u, t))
            if downed(u, t) or u not in aistart[t]:
                continue
            b = aistart[t][u]
            dist = d2(tup(k["pos"]), tup(b["pos"]))
            t_moved[size].add(battle, dist >= 3)
            t_stats[size]["same" if dist == 0 else "1-2" if dist <= 2 else "3-5" if dist <= 5 else "6-10" if dist <= 10 else ">10"] += 1
            t_seen_next[size].add(battle, int(b.get("seenby", 0)) > 0)
            t_dir[size].add(battle, b.get("dir") != k.get("dir"))
        # two AI fighters within 3 cells of each other, a player's unit seen within 15 of the first
        ids = sorted(ai, key=lambda k: int(k["unit"]))
        for i, a in enumerate(ids):
            ap = tup(a["pos"])
            tgt = [e for e in seen_pl if d2(ap, tup(e["pos"])) <= 15]
            if not tgt:
                continue
            tgt = min(tgt, key=lambda e: d2(ap, tup(e["pos"])))
            for b in ids[i + 1:]:
                if d2(ap, tup(b["pos"])) > 3:
                    continue
                al = not downed(a["unit"], t) and not downed(b["unit"], t)
                pair_alive.add(battle, al)
                ok_tgt = not downed(tgt["unit"], t) and tgt["unit"] in aistart[t] and int(aistart[t][tgt["unit"]].get("seenby", 0)) > 0
                full = al and all(x["unit"] in aistart[t] and aistart[t][x["unit"]]["tu"] == aistart[t][x["unit"]].get("tumax") for x in (a, b))
                pair_full.add(battle, full)
                pair_tgt.add(battle, full and ok_tgt)
    # the whole army, turn by turn: which unit-turns had any enemy in the unit's sight, any attack, or only walking
    ut = defaultdict(lambda: {"seen": False, "attack": False, "walk": False, "n": 0, "modes": set()})
    for s in L:
        if s.startswith("[AIDECIDE]"):
            k = kv(s)
            if k.get("side") != "1":
                continue
            x = ut[(k["turn"], k["unit"])]
            x["n"] += 1
            x["modes"].add(k["mode"])
            x["seen"] = x["seen"] or k.get("seen", "-") not in ("-", "")
            x["attack"] = x["attack"] or int(k["act"]) in (6, 7, 8, 9, 10, 12, 13, 14)
            x["walk"] = x["walk"] or int(k["act"]) == 2
    for x in ut.values():
        army["unit-turns"] += 1
        army["side saw no enemy (seen= is the side's list, not the unit's)"] += not x["seen"]
        army["attacked"] += x["attack"]
        army["only patrol mode"] += x["modes"] == {"0"}
    # decisions: what the unit chose against what was on the table
    rec = {}
    cand = {}
    dec = None
    for s in L:
        if s.startswith("[AICAND]"):
            m = re.match(r"\[AICAND\] acts=(\w+) unit=(\d+) list=(.*)", s)
            if m:
                try:
                    cand[m.group(1)] = {c["id"]: c for c in json.loads(m.group(3))}
                except ValueError:
                    pass
        elif s.startswith("[AIDECIDE]"):
            dec = kv(s)
        elif s.startswith("[AIREC]"):
            try:
                j = json.loads(s[8:])
            except ValueError:
                continue
            if j.get("side") == 1 and dec:
                rec[j["rec"]] = (dec, j)
        elif s.startswith("[AIEXEC]"):
            try:
                e = json.loads(s[9:])
            except ValueError:
                continue
            if e.get("rec") not in rec:
                continue
            d, j = rec[e["rec"]]
            act = int(d["act"])
            base = j.get("base") or {}
            props = (base.get("reason") or {}).get("props") or []
            mode = d["mode"]
            mode_all[mode] += 1
            attack_on_table = any(p.get("t") in (6, 7, 8, 9, 10, 12, 13, 14) for p in props)
            charge_on_table = any(p.get("s") == "x" and str(p.get("src", "")).startswith("melee") for p in props)
            if attack_on_table or charge_on_table:
                took = act in (6, 7, 8, 9, 10, 12, 13, 14) or (act == 2 and str(base.get("src", "")).startswith("melee"))
                attack_taken.add(battle, took)
                attack_taken_mode["attack" if took else f"other mode{mode} act{act}"] += 1
            if act == 2 and d.get("to") and d["from"] != d["to"]:
                to = tup(d["to"])
                done = tuple(e.get("pos") or ()) == to
                walk[f"mode{mode}"].add(battle, done)
                walk["all"].add(battle, done)
                if not done:
                    walk_why["no step" if e.get("spent", 0) == 0 else "spotted something" if e.get("seen") or e.get("spotted") else "hit on the way" if e.get("hp_lost") else "other stop"] += 1
            if act in (7, 8, 9, 10):
                acts = (j.get("cand") or {}).get("acts")
                c = cand.get(acts, {}).get(base.get("id"))
                if c and "p" in c:
                    p = c["p"]
                    b = "0-19" if p < 20 else "20-39" if p < 40 else "40-59" if p < 60 else "60-79" if p < 80 else "80+"
                    calib[("melee" if act == 10 else "fire", b)].add(battle, e.get("dmg", 0) > 0 or e.get("stunned", 0) > 0)
print("battles:", len(names))
print("I. the army by unit-turns:", army.most_common())
print("A. put out (dead or stunned) inside the player's turn, of AI units alive at the end of the AI's turn")
print("   all:", surv_all.text())
for k in ("0", "1", "2+"):
    print("   hidden fact, player's units seeing it (seenby) at that moment", k, surv_seen[k].text())
for k in ("<=5", "6-10", "11-20", ">20", "none seen"):
    print("   legal, distance to the nearest player's unit the side sees", k, surv_legal[k].text())
for k in sorted(surv_cross):
    print("   ", k, surv_cross[k].text())
print("B. cell someone already stood on through an earlier player's turn and was not put out, this battle:", cell_old.text())
print("   cell nobody had yet:", cell_new.text())
print("C. player's unit the side sees at the end of its turn, over the player's turn")
for s in t_moved:
    print("  ", s, "alive after it:", t_alive[s].text(), "| moved 3+ cells:", t_moved[s].text(), "| still seen at the AI's start:", t_seen_next[s].text(), "| direction changed:", t_dir[s].text(), "| moved:", dict(t_stats[s]))
print("D. full TU at the AI's start, of AI units that lived through the player's turn:", tu_full.text(), "| of those hit in it:", tu_full_hit.text())
print("E. walk reached its cell in one decision")
for k in sorted(walk):
    print("  ", k, walk[k].text())
print("   stops:", walk_why.most_common())
print("F. modes of AI decisions:", mode_all.most_common(), "| attack or charge on the table, taken:", attack_taken.text())
print("   instead:", attack_taken_mode.most_common(12))
print("G. p of [AICAND] (BattleUnit::getFiringAccuracy: the shooter's accuracy, no distance, no armour, not a chance to hit) of the chosen attack, against the action doing any damage or stun to the other side")
for k in sorted(calib):
    print("  ", k, calib[k].text())
print("H. two AI fighters within 3 cells, a player's unit seen within 15 of the first: pair over the player's turn")
print("   both still in the fight:", pair_alive.text())
print("   and both with full TU:", pair_full.text())
print("   and the target alive and seen at the AI's start:", pair_tgt.text())
