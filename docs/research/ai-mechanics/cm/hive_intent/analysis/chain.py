"""RESTORE COMBAT AUTONOMY, stage 1: every decision of the AI side against what the headquarters' patrol() answered for it, reconstructed from HIVEORD (the same conditions as patrol()), what the dice rolled and what the unit ended with; what it could lawfully do at that moment by the journal's own candidates. Read only.
Usage: chain.py <run> ...; writes decisions_<run>.tsv next to this file and prints the tables."""
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
ATT = set(range(4, 21))
TERMINAL = {"BLOCKED", "INTERRUPTED", "CANCELLED"}
LAST = 8


def analyse(run):
    L = read(run)
    role = {}
    last_order = {}
    pause = {}
    acts = {}
    rows = []
    pending = None
    for s in L:
        if s.startswith("[HIVECC]"):
            k = kv(s)
            if k["event"] == "ASSIGN":
                role[k["squad"]] = k["to"]
        elif s.startswith("[HIVEORD]"):
            k = kv(s)
            note = s.split("note=", 1)[1] if "note=" in s else ""
            last_order[k["unit"]] = dict(k, note=note)
            if "pause_no_time_units" in note:
                pause[k["unit"]] = k["turn"]
        elif s.startswith("[AICAND] acts="):
            head, _, tail = s.partition(" list=")
            h = head.split("acts=")[1].split(" ")[0]
            try:
                acts[h] = json.loads(tail)
            except ValueError:
                pass
        elif s.startswith("[AIREC]"):
            try:
                j = json.loads(s[8:])
            except ValueError:
                continue
            # the record right after a decision is its own; n repeats inside a unit's turn, (turn, unit, n) is no key
            if pending is not None:
                pending[4] = j
                pending = None
        elif s.startswith("[AIDECIDE]"):
            k = kv(s)
            pending = None
            if k["side"] != "1" or int(k["turn"]) > LAST:
                continue
            pending = [k, dict(last_order.get(k["unit"], {})), dict(role), pause.get(k["unit"]), {}]
            rows.append(pending)
    out = []
    for k, o, rl, p, j in rows:
        t, u, n = int(k["turn"]), int(k["unit"]), int(k["n"])
        b = j.get("base") or {}
        reason = b.get("reason") or {}
        odds = reason.get("odds") or []
        rolled = odds[-1]["mode"] if odds else "-"
        props = reason.get("props") or []
        hold = ""
        if o and o.get("state") not in TERMINAL:
            if o.get("kind") == "STAY":
                hold = "stay:" + o.get("why", "")
            elif o.get("state") == "COMPLETED":
                hold = "arrived"
            elif p == k["turn"]:
                hold = "pause"
        squad = o.get("squad", "")
        r = rl.get(squad, "MAINTAIN")
        label = r if r != "MAINTAIN" else ("GUARD" if o.get("task") == "HOLD" else "SEARCH" if o.get("task") == "SEARCH" else "NONE")
        tu = int(k["tu"])
        act = int(k["act"])
        cand = j.get("cand") or {}
        lst = acts.get(cand.get("acts"), [])
        seen = set(k.get("seen", "").split(","))
        shot = [c for c in lst if c.get("k") == "a" and c.get("lof") == 1 and c.get("tu", 10 ** 6) <= tu and str(c.get("u")) in seen]
        out.append(dict(run=run, turn=t, unit=u, n=n, tu=tu, mode=int(k["mode"]), act=act, rolled=rolled, hold=hold, label=label, task=o.get("task", ""), why=o.get("why", ""), has_p=int(any(x.get("s") == "p" for x in props)), prepared=int(any(x.get("t") in ATT and x.get("s") != "e" for x in props)),
                        src=b.get("src", ""), shot_now=len(shot), shot_tu=min((c["tu"] for c in shot), default=-1), nmoves=cand.get("nmoves", 0), frm=k["from"], to=k["to"], aim=k["aim"], trail=";".join(reason.get("trail") or [])))
    return out


def classify(d):
    if d["act"] in ATT:
        return "attack"
    held = bool(d["hold"])
    m, r, walk = d["mode"], d["rolled"], d["act"] == 2
    if m == 3:
        if r == 3:
            return "esc_dice_walk" if walk else "esc_dice_stand"
        if r == "-":
            return "esc_kept_walk" if walk else "esc_kept_stand"
        return ("art_esc_walk" if walk else "art_esc_stand") if held else ("natural_fallback_walk" if walk else "natural_fallback_stand")
    if m == 0:
        return "patrol_walk" if walk else ("held_patrol_stand" if held else "patrol_stand")
    if m == 1:
        return "ambush_walk" if walk else "ambush_stand"
    return "combat_walk" if walk else "combat_other"


def main():
    allrows = {}
    for run in sys.argv[1:]:
        rows = analyse(run)
        allrows[run] = rows
        for d in rows:
            d["cls"] = classify(d)
        with open(HERE / f"decisions_{run}.tsv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), delimiter="\t")
            w.writeheader()
            w.writerows(rows)
        print("==", run, "decisions", len(rows), "unit-turns", len({(d["turn"], d["unit"]) for d in rows}))
        c = Counter(d["cls"] for d in rows)
        print("  classes", dict(c.most_common()))
        # the check on the reconstruction: a held decision has no patrol proposal
        held = [d for d in rows if d["hold"]]
        print("  held decisions", len(held), "with a patrol proposal (must be 0)", sum(d["has_p"] for d in held), "not held without one", sum(1 for d in rows if not d["hold"] and not d["has_p"]))
        print("  rolled -> final when held / when not held")
        for r in (0, 1, 2, 3, "-"):
            a = Counter(d["mode"] for d in rows if d["rolled"] == r and d["hold"])
            b = Counter(d["mode"] for d in rows if d["rolled"] == r and not d["hold"])
            print(f"    rolled {r}: held {dict(sorted(a.items()))} | free {dict(sorted(b.items()))}")
        lab = defaultdict(Counter)
        for d in rows:
            lab[d["label"]]["decisions"] += 1
            lab[d["label"]][d["cls"]] += 1
        print("  by role: decisions art_stand art_walk held_patrol_stand esc_dice attack")
        for name, x in sorted(lab.items()):
            print("   ", name, x["decisions"], x["art_esc_stand"], x["art_esc_walk"], x["held_patrol_stand"], x["esc_dice_stand"] + x["esc_dice_walk"], x["attack"])
        hk = Counter((d["hold"].split(":")[-1] if d["hold"].startswith("stay") else d["hold"]) for d in rows if d["cls"] in ("art_esc_stand", "art_esc_walk"))
        print("  artificial by hold kind", dict(hk.most_common()))
        # unit turns
        byturn = defaultdict(list)
        for d in rows:
            byturn[(d["turn"], d["unit"])].append(d)
        tally = Counter()
        tu_left = Counter()
        for key, ds in byturn.items():
            arts = [i for i, d in enumerate(ds) if d["cls"] in ("art_esc_stand", "art_esc_walk", "held_patrol_stand")]
            if not arts:
                continue
            tally["unit_turns_with_art"] += 1
            first = arts[0]
            later_att = any(d["cls"] == "attack" for d in ds[first + 1:])
            d0 = ds[first]
            if later_att:
                tally["attacked_later_same_turn"] += 1
            elif any(ds[i]["shot_now"] > 0 for i in arts):
                tally["shot_possible_unused"] += 1
                tu_left["shot_possible_unused"] += ds[-1]["tu"]
            elif d0["nmoves"] > 0:
                tally["could_only_walk"] += 1
                tu_left["could_only_walk"] += ds[-1]["tu"]
            else:
                tally["nothing_possible"] += 1
                tu_left["nothing_possible"] += ds[-1]["tu"]
            if any(ds[i]["cls"] == "art_esc_walk" for i in arts):
                tally["fled_on_foot"] += 1
        print("  unit turns", dict(tally), "tu at the end", dict(tu_left))


main()
