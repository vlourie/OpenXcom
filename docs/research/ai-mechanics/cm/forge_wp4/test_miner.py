"""The miner against what already exists: the archives, the logs of WP3, and made-up rows. No battle is run here. py -3.13 test_miner.py"""
import gzip
import json
import math
import random
import re
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import AIForgeOpportunityMiner as M

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
fails = 0


def check(name, ok, detail=""):
    global fails
    fails += 0 if ok else 1
    print(("ok   " if ok else "FAIL ") + name + (f": {detail}" if detail != "" else ""))


with gzip.open(HERE / "opportunities.jsonl.gz", "rt", encoding="utf-8") as f:
    OPS = [json.loads(s) for s in f]
PTS = M.load_points()

# 1. the decisions and the engine's list
check("d = rec + 1 at every opportunity", all(o["d"] == o["rec"] + 1 for o in OPS), len(OPS))
check("the alternative is not the action D0 chose", all((o["new"], o["new_to"], o["new_weapon"]) != (o["from"], o["to"], o["weapon"]) for o in OPS))
check("every alternative leaves the margin", all(o["tu_new"] + M.MARGIN <= o["tu"] for o in OPS))
check("every enemy decision is a unit of the enemy", all(o["unit"] >= M.PLAYER_BELOW and o["target"] < M.PLAYER_BELOW and o["new_unit"] < M.PLAYER_BELOW for o in OPS))
fams = {o["family"]: 0 for o in OPS}
for o in OPS:
    fams[o["family"]] += 1
check("family T: same weapon, same mode, closer by the gap", all(o["new"] == o["from"] and o["new_weapon"] == o["weapon"] and o["new_unit"] != o["target"] and o["dist"] >= M.T_FAR and o["new_dist"] <= o["dist"] - M.T_GAP for o in OPS if o["family"] == "T"), fams)
check("family P: mind control of the same target", all(o["new"] == M.MC and o["new_unit"] == o["target"] for o in OPS if o["family"] == "P"))
check("family M: a real melee weapon on the same target", all(o["new"] == M.HIT and o["new_unit"] == o["target"] and o["new_weapon"] != o["weapon"] for o in OPS if o["family"] == "M"))

# 2. the rules read only what stood before the decision: a log cut off right after the decision's record gives the same point
p = PTS["T1"]
label, lines, _ = M.read_archive(p["zip"], p["label"].split("_D_")[0], p["scen"], p["k"])
cut = next(i for i, s in enumerate(lines) if "[AIREC] " in s and json.loads(s[s.index("{"):])["rec"] == p["rec"])
_, ops = M.scan_battle(p["zip"], p["label"].split("_D_")[0], p["scen"], p["k"], lines[:cut + 1])
found = [o for o in ops if o["family"] == "T" and o["rec"] == p["rec"]]
check("a log with nothing after the decision gives the same point", found and {k: found[0][k] for k in p if k != "slot"} == {k: p[k] for k in p if k != "slot"})
_, ops_full = M.scan_battle(p["zip"], p["label"].split("_D_")[0], p["scen"], p["k"], lines)
tampered = [("0" if s.startswith(("[AIEXEC]", "[AIAFTER]", "[AIRESULT]", "[AICASUALTY]")) else s) for s in lines]
_, ops_t = M.scan_battle(p["zip"], p["label"].split("_D_")[0], p["scen"], p["k"], tampered)
check("the outcome lines do not matter to the scan", ops_full == ops_t, len(ops_t))

# 3. selection
shuffled = OPS[:]
random.Random(7).shuffle(shuffled)
a, b = M.choose_points(OPS), M.choose_points(shuffled)
check("selection does not depend on the order of the file", a == b)
check("POINTS.json is the rule's output", a == PTS)
check("L8 s1 is left out", all((x["scen"], x["k"]) != M.FORBIDDEN_BATTLE for x in PTS.values()))
main = [s for s in PTS if not s.endswith("R")]
check("no battle stands twice among the slots", len({(PTS[s]["scen"], PTS[s]["k"]) for s in main}) == len(main), len(main))
check("a slot's reserve is another battle or at least another unit", all((PTS[s]["k"], PTS[s]["unit"]) != (PTS[s + "R"]["k"], PTS[s + "R"]["unit"]) for s in main))
check("eight slots at least: six exploration and two for each family's validation", all(s in PTS for s in M.EXPLORE) and all(s in PTS for v in M.VALIDATE.values() for s in v))
for family, slots in M.VALIDATE.items():
    exp = {(PTS[s]["scen"], PTS[s]["k"]) for s in M.FAMILY_SLOTS[family]}
    check(f"validation of {family}: other battles", not exp & {(PTS[s]["scen"], PTS[s]["k"]) for s in slots}, [PTS[s]["scen"] for s in slots])

# 4. the arms
arms = M.all_arms(PTS)
x = [a for a, s in arms.items() if s["slot"] in M.EXPLORE and s["i"] > 0]
check("72 exploration runs", len(x) == 72, len(x))
check("a branch's flags", all(("OXCE_AI_FORGE_BRANCH_MODE=act" in s["env"] and "OXCE_AI_FORGE_BRANCH_STOPSIDE=1" in s["env"]) for s in arms.values() if s["env"]))
a1 = arms["Z4P1A1"]["env"]
b1 = arms["Z4P1B1"]["env"]
pp = PTS["P1"]
check("A keeps think()'s action", f"OXCE_AI_FORGE_BRANCH_TYPE={pp['from']}" in a1 and f"OXCE_AI_FORGE_BRANCH_NEWWEAPON={pp['weapon']}" in a1 and f"OXCE_AI_FORGE_BRANCH_NEWUNIT={pp['target']}" in a1)
check("B takes the alternative", f"OXCE_AI_FORGE_BRANCH_TYPE={pp['new']}" in b1 and f"OXCE_AI_FORGE_BRANCH_NEWWEAPON={pp['new_weapon']}" in b1 and f"OXCE_AI_FORGE_BRANCH_NEWUNIT={pp['new_unit']}" in b1)
check("A and B differ only in the action", {e for e in a1 if not e.startswith(("OXCE_AI_FORGE_BRANCH_TYPE", "OXCE_AI_FORGE_BRANCH_NEW"))} == {e for e in b1 if not e.startswith(("OXCE_AI_FORGE_BRANCH_TYPE", "OXCE_AI_FORGE_BRANCH_NEW"))})
check("pair i has one seed, the pairs differ", arms["Z4P1A3"]["seed"] == arms["Z4P1B3"]["seed"] != arms["Z4P1A4"]["seed"])
check("the same seed list on every exploration point, another on validation", arms["Z4T1A2"]["seed"] == arms["Z4M2B2"]["seed"] != arms["Z4TV1A2"]["seed"])
check("OFF sets nothing", arms["Z4O"]["env"] == [])
check("the control seed is on no point", M.K1 not in M.EXPLORE_SEEDS + M.VALIDATE_SEEDS)
check("run s: one run under its own prefix", [a for a, s in arms.items() if s["prefix"] == "f4sT1"] == ["Z4T1B1"])
check("run x: the other eleven", len([a for a, s in arms.items() if s["prefix"] == "f4xT1"]) == 11)
names = [a for a, s in arms.items() if s["prefix"] == "f4xT1"]
check("fit_pairs: all if it fits", sorted(M.fit_pairs(names, "T1", 11)) == sorted(names))
check("fit_pairs: whole pairs only", M.fit_pairs(names, "T1", 4) == ["Z4T1A1", "Z4T1A2", "Z4T1B2"])
check("fit_pairs: nothing left", M.fit_pairs(names, "T1", 0) == [])
blk = M.block(arms)
check("the block of arms is python and holds each arm once", len(re.findall(r'^ARMS\["', blk, re.M)) == len(arms))
ns = {"ARMS": {}, "COMMON_D0": []}
exec(blk, ns)
check("env of the arms round-trips", ns["ARMS"]["Z4T1B4"][1] == arms["Z4T1B4"]["env"] and ns["ARMS"]["Z4T1B4"][0] == "env_F4.txt")

# 5. the signal
t = M.tally([0, 0, 5, 5, 3, 3], [1, 1, 1, 9, 3, 4])
check("tally", (t["better"], t["worse"], t["equal"]) == (4, 1, 1), t)
check("tally with direction", (lambda r: (r["better"], r["worse"]))(M.tally([0, 0, 5], [1, 1, 1], -1)) == (1, 2))
check("point +", M.point_signal({"better": 4, "worse": 1}) and not M.point_signal({"better": 4, "worse": 2}) and not M.point_signal({"better": 3, "worse": 0}))
check("family: 7 of 12, at most 2 worse, more better than worse in each", M.family_signal({"better": 4, "worse": 1}, {"better": 3, "worse": 1}))
check("family: 6 better is not enough", not M.family_signal({"better": 3, "worse": 0}, {"better": 3, "worse": 0}))
check("family: 3 worse is too many", not M.family_signal({"better": 4, "worse": 1}, {"better": 3, "worse": 2}))
check("family: one point alone cannot carry it", not M.family_signal({"better": 6, "worse": 0}, {"better": 1, "worse": 1}))


def series(good, guard_bad=0):
    out = {}
    for h in M.HORIZONS:
        for m, _ in M.EFFECTS:
            out[h, m] = ([0] * 6, [1] * good + [0] * (6 - good))
    for h, m, _ in M.GUARD_METRICS:
        out[h, m] = ([0] * 6, [1] * guard_bad + [0] * (6 - guard_bad))
    return out


sig, pts = M.signals_of({"T1": series(5), "T2": series(4)}, ("T1", "T2"))
check("a clean effect passes on every effect metric", len(sig) == 10 and "T1" in pts, len(sig))
sig, _ = M.signals_of({"T1": series(5, 3), "T2": series(4, 3)}, ("T1", "T2"))
check("the same effect with own losses in six pairs does not pass", sig == [])
sig, _ = M.signals_of({"T1": series(5), "T2": series(0)}, ("T1", "T2"))
check("on one map alone it does not pass", sig == [])

# the exact false rate of the rule under no difference, by the chance that a pair differs each way
def rate(q, n1=6, n2=6):
    def dist(n):
        return {(b, w): math.comb(n, b) * math.comb(n - b, w) * q ** (b + w) * (1 - 2 * q) ** (n - b - w) for b in range(n + 1) for w in range(n + 1 - b)}
    d1, d2 = dist(n1), dist(n2)
    return sum(p1 * p2 for (b1, w1), p1 in d1.items() for (b2, w2), p2 in d2.items() if M.family_signal({"better": b1, "worse": w1}, {"better": b2, "worse": w2}))


rates = {q: rate(q) for q in (0.05, 0.1, 0.2, 0.25, 0.3, 0.4, 0.45)}
print("false rate per metric and family, no difference, q = chance of each way:", {k: round(v, 5) for k, v in rates.items()})
check("the rule stays rare at any q", max(rates.values()) < 0.05, round(max(rates.values()), 5))

# 6. the numbers from rows
mk = lambda u, **kw: f"u={u} " + " ".join(f"{k}={v}" for k, v in {"fac": 0, "ofac": 0, "st": 0, "tu": 50, "en": 50, "hp": 40, "stun": 0, "mor": 80, "mana": 30, "fire": 0, "wounds": 0, "ammo": 5, "armor": "10,10,10,10,10", **kw}.items())
before = [mk(1), mk(2), mk(1000001, fac=1, ofac=1), mk(1000002, fac=1, ofac=1), mk(1000003, fac=2, ofac=2), "tiles_changed=0 objects=0 fire_now=0 fire_new=0 smoke_now=0 smoke_new=0 light_only=0"]
after = [mk(1, fac=1, mor=60), mk(2, hp=30, armor="10,8,10,10,10", wounds=1, st=7, stun=35), mk(1000001, fac=1, ofac=1, tu=20, en=45, ammo=4, hp=38, mor=70), mk(1000002, fac=1, ofac=1, hp=-1, st=6), mk(1000003, fac=2, ofac=2, hp=25), mk(7, fac=0, ofac=0), "tiles_changed=4 objects=2 fire_now=1 fire_new=1 smoke_now=0 smoke_new=3 light_only=1"]
h = M.horizon_metrics(before, after, 1000001, 2, 1)
want = {"player_hp_lost": 10, "player_armor_lost": 2, "player_stun_gain": 35, "player_morale_loss": 20, "player_wounds_gain": 1, "player_controlled_new": 1, "player_out_new": 1, "player_unconscious_new": 1, "player_dead_new": 0, "player_new_units": 1,
        "hostile_hp_lost": 42, "hostile_out_new": 1, "hostile_dead_new": 1, "own_hp_lost": 40, "own_out_new": 1, "actor_hp_lost": 2, "actor_morale_lost": 10, "actor_out_new": 0, "tu_spent": 30, "energy_spent": 5, "ammo_spent": 1, "neutral_hp_lost": 15, "target_hp_lost": 10, "alt_target_controlled_new": 1, "alt_target_morale_loss": 20, "objects": 2, "fire_new": 1, "smoke_new": 3}
bad = {k: (h.get(k), v) for k, v in want.items() if h.get(k) != v}
check("metrics of made-up rows", not bad, bad)

# 7. the runs of WP3 as fixtures of the reading only; no new experiment
F3 = HERE.parent / "forge3" / "res"
with zipfile.ZipFile(F3 / "res_f3p.zip") as z:
    labs = sorted({m.group(1) for n in z.namelist() for m in [re.search(r"out/([^/]+)/openxcom\.log\.gz", n)] if m})
print("fixtures", labs[:4], len(labs))
ra = M.Run(labs[0], M.sic.read_log(F3 / "res_f3p.zip", labs[0]), (F3 / "res_f3p.zip", labs[0]))
rb = M.Run(labs[1], M.sic.read_log(F3 / "res_f3p.zip", labs[1]), (F3 / "res_f3p.zip", labs[1]))
pre = dict(ra.phase("pre"))
fix = {"d": 49, "rec": 48, "unit": int(pre.get("unit", 0)) or None, "target": None, "new_unit": None, "from": int(pre["type"]), "turn": None, "to": [int(v) for v in pre["to"].split(",")]}
check("a real log: the dumps by name", bool(M.dump_of(ra, "intervene")) and bool(M.dump_of(ra, "after_branch")), [r[:60] for r in M.dump_of(ra, "intervene")[:1]])
check("a real log: the action follows its decision", M.act_index(ra.events(), 49) is not None)
check("a run is identical to itself", M.same_run(ra, ra)["verdict"] == "IDENTICAL")
check("two seeds are not identical", M.same_run(ra, rb)["verdict"] == "DIFFERENT")
arch = M.archive_run({"zip": str(M.A / "side_first_v0/res/res_sfF.zip"), "label": "sfF_D_L8_s1"})
capped = M.archive_run({"zip": str(M.A / "commander_2026-10-29/res_csd.zip"), "label": "csd_D_L8_s1"})
check("another turn cap in the archive is caught", not M.prefix_check(ra, capped)["same"])
check("every point runs under its archive's cap, and the horizon fits under it", all(x["cap"] in (8, 60) and x["turn"] < x["cap"] for x in PTS.values()), sorted({(x["scen"], x["k"], x["cap"]) for x in PTS.values() if x["cap"] != 60}))
check("the arm carries the cap", arms["Z4P1A1"]["cap"] == PTS["P1"]["cap"] and arms["Z4K1"]["cap"] == PTS["P1"]["cap"] and arms["Z4O"]["cap"] == PTS["T1"]["cap"])
px = M.prefix_check(ra, arch)
check("a real log: the prefix is the archive's", px["same"], px["lines"])
broken = M.Run("x", ra.lines, ra.source)
broken.game = broken.game[:]
broken.game[10] = "changed"
check("a changed line in the prefix is found", not M.prefix_check(broken, arch)["same"])
check("post_types reads the first to=", M.post_types(ra)[0] == str(fix["from"]), M.post_types(ra))
fr = M.follow_up(ra, {"rec": 48, "unit": next((json.loads(s[s.index("{"):])["unit"] for s in ra.lines if "[AIREC] " in s and '"rec":48,' in s), 0), "turn": next((json.loads(s[s.index("{"):])["turn"] for s in ra.lines if "[AIREC] " in s and '"rec":48,' in s), 0)})
check("a real log: what the actor could do next and the action's own record", fr["exec_spent"] is not None and fr["exec_dmg"] is not None, fr)
# the check of a run, on a WP3 log: only its exe folder and its missing next_side can be other than expected
M.frozen = lambda: {"exe_sha256": M.prov_fields(ra)["exe_sha256"]}
seed = int(ra.phase("reseed")["seed"])
fp = {"d": 49, "rec": 48, "unit": 1000006, "turn": 1, "target": 324, "new_unit": 324, "from": 7, "new": 7, "to": [12, 17, 0]}
cr = M.check_run(ra, {"branch": "A", "seed": seed}, fp, arch)
check("check_run on a real log: only the exe folder", len(cr["defects"]) == 1 and cr["defects"][0].startswith("exe "), cr["defects"])
cr2 = M.check_run(ra, {"branch": "A", "seed": seed + 1}, fp, arch)
check("check_run: another seed is a defect", any("reseed" in d for d in cr2["defects"]))
cr3 = M.check_run(ra, {"branch": "A", "seed": seed}, {**fp, "from": 8}, arch)
check("check_run: another action of think() is a defect", any("think() chose" in d for d in cr3["defects"]))
cr4 = M.check_run(ra, {"branch": "B", "seed": seed}, fp | {"new": 13}, arch)
check("check_run: an action not carried out is a defect", any("post" in d for d in cr4["defects"]))
rm = M.run_metrics(ra, fp)
check("run_metrics: horizons of a real log", all(rm[h] for h in ("h1", "r0", "hn")) and "tu_spent" in rm["h1"] and "reactions" in rm["h1"], {k: rm["h1"].get(k) for k in ("tu_spent", "ammo_spent", "player_armor_lost", "fire_new", "reactions", "follow_same_turn", "follow_tu", "follow_attacks", "exec_spent")})
pc = M.pair_check(ra, rb, fp)
check("pair_check: two seeds with one state before the action", pc["defects"] == [], pc["defects"])
# a refused run is an answer, not a defect
refused = M.Run("r", ["[FORGE] n=5 h=ab rng=cd t=1 s=1 ev=VIOLATION kind=branch_refused why=no_line_of_fire unit=1"], None)
check("the reason of a refusal", M.refused_by(refused) == "no_line_of_fire")

# 8. the frozen rules of the plan
check("the budget", M.BUDGET == {"c": 4, "x": 72, "v": 24} and sum(M.BUDGET.values()) == 100)
print("FAILS", fails)
sys.exit(1 if fails else 0)
