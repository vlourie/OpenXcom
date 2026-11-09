"""Offline: the last figures of the report: empty series with a legal shot, the checks summed, the batches' time, the scan's counts. No battle. Writes POST4.json."""
import collections
import json
import re
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
        rows.append({"label": label, "scen": scen, "seed": seed, "rec": r["rec"], "turn": r["turn"], "unit": r["unit"], "w": b["w"], "tu": tu, "player": bool(c) and c.get("u", M.PLAYER_BELOW) < M.PLAYER_BELOW, "spent": e.get("spent", 0), "effect": e.get("dmg", 0) > 0 or e.get("stunned", 0) > 0, "shots": len(same), "cheapest": min((x["tu"] for x in same), default=None), "weapons": sorted({x["w"] for x in same})})
empty = [r for r in rows if not r["effect"]]
print("blows", len(rows), "player's", sum(r["player"] for r in rows), "empty", len(empty), "TU", sum(r["spent"] for r in rows), "empty TU", sum(r["spent"] for r in empty))
cand = [r for r in empty if r["player"] and r["shots"]]
print("empty at a player's unit with a legal shot at it:", len(cand), "TU", sum(r["spent"] for r in cand), "cheapest shot TU mean", sum(r["cheapest"] for r in cand) / max(1, len(cand)))
print(" by mission", collections.Counter(r["scen"] for r in cand), "battles", len({(r["scen"], r["seed"]) for r in cand}), "units", len({(r["scen"], r["seed"], r["unit"]) for r in cand}))
print(" by weapon", collections.Counter(r["w"] for r in cand), collections.Counter(w for r in cand for w in r["weapons"]))
eff_with = [r for r in rows if r["effect"] and r["player"] and r["shots"]]
print("with an effect and a legal shot too", len(eff_with), collections.Counter(r["w"] for r in eff_with))
fist = [r for r in rows if r["w"] == "AUX_FISTO"]
print("AUX_FISTO", len(fist), "TU", sum(r["spent"] for r in fist), "mean", sum(r["spent"] for r in fist) / len(fist), "with a shot", sum(r["shots"] > 0 for r in fist), "player's with a shot", sum(r["shots"] > 0 and r["player"] for r in fist), collections.Counter(r["scen"] for r in fist), collections.Counter(r["scen"] for r in fist if r["shots"] > 0))
for r in cand:
    print("  ", r["label"], "rec", r["rec"], "turn", r["turn"], "unit", r["unit"], r["w"], "tu", r["tu"], "spent", r["spent"], "shot from", r["cheapest"], r["weapons"])
out["candidate"] = cand
out["blows"] = {"n": len(rows), "player": sum(r["player"] for r in rows), "empty": len(empty), "tu": sum(r["spent"] for r in rows), "empty_tu": sum(r["spent"] for r in empty)}

# the scan
sc = json.loads((HERE / "SCAN.json").read_text(encoding="utf-8-sig"))
print({k: sum(v["decisions"].values()) for k, v in sc["families"].items()}, {k: len(v["decisions"]) for k, v in sc["families"].items()})
print(sc["with_alternative"], sc["walks_with_a_legal_attack_by_source"])
out["scan"] = {k: sc[k] for k in ("battles", "decisions", "rng_touched", "with_alternative", "walks_with_a_legal_attack_by_source")}
out["families"] = sc["families"]

# the checks
tot = collections.Counter()
for p in sorted(HERE.glob("check_*.json")):
    d = json.loads(p.read_text(encoding="utf-8-sig"))
    tot[d["verdict"]] += 1
    for x in d.get("runs", []):
        tot["runs"] += 1
        tot["events"] += x["events"]
        tot["violations"] += x["violations"]
        tot["notes"] += x["notes"]
        tot["refused"] += bool(x.get("refused"))
        for k, v in (x.get("tu_kinds") or {}).items():
            tot[k] += v
    tot["pairs"] += len(d.get("pairs", []))
    tot["pair_defects"] += sum(len(y["defects"]) for y in d.get("pairs", []))
    print(p.name, d["verdict"], d.get("distinct_courses_a"))
print(dict(tot))
out["checks"] = dict(tot)
c = json.loads((HERE / "check_c.json").read_text(encoding="utf-8-sig"))
out["off"] = c["off_vs_d0"]
out["aa"] = {k: c["AA"][k] for k in ("verdict", "forge_events", "game_lines", "dumps_compared", "raw_differences")}
print(out["off"], out["aa"])
# the time of the batches
secs = {}
for p in sorted(M.RES.glob("run_*.txt")):
    t = p.read_text(encoding="utf-8", errors="replace")
    m = re.findall(r"total=(\d+)s", t)
    secs[p.stem] = int(m[-1]) if m else None
print(secs, sum(v for v in secs.values() if v))
out["seconds"] = secs
print(len(M.ledger()), collections.Counter(x[1] for x in M.ledger()))
(HERE / "POST4.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8-sig")
