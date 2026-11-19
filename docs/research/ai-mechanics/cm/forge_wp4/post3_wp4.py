"""Offline, the whole archive: D0's own series of blows; what else the engine's list held at those decisions; the noise of within-branch comparisons over every derangement. No battle. Writes POST3.json."""
import collections
import itertools
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import AIForgeOpportunityMiner as M

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
out = {}
rows = []
for src, prefix, scen, seed in M.archived_battles():
    label, text, _ = M.read_archive(src, prefix, scen, seed)
    acts, recs = M.candidates_and_records(text)
    execs = {}
    for s in text:
        if "[AIEXEC] " in s:
            e = json.loads(s[s.index("{"):])
            execs[e["rec"]] = e
    for r in recs:
        b = r["base"]
        if r["side"] != 1 or r["unit"] < M.PLAYER_BELOW or b["t"] != M.HIT:
            continue
        cs = acts.get(r["cand"]["acts"], [])
        c = next((x for x in cs if x["id"] == b["id"]), None)
        e = execs.get(r["rec"], {})
        tu = r["state"]["tu"]
        same = [x for x in cs if x["k"] == "a" and x["lof"] == 1 and x["t"] in M.SHOT and c and x.get("u") == c.get("u") and 0 < x["tu"] <= tu]
        anyp = [x for x in cs if x["k"] == "a" and x["lof"] == 1 and x["t"] in M.SHOT and x.get("u", M.PLAYER_BELOW) < M.PLAYER_BELOW and 0 < x["tu"] <= tu]
        rows.append({"battle": label, "scen": scen, "seed": seed, "rec": r["rec"], "turn": r["turn"], "unit": r["unit"], "w": b["w"], "tu": tu, "target": c.get("u") if c else None, "player_target": bool(c) and c.get("u", M.PLAYER_BELOW) < M.PLAYER_BELOW, "spent": e.get("spent", 0), "dmg": e.get("dmg", 0), "stunned": e.get("stunned", 0), "downed": e.get("downed", 0), "hp_lost": e.get("hp_lost", 0), "shot_same_target": len(same), "shot_any_player": len(anyp), "shot_weapons": sorted({x["w"] for x in anyp})[:3]})
by = collections.defaultdict(list)
for r in rows:
    by[r["w"]].append(r)
print("D0's blows by weapon: decisions, with an effect, TU, damage, actor's HP lost, a legal shot at the same target, at any player's unit; missions")
table = {}
for w, xs in sorted(by.items(), key=lambda kv: -len(kv[1])):
    t = {"n": len(xs), "with_effect": sum(x["dmg"] > 0 or x["stunned"] > 0 for x in xs), "spent": sum(x["spent"] for x in xs), "dmg": sum(x["dmg"] for x in xs), "stunned": sum(x["stunned"] for x in xs), "actor_hp_lost": sum(x["hp_lost"] for x in xs), "shot_same": sum(x["shot_same_target"] > 0 for x in xs), "shot_any": sum(x["shot_any_player"] > 0 for x in xs), "player_target": sum(x["player_target"] for x in xs), "missions": sorted({x["scen"] for x in xs}), "units": len({(x["scen"], x["seed"], x["unit"]) for x in xs})}
    table[w] = t
    print(w, t)
out["blows"] = table
fist = by["AUX_FISTO"]
print("AUX_FISTO", [(x["battle"], x["rec"], x["unit"], x["tu"], x["spent"], x["shot_same_target"], x["shot_weapons"]) for x in fist][:30])
out["fisto"] = fist
out["blows_total"] = {"n": len(rows), "with_effect": sum(x["dmg"] > 0 or x["stunned"] > 0 for x in rows), "spent": sum(x["spent"] for x in rows), "no_effect_spent": sum(x["spent"] for x in rows if not (x["dmg"] > 0 or x["stunned"] > 0))}
print(out["blows_total"])

# within a branch over every derangement of six seeds: how often does a cell read 4 or more one way and at most 1 the other
records = M.load_records()
der = [p for p in itertools.permutations(range(6)) if all(i != p[i] for i in range(6))]
print("derangements", len(der))
res = {}
for key, table_ in (("hn", M.SHOWN_HN), ("h1", M.SHOWN_H1)):
    hits, total = 0, 0
    per_metric = collections.Counter()
    for slot in M.EXPLORE:
        for m, name in table_:
            for b in "AB":
                xs = M.series_of(records, slot, key, m, b)
                for p in der:
                    ys = [xs[i] for i in p]
                    more = sum(y > x for x, y in zip(xs, ys))
                    less = sum(y < x for x, y in zip(xs, ys))
                    total += 1
                    if max(more, less) >= 4 and min(more, less) <= 1:
                        hits += 1
                        per_metric[m] += 1
    res[key] = {"rate": hits / total, "of": total, "metrics": per_metric.most_common(6)}
    print(key, res[key])
out["derangements"] = res
real = {}
for key, table_ in (("hn", M.SHOWN_HN), ("h1", M.SHOWN_H1)):
    cells = []
    for slot in M.EXPLORE:
        for m, name in table_:
            xs, ys = M.series_of(records, slot, key, m, "A"), M.series_of(records, slot, key, m, "B")
            more = sum(y > x for x, y in zip(xs, ys))
            less = sum(y < x for x, y in zip(xs, ys))
            if max(more, less) >= 4 and min(more, less) <= 1:
                cells.append((slot, m, more, less))
    real[key] = cells
    print(key, len(cells), cells)
out["real_cells"] = real
# the effect metrics, both ways, per point and family
eff = {}
for fam, slots in M.FAMILY_SLOTS.items():
    for h in M.HORIZONS:
        for m, _ in M.EFFECTS:
            ts = [M.tally(M.series_of(records, s, h, m, "A"), M.series_of(records, s, h, m, "B")) for s in slots]
            eff[f"{fam}.{h}.{m}"] = {"better": [t["better"] for t in ts], "worse": [t["worse"] for t in ts], "equal": [t["equal"] for t in ts]}
out["effects"] = eff
for k, v in eff.items():
    print(k, v)
(HERE / "POST3.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8-sig")
