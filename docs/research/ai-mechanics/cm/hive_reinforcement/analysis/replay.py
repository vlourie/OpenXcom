"""Static check of the chosen gate on the CONTACT_COORDINATION archive: for each assignment, members that the gate would admit at the moment of assignment (fire or in_place, a firearm), and what those and the others did in that turn. Read only.
This is a look back at orders of a battle that went its own way; it cannot say what a filtered battle would have done."""
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
members = list(csv.DictReader(open(HERE / "members.tsv", encoding="utf-8-sig"), delimiter="\t"))
assigns = [r for r in csv.DictReader(open(HERE / "assignments.tsv", encoding="utf-8-sig"), delimiter="\t") if not r["run"].startswith("cc1_")]
MELEE = {"AUX_CHRYSSALID_WEAPON"}


def admitted(r):
    return r["kind"] in ("fire", "in_place") and r["weapon"] not in MELEE and int(r["shot"] if r["shot"] != "-" else 0) >= 0


by = defaultdict(list)
for r in members:
    by[(r["run"], r["squad"], int(r["turn"]))].append(r)
tot = {k: Counter() for k in ("first_only", "pass1", "fail1", "pass2", "fail2", "retarget")}
print("run\tsquad\tturn\tcontact\twhy\tdist\tmembers\tadmitted\tatt_contact\tatt_other\tdmg\tlost\tverdict>=1\tverdict>=2")
for a in assigns:
    t0 = int(a["from"])
    ms = by[(a["run"], a["squad"], t0)]
    n = sum(admitted(r) for r in ms)
    retarget = a["why"].startswith("contact_not_in_sight")
    v1 = "RETARGET" if retarget else "PASS" if n >= 1 else "NO_VIABLE"
    v2 = "RETARGET" if retarget else "PASS" if n >= 2 else "NO_VIABLE"
    print(a["run"][:6], a["squad"], t0, a["contact"], a["why"][:12], a["dist"], len(ms), n, a["atk_contact"], a["atk_other"], a["dmg"], a["lost"], v1, v2, sep="\t")
    for tag, vv in (("1", v1), ("2", v2)):
        key = "retarget" if vv == "RETARGET" else ("pass" if vv == "PASS" else "fail") + tag
        if vv == "RETARGET" and tag == "2":
            continue
        c = tot[key]
        c["assignments"] += 1
        c["att_contact"] += int(a["atk_contact"])
        c["att_other"] += int(a["atk_other"])
        c["dmg"] += int(a["dmg"])
        c["lost"] += int(a["lost"])
        c["any_contact_attack"] += int(a["atk_contact"]) > 0
print()
for k in ("pass1", "fail1", "pass2", "fail2", "retarget"):
    print(k, dict(tot[k]))
# member level: admitted against refused, all REINFORCE unit-turns
c = defaultdict(Counter)
for r in members:
    k = "admitted" if admitted(r) else "refused"
    c[k]["unit_turns"] += 1
    c[k]["att_contact"] += int(r["att_c"]) > 0
    c[k]["any_attack"] += int(r["att_c"]) + int(r["att_o"]) > 0
    c[k]["stood"] += r["fate"] == "stand"
print({k: dict(v) for k, v in c.items()})
