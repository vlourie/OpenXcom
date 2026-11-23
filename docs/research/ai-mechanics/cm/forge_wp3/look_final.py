"""AI FORGE WP3: the numbers the report needs beyond the tables: all from the frozen results."""
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
r = json.loads((HERE / "WP3_RESULTS.json").read_text(encoding="utf-8-sig"))
runs = [json.loads(s) for s in (HERE / "WP3_RUNS.jsonl").read_text(encoding="utf-8").splitlines()]
by = {x["arm"]: x for x in runs}
print("verdict", r["verdict_use"], r["signals"], "placebo signals", r["placebo_signals_before_holm"], "of", len(r["placebo"]), "same seed AA", r["same_seed_AA"])
print("coupling steps", sorted(set(r["coupling"]["events_in_step"])), "shared share min, median, max", r["coupling"]["shared_state_share_of_b"][0], r["coupling"]["shared_state_share_of_b"][12], r["coupling"]["shared_state_share_of_b"][-1])
print("independence", r["independence"])
print("cost", r["cost_ms"], "logs MB", r["log_mb_total"])
for m in ("target_armor_lost", "objects", "fire_new", "smoke_new", "ammo_spent", "tu_spent"):
    v = r["h1"][m]
    print("h1", m, "ratio", v.get("variance_ratio_paired_to_independent"), "corr", v["correlation"], "se", v["se_paired"], v["se_independent"], "ci", v["ci95_t"], "more/less/eq", v["b_more"], v["b_less"], v["equal"])
A = [by[f"Z3A{i:02d}"] for i in range(1, 25)]
B = [by[f"Z3B{i:02d}"] for i in range(1, 25)]
for name, xs in (("A", A), ("B", B)):
    h1 = [x["metrics"]["h1"] for x in xs]
    h2 = [x["metrics"]["h2"] for x in xs]
    print(name, "object changed share", sum(h["objects"] > 0 for h in h1), "fire share", sum(h["fire_new"] > 0 for h in h1), "armor>0", sum(h["target_armor_lost"] > 0 for h in h1), "armor values", sorted(h["target_armor_lost"] for h in h1))
    print(" objects", sorted(h["objects"] for h in h1), "fire", sorted(h["fire_new"] for h in h1))
    print(" light_only h1 min/mean/max", min(h["light_only"] for h in h1), sum(h["light_only"] for h in h1) / 24, max(h["light_only"] for h in h1), "tiles", sum(h["tiles_changed"] for h in h1) / 24)
    print(" h2 turn", sorted({x["h2_turn"] for x in xs}), "player hp range", min(h["player_hp_lost"] for h in h2), max(h["player_hp_lost"] for h in h2), "hostile hp range", min(h["hostile_hp_lost"] for h in h2), max(h["hostile_hp_lost"] for h in h2))
    print(" end turn", sorted(int(x["result"]["turn"]) for x in xs), "how", sorted({x["result"]["how"] for x in xs}), "phplost range", min(int(x["result"]["phplost"]) for x in xs), max(int(x["result"]["phplost"]) for x in xs))
    print(" hdead", sorted(int(x["result"]["hdead"]) for x in xs), "pdead", sorted(int(x["result"]["pdead"]) for x in xs))
# how many pairs a given half-width would take, from the observed SD of the differences (normal approximation): a guide, not a promise
for m, w in (("player_hp_lost", 30), ("hostile_hp_lost", 30), ("player_out_new", 0.5), ("hostile_out_new", 0.5)):
    sd = r["h2"][m]["sd_diff"]
    print("need", m, "half width", w, "pairs", math.ceil((1.96 * sd / w) ** 2), "sd", sd, "half width now", r["h2"][m]["ci95_t"][1] - r["h2"][m]["diff"])
print("runs file MB", (HERE / "WP3_RUNS.jsonl").stat().st_size / 1e6, "results MB", (HERE / "WP3_RESULTS.json").stat().st_size / 1e6)
print("control K1 A end", by["Z3KA1"]["result"]["turn"], by["Z3KA1"]["result"]["phplost"], by["Z3KA1"]["result"]["hdead"], "K1 B end", by["Z3KB1"]["result"]["turn"], by["Z3KB1"]["result"]["phplost"], by["Z3KB1"]["result"]["hdead"])
