"""RESTORE COMBAT AUTONOMY: walks that did nothing. A walk decision whose [AIEXEC] spent no TU and left the unit where it was; by the headquarters' answer and the reason of the stop. A free choice must not turn a hold into a loop of empty walks. Read only.
Usage: empty_walks.py <run> ...; empty_walks.py <run> <unit> <turn> prints that unit-turn."""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")


def stream(run):
    """Every decision of the AI side with its record and its execution, in the log's order."""
    answer = {}
    out = []
    last = None
    recs = {}
    for s in read(run):
        if s.startswith("[HIVECC] event=AUTONOMY"):
            k = kv(s)
            answer[k["unit"]] = k["answer"] + ":" + k["from"]
        elif s.startswith("[AIDECIDE]"):
            k = kv(s)
            last = None
            if k["side"] == "1":
                last = dict(k, answer=answer.pop(k["unit"], ""), exec=None)
                out.append(last)
        elif s.startswith("[AIREC]") and last is not None and "rec" not in last:
            try:
                j = json.loads(s[8:])
            except ValueError:
                continue
            last["rec"] = j["rec"]
            recs[j["rec"]] = last
        elif s.startswith("[AIEXEC]"):
            try:
                j = json.loads(s[9:])
            except ValueError:
                continue
            if j["rec"] in recs:
                recs[j["rec"]]["exec"] = j
    return out


def main():
    if len(sys.argv) == 4 and sys.argv[2].isdigit():
        for d in stream(sys.argv[1]):
            if d["unit"] == sys.argv[2] and d["turn"] == sys.argv[3]:
                e = d["exec"] or {}
                print("n", d["n"], "tu", d["tu"], "mode", d["mode"], "act", d["act"], d["from"], "->", d["to"], d["answer"], "| spent", e.get("spent"), "pos", e.get("pos"), "en?", "trail", (e.get("trail") or [])[:2])
        return
    for run in sys.argv[1:]:
        D = stream(run)
        c = Counter()
        why = Counter()
        ut = Counter()
        for d in D:
            if d["act"] != "2":
                continue
            e = d["exec"]
            c["walks"] += 1
            a = d["answer"].split(":")[0] or "none"
            c["walks_" + a] += 1
            if e and e.get("spent", 0) == 0:
                c["empty"] += 1
                c["empty_" + a] += 1
                ut[(d["turn"], d["unit"])] += 1
                tr = (e.get("trail") or ["?"])[0].split(" ")[0]
                why[tr] += 1
            elif not e:
                c["no_exec"] += 1
        print(run, dict(sorted(c.items())))
        print("   reasons", dict(why.most_common(8)), "unit-turns with an empty walk", len(ut), "max in one", max(ut.values(), default=0))


main()
