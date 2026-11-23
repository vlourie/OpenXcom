"""AI FORGE WP3: every number of the result document that is not in the tables, read from the frozen results."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
r = json.loads((HERE / "WP3_RESULTS.json").read_text(encoding="utf-8-sig"))
runs = [json.loads(s) for s in (HERE / "WP3_RUNS.jsonl").read_text(encoding="utf-8").splitlines()]
by = {x["arm"]: x for x in runs}
print("top keys", sorted(r))
print("run keys", sorted(by["Z3A01"]))
print("h2 keys", sorted(r["h2"]))
print("h1 keys", sorted(r["h1"]))
print("cost", r["cost_ms"])
for hz in ("h1", "h2"):
    for m, v in r[hz].items():
        print(hz, m, "A", v.get("mean_a"), "B", v.get("mean_b"), "d", v.get("diff"), "sd", v.get("sd_diff"), "t", v.get("ci95_t"), "boot", v.get("ci95_boot"), "more/less/eq", v.get("b_more"), v.get("b_less"), v.get("equal"), "better/worse", v.get("b_better"), v.get("b_worse"), "se", v.get("se_paired"), v.get("se_independent"), "ratio", v.get("variance_ratio_paired_to_independent"), "corr", v.get("correlation"))
A = [by[f"Z3A{i:02d}"] for i in range(1, 25)]
B = [by[f"Z3B{i:02d}"] for i in range(1, 25)]
for name, xs in (("A", A), ("B", B)):
    ph = [int(x["result"]["phplost"]) for x in xs]
    tn = [int(x["result"]["turn"]) for x in xs]
    print(name, "end phplost", min(ph), max(ph), "mean", sum(ph) / 24, "turn", min(tn), max(tn), "mean", sum(tn) / 24)
print("placebo", json.dumps(r["placebo"], ensure_ascii=False)[:1500])
print("signals", r["signals"], r["verdict_use"], r["placebo_signals_before_holm"])
for k in ("primary", "holm", "primary_tests"):
    if k in r:
        print(k, json.dumps(r[k], ensure_ascii=False)[:1500])
