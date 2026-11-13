"""HIVE COMMAND gate: the real objective fields of the D0 scenarios' deployments in the installed game's rulesets (read only). Usage: objectives.py <scen.tsv> <game dir>"""
import csv
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
scen, game = Path(sys.argv[1]), Path(sys.argv[2])
want = {r["mission"]: r["id"] for r in csv.DictReader(open(scen, encoding="utf-8-sig"), delimiter="\t")}
files = list((game / "user" / "mods").rglob("*.rul")) + list((game / "standard").rglob("*.rul"))
FIELDS = ("objectiveType", "objectivesRequired", "objectiveCompleteScore", "objectiveCompleteText", "turnLimit", "chronoTrigger", "cheatTurn", "escapeType", "genMission", "isHidden", "baseDetectionRange", "skipReinforcement", "civilians")
found = {}
for f in files:
    try:
        text = f.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        continue
    if "alienDeployments" not in text:
        continue
    blocks = re.split(r"(?m)^  - (?:type|delete): *", text[text.index("alienDeployments"):])
    for b in blocks[1:]:
        name = b.split("\n", 1)[0].strip()
        if name in want:
            got = {}
            for k in FIELDS:
                m = re.search(rf"(?m)^    {k}: *(.+)$", b)
                if m:
                    got[k] = m.group(1).strip()
            found.setdefault(name, []).append((f.name, got))
for name, sc in want.items():
    print(sc, name, found.get(name, "NOT FOUND"))
