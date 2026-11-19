"""AI FORGE WP3: the oracle's arithmetic and readers, on fixed numbers and on WP2.1's real logs, before a single new run."""
import math
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import AIForgeStochasticOracle as o

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
fails = 0
count = 0


def check(name, ok, info=""):
    global fails, count
    count += 1
    if not ok:
        fails += 1
        print("FAIL", name, info)


def near(a, b, eps=1e-3):
    return abs(a - b) <= eps


# seeds: from fixed text, all different, none zero
check("seeds count", len(o.SEEDS) == 24 and len(set(o.SEEDS)) == 24)
check("seeds repeat", o.seed_of("experiment", 1) == o.SEEDS[0])
check("controls apart", o.K1 not in o.SEEDS and o.K2 not in o.SEEDS and o.K1 != o.K2)
check("budget", sum(len(v) for v in o.BATCH.values()) == 54 and o.BUDGET == 54)
check("pairs share a seed", all(o.ARMS[f"Z3A{i:02d}"][1] == o.ARMS[f"Z3B{i:02d}"][1] for i in range(1, 25)))
check("modes", all(o.ARMS[f"Z3A{i:02d}"][0] == 7 and o.ARMS[f"Z3B{i:02d}"][0] == 8 for i in range(1, 25)))
check("half is half", len(o.BATCH["p"]) == 24 and len(o.BATCH["q"]) == 24 and not set(o.BATCH["p"]) & set(o.BATCH["q"]))
check("labels", o.label_of("Z3A13") == "f3q_Z3A13_L8_s1" and o.label_of("Z3B12") == "f3p_Z3B12_L8_s1" and o.label_of("Z3O") == "f3c_Z3O_L8_s1")

# the arms' block for run_cm: it must run as Python and give each arm its seed
space = {"COMMON_D0": ["c"], "ARMS": {}}
exec(o.block(), space)
check("block arms", set(space["ARMS"]) == set(o.ARMS))
check("block seed", any(f"OXCE_AI_FORGE_RESEED={o.SEEDS[23]}" == x for x in space["ARMS"]["Z3B24"][1]) and "OXCE_AI_FORGE_BRANCH_TYPE=8" in space["ARMS"]["Z3B24"][1])
check("block off", space["ARMS"]["Z3O"][1] == [] and space["ARMS"]["Z3O"][0] == "env_F3.txt")
check("block state", f"OXCE_AI_FORGE_BRANCH_STATE={o.REF_STATE}" in space["ARMS"]["Z3A01"][1] and f"OXCE_AI_FORGE_BRANCH_CHAIN={o.REF_CHAIN}" in space["ARMS"]["Z3A01"][1])

# the statistics
xa = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
xb = [2, 2, 5, 4, 8, 6, 7, 9, 9, 13, 11, 12]
d = o.describe(xa, xb, 1, random.Random(1), True)
ds = [b - a for a, b in zip(xa, xb)]
check("mean diff", near(d["diff"], sum(ds) / 12))
check("sd", near(d["sd_a"], math.sqrt(13.0)))
sd = math.sqrt(sum((x - sum(ds) / 12) ** 2 for x in ds) / 11)
check("t interval", near(d["ci95_t"][1] - d["ci95_t"][0], 2 * 2.2010 * sd / math.sqrt(12)))
check("shares", d["b_better"] == 5 and d["b_worse"] == 0 and d["equal"] == 7, d)
check("less is better", o.describe(xa, xb, -1, random.Random(1))["b_better"] == 0)
check("no direction", o.describe(xa, xb, None, random.Random(1))["b_better"] is None)
check("no spread", o.describe([1] * 12, [3] * 12, 1, random.Random(1))["ci95_t"] is None and o.describe([1] * 12, [3] * 12, 1, random.Random(1))["ci95_bootstrap"] is None)
check("no spread diff", o.describe([1] * 12, [3] * 12, 1, random.Random(1))["diff"] == 2)
same = o.describe(xa, xa, 1, random.Random(1), True)
check("A/A equal", same["diff"] == 0 and same["p_sign_flip"] == 1.0 and same["equal"] == 12)
check("paired beats independent when they move together", same["se_paired"] == 0 and same["se_independent"] > 0)
check("correlation one", near(same["correlation"], 1.0))
check("sign flip strong", o.sign_flip_p([5] * 24, random.Random(1)) < 0.001)
check("sign flip null", o.sign_flip_p([1, -1] * 12, random.Random(1)) > 0.9)
# all same sign on 12: exact two-sided p = 2 / 2^12
check("sign flip exact", abs(o.sign_flip_p([3] * 12, random.Random(2)) - 2 / 4096) < 0.0005)
h = o.holm({"a": 0.01, "b": 0.04, "c": 0.03})
check("holm", near(h["a"], 0.03) and near(h["c"], 0.06) and near(h["b"], 0.06), h)
check("holm caps", o.holm({"a": 0.9, "b": 0.9})["a"] == 1.0)

# a unit's change
a = {"hp": "50", "armor": "10,10,10,10,10", "stun": "0", "mor": "90", "wounds": "0", "fire": "0", "st": "0"}
b = {"hp": "40", "armor": "8,10,10,10,10", "stun": "3", "mor": "80", "wounds": "1", "fire": "2", "st": "0"}
c = o.unit_change(a, b)
check("unit change", c == {"hp_lost": 10, "armor_lost": 2, "stun_gain": 3, "morale_loss": 10, "wounds_gain": 1, "burning_new": 1, "dead_new": 0, "unconscious_new": 0, "out_new": 0}, c)
check("dead by status", o.unit_change(a, dict(b, st="6"))["dead_new"] == 1 and o.unit_change(a, dict(b, st="6"))["out_new"] == 1)
check("dead by hp", o.unit_change(a, dict(b, hp="-3"))["hp_lost"] == 50 and o.unit_change(a, dict(b, hp="-3"))["dead_new"] == 1)
check("stun over hp", o.unit_change(a, dict(b, stun="45"))["unconscious_new"] == 1 and o.unit_change(a, dict(b, stun="45"))["dead_new"] == 0)
check("dead already", o.unit_change(dict(a, st="6", hp="0"), dict(a, st="6", hp="0"))["out_new"] == 0)
check("healing does not count", o.unit_change(b, a)["hp_lost"] == 0)

# the horizon on rows: by the side at the start, a mind control does not move a unit across
row = "u={u} type=T fac={f} ofac={of} st=0 pos=1,1,0 tu={tu} hp={hp} stun=0 mor=100 fire=0 wounds=0 right=W ammo={am} armor={ar} vis=-"
before = [row.format(u=1000006, f=1, of=1, tu=98, hp=66, am=24, ar="45,45,45,45,45"), row.format(u=324, f=0, of=0, tu=50, hp=52, am=1, ar="79,79,79,79,79"), row.format(u=91, f=0, of=0, tu=50, hp=20, am=1, ar="5,5,5,5,5"), row.format(u=1000001, f=1, of=1, tu=50, hp=30, am=1, ar="5,5,5,5,5")]
after = [row.format(u=1000006, f=1, of=1, tu=67, hp=66, am=21, ar="45,45,45,45,45"), row.format(u=324, f=0, of=0, tu=50, hp=52, am=1, ar="79,77,79,79,79"), row.format(u=91, f=1, of=0, tu=50, hp=15, am=1, ar="5,5,5,5,5"), row.format(u=1000001, f=1, of=1, tu=50, hp=25, am=1, ar="5,5,5,5,5"), "tile=7,21,0 was=1 now=2", "tiles_changed=2827 objects=1 fire_now=1 fire_new=1 smoke_now=1 smoke_new=1 light_only=2800"]
m = o.horizon_metrics(before, after)
check("tu and ammo", m["tu_spent"] == 31 and m["ammo_spent"] == 3, m)
check("target", m["target_armor_lost"] == 2 and m["target_hp_lost"] == 0, m)
check("player by start side", m["player_hp_lost"] == 5 and m["hostile_hp_lost"] == 5, m)
check("own without the actor", m["own_hp_lost"] == 5 and m["actor_hp_lost"] == 0, m)
check("tiles", m["objects"] == 1 and m["fire_new"] == 1 and m["light_only"] == 2800 and m["tiles_changed"] == 2827, m)
check("new unit", o.horizon_metrics(before, after + [row.format(u=1000040, f=1, of=1, tu=1, hp=1, am=1, ar="1,1,1,1,1")])["hostile_new_units"] == 1)

# the real logs of WP2.1: the readers against what its report says
A1, B1 = o.Run("wp21A", o.ARCHIVE_WP21_A1), o.Run("wp21B", (o.S / "forge21" / "res" / "res_fxB1.zip", "fxB1_YB_L8_s1"))
ma, mb = o.run_metrics(A1), o.run_metrics(B1)
check("A1 tu, ammo", ma["h1"]["tu_spent"] == 31 and ma["h1"]["ammo_spent"] == 3, ma["h1"])
check("B1 tu, ammo", mb["h1"]["tu_spent"] == 23 and mb["h1"]["ammo_spent"] == 1, mb["h1"])
check("A1 target", ma["h1"]["target_armor_lost"] == 2 and ma["h1"]["target_hp_lost"] == 0, ma["h1"])
check("B1 target", mb["h1"]["target_armor_lost"] == 2 and mb["h1"]["target_hp_lost"] == 0, mb["h1"])
check("A1 tiles changed", ma["h1"]["tiles_changed"] == 0 or ma["h1"]["tiles_changed"] == 2827, ma["h1"]["tiles_changed"])
check("act index", o.act_index(A1.events()) == o.PREFIX_EVENTS and o.act_index(B1.events()) == o.PREFIX_EVENTS)
check("prefix lines", len(A1.game_before(A1.events()[o.PREFIX_EVENTS][0])) == o.PREFIX_GAME)
pre = A1.phase("pre")
check("reference state", pre.get("chain") == o.REF_CHAIN and pre.get("state") == o.REF_STATE and pre.get("rng") == o.REF_RNG, pre)
check("same_run of a run with itself", o.same_run(A1, A1)["verdict"] == "IDENTICAL")
check("same_run A against B", o.same_run(A1, B1)["verdict"] == "DIFFERENT")
c = o.coupling(A1, B1)
check("coupling fields", set(c["act_fields_differ"]) == {"type"}, c)
check("coupling in step", c["events_in_step"] >= 1, c)
check("pair check of WP2.1", not o.pair_check(A1, B1)["defects"], o.pair_check(A1, B1))
check("different seeds on A, B would show", o.different_seeds(A1, B1)["same_course"] is False)
# added after the first check of batch c: the two readers it showed wrong, on real lines
check("prov by lines", o.prov_fields(A1).get("exe_sha256") == "3015ae0e32b1326ae6571727753a74acd00184101cf88bf78eeb7a4cf3ab7db1" and o.prov_fields(A1).get("exe_path", "").endswith(".exe") and "\\exe\\FX\\" in o.prov_fields(A1).get("exe_path", ""), o.prov_fields(A1))
check("post modes", o.post_modes(B1) == ("7", "8") and o.post_modes(A1) == ("7", "7"), (o.post_modes(A1), o.post_modes(B1)))
print(f"{count} checks, FAILS {fails}")
print("coupling on WP2.1", c)
print("A1 h1", {k: v for k, v in ma["h1"].items() if v})
print("B1 h1", {k: v for k, v in mb["h1"].items() if v})
sys.exit(1 if fails else 0)
