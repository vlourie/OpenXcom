"""RESTORE COMBAT AUTONOMY, stage 1, question 6: of the unit turns the headquarters' hold ended early, what was really lost. A prepared attack the dice passed over, a shot the journal's candidates show (upper bound: side's seen, not the unit's own), walking a task still wanted, and what the kept TU paid for in the next player phase (reaction). Read only. Needs chain.py's decisions_<run>.tsv.
Usage: losses.py <run> ..."""
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
ART = {"art_esc_stand", "art_esc_walk", "held_patrol_stand"}
ATT_T = set(range(4, 21))


def main():
    for run in sys.argv[1:]:
        rows = list(csv.DictReader(open(HERE / f"decisions_{run}.tsv", encoding="utf-8-sig"), delimiter="\t"))
        L = read(run)
        react = Counter()
        hive_react = Counter()
        for s in L:
            if s.startswith("[AIEVENT]") and "what=reaction" in s:
                k = kv(s)
                if k.get("side") == "0" and int(k["unit"]) >= 1000000:
                    react[(int(k["turn"]), k["unit"])] += 1
            elif s.startswith("[HIVEREACT]"):
                k = kv(s)
                hive_react[(int(k["turn"]), k["unit"])] += int(k["tu_spent"])
        byturn = defaultdict(list)
        for d in rows:
            byturn[(int(d["turn"]), d["unit"])].append(d)
        T = Counter()
        role_tu = defaultdict(Counter)
        srcs = Counter()
        rolled = Counter()
        chain = Counter()
        for (t, u), ds in byturn.items():
            arts = [i for i, d in enumerate(ds) if d["cls"] in ART]
            if not arts:
                if react.get((t + 1, u)):
                    T["react_after_other_turn"] += react[(t + 1, u)]
                continue
            T["unit_turns"] += 1
            d0 = ds[arts[0]]
            end_tu = int(ds[-1]["tu"])
            if ds[-1]["act"] not in ("0",):
                end_tu = 0  # the last decision spent something more: what was left is not in this record
            T["tu_kept"] += end_tu
            label = d0["label"]
            role_tu[label]["unit_turns"] += 1
            role_tu[label]["tu"] += end_tu
            later_att = any(d["cls"] == "attack" for d in ds[arts[0] + 1:])
            pre = any(ds[i]["prepared"] == "1" for i in arts)
            shot = any(int(ds[i]["shot_now"]) > 0 for i in arts)
            if later_att:
                T["attacked_later_this_turn"] += 1
            if pre and not later_att:
                T["prepared_attack_passed_over"] += 1
                role_tu[label]["prepared"] += 1
            if shot and not later_att and not pre:
                T["shot_in_candidates_only"] += 1
                role_tu[label]["shot_only"] += 1
            if not shot and not later_att and not pre:
                role_tu[label]["walk_only"] += 1
                role_tu[label]["walk_tu"] += end_tu
            for i in arts:
                srcs[ds[i]["src"]] += 1
                rolled[ds[i]["rolled"]] += 1
            # the mode kept after an artificial escape: the next decisions without a roll in mode 3
            for i in range(arts[0] + 1, len(ds)):
                if ds[i]["cls"].startswith("esc_kept"):
                    chain["kept_same_turn"] += 1
            r = react.get((t + 1, u), 0)
            if r:
                T["react_after_art_turn"] += r
                T["unit_turns_with_react"] += 1
            T["tu_spent_on_react_hold_task"] += hive_react.get((t + 1, u), 0)
        # a kept escape on the first decision of the next turn after an artificial one
        ordered = sorted(byturn)
        for (t, u) in ordered:
            nxt = byturn.get((t + 1, u))
            if nxt and any(d["cls"] in ART and d["cls"] != "held_patrol_stand" for d in byturn[(t, u)]) and nxt[0]["cls"].startswith("esc_kept"):
                chain["kept_next_turn"] += 1
                chain["kept_next_turn_walk"] += nxt[0]["cls"] == "esc_kept_walk"
        print("==", run)
        print("  ", dict(T))
        print("   hold-ended turns by role:")
        for k, v in sorted(role_tu.items()):
            print("    ", k, dict(v))
        print("   rolled", dict(rolled), "src", dict(srcs.most_common(5)), "kept", dict(chain))
        print("   reaction events by AI side, whole battle", sum(react.values()))


main()
