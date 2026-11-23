"""AI FORGE WP4: Natural Tactical Opportunity Miner. Finds, in archived D0 battles, the decisions where the engine's own list offered another legal attack; plays them through the arena; compares what each did.
ARCHIVE -> engine's own candidates -> families -> points by rules fixed in advance -> REPLAY to the decision -> full think() -> the same action or the alternative -> game RNG := seed of the pair -> engine -> dumps -> no single score.
Offline only: nothing here or in the arena is a part of the living AI.

  scan                   every archived D0 decision: the alternatives by family -> SCAN.json, opportunities.jsonl.gz; no battle
  select                 the points by the plan's rules -> POINTS.json; never reads what followed a decision
  seeds                  the seeds, from fixed text
  up                     exe F4, env, the arms to rabota, hashes compared
  freeze                 exe, monitor, this file, plan, points, seeds -> FROZEN.txt; every run refuses anything else
  run c                  the controls (4 runs)
  run s <slot>           the first alternative of an exploration point: is it legal (1 run)
  run x <slot>           the rest of an exploration point (11 runs, or 12 if its first was not run)
  check <batch>          the checks of a batch -> check_<batch>.json
  gate                   the exploration points -> GATE.json: a repeating signal or none
  run v <family>         the validation points of the family the gate named; refused without a gate
  analyze                everything -> WP4_RUNS.jsonl, WP4_RESULTS.json, WP4_TABLES.md

Normalised, and only these, as in WP2, WP2.1, WP3: [AIRESULT] ms=, [AIREUSE] fallback_us=."""
import collections
import gzip
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import scheduler_integrity_check as sic

S = HERE.parent
ST = S / "cm" / "st"
RES = HERE / "res"
LEDGER = HERE / "ledger.tsv"
FROZEN = HERE / "FROZEN.txt"
POINTS = HERE / "POINTS.json"
GATE = HERE / "GATE.json"
BUDGET = {"c": 4, "x": 72, "v": 24}
KEY = os.path.expanduser("~/.ssh/oxce_worker")
HOST = "user@100.93.184.94"
R = "C:\\OXCE_AIWorker\\cmrun"
X = "openxcom" ".exe"
EXE = HERE / "b-x" / "bin" / X
SEEDLESS = 20261106
A = Path("E:/OXCE_AIWorker/battles_archive")
SOURCES = [A / "commander_2026-10-29/res_csd.zip", A / "commander_2026-10-29/res_d0p.zip", A / "side_first_v0/res/res_sfF.zip"]
TURN_CAP = re.compile(r"turn cap (\d+)")
LAB = re.compile(r"out/([A-Za-z0-9]+)_D_([A-Z]+\d+)_s(\d+)/openxcom\.log\.gz")
D0_EXE = "0ff1e0f791906adb"
SHOT = {7, 8, 9}
THROW, HIT, MC, PANIC, WALK = 6, 10, 13, 14, 2
ATTACK = {6, 7, 8, 9, 10, 12, 13, 14}
TYPE_NAME = {0: "none", 2: "walk", 6: "throw", 7: "auto", 8: "snap", 9: "aimed", 10: "melee", 12: "launch", 13: "mind", 14: "panic", 15: "rethink"}
PLAYER_BELOW = 1000000
DEAD, UNCONSCIOUS = 6, 7
NORMALISED = {"[AIRESULT] ms=": re.compile(r" ms=\d+"), "[AIREUSE] fallback_us=": re.compile(r" fallback_us=\d+")}
# the rules of the plan, written before any point is known
MARGIN = 8           # time units left over the alternative's cost: a turn towards the new target can cost some
T_FAR, T_GAP = 20, 10
FORBIDDEN_BATTLE = ("L8", 1)  # GO: no more experiments on L8 s1 decision 49; the whole battle is left out
EXPLORE = {"T1": ("T", "M3"), "T2": ("T", "M8"), "P1": ("P", "L8"), "P2": ("P", "L9"), "M1": ("M", "L4"), "M2": ("M", "M10")}
FAMILY_SLOTS = {"T": ("T1", "T2"), "P": ("P1", "P2"), "M": ("M1", "M2")}
VALIDATE = {"T": ("TV1", "TV2"), "P": ("PV1", "PV2"), "M": ("MV1", "MV2")}
PAIRS = 6
JOBS = 12


def seed_of(kind, i):
    """From fixed text; 0 would stop the generator for good."""
    v = int.from_bytes(hashlib.sha256(f"AI FORGE WP4 {kind} {i}".encode()).digest()[:8], "big")
    assert v != 0
    return v


K1 = seed_of("control", 1)
EXPLORE_SEEDS = [seed_of("exploration", i) for i in range(1, PAIRS + 1)]
VALIDATE_SEEDS = [seed_of("validation", i) for i in range(1, PAIRS + 1)]
assert len({K1, *EXPLORE_SEEDS, *VALIDATE_SEEDS}) == 1 + 2 * PAIRS


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


# the archive


def archived_battles():
    """(zip, prefix, scen, seed), each battle once."""
    seen = set()
    for src in SOURCES:
        with zipfile.ZipFile(src) as z:
            names = z.namelist()
        for n in names:
            m = LAB.search(n)
            if m and (m[2], int(m[3])) not in seen:
                seen.add((m[2], int(m[3])))
                yield src, m[1], m[2], int(m[3])


def read_archive(src, prefix, scen, seed):
    label = f"{prefix}_D_{scen}_s{seed}"
    with zipfile.ZipFile(src) as z:
        text = gzip.decompress(z.read(f"out/{label}/openxcom.log.gz")).decode("utf-8", "replace").splitlines()
        prov = z.read(f"arena/{label}.prov.txt").decode("utf-8", "replace")
    return label, text, prov


def candidates_and_records(lines):
    """The engine's lists stand once under their hash, the records of the decisions refer to them. The record of a decision says nothing of what followed it."""
    acts, recs = {}, []
    for s in lines:
        if "[AICAND] acts=" in s:
            acts[s[s.index("acts=") + 5:].split(" ", 1)[0]] = json.loads(s[s.index("list=") + 5:])
        elif "[AIREC] " in s:
            recs.append(json.loads(s[s.index("{"):]))
    return acts, recs


def legal_attacks(cands, tu):
    return [c for c in cands if c["k"] == "a" and c["lof"] == 1 and 0 < c["tu"] <= tu]


def family_of(c, base, chosen):
    """What sort of alternative a legal attack is to what think() chose."""
    if base["t"] not in ATTACK:
        return "attack_vs_" + TYPE_NAME.get(base["t"], str(base["t"]))
    if c["t"] in (MC, PANIC) and base["t"] not in (MC, PANIC):
        return "psi"
    if c["t"] == HIT and base["t"] != HIT:
        return "melee"
    if c["t"] == THROW and base["t"] != THROW:
        return "throw"
    if c.get("u") != (chosen.get("u") if chosen else None):
        return "target_same_mode" if c["t"] == base["t"] and c["w"] == base["w"] else "target_other_mode"
    if c["w"] != base["w"]:
        return "weapon"
    return "mode"


# the rules of the three families; every argument is what stood before the decision


def eligible(rec, chosen):
    """D0 shoots at a player's unit, the record found it in the engine's list with a line of fire, and nothing had touched the generator."""
    b = rec["base"]
    return (rec["side"] == 1 and rec["unit"] >= PLAYER_BELOW and b["t"] in SHOT and b.get("tk") == "enemy" and b.get("in") == 1 and rec["cand"]["rng"] == 0
            and chosen is not None and chosen["lof"] == 1 and chosen.get("u", PLAYER_BELOW) < PLAYER_BELOW)


def alternative(family, rec, cands, chosen):
    """The family's alternative, or None."""
    tu = rec["state"]["tu"]
    usable = [c for c in cands if c["k"] == "a" and c["lof"] == 1 and c.get("u", PLAYER_BELOW) < PLAYER_BELOW and 0 < c["tu"] and c["tu"] + MARGIN <= tu]
    if family == "T":
        if chosen["d"] < T_FAR:
            return None
        xs = [c for c in usable if c["t"] == chosen["t"] and c["w"] == chosen["w"] and c["u"] != chosen["u"] and c["d"] <= chosen["d"] - T_GAP]
        return min(xs, key=lambda c: (c["d"], c["u"])) if xs else None
    if family == "P":
        xs = [c for c in usable if c["t"] == MC and c["u"] == chosen["u"]]
    elif family == "M":
        xs = [c for c in usable if c["t"] == HIT and c["u"] == chosen["u"] and c["w"] != chosen["w"]]
    else:
        raise ValueError(family)
    return min(xs, key=lambda c: (c["tu"], c["w"])) if xs else None


def point_of(family, src, prefix, scen, seed, cap, d, rec, chosen, alt):
    return {"family": family, "zip": str(src), "label": f"{prefix}_D_{scen}_s{seed}", "scen": scen, "k": seed, "cap": cap, "d": d, "rec": rec["rec"], "turn": rec["turn"], "unit": rec["unit"], "n": rec["n"], "tu": rec["state"]["tu"], "kneel": rec["state"]["kneel"],
            "from": chosen["t"], "to": chosen["to"], "weapon": chosen["w"], "target": chosen["u"], "dist": chosen["d"], "tu_from": chosen["tu"], "aim_from": chosen["p"],
            "new": alt["t"], "new_to": alt["to"], "new_weapon": alt["w"], "new_unit": alt["u"], "new_dist": alt["d"], "tu_new": alt["tu"], "aim_new": alt["p"]}


def scan_battle(src, prefix, scen, seed, lines=None):
    """One battle: every hostile decision with its alternatives by family; the opportunities of the three families."""
    label, text, prov = (None, lines, None) if lines is not None else read_archive(src, prefix, scen, seed)
    acts, recs = candidates_and_records(text)
    cap = next((int(m[1]) for m in map(TURN_CAP.search, text) if m), 0)
    tally = collections.Counter()
    per_unit = collections.defaultdict(set)
    walks = collections.Counter()
    base_types = collections.Counter()
    opportunities = []
    rng_touched = 0
    for i, r in enumerate(recs):
        if r["side"] != 1 or r["unit"] < PLAYER_BELOW:
            continue
        d = i + 1  # the monitor's decision: every decision of every side has one record, in order
        b = r["base"]
        base_types[TYPE_NAME.get(b["t"], str(b["t"]))] += 1
        rng_touched += r["cand"]["rng"] != 0
        cands = acts.get(r["cand"]["acts"], [])
        chosen = next((c for c in cands if c["id"] == b["id"]), None)
        fams = set()
        for c in legal_attacks(cands, r["state"]["tu"]):
            if c["id"] != b["id"] and c.get("u", PLAYER_BELOW) < PLAYER_BELOW:
                fams.add(family_of(c, b, chosen))
        for f in fams:
            tally[f] += 1
            per_unit[f].add(r["unit"])
        if "attack_vs_walk" in fams:
            walks[b["src"] or "-"] += 1
        if eligible(r, chosen) and r["turn"] < cap:  # the side's next turn exists under the archive's cap
            tally["D0_shot_at_player"] += 1
            for family in FAMILY_SLOTS:
                alt = alternative(family, r, cands, chosen)
                if alt:
                    opportunities.append(point_of(family, src, prefix, scen, seed, cap, d, r, chosen, alt))
    return {"scen": scen, "seed": seed, "cap": cap, "decisions": sum(base_types.values()), "last_turn": recs[-1]["turn"] if recs else 0, "rng_touched": rng_touched, "base": dict(base_types), "tally": dict(tally), "units": {k: len(v) for k, v in per_unit.items()}, "walks": dict(walks),
            "exe": re.search(r"exe_sha256=(\w+)", prov)[1] if prov else None, "data": re.search(r"data=(\w+)", prov)[1] if prov else None}, opportunities


def cmd_scan():
    battles, all_ops = [], []
    for src, prefix, scen, seed in archived_battles():
        b, ops = scan_battle(src, prefix, scen, seed)
        battles.append(b)
        all_ops += ops
    with gzip.open(HERE / "opportunities.jsonl.gz", "wt", encoding="utf-8") as f:
        for o in all_ops:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")
    total = collections.Counter()
    by_mission = collections.defaultdict(collections.Counter)
    walks = collections.Counter()
    for b in battles:
        total.update(b["tally"])
        walks.update(b["walks"])
        by_mission[b["scen"]].update(b["tally"])
    fam = collections.defaultdict(collections.Counter)
    units = collections.defaultdict(set)
    for o in all_ops:
        fam[o["family"]][o["scen"]] += 1
        units[o["family"], o["scen"]].add((o["k"], o["unit"]))
    out = {"battles": len(battles), "decisions": sum(b["decisions"] for b in battles), "rng_touched": sum(b["rng_touched"] for b in battles), "exes": collections.Counter(b["exe"] for b in battles), "data": collections.Counter(b["data"] for b in battles),
           "with_alternative": dict(total), "by_mission": {k: dict(v) for k, v in by_mission.items()}, "walks_with_a_legal_attack_by_source": dict(walks.most_common()),
           "families": {k: {"decisions": dict(sorted(v.items())), "units": {s: len(units[k, s]) for s in sorted(v)}} for k, v in fam.items()}, "battle_list": battles}
    (HERE / "SCAN.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8-sig")
    print("battles", out["battles"], "decisions", out["decisions"], "rng", out["rng_touched"], "exes", dict(out["exes"]), "data", dict(out["data"]))
    print(json.dumps(out["with_alternative"], ensure_ascii=False))
    print(json.dumps(out["families"], ensure_ascii=False))


# the points: by the plan's rules alone


def order_key(o):
    return hashlib.sha256(f"AI FORGE WP4 point|{o['family']}|{o['scen']}|{o['k']}|{o['rec']}".encode()).hexdigest()


def choose_points(ops):
    """Exploration slots first, each in its named mission; the validation slots in the missions with the most distinct units left. One battle serves one slot, its reserve another battle if there is one."""
    ops = [o for o in ops if (o["scen"], o["k"]) != FORBIDDEN_BATTLE]
    used = set()
    out = {}

    def take(slot, family, scen):
        xs = sorted((o for o in ops if o["family"] == family and o["scen"] == scen and (o["scen"], o["k"]) not in used), key=order_key)
        if not xs:
            return False
        first = xs[0]
        used.add((first["scen"], first["k"]))
        out[slot] = {**first, "slot": slot}
        others = [o for o in xs if (o["k"], o["unit"]) != (first["k"], first["unit"])]
        other_battle = [o for o in others if o["k"] != first["k"]]
        reserve = (other_battle or others or [None])[0]
        if reserve:
            used.add((reserve["scen"], reserve["k"]))
            out[slot + "R"] = {**reserve, "slot": slot + "R"}
        return True

    for slot, (family, scen) in EXPLORE.items():
        if not take(slot, family, scen):
            raise SystemExit(f"{slot}: no point in {scen}")
    for family, slots in VALIDATE.items():
        spent = {EXPLORE[s][1] for s in FAMILY_SLOTS[family]}
        missions = collections.defaultdict(set)
        for o in ops:
            if o["family"] == family and (o["scen"], o["k"]) not in used:
                missions[o["scen"]].add((o["k"], o["unit"]))
        ranked = sorted(missions, key=lambda m: (m in spent, -len(missions[m]), m))
        done = 0
        for m in ranked:
            if done == len(slots):
                break
            if take(slots[done], family, m):
                done += 1
        if done < len(slots):
            print(f"{family}: {done} of {len(slots)} validation slots", file=sys.stderr)
    return out


def cmd_select():
    if FROZEN.exists():
        raise SystemExit("frozen")
    with gzip.open(HERE / "opportunities.jsonl.gz", "rt", encoding="utf-8") as f:
        ops = [json.loads(s) for s in f]
    pts = choose_points(ops)
    POINTS.write_text(json.dumps(pts, ensure_ascii=False, indent=1), encoding="utf-8-sig")
    for k, p in pts.items():
        print(k, p["family"], p["scen"], f"s{p['k']}", "d", p["d"], "turn", p["turn"], "unit", p["unit"], "tu", p["tu"], TYPE_NAME[p["from"]], p["weapon"], "at", p["target"], "dist", p["dist"], "tu", p["tu_from"], "->", TYPE_NAME[p["new"]], p["new_weapon"], "at", p["new_unit"], "dist", p["new_dist"], "tu", p["tu_new"])


def load_points():
    return json.loads(POINTS.read_text(encoding="utf-8-sig"))


# the arms


def xyz(p):
    return f"{p[0]}.{p[1]}.{p[2]}"


def arm_env(p, branch, seed):
    """Both branches take the same path: the action, checked, and the seed. A keeps what think() chose."""
    new = {"A": (p["from"], p["to"], p["weapon"], p["target"]), "B": (p["new"], p["new_to"], p["new_weapon"], p["new_unit"])}[branch]
    return ["OXCE_AI_FORGE=1", f"OXCE_AI_FORGE_SEEDLESS={SEEDLESS}", f"OXCE_AI_FORGE_BRANCH_AT={p['d']}", f"OXCE_AI_FORGE_BRANCH_UNIT={p['unit']}", f"OXCE_AI_FORGE_BRANCH_FROM={p['from']}", f"OXCE_AI_FORGE_BRANCH_TO={xyz(p['to'])}", f"OXCE_AI_FORGE_BRANCH_WEAPON={p['weapon']}",
            "OXCE_AI_FORGE_BRANCH_MODE=act", "OXCE_AI_FORGE_BRANCH_STOPSIDE=1", f"OXCE_AI_FORGE_BRANCH_TYPE={new[0]}", f"OXCE_AI_FORGE_BRANCH_NEWTO={xyz(new[1])}", f"OXCE_AI_FORGE_BRANCH_NEWWEAPON={new[2]}", f"OXCE_AI_FORGE_BRANCH_NEWUNIT={new[3]}", f"OXCE_AI_FORGE_RESEED={seed}"]


def slot_seeds(slot):
    return VALIDATE_SEEDS if "V" in slot else EXPLORE_SEEDS


def all_arms(points):
    """arm -> what it is."""
    out = {}
    for slot, p in points.items():
        for i, s in enumerate(slot_seeds(slot), 1):
            for b in "AB":
                prefix = f"f4v{slot}" if "V" in slot else (f"f4s{slot}" if (b, i) == ("B", 1) else f"f4x{slot}")
                out[f"Z4{slot}{b}{i}"] = {"slot": slot, "branch": b, "i": i, "seed": s, "scen": p["scen"], "k": p["k"], "prefix": prefix, "cap": p["cap"], "env": arm_env(p, b, s)}
    p1, m1, t1 = points["P1"], points["M1"], points["T1"]
    out["Z4O"] = {"slot": "T1", "branch": None, "i": 0, "seed": None, "scen": t1["scen"], "k": t1["k"], "prefix": "f4c1", "cap": t1["cap"], "env": []}
    for n, p, prefix, slot in (("Z4K1", p1, "f4c2", "P1"), ("Z4K2", p1, "f4c2", "P1"), ("Z4K3", m1, "f4c3", "M1")):
        out[n] = {"slot": slot, "branch": "B", "i": 0, "seed": K1, "scen": p["scen"], "k": p["k"], "prefix": prefix, "cap": p["cap"], "env": arm_env(p, "B", K1)}
    return out


def label_of(arm, spec):
    return f"{spec['prefix']}_{arm}_{spec['scen']}_s{spec['k']}"


def zip_of(spec):
    return RES / f"res_{spec['prefix']}.zip"


# the logs


def normal(s):
    for head, pattern in NORMALISED.items():
        if s.startswith(head.split(" ")[0]):
            return pattern.sub("", s)
    return s


class Run:
    """One log, by kind of line."""

    def __init__(self, name, lines, source=None):
        self.name = name
        self.source = source
        self.lines = lines
        self.game, self.raw, self.forge, self.time, self.branch, self.legal = [], [], [], [], [], []
        self.dumps = {}
        self.at_pre = None
        for i, s in enumerate(lines):
            if s.startswith("[FORGE] "):
                self.forge.append(s)
            elif s.startswith("[FORGEDUMP] "):
                m = re.match(r"\[FORGEDUMP\] at=(\d+) (.*)", s)
                self.dumps.setdefault(int(m.group(1)), []).append(m.group(2))
            elif s.startswith("[FORGETIME] "):
                self.time.append(s)
            elif s.startswith("[FORGEBRANCH] "):
                self.branch.append(s)
                if " phase=pre " in s and self.at_pre is None:
                    self.at_pre = len(self.game)
            elif s.startswith("[FORGELEGAL] "):
                self.legal.append(s)
            elif s.startswith("[AI"):
                self.game.append(normal(s))
                self.raw.append(s)

    def events(self):
        out = []
        for s in self.forge:
            m = sic.LINE.match(s)
            out.append((int(m.group(1)), m.group(2), m.group(3), dict(sic.KV.findall(m.group(3)))))
        return out

    def result(self):
        s = next((x for x in self.lines if x.startswith("[AIRESULT]")), "")
        return dict(sic.KV.findall(s))

    def phase(self, name):
        s = next((x for x in self.branch if f" phase={name} " in x), "")
        return dict(sic.KV.findall(s))

    def clock(self, at):
        s = next((x for x in self.time if f"at={at} " in x), "")
        d = dict(sic.KV.findall(s))
        return int(d["battle_real_ms"]) if "battle_real_ms" in d else None


def run_of(arm, spec):
    return Run(arm, sic.read_log(zip_of(spec), label_of(arm, spec)), (zip_of(spec), label_of(arm, spec)))


def archive_run(p):
    return Run("arch", sic.read_log(p["zip"], p["label"]), (p["zip"], p["label"]))


def one_dump(rows):
    """Dumps are kept by the event number, and two can share one: only the first of them."""
    return rows[:next((i for i, r in enumerate(rows) if i and r.startswith("why=")), len(rows))]


def dump_of(run, why):
    return one_dump(next((rows[i:] for rows in run.dumps.values() for i, r in enumerate(rows) if r.startswith(f"why={why}")), []))


def unit_rows(rows):
    out = {}
    for r in rows:
        m = re.match(r"u=(\d+) ", r)
        if m:
            out[m.group(1)] = dict(sic.KV.findall(r))
    return out


def number(d, key):
    return int(d.get(key, 0))


def armor_sum(d):
    return sum(int(x) for x in d.get("armor", "0").split(","))


def is_dead(d):
    return number(d, "st") == DEAD or number(d, "hp") <= 0


def is_unconscious(d):
    return not is_dead(d) and (number(d, "st") == UNCONSCIOUS or number(d, "stun") >= number(d, "hp"))


def is_controlled(d):
    return d.get("fac") != d.get("ofac") and not is_dead(d)


def unit_change(a, b):
    """One unit from the intervention to a horizon; what it gained back does not cancel what another lost."""
    return {"hp_lost": max(0, number(a, "hp") - max(0, number(b, "hp"))), "armor_lost": max(0, armor_sum(a) - armor_sum(b)), "stun_gain": max(0, number(b, "stun") - number(a, "stun")),
            "morale_loss": max(0, number(a, "mor") - number(b, "mor")), "mana_lost": max(0, number(a, "mana") - number(b, "mana")), "wounds_gain": max(0, number(b, "wounds") - number(a, "wounds")),
            "burning_new": int(number(b, "fire") > 0 and number(a, "fire") == 0), "controlled_new": int(is_controlled(b) and not is_controlled(a)),
            "dead_new": int(is_dead(b) and not is_dead(a)), "unconscious_new": int(is_unconscious(b) and not is_unconscious(a) and not is_dead(a)),
            "out_new": int((is_dead(b) or is_unconscious(b)) and not (is_dead(a) or is_unconscious(a)))}


FIELDS = ("hp_lost", "armor_lost", "stun_gain", "morale_loss", "mana_lost", "wounds_gain", "burning_new", "controlled_new", "dead_new", "unconscious_new", "out_new")


def tiles_row(rows):
    r = next((x for x in rows if x.startswith("tiles_changed=")), "")
    return dict(sic.KV.findall(r))


def horizon_metrics(before, after, actor, target, alt_target=None):
    """Relative to the state at the intervention, by the side a unit fought for at the start: the sums are what they say, no weights."""
    ua, ub = unit_rows(before), unit_rows(after)
    out = {}
    for name, fac in (("player", "0"), ("hostile", "1"), ("neutral", "2")):
        total = dict.fromkeys(FIELDS, 0)
        for u, a in ua.items():
            if a.get("ofac", a.get("fac")) == fac and u in ub:
                for k, v in unit_change(a, ub[u]).items():
                    total[k] += v
        for k, v in total.items():
            out[f"{name}_{k}"] = v
        out[f"{name}_new_units"] = sum(1 for u, b in ub.items() if u not in ua and b.get("ofac", b.get("fac")) == fac)
    a = str(actor)
    if a in ua and a in ub:
        change = unit_change(ua[a], ub[a])
        out["actor_hp_lost"] = change["hp_lost"]
        out["actor_morale_lost"] = change["morale_loss"]
        out["actor_mana_lost"] = change["mana_lost"]
        out["actor_out_new"] = change["out_new"]
        for k in FIELDS:
            out[f"own_{k}"] = out[f"hostile_{k}"] - change[k]
        out["tu_spent"] = number(ua[a], "tu") - number(ub[a], "tu")
        out["energy_spent"] = number(ua[a], "en") - number(ub[a], "en")
        out["ammo_spent"] = max(0, number(ua[a], "ammo") - number(ub[a], "ammo"))
    t = str(target)
    if t in ua and t in ub:
        for k, v in unit_change(ua[t], ub[t]).items():
            out[f"target_{k}"] = v
    t = str(alt_target)
    if t in ua and t in ub:
        for k, v in unit_change(ua[t], ub[t]).items():
            out[f"alt_target_{k}"] = v
    tiles = tiles_row(after)
    for k in ("objects", "fire_new", "smoke_new", "fire_now", "smoke_now", "light_only", "tiles_changed"):
        out[k] = int(tiles.get(k, 0))
    return out


def act_index(ev, d):
    for i, (_, _, _, kv) in enumerate(ev):
        if kv.get("ev") == "decide" and kv.get("d") == str(d):
            for j in range(i + 1, len(ev)):
                if ev[j][3].get("ev") == "act":
                    return j
    return None


def follow_up(run, p):
    """What the actor could still do at its next record, as the engine's own list says it; nothing here is a judgement of whether it did well."""
    acts, recs = candidates_and_records(run.lines)
    later = [r for r in recs if r["rec"] > p["rec"] and r["unit"] == p["unit"]]
    out = {"follow_same_turn": 0, "follow_attacks": 0, "follow_tu": 0}
    if later:
        r = later[0]
        out["follow_same_turn"] = int(r["turn"] == p["turn"])
        out["follow_tu"] = r["state"]["tu"] if r["turn"] == p["turn"] else 0
        out["follow_attacks"] = sum(1 for c in legal_attacks(acts.get(r["cand"]["acts"], []), r["state"]["tu"]) if c.get("u", PLAYER_BELOW) < PLAYER_BELOW)
    done = next((json.loads(s[s.index("{"):]) for s in run.lines if s.startswith("[AIEXEC]") and f'"rec":{p["rec"]},' in s), None)
    out["exec_spent"] = done["spent"] if done else None
    out["exec_dmg"] = done["dmg"] if done else None
    return out


def panics(ev, j, last, unit_below=PLAYER_BELOW):
    return sum(1 for k in range(j, last) if ev[k][3].get("ev") == "panic" and int(ev[k][3].get("unit", 0)) < unit_below)


def run_metrics(run, p):
    before = dump_of(run, "intervene")
    h1, r0, hn, end = dump_of(run, "after_branch"), dump_of(run, "round0"), dump_of(run, "next_side"), dump_of(run, "end")
    ev = run.events()
    j = act_index(ev, p["d"])
    out = {}
    for name, rows in (("h1", h1), ("r0", r0 or end), ("hn", hn or end)):
        out[name] = horizon_metrics(before, rows, p["unit"], p["target"], p["new_unit"]) if rows else None
    nxt = next((k for k in range(j + 1, len(ev)) if ev[k][3].get("ev") == "decide"), len(ev)) if j is not None else None
    if out["h1"] is not None and j is not None:
        out["h1"]["reactions"] = sum(1 for k in range(j, nxt) if ev[k][3].get("ev") == "react")
    if out["hn"] is not None and j is not None:
        out["hn"]["player_panics"] = panics(ev, j, len(ev))
        out["hn"]["ended_before"] = int(not hn)
    if out["h1"] is not None:
        out["h1"].update(follow_up(run, p))
    return out


# the checks: any defect is a STOP; a refusal is not a defect, it is the answer for that point


def prov_of(run):
    with zipfile.ZipFile(run.source[0]) as z:
        return z.read(f"arena/{run.source[1]}.prov.txt").decode("utf-8", errors="replace")


def prov_fields(run):
    """Line by line: the pattern of key=value would run on across a line end (R-787)."""
    return dict(x.split("=", 1) for x in prov_of(run).split("effective_env:")[0].splitlines()[1:] if "=" in x)


def post_types(run):
    """The first from= and to= of the line: the action's text after them has a to= of its own, the target (R-787)."""
    m = re.search(r" phase=post from=(\d+) to=(\d+) ", next((x for x in run.branch if " phase=post " in x), ""))
    return (m.group(1), m.group(2)) if m else (None, None)


def frozen():
    return dict(x.split("=", 1) for x in FROZEN.read_text(encoding="utf-8").splitlines() if "=" in x)


def refused_by(run):
    return next((d.get("why") for *_, d in run.events() if d.get("ev") == "VIOLATION" and d.get("kind") == "branch_refused"), None)


def first_difference(xs, ys):
    for i, (x, y) in enumerate(zip(xs, ys)):
        if x != y:
            return {"index": i, "a": x[:600], "b": y[:600]}
    if len(xs) != len(ys):
        k = min(len(xs), len(ys))
        return {"index": k, "a": (xs[k][:600] if len(xs) > k else "<end>"), "b": (ys[k][:600] if len(ys) > k else "<end>")}
    return None


def prefix_check(run, arch):
    """The run's engine lines before the intervention are the archived battle's, line by line. The decision's record is written after the intervention, so the last lines before it must be followed in the archive by it."""
    n = run.at_pre
    if n is None:
        return {"same": False, "lines": 0, "difference": "no phase=pre"}
    diff = first_difference(run.game[:n], arch.game[:n])
    return {"same": diff is None and len(arch.game) > n, "lines": n, "difference": diff}


def check_run(run, spec, p, arch):
    """One run with the arena on: what it must have found and done, whatever its seed."""
    bad = []
    prov = prov_fields(run)
    exe = frozen()["exe_sha256"]
    if prov.get("exe_sha256") != exe or "\\exe\\F4\\" not in prov.get("exe_path", ""):
        bad.append(f"exe {prov.get('exe_sha256')} {prov.get('exe_path')}")
    pre = run.phase("pre")
    if pre.get("type") != str(p["from"]):
        bad.append(f"think() chose {pre.get('type')}")
    if pre.get("to") != ",".join(map(str, p["to"])):
        bad.append(f"think()'s target {pre.get('to')}")
    px = prefix_check(run, arch)
    if not px["same"]:
        bad.append(f"the prefix is not the archive's at {px['difference']}")
    c = sic.check(run.lines)
    why = refused_by(run)
    other = [v for v in c["first_violations"] if v[0] != "branch_refused"]
    if other:
        bad.append(f"violations {other[:3]}")
    if why:
        return {"arm": run.name, "defects": bad, "refused": why, "events": c["events"], "violations": c["violations"], "prefix_lines": px["lines"], "notes": c["notes"]}
    want = (p["from"], p["new"]) if spec["branch"] == "B" else (p["from"], p["from"])
    if post_types(run) != tuple(map(str, want)):
        bad.append(f"post {post_types(run)}, wanted {want}")
    re_ = run.phase("reseed")
    if re_.get("seed") != str(spec["seed"]) or re_.get("now") != f"{spec['seed']:x}":
        bad.append(f"reseed {re_}")
    ev = run.events()
    j = act_index(ev, p["d"])
    if j is None:
        bad.append("no action after the decision")
    else:
        if ev[j][3].get("type") != str(want[1]):
            bad.append(f"carried out type {ev[j][3].get('type')}")
        if ev[j][3].get("rng") != f"{spec['seed']:x}":
            bad.append(f"the action line's rng {ev[j][3].get('rng')} is not the seed")
    if not dump_of(run, "after_branch"):
        bad.append("no dump after the action")
    if not (dump_of(run, "next_side") or dump_of(run, "end")):
        bad.append("no horizon of the side's next turn")
    if not run.result().get("how"):
        bad.append("no result line")
    stop = next((d.get("why") for *_, d in ev if d.get("ev") == "stop"), None)
    if not dump_of(run, "next_side") and stop != "no_decision_of_the_side" and not dump_of(run, "end"):
        bad.append(f"stopped by {stop}")
    return {"arm": run.name, "defects": bad, "refused": None, "events": c["events"], "violations": c["violations"], "prefix_lines": px["lines"], "stop": stop, "tu_kinds": {k: v for k, v in c["counts"].items() if k.startswith("tu")}, "notes": c["notes"], "mechanics": run_metrics(run, p)["h1"]}


def same_run(a, b):
    """Two runs with one seed and one action: to the last event."""
    common = sorted(set(a.dumps) & set(b.dumps))
    out = {"a": a.name, "b": b.name, "forge_events": [len(a.forge), len(b.forge)], "game_lines": [len(a.game), len(b.game)], "chain_identical": a.forge == b.forge, "chain_first_difference": first_difference(a.forge, b.forge),
           "game_identical": a.game == b.game, "game_first_difference": first_difference(a.game, b.game), "dumps_compared": len(common), "dumps_only_one": sorted(set(a.dumps) ^ set(b.dumps)),
           "dump_first_difference": next((first_difference(a.dumps[n], b.dumps[n]) for n in common if a.dumps[n] != b.dumps[n]), None), "branch_lines_equal": a.branch == b.branch, "legal_lines_equal": a.legal == b.legal,
           "raw_differences": sum(1 for x, y in zip(a.raw, b.raw) if x != y) + abs(len(a.raw) - len(b.raw))}
    out["verdict"] = "IDENTICAL" if all((out["chain_identical"], out["game_identical"], out["dump_first_difference"] is None, not out["dumps_only_one"], out["branch_lines_equal"], out["legal_lines_equal"])) else "DIFFERENT"
    return out


def pair_check(a, b, p):
    """One seed, the same point, two actions: everything before the action is one state."""
    bad = []
    ea, eb = a.events(), b.events()
    ja, jb = act_index(ea, p["d"]), act_index(eb, p["d"])
    if a.forge[:ja] != b.forge[:jb]:
        bad.append(f"chain before the action differs {first_difference(a.forge[:ja], b.forge[:jb])}")
    if a.game[:a.at_pre] != b.game[:b.at_pre]:
        bad.append("engine lines before the action differ")
    if dump_of(a, "intervene") != dump_of(b, "intervene"):
        bad.append("dump at the intervention differs")
    if a.phase("pre") != b.phase("pre"):
        bad.append("phase pre differs")
    return {"pair": [a.name, b.name], "defects": bad, "act_a": ea[ja][2][:200], "act_b": eb[jb][2][:200]}


def check_batch(batch, slot=None):
    points = load_points()
    arms = all_arms(points)
    out = {"batch": batch, "slot": slot, "frozen": frozen()}
    defects = []
    if batch == "c":
        off = run_of("Z4O", arms["Z4O"])
        d0 = archive_run(points["T1"])
        out["off_vs_d0"] = {"battle": points["T1"]["label"], "game_lines": [len(off.game), len(d0.game)], "identical": off.game == d0.game, "first_difference": first_difference(off.game, d0.game), "raw_differences": sum(1 for x, y in zip(off.raw, d0.raw) if x != y) + abs(len(off.raw) - len(d0.raw)), "monitor_lines": len(off.forge) + len(off.branch) + sum(len(v) for v in off.dumps.values())}
        prov = prov_fields(off)
        out["off_exe"] = [prov.get("exe_sha256"), prov.get("exe_path")]
        if not out["off_vs_d0"]["identical"] or out["off_vs_d0"]["monitor_lines"]:
            defects.append("OFF is not D0")
        if out["off_exe"][0] != frozen()["exe_sha256"]:
            defects.append("OFF ran another exe")
        out["runs"] = []
        rs = {}
        for name, slot_ in (("Z4K1", "P1"), ("Z4K2", "P1"), ("Z4K3", "M1")):
            rs[name] = run_of(name, arms[name])
            out["runs"].append(check_run(rs[name], arms[name], points[slot_], archive_run(points[slot_])))
        out["AA"] = same_run(rs["Z4K1"], rs["Z4K2"])
        if out["AA"]["verdict"] != "IDENTICAL":
            defects.append("A/A differs")
    elif batch in ("s", "x", "v"):
        p = points[slot]
        names = [a for a, s in arms.items() if s["slot"] == slot and s["branch"] and s["i"] > 0 and (batch != "s" or (s["branch"], s["i"]) == ("B", 1))]
        done = {x[0] for x in ledger()}
        have = [a for a in names if a in done]
        arch = archive_run(p)
        rs = {a: run_of(a, arms[a]) for a in have}
        out["runs"] = [check_run(rs[a], arms[a], p, arch) for a in have]
        if batch != "s":
            out["pairs"] = []
            for i in range(1, PAIRS + 1):
                an, bn = f"Z4{slot}A{i}", f"Z4{slot}B{i}"
                if an in rs and bn in rs and not refused_by(rs[bn]):
                    out["pairs"].append(pair_check(rs[an], rs[bn], p))
            defects += [f"{x['pair']}: {d}" for x in out["pairs"] for d in x["defects"]]
            finals = {a: tuple(r.game[r.at_pre:]) for a, r in rs.items() if a[len(f"Z4{slot}")] == "A"}
            out["distinct_courses_a"] = [len(set(finals.values())), len(finals)]
    defects += [f"{x['arm']}: {d}" for x in out.get("runs", []) for d in x["defects"]]
    out["refused"] = {x["arm"]: x["refused"] for x in out.get("runs", []) if x.get("refused")}
    out["defects"] = defects
    out["verdict"] = "STOP" if defects else "PASS"
    return out


# the signal, by the plan


EFFECTS = [("player_hp_lost", "игрок: HP"), ("player_out_new", "игрок: выбыли"), ("player_stun_gain", "игрок: оглушение"), ("player_morale_loss", "игрок: мораль"), ("player_controlled_new", "игрок: под контролем")]
HORIZONS = ("h1", "hn")
SHOWN_H1 = [("tu_spent", "ОВ действующего"), ("energy_spent", "энергия действующего"), ("ammo_spent", "патроны в правой руке"), ("actor_mana_lost", "мана действующего"), ("actor_morale_lost", "мораль действующего"), ("target_hp_lost", "цель D0: HP"), ("target_armor_lost", "цель D0: броня"), ("alt_target_hp_lost", "цель альтернативы: HP"), ("alt_target_armor_lost", "цель альтернативы: броня"), ("alt_target_morale_loss", "цель альтернативы: мораль"), ("alt_target_controlled_new", "цель альтернативы: под контролем"),
            ("player_hp_lost", "игрок: HP"), ("player_armor_lost", "игрок: броня"), ("player_stun_gain", "игрок: оглушение"), ("player_morale_loss", "игрок: мораль"), ("player_wounds_gain", "игрок: раны"), ("player_burning_new", "игрок: загорелись"), ("player_controlled_new", "игрок: под контролем"), ("player_out_new", "игрок: выбыли"),
            ("own_hp_lost", "свои без действующего: HP"), ("own_out_new", "свои без действующего: выбыли"), ("neutral_hp_lost", "нейтралы: HP"), ("actor_hp_lost", "действующий: HP"), ("reactions", "реакций до следующего решения"), ("follow_same_turn", "действует ещё в этом ходу"), ("follow_tu", "ОВ при следующем решении в ходу"), ("follow_attacks", "законных атак при следующем решении"),
            ("objects", "клетки с изменённым объектом"), ("fire_new", "новые клетки с огнём"), ("smoke_new", "новые клетки с дымом")]
SHOWN_HN = [("player_hp_lost", "игрок: HP"), ("player_armor_lost", "игрок: броня"), ("player_stun_gain", "игрок: оглушение"), ("player_morale_loss", "игрок: мораль"), ("player_wounds_gain", "игрок: раны"), ("player_controlled_new", "игрок: под контролем"), ("player_dead_new", "игрок: погибли"), ("player_out_new", "игрок: выбыли"), ("player_panics", "игрок: паника"),
            ("hostile_hp_lost", "враг: HP"), ("hostile_morale_loss", "враг: мораль"), ("hostile_dead_new", "враг: погибли"), ("hostile_out_new", "враг: выбыли"), ("neutral_hp_lost", "нейтралы: HP"), ("objects", "клетки с изменённым объектом"), ("fire_new", "новые клетки с огнём"), ("smoke_new", "новые клетки с дымом"), ("ended_before", "бой кончился раньше")]


def tally(xa, xb, direction=1):
    """B against A by pairs; direction +1: more of it is better for the side that acts."""
    b = sum((y - x) * direction > 0 for x, y in zip(xa, xb))
    w = sum((y - x) * direction < 0 for x, y in zip(xa, xb))
    return {"better": b, "worse": w, "equal": len(xa) - b - w, "mean_a": sum(xa) / len(xa) if xa else None, "mean_b": sum(xb) / len(xb) if xb else None}


def point_signal(t):
    return t["better"] >= 4 and t["worse"] <= 1


def family_signal(t1, t2):
    """Twelve pairs of two missions: at least 7 better, at most 2 worse, and better than worse in each."""
    return t1["better"] + t2["better"] >= 7 and t1["worse"] + t2["worse"] <= 2 and t1["better"] > t1["worse"] and t2["better"] > t2["worse"]


GUARD_METRICS = [("h1", "own_out_new", -1), ("h1", "own_hp_lost", -1), ("hn", "hostile_out_new", -1), ("hn", "hostile_hp_lost", -1)]


def guards_pass(tables):
    """What the same action must not have cost at the same time, each on its own: tables: (horizon, metric) -> the tally summed over the points, with the direction that is good for the side that acts."""
    return all(tables[h, m]["worse"] - tables[h, m]["better"] <= 2 for h, m, _ in GUARD_METRICS)


def sum_tally(ts):
    return {k: sum(t[k] for t in ts) for k in ("better", "worse", "equal")}


def signals_of(series_by_slot, slots):
    """series_by_slot: slot -> (horizon, metric) -> (xs of A, xs of B). The repeating signals of a family, with what each would have to give up."""
    out = []
    per = {s: {} for s in slots}
    for s in slots:
        for h in HORIZONS:
            for m, _ in EFFECTS:
                per[s][h, m] = tally(*series_by_slot[s][h, m], 1)
        for h, m, d in GUARD_METRICS:
            per[s][h, m] = tally(*series_by_slot[s][h, m], d)
    tables = {k: sum_tally([per[s][k] for s in slots]) for k in per[slots[0]]}
    for h in HORIZONS:
        for m, _ in EFFECTS:
            if family_signal(per[slots[0]][h, m], per[slots[1]][h, m]) and guards_pass(tables):
                out.append({"horizon": h, "metric": m, "better": tables[h, m]["better"], "worse": tables[h, m]["worse"], "equal": tables[h, m]["equal"]})
    points = {s: [{"horizon": h, "metric": m, **per[s][h, m]} for h in HORIZONS for m, _ in EFFECTS if point_signal(per[s][h, m])] for s in slots}
    return out, points


def series_of(records, slot, horizon, metric, branch, seeds=None):
    xs = []
    for i in seeds or range(1, PAIRS + 1):
        r = records.get(f"Z4{slot}{branch}{i}")
        v = (r["metrics"].get(horizon) or {}) if r and not r.get("refused") else {}
        xs.append(v.get(metric, 0))
    return xs


def complete(records, slot):
    return [i for i in range(1, PAIRS + 1) if records.get(f"Z4{slot}A{i}") and records.get(f"Z4{slot}B{i}") and not records[f"Z4{slot}B{i}"].get("refused") and not records[f"Z4{slot}A{i}"].get("refused")]


def build_series(records, slot, flip=None):
    """(horizon, metric) -> (A, B) over the complete pairs. flip: the same branch against itself on the next seed, round the circle: no action differs, whatever shows is the RNG."""
    out = {}
    ids = complete(records, slot)
    metrics = {(h, m) for h in HORIZONS for m, _ in EFFECTS} | {(h, m) for h, m, _ in GUARD_METRICS}
    for h, m in metrics:
        if flip:
            xs = series_of(records, slot, h, m, flip, ids)
            out[h, m] = (xs, xs[1:] + xs[:1])
        else:
            out[h, m] = (series_of(records, slot, h, m, "A", ids), series_of(records, slot, h, m, "B", ids))
    return out


def load_records():
    p = HERE / "WP4_RUNS.jsonl"
    return {r["arm"]: r for r in map(json.loads, p.read_text(encoding="utf-8").splitlines())} if p.exists() else {}


def collect_records():
    points = load_points()
    arms = all_arms(points)
    done = {x[0] for x in ledger()}
    records = {}
    for arm in arms:
        if arm not in done:
            continue
        spec = arms[arm]
        if spec["branch"] is None:
            continue
        p = points[spec["slot"]]
        run = run_of(arm, spec)
        why = refused_by(run)
        res = run.result()
        records[arm] = {"arm": arm, "label": label_of(arm, spec), "slot": spec["slot"], "branch": spec["branch"], "i": spec["i"], "seed": spec["seed"], "refused": why, "metrics": {} if why else run_metrics(run, p), "result": {k: res.get(k) for k in ("how", "turn", "player", "pdead", "pout", "pwounded", "phplost", "hostile", "hdead", "hout", "hleft", "pmoves", "pattacks", "hmoves", "hattacks", "vms")},
                        "stop": next((d.get("why") for *_, d in run.events() if d.get("ev") == "stop"), None), "cost_ms": {"prefix": run.clock("intervene"), "h1": run.clock("after_branch"), "hn": run.clock("next_side"), "end": run.clock("end")}}
    with open(HERE / "WP4_RUNS.jsonl", "w", encoding="utf-8") as f:
        for arm in records:
            f.write(json.dumps(records[arm], ensure_ascii=False) + "\n")
    return records


def standing(records, slot):
    """The slot itself; its reserve if the engine refused the slot's first alternative and the reserve was run."""
    if records.get(f"Z4{slot}B1", {}).get("refused") and records.get(f"Z4{slot}RB1"):
        return slot + "R"
    return slot


def cmd_gate():
    records = collect_records()
    if not any(records.get(f"Z4{s}A1") for s in EXPLORE):
        raise SystemExit("nothing to judge")
    out = {"families": {}, "placebo": {}, "note": "a gate for spending the validation runs, not a claim"}
    best = []
    for family, slots in FAMILY_SLOTS.items():
        slots = tuple(standing(records, s) for s in slots)
        series = {s: build_series(records, s) for s in slots}
        if not all(complete(records, s) for s in slots):
            out["families"][family] = {"signals": [], "points": {}, "pairs": {s: complete(records, s) for s in slots}, "note": "a point has no complete pair"}
            continue
        sig, pts = signals_of(series, slots)
        out["families"][family] = {"signals": sig, "points": pts, "pairs": {s: complete(records, s) for s in slots}}
        best += [{"family": family, **x} for x in sig]
        for flip in "AB":
            ps = {s: build_series(records, s, flip) for s in slots}
            sig_p, pts_p = signals_of(ps, slots)
            out["placebo"][f"{family}.{flip}"] = {"signals": sig_p, "points": pts_p}
    # the horizon of the side's next turn before the action's own; then the widest margin
    best.sort(key=lambda x: (x["horizon"] != "hn", -(x["better"] - x["worse"]), x["family"], x["metric"]))
    out["best"] = best[0] if best else None
    out["placebo_family_signals"] = sum(len(v["signals"]) for v in out["placebo"].values())
    out["placebo_point_signals"] = sum(len(y) for v in out["placebo"].values() for y in v["points"].values())
    out["real_point_signals"] = sum(len(y) for v in out["families"].values() for y in v["points"].values())
    GATE.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8-sig")
    print(json.dumps(out, ensure_ascii=False, indent=1)[:6000])
    return out


def describe_point(records, slot):
    ids = complete(records, slot)
    out = {"pairs": ids, "h1": {}, "hn": {}}
    for key, table in (("h1", SHOWN_H1), ("hn", SHOWN_HN)):
        for m, name in table:
            xa, xb = series_of(records, slot, key, m, "A", ids), series_of(records, slot, key, m, "B", ids)
            ds = [y - x for x, y in zip(xa, xb)]
            out[key][m] = {"name": name, "a": xa, "b": xb, "mean_a": sum(xa) / len(xa) if xa else None, "mean_b": sum(xb) / len(xb) if xb else None, "more": sum(d > 0 for d in ds), "less": sum(d < 0 for d in ds), "same": sum(d == 0 for d in ds)}
    return out


def fmt(x, digits=2):
    if x is None:
        return "—"
    return f"{x:.{digits}f}".replace(".", ",")


def tables_md(out, points):
    t = []
    for slot, v in out["points"].items():
        p = points[slot]
        t += [f"## {slot}: {p['scen']} s{p['k']}, решение {p['d']}, ход {p['turn']}, юнит {p['unit']}", "", f"D0: {TYPE_NAME[p['from']]} {p['weapon']} по {p['target']} (дистанция {p['dist']}, {p['tu_from']} ОВ). Альтернатива: {TYPE_NAME[p['new']]} {p['new_weapon']} по {p['new_unit']} (дистанция {p['new_dist']}, {p['tu_new']} ОВ). ОВ у юнита {p['tu']}. Пар: {len(v['pairs'])}.", ""]
        for key, title in (("h1", "Сразу после действия"), ("hn", "К следующему ходу стороны")):
            t += [f"### {title}", "", "| Показатель | D0 среднее | Альтернатива среднее | Альт. больше / меньше / равно | D0 по парам | Альтернатива по парам |", "|---|---|---|---|---|---|"]
            for m, x in v[key].items():
                t.append(f"| {x['name']} | {fmt(x['mean_a'])} | {fmt(x['mean_b'])} | {x['more']} / {x['less']} / {x['same']} | {' '.join(map(str, x['a']))} | {' '.join(map(str, x['b']))} |")
            t.append("")
    return "\n".join(t) + "\n"


def cmd_analyze():
    points = load_points()
    records = collect_records()
    slots = [s for s in points if complete(records, s)]
    out = {"frozen": frozen(), "seeds": {"control": K1, "exploration": EXPLORE_SEEDS, "validation": VALIDATE_SEEDS}, "ledger": ledger(), "points": {s: describe_point(records, s) for s in slots}, "gate": json.loads(GATE.read_text(encoding="utf-8-sig")) if GATE.exists() else None}
    val = {}
    best = (out["gate"] or {}).get("best")
    if best:
        vs = [standing(records, s) for s in VALIDATE[best["family"]]]
        if all(complete(records, s) for s in vs):
            series = {s: build_series(records, s) for s in vs}
            per = {s: tally(*series[s][best["horizon"], best["metric"]], 1) for s in vs}
            guards = {f"{h}.{m}": sum_tally([tally(*series[s][h, m], d) for s in vs]) for h, m, d in GUARD_METRICS}
            val = {"metric": best["metric"], "horizon": best["horizon"], "per_point": per, "reproduced": family_signal(per[vs[0]], per[vs[1]]), "guards": guards}
    out["validation"] = val
    cost = [r["cost_ms"] for r in records.values()]
    out["cost_ms"] = {k: {"n": len([c[k] for c in cost if c[k] is not None]), "mean": (sum(c[k] for c in cost if c[k] is not None) / max(1, len([c[k] for c in cost if c[k] is not None]))), "max": max([c[k] for c in cost if c[k] is not None] or [0])} for k in ("prefix", "h1", "hn", "end")}
    out["refused"] = {a: r["refused"] for a, r in records.items() if r["refused"]}
    out["stops"] = dict(collections.Counter(r["stop"] for r in records.values()))
    (HERE / "WP4_RESULTS.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8-sig")
    text = tables_md(out, points)
    (HERE / "WP4_TABLES.md").write_text(text, encoding="utf-8-sig")
    print(text[:9000])
    print(json.dumps({k: out[k] for k in ("validation", "refused", "stops", "cost_ms")}, ensure_ascii=False)[:2000])


# the stand


def ssh(cmd):
    return subprocess.run(["ssh", "-o", "ConnectTimeout=15", "-i", KEY, HOST, cmd], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout


def ps(cmd):
    return ssh(f'powershell -NoProfile -ExecutionPolicy Bypass -Command "{cmd}"')


def scp(*args):
    subprocess.check_call(["scp", "-q", "-i", KEY, *args])


def remote_hash(path):
    return ps(f"(Get-FileHash '{path}').Hash").strip().lower()


def cmd_seeds():
    print("control", K1)
    print("exploration", EXPLORE_SEEDS)
    print("validation", VALIDATE_SEEDS)


def block(arms):
    lines = ["# AI FORGE WP4 (GO Vitali 06.11, at most 100 runs): exe F4; Z4O - nothing set; the rest - at a decision the engine's own list holds an alternative for, the same action or that one, the game RNG := the seed of the pair; ends at the side's next turn (offline arena only)"]
    lines.append('ARMS["Z4O"] = ("env_F4.txt", [], COMMON_D0)')
    lines += [f'ARMS["{a}"] = ("env_F4.txt", {s["env"]!r}, COMMON_D0)' for a, s in arms.items() if s["env"]]
    return "\n".join(lines) + "\n"


def cmd_up():
    arms = all_arms(load_points())
    d = ST / "exe" / "F4"
    d.mkdir(parents=True, exist_ok=True)
    h = sha(EXE)
    (d / X).write_bytes(EXE.read_bytes())
    (d / "BUILD_INFO.txt").write_text(f"build_label=cmrun-F4\ngit_commit=07680cadb\nnote=HEAD + al.diff + al3.diff + AI FORGE monitor + WP2.1 arena + WP3 reseed and horizons + WP4 other attacks and next_side (flags only)\nmonitor_sha256={sha(HERE / 'mon' / 'SchedulerIntegrityMonitor.cpp')}\n", encoding="utf-8")
    env = (ST / "env_D0.txt").read_text(encoding="utf-8").replace("/exe/D0/", "/exe/F4/")
    assert "/exe/F4/" in env
    (ST / "env_F4.txt").write_text(env, encoding="utf-8")
    run = (ST / "run_cm.py").read_text(encoding="utf-8")
    # R-773, R-785: an arm name already taken would silently keep the old arm and its exe
    if 'ARMS["Z4O"]' not in run:
        assert '"Z4' not in run, "arm name taken"
        old = "}\nTURNS = 60\n"
        if run.count(old) != 1:
            old = "\nTURNS = 60\n"
        assert run.count(old) == 1
        run = run.replace(old, ("}\n" if old.startswith("}") else "\n") + block(arms) + "TURNS = 60\n")
        (ST / "run_cm.py").write_text(run, encoding="utf-8")
    ssh(f"if not exist {R}\\exe\\F4 mkdir {R}\\exe\\F4")
    scp(str(d / X), str(d / "BUILD_INFO.txt"), f"{HOST}:C:/OXCE_AIWorker/cmrun/exe/F4/")
    scp(str(ST / "env_F4.txt"), str(ST / "run_cm.py"), f"{HOST}:C:/OXCE_AIWorker/cmrun/")
    rh = remote_hash(f"{R}\\exe\\F4\\{X}")
    print("local ", h)
    print("remote", rh, "OK" if rh == h else "DIFFERENT")
    print("run_cm", sha(ST / "run_cm.py") == remote_hash(f"{R}\\run_cm.py"))
    if rh != h:
        raise SystemExit(2)


def cmd_freeze():
    if FROZEN.exists():
        raise SystemExit("already frozen")
    FROZEN.write_text(f"exe_sha256={sha(EXE)}\nfrozen={time.strftime('%Y-%m-%dT%H:%M:%S')}\nmonitor_cpp={sha(HERE / 'mon' / 'SchedulerIntegrityMonitor.cpp')}\nlegal_h={sha(HERE / 'ForgeLegal.h')}\nminer={sha(Path(__file__))}\nrun_cm={sha(ST / 'run_cm.py')}\nplan={sha(HERE / 'WP4_PLAN.md')}\npoints={sha(POINTS)}\nseeds={hashlib.sha256(repr((K1, EXPLORE_SEEDS, VALIDATE_SEEDS)).encode()).hexdigest()}\n", encoding="utf-8")
    print(FROZEN.read_text(encoding="utf-8"))


def ledger():
    if not LEDGER.exists():
        return []
    return [s.split("\t") for s in LEDGER.read_text(encoding="utf-8").splitlines() if s.strip()]


def preflight(names):
    fr = frozen()
    if sha(EXE) != fr["exe_sha256"] or sha(Path(__file__)) != fr["miner"] or sha(POINTS) != fr["points"]:
        raise SystemExit("the exe, the miner or the points are not the frozen ones")
    rh = remote_hash(f"{R}\\exe\\F4\\{X}")
    if rh != fr["exe_sha256"]:
        raise SystemExit(f"exe on rabota {rh}")
    if sha(ST / "run_cm.py") != fr["run_cm"] or remote_hash(f"{R}\\run_cm.py") != fr["run_cm"]:
        raise SystemExit("run_cm differs")
    env_ok = ssh(f"type {R}\\env_F4.txt").replace("/exe/F4/", "/exe/D0/").strip() == (ST / "env_D0.txt").read_text(encoding="utf-8").strip()
    if not env_ok:
        raise SystemExit("env_F4 is not env_D0 with another exe folder")
    text = (ST / "run_cm.py").read_text(encoding="utf-8")
    for arm in names:
        if text.count(f'ARMS["{arm}"] = ("env_F4.txt"') != 1:
            raise SystemExit(f"arm {arm}")
    if ps("(Get-ScheduledTask oxce_cmrun).State").strip() != "Ready":
        raise SystemExit("the task is not Ready")
    if ps("(Get-Process openxcom -ErrorAction SilentlyContinue | Measure-Object).Count").strip() != "0":
        raise SystemExit("a game is running on rabota")


def launch(prefix, names, scen, k, batch, turns):
    fr = frozen()
    done = ledger()
    if any(x[0] in names for x in done):
        raise SystemExit(f"{prefix}: already run")
    used = sum(1 for x in done if x[1] == batch)
    if used + len(names) > BUDGET[batch]:
        raise SystemExit(f"budget of {batch}: {used} + {len(names)} of {BUDGET[batch]}")
    preflight(names)
    with open(LEDGER, "a", encoding="utf-8") as f:
        for arm in names:
            f.write(f"{arm}\t{batch}\t{time.strftime('%Y-%m-%dT%H:%M:%S')}\t{fr['exe_sha256']}\t{scen}\t{k}\t{prefix}\tturns={turns}\n")
    print(f"{prefix}: {len(names)} runs, {batch}: {used + len(names)} of {BUDGET[batch]}", flush=True)
    t0 = time.time()
    ssh(f"powershell -NoProfile -ExecutionPolicy Bypass -File {R}\\cm_launch.ps1 -Jobs {JOBS} -Tag {prefix} -Arms {','.join(names)} -Prefix {prefix} -Turns {turns} -Pairs {scen}:{k}")
    seen = ""
    for _ in range(25):
        seen = ps("Get-Process openxcom -ErrorAction SilentlyContinue | ForEach-Object { $_.Path + ' ' + (Get-FileHash $_.Path).Hash } | Sort-Object -Unique").strip()
        if seen:
            break
        time.sleep(1)
    (HERE / f"process_{prefix}.txt").write_text(seen + "\n", encoding="utf-8")
    print("process", seen, flush=True)
    time.sleep(5)
    while True:
        if ps("(Get-ScheduledTask oxce_cmrun).State").strip() == "Ready":
            break
        if time.time() - t0 > 3000:
            raise SystemExit("still running after 3000 s")
        time.sleep(10)
    print(f"{time.time() - t0:.0f} s", flush=True)
    print(ssh(f"C:\\OXCE_AIWorker\\python\\python.exe -I {R}\\pack_logs.py {R} {prefix} {R}\\res_{prefix}.zip").strip()[:160], flush=True)
    RES.mkdir(exist_ok=True)
    scp(f"{HOST}:C:/OXCE_AIWorker/cmrun/res_{prefix}.zip", f"{HOST}:C:/OXCE_AIWorker/cmrun/logs/run_{prefix}.txt", str(RES))
    print((RES / f"run_{prefix}.txt").read_text(encoding="utf-8", errors="replace")[-240:], flush=True)


def fit_pairs(names, slot, left):
    """The arms of the rest of a point in the order of their pairs, as many as the budget holds: a pair is whole or not there; the first pair has its B already."""
    keep = []
    for i in range(1, PAIRS + 1):
        pair = [a for a in (f"Z4{slot}A{i}", f"Z4{slot}B{i}") if a in names]
        if len(keep) + len(pair) > left:
            break
        keep += pair
    return keep


def cmd_run(batch, slot=None):
    points = load_points()
    arms = all_arms(points)
    if batch == "c":
        for prefix, names in (("f4c1", ["Z4O"]), ("f4c2", ["Z4K1", "Z4K2"]), ("f4c3", ["Z4K3"])):
            launch(prefix, names, arms[names[0]]["scen"], arms[names[0]]["k"], "c", arms[names[0]]["cap"])
        cmd_check("c")
    elif batch == "s":
        p = points[slot]
        launch(f"f4s{slot}", [f"Z4{slot}B1"], p["scen"], p["k"], "x", p["cap"])
        cmd_check("s", slot)
    elif batch == "x":
        p = points[slot]
        done = {x[0] for x in ledger()}
        names = [a for a, s in arms.items() if s["slot"] == slot and s["prefix"] == f"f4x{slot}"]
        if f"Z4{slot}B1" not in done:
            raise SystemExit("the first alternative has not been run")
        kept = fit_pairs(names, slot, BUDGET["x"] - sum(1 for x in ledger() if x[1] == "x"))
        if len(kept) != len(names):
            print(f"{slot}: the budget holds {len(kept)} of {len(names)} runs", flush=True)
        if kept:
            launch(f"f4x{slot}", kept, p["scen"], p["k"], "x", p["cap"])
        cmd_check("x", slot)
    elif batch == "v":
        family = slot
        g = json.loads(GATE.read_text(encoding="utf-8-sig"))
        if not g.get("best") or g["best"]["family"] != family:
            raise SystemExit(f"the gate did not name {family}")
        for s in VALIDATE[family]:
            p = points[s]
            launch(f"f4v{s}", [a for a, x in arms.items() if x["slot"] == s and x["prefix"] == f"f4v{s}"], p["scen"], p["k"], "v", p["cap"])
            cmd_check("v", s)


def cmd_check(batch, slot=None):
    out = check_batch(batch, slot)
    name = f"check_{batch}{slot or ''}.json"
    (HERE / name).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8-sig")
    print(batch, slot, out["verdict"], "refused", out["refused"], json.dumps(out["defects"], ensure_ascii=False)[:1500])
    for k in ("off_vs_d0", "off_exe", "distinct_courses_a"):
        if k in out:
            print(k, json.dumps(out[k], ensure_ascii=False)[:600])
    if "AA" in out:
        print("A/A", out["AA"]["verdict"], out["AA"]["forge_events"], out["AA"]["game_lines"], "dumps", out["AA"]["dumps_compared"], "raw", out["AA"]["raw_differences"], json.dumps(out["AA"]["game_first_difference"], ensure_ascii=False)[:300])
    for x in out.get("runs", []):
        print(x["arm"], "refused", x.get("refused"), "stop", x.get("stop"), "prefix", x.get("prefix_lines"), "violations", x["violations"], "notes", x["notes"], json.dumps({k: v for k, v in (x.get("mechanics") or {}).items() if k in ("tu_spent", "exec_spent", "target_hp_lost", "player_hp_lost", "player_morale_loss", "player_controlled_new", "player_stun_gain", "player_out_new")}))
    if out["verdict"] != "PASS":
        raise SystemExit("STOP")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    a = sys.argv[1:]
    {"scan": cmd_scan, "select": cmd_select, "seeds": cmd_seeds, "up": cmd_up, "freeze": cmd_freeze, "gate": cmd_gate, "analyze": cmd_analyze}.get(a[0], lambda: None)()
    if a[0] == "run":
        cmd_run(a[1], a[2] if len(a) > 2 else None)
    elif a[0] == "check":
        cmd_check(a[1], a[2] if len(a) > 2 else None)


if __name__ == "__main__":
    main()
