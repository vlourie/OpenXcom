"""Totals of stage 1's table over the archive battles. Read only."""
import csv
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
A = [a for a in csv.DictReader(open(HERE / "assignments.tsv", encoding="utf-8-sig"), delimiter="\t") if not a["run"].startswith("cc1_")]
M = [m for m in csv.DictReader(open(HERE / "members.tsv", encoding="utf-8-sig"), delimiter="\t") if not m["run"].startswith("cc1_")]
print("assignments", len(A), "with attack on contact", sum(int(a["atk_contact"]) > 0 for a in A), "attacks on contact", sum(int(a["atk_contact"]) for a in A), "other", sum(int(a["atk_other"]) for a in A), "lost", sum(int(a["lost"]) for a in A))
print("left a search goal", sum(a["objective_left"] != "-" and not a["why"].startswith("contact_not") for a in A), "no goal yet", sum(a["objective_left"] == "-" for a in A), "retarget", sum(a["why"].startswith("contact_not") for a in A))
print("members", len(M), Counter(m["kind"] for m in M))
print("shot known", sum(int(m["shot"]) > 0 for m in M), "fits tu", sum(0 < int(m["shot"]) <= int(m["tu"]) for m in M), "melee or none", sum(int(m["shot"]) == 0 and m["kind"] != "no_node" for m in M))
print("stood on the turn before", sum(m["prev_fate"] == "stand" for m in M), "mode 3 on this turn", sum("3" in m["modes"].split("/") for m in M))
