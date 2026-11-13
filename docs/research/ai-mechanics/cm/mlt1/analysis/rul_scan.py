"""MISSION-LEVEL TACTICS: what the deployments of the 24 bench scenarios say about the side's task. Reads the ruleset index and prints each
deployment's fields, then every deployment entry block's objective fields from its source file.

  py -3.13 -I rul_scan.py <index dir> <scen.tsv> <mod root>"""
import csv
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
idx, scen, mod = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
rows = list(csv.DictReader(open(idx / "entries.tsv", encoding="utf-8-sig", newline=""), delimiter="\t"))
sections = {r["section"] for r in rows}
print("sections with deploy:", [s for s in sections if "eploy" in s])
dep = {r["id"]: r for r in rows if r["section"].lower().startswith("aliendeploy") or r["section"] == "alienDeployments"}
print("deployments in index", len(dep))
WANT = ("objectiveType", "objectivesRequired", "turnLimit", "chronoTrigger", "escapeType", "cheatTurn", "noRetreat", "objectivePopup",
        "objectiveComplete", "objectiveFailed", "vipSurvivalPercentage", "vipEscapeType", "genMission", "isAlienBase", "abortCutscene",
        "winCutscene", "loseCutscene", "reinforcements", "unlockedResearch", "missionBountyItem", "shade", "alert", "briefing", "nextStage")
seen = set()
for line in open(scen, encoding="utf-8-sig"):
    p = line.rstrip("\n").split("\t")
    if p[0] == "id":
        continue
    sid, mission = p[0], p[3]
    if mission in seen:
        print(f"{sid} {mission} (see above)")
        continue
    seen.add(mission)
    r = dep.get(mission)
    if not r:
        print(f"{sid} {mission}: not a deployment id in the index")
        continue
    print(f"{sid} {mission}  {r['file']}:{r['line']} fields={r.get('fields', '')[:200]}")
