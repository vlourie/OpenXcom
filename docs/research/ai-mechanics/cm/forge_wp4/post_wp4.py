"""After the gate, offline only, no battle: why the mind control and the blows did what they did. Writes POST.json."""
import collections
import gzip
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import AIForgeOpportunityMiner as M

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
pts = M.load_points()
arms = M.all_arms(pts)
out = {}

print("chances at the points (the engine's p)")
for s in M.EXPLORE:
    p = pts[s]
    print(s, p["scen"], "D0", M.TYPE_NAME[p["from"]], "p", p["aim_from"], "alt", M.TYPE_NAME[p["new"]], "p", p["aim_new"], "tu", p["tu_from"], p["tu_new"])
    out[f"aim_{s}"] = [p["aim_from"], p["aim_new"]]

# the same alternative at every opportunity
with gzip.open(HERE / "opportunities.jsonl.gz", "rt", encoding="utf-8") as f:
    ops = [json.loads(x) for x in f]
for fam in "PMT":
    xs = sorted(o["aim_new"] for o in ops if o["family"] == fam)
    print(fam, "alt p: n", len(xs), "min", xs[0], "median", xs[len(xs) // 2], "max", xs[-1], "share >=100", sum(x >= 100 for x in xs))
    out[f"alt_p_{fam}"] = {"n": len(xs), "min": xs[0], "median": xs[len(xs) // 2], "max": xs[-1]}

# what D0 itself did with these actions in the whole archive
nat = collections.defaultdict(lambda: collections.Counter())
psi_p = collections.defaultdict(list)
for src, prefix, scen, seed in M.archived_battles():
    label, text, _ = M.read_archive(src, prefix, scen, seed)
    acts, recs = M.candidates_and_records(text)
    execs = {}
    for s in text:
        if s.startswith("[AIEXEC]"):
            e = json.loads(s[s.index("{"):])
            execs[e["rec"]] = e
    afters = {}
    for r in recs:
        b = r["base"]
        if r["side"] != 1 or r["unit"] < M.PLAYER_BELOW or b["t"] not in (M.HIT, M.MC, M.PANIC):
            continue
        c = next((x for x in acts.get(r["cand"]["acts"], []) if x["id"] == b["id"]), None)
        e = execs.get(r["rec"], {})
        key = (M.TYPE_NAME[b["t"]], b["w"])
        n = nat[key]
        n["n"] += 1
        n["dmg"] += e.get("dmg", 0)
        n["stunned"] += e.get("stunned", 0)
        n["downed"] += e.get("downed", 0)
        n["spent"] += e.get("spent", 0)
        n["any_dmg"] += e.get("dmg", 0) > 0 or e.get("stunned", 0) > 0
        if b["t"] in (M.MC, M.PANIC) and c:
            psi_p[M.TYPE_NAME[b["t"]]].append(c["p"])
print("D0's own, whole archive")
for k, v in sorted(nat.items(), key=lambda kv: -kv[1]["n"])[:16]:
    print(k, {x: v[x] for x in ("n", "any_dmg", "dmg", "stunned", "downed", "spent")})
out["natural"] = {f"{k[0]} {k[1]}": dict(v) for k, v in nat.items()}
print("p of D0's own psi", {k: sorted(v) for k, v in psi_p.items()})
out["natural_psi_p"] = {k: sorted(v) for k, v in psi_p.items()}

# the runs: blows, what they did, real reaction shots
print("runs")
rows = {}
for slot in M.EXPLORE:
    p = pts[slot]
    for b in "AB":
        for i in range(1, 7):
            arm = f"Z4{slot}{b}{i}"
            r = M.run_of(arm, arms[arm])
            ev = r.events()
            j = M.act_index(ev, p["d"])
            nxt = next((k for k in range(j + 1, len(ev)) if ev[k][3].get("ev") == "decide"), len(ev))
            spend = [e[3] for e in ev[j:nxt] if e[3].get("ev") == "tu" and e[3].get("kind") == "cost"]
            actor_spend = [s for s in spend if s.get("unit") == str(p["unit"])]
            player_spend = [s for s in spend if int(s.get("unit", 0)) < M.PLAYER_BELOW]
            react = sum(1 for e in ev[j:nxt] if e[3].get("ev") == "react")
            ex = next((json.loads(s[s.index("{"):]) for s in r.lines if s.startswith("[AIEXEC]") and f'"rec":{p["rec"]},' in s), {})
            m = M.run_metrics(r, p)
            h1 = m["h1"]
            rows[arm] = {"blows_or_actions": len(actor_spend), "react_events": react, "player_cost_lines": len(player_spend), "dmg": ex.get("dmg"), "stunned": ex.get("stunned"), "downed": ex.get("downed"), "spent": ex.get("spent"), "exec_tu": ex.get("tu"), "actor_out_h1": h1.get("actor_out_new"), "actor_hp": h1.get("actor_hp_lost"),
                         "ctrl_h1": h1.get("player_controlled_new"), "ctrl_hn": (m["hn"] or {}).get("player_controlled_new"), "alt_mor_h1": h1.get("alt_target_morale_loss"), "ammo": h1.get("ammo_spent")}
    for b in "AB":
        ks = [f"Z4{slot}{b}{i}" for i in range(1, 7)]
        print(slot, b, {f: [rows[k][f] for k in ks] for f in ("blows_or_actions", "react_events", "player_cost_lines", "dmg", "stunned", "spent", "actor_out_h1", "ctrl_h1", "ctrl_hn", "ammo")})
out["runs"] = rows

# the psi lines of an arm
r = M.run_of("Z4P1B1", arms["Z4P1B1"])
print([s[:240] for s in r.lines if "psi" in s.lower() and s.startswith("[AI")][:6])

# how wide the noise is: per point and metric at each horizon, real against placebo
records = M.load_records()


def wide(flip=None):
    n = collections.Counter()
    for slot in M.EXPLORE:
        ids = M.complete(records, slot)
        for key, table in (("h1", M.SHOWN_H1), ("hn", M.SHOWN_HN)):
            for m, _ in table:
                xs = M.series_of(records, slot, key, m, flip or "A", ids)
                ys = xs[1:] + xs[:1] if flip else M.series_of(records, slot, key, m, "B", ids)
                more = sum(y > x for x, y in zip(xs, ys))
                less = sum(y < x for x, y in zip(xs, ys))
                if max(more, less) >= 4 and min(more, less) <= 1:
                    n[key] += 1
                n[key + "_cells"] += 1
    return dict(n)


out["wide_real"] = wide()
out["wide_placebo_A"] = wide("A")
out["wide_placebo_B"] = wide("B")
print("cells with 4 or more one way and at most 1 the other", out["wide_real"], out["wide_placebo_A"], out["wide_placebo_B"])
(HERE / "POST.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8-sig")
