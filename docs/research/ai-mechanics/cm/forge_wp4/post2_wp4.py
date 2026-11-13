"""Offline: D0's own blows and mind controls in the whole archive; the blows of the arena; the mind control's target. No battle. Writes POST2.json."""
import collections
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
nat = collections.defaultdict(collections.Counter)
psi = []
blow_targets = collections.Counter()
for src, prefix, scen, seed in M.archived_battles():
    label, text, _ = M.read_archive(src, prefix, scen, seed)
    acts, recs = M.candidates_and_records(text)
    execs = {}
    for s in text:
        if "[AIEXEC] " in s:
            e = json.loads(s[s.index("{"):])
            execs[e["rec"]] = e
    states = collections.defaultdict(list)
    for s in text:
        if "[AISTATE] " in s:
            m = re.search(r"\[AISTATE\] (\w+) turn=(\d+) unit=(\d+) .*?faction=(\d+)", s)
            if m:
                states[int(m[3])].append((int(m[2]), m[1], int(m[4])))
    for r in recs:
        b = r["base"]
        if r["side"] != 1 or r["unit"] < M.PLAYER_BELOW or b["t"] not in (M.HIT, M.MC, M.PANIC):
            continue
        cs = acts.get(r["cand"]["acts"], [])
        c = next((x for x in cs if x["id"] == b["id"]), None)
        e = execs.get(r["rec"], {})
        n = nat[M.TYPE_NAME[b["t"]], b["w"]]
        n["n"] += 1
        n["spent"] += e.get("spent", 0)
        n["dmg"] += e.get("dmg", 0)
        n["stunned"] += e.get("stunned", 0)
        n["downed"] += e.get("downed", 0)
        n["any"] += (e.get("dmg", 0) > 0 or e.get("stunned", 0) > 0)
        n["no_exec"] += not e
        if b["t"] in (M.MC, M.PANIC):
            target = c.get("u") if c else None
            later = [x for x in states.get(target, []) if x[0] > r["turn"]][:1]
            psi.append({"battle": label, "rec": r["rec"], "turn": r["turn"], "unit": r["unit"], "type": M.TYPE_NAME[b["t"]], "target": target, "dist": c.get("d") if c else None, "tu": b.get("k"), "morale_actor": r["state"]["morale"], "spent": e.get("spent"), "next_turn_faction": later[0][2] if later else None})
print("D0's own")
for k, v in sorted(nat.items(), key=lambda kv: -kv[1]["n"]):
    print(k, {x: v[x] for x in ("n", "no_exec", "any", "dmg", "stunned", "downed", "spent")})
out["natural"] = {f"{k[0]} {k[1]}": dict(v) for k, v in nat.items()}
for x in psi:
    print(x)
out["natural_psi"] = psi

# the arena's blows: the targets' armour, what the first blow's chance would be, the fate of the line after each blow
for slot in ("M1", "M2", "P1", "P2"):
    p = pts[slot]
    arm = f"Z4{slot}B1"
    r = M.run_of(arm, arms[arm])
    before = M.unit_rows(M.dump_of(r, "intervene"))
    after = M.unit_rows(M.dump_of(r, "after_branch"))
    print(slot, "target before", {k: before[str(p["new_unit"])].get(k) for k in ("type", "hp", "stun", "armor", "mor", "tu", "pos", "fac")})
    print(slot, "target after ", {k: after[str(p["new_unit"])].get(k) for k in ("type", "hp", "stun", "armor", "mor", "tu", "pos", "fac")})
    print(slot, "actor  before", {k: before[str(p["unit"])].get(k) for k in ("type", "hp", "tu", "en", "mor", "pos")})
    print(slot, "actor  after ", {k: after[str(p["unit"])].get(k) for k in ("type", "hp", "tu", "en", "mor", "pos")})
    i = next(k for k, s in enumerate(r.lines) if " phase=reseed " in s)
    kinds = collections.Counter()
    for s in r.lines[i:i + 400]:
        if s.startswith("[AIEVENT]"):
            kinds[re.search(r"what=(\S+)", s)[1]] += 1
    print(slot, "events after the action", dict(kinds))
    ex = next(json.loads(s[s.index("{"):]) for s in r.lines if s.startswith("[AIEXEC]") and f'"rec":{p["rec"]},' in s)
    print(slot, "exec", ex)
(HERE / "POST2.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8-sig")
