"""Cross tables from members.tsv: which features known at the plan separate useful REINFORCE orders. And wasted TU of the whole side per run. Read only."""
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
rows = list(csv.DictReader(open(HERE / "members.tsv", encoding="utf-8-sig"), delimiter="\t"))


def bucket(d):
    d = int(d)
    return "<0" if d < 0 else "00-08" if d <= 8 else "09-14" if d <= 14 else "15-20" if d <= 20 else "21+"


def table(title, key, flt=lambda r: True):
    t = defaultdict(Counter)
    for r in rows:
        if not flt(r):
            continue
        k = key(r)
        c = t[k]
        c["n"] += 1
        c["attack_now"] += r["fate"] == "attack"
        c["c_now"] += int(r["att_c"]) > 0
        c["c_now_next"] += int(r["att_c"]) + int(r["att_c_next"]) > 0
        c["any_now_next"] += int(r["att_c"]) + int(r["att_o"]) + int(r["att_c_next"]) + int(r["att_o_next"]) > 0
        c["stand"] += r["fate"] == "stand"
    print("--", title)
    print("key\tn\tattack_now\ton_contact_now\ton_contact_now_or_next\tany_attack_now_or_next\tstand")
    for k in sorted(t, key=str):
        c = t[k]
        print(f"{k}\t{c['n']}\t{c['attack_now']}\t{c['c_now']}\t{c['c_now_next']}\t{c['any_now_next']}\t{c['stand']}")


M6 = lambda r: "_M6_" in r["run"]
M3 = lambda r: "_M3_" in r["run"]
table("kind, all", lambda r: r["kind"])
table("kind, M6", lambda r: r["kind"], M6)
table("kind, M3", lambda r: r["kind"], M3)
table("approach: distance from the target node to the contact", lambda r: bucket(r["d_tgt"]), lambda r: r["kind"] == "approach")
table("approach: distance from the unit to the contact", lambda r: bucket(r["d_now"]), lambda r: r["kind"] == "approach")
table("fire: distance from the unit to the contact", lambda r: bucket(r["d_now"]), lambda r: r["kind"] == "fire")
table("no_node: distance from the unit to the contact", lambda r: bucket(r["d_now"]), lambda r: r["kind"] == "no_node")
table("previous mode of the unit", lambda r: r["prev_mode"])
table("previous fate of the unit", lambda r: r["prev_fate"])
table("no_node by previous fate", lambda r: r["prev_fate"], lambda r: r["kind"] == "no_node")
table("cost share of TU, approach", lambda r: "cost+shot<=tu" if int(r["cost"]) + int(r["shot"]) <= int(r["tu"]) else "no_shot_after_walk", lambda r: r["kind"] == "approach")
table("weapon", lambda r: r["weapon"])


def waste(run, last=8):
    """TU left on the last decision of each unit-turn of the AI side, and how that last decision was."""
    last_dec = {}
    for s in read(run):
        if s.startswith("[AIDECIDE]"):
            k = kv(s)
            if k["side"] == "1" and int(k["turn"]) <= last:
                last_dec[(int(k["turn"]), k["unit"])] = k
    n = sum_tu = stood = stood_tu = 0
    for k in last_dec.values():
        n += 1
        tu = int(k["tu"])
        if k["act"] == "0":
            stood += 1
            stood_tu += tu
    return n, stood, stood_tu


print("-- side: unit-turns, of them ended with no action on the last decision, TU left in those")
for run in sys.argv[1:]:
    print(run, *waste(run))
