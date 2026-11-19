"""RESTORE COMBAT AUTONOMY, main check: the first causal point of a pair. The two battles are the same up to the first differing line; that decision is the only one the change alone explains (the dice stream differs after it). Prints the headquarters' answer, what each did, and that unit's turn and next turn in both. Read only. Run chain.py on both first.
Usage: first_point.py <base run (CC)> <fixed run (RA)>"""
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
TAGS = ("[AIDECIDE]", "[AIEXEC]", "[AISTATE]", "[AICASUALTY]", "[AIREC]", "[AIPANIC]", "[AIAFTER]", "[AIPOSTWALK]", "[AIEVENT]")
timing = re.compile(r" (?:\w*us|\w*ms|\w*_ns|t|ms)=[-0-9.]+")
cfg = re.compile(r'"cfg":"[0-9a-f]+",')


def lines(run):
    return [cfg.sub("", timing.sub("", s)) for s in read(run) if s.startswith(TAGS)]


def table(run):
    return list(csv.DictReader(open(HERE / f"decisions_{run}.tsv", encoding="utf-8-sig"), delimiter="\t"))


def show(run, turn, unit):
    t = table(run)
    for nt in (turn, turn + 1):
        ds = [d for d in t if d["turn"] == str(nt) and d["unit"] == unit]
        print(f"  {run} turn {nt}:", "; ".join(f"n{d['n']} {d['cls']} tu={d['tu']} mode={d['mode']} act={d['act']} {d['frm']}->{d['to']} rolled={d['rolled']}" for d in ds) or "no decisions")
    fell = [s for s in read(run) if s.startswith("[AICASUALTY]") and f"victim={unit} " in s]
    print(f"  {run} fell:", fell[0][:90] if fell else "no")


def main():
    base, fixed = sys.argv[1], sys.argv[2]
    a, b = lines(base), lines(fixed)
    print("lines", len(a), len(b))
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            break
    else:
        print("no difference")
        return
    print("first differing line", i, "same before it")
    print(" A", a[i][:150])
    print(" B", b[i][:150])
    if a[i].startswith("[AIDECIDE]") and b[i].startswith("[AIDECIDE]"):
        x, y = kv(a[i]), kv(b[i])
        print(" fields that differ", {f: (x.get(f), y.get(f)) for f in set(x) | set(y) if x.get(f) != y.get(f)})
    # the first decision whose action differs, not only its dice hash
    act = ("turn", "unit", "n", "tu", "mode", "act", "from", "to", "aim")
    da = [kv(s) for s in a[i:] if s.startswith("[AIDECIDE]")]
    db = [kv(s) for s in b[i:] if s.startswith("[AIDECIDE]")]
    for x, y in zip(da, db):
        if any(x.get(f) != y.get(f) for f in act):
            print(" first differing action, A", {f: x.get(f) for f in act})
            print(" first differing action, B", {f: y.get(f) for f in act})
            break
    # the decision that line belongs to: the last or the next AIDECIDE
    pick = None
    for j in range(i, -1, -1):
        if a[j].startswith("[AIDECIDE]"):
            pick = j
            break
    next_a = next((s for s in a[i:] if s.startswith("[AIDECIDE]")), "")
    next_b = next((s for s in b[i:] if s.startswith("[AIDECIDE]")), "")
    ka, kb = kv(next_a), kv(next_b)
    print(" next decision A", {x: ka.get(x) for x in ("turn", "unit", "n", "tu", "mode", "act", "from", "to")})
    print(" next decision B", {x: kb.get(x) for x in ("turn", "unit", "n", "tu", "mode", "act", "from", "to")})
    if pick is not None:
        kp = kv(a[pick])
        print(" last decision before", {x: kp.get(x) for x in ("turn", "unit", "n", "tu", "mode", "act")})
    t, u, n = ka.get("turn"), ka.get("unit"), ka.get("n")
    d = next((x for x in table(base) if (x["turn"], x["unit"], x["n"], x["tu"]) == (t, u, n, ka.get("tu"))), {})
    print(" base class of that decision:", d.get("cls"), "hold:", d.get("hold"), "label:", d.get("label"), "task:", d.get("task"), "rolled:", d.get("rolled"))
    ans = [s for s in read(fixed) if s.startswith("[HIVECC] event=AUTONOMY") and f" unit={u} " in s and f"turn={t} " in s]
    print(" answers in the fixed run, that unit-turn:", [kv(s)["answer"] + ":" + kv(s)["from"] + ":" + kv(s)["why"] for s in ans][:6])
    show(base, int(t), u)
    show(fixed, int(t), u)
    # the first soldier given back the free choice: the dice stream differs by now, so this is a description, not a pair
    L = read(fixed)
    fi = next((i for i, s in enumerate(L) if s.startswith("[HIVECC] event=AUTONOMY") and " answer=FREE" in s), None)
    if fi is None:
        print("no free answer")
        return
    kf = kv(L[fi])
    dec = next(kv(s) for s in L[fi:] if s.startswith("[AIDECIDE]") and f" unit={kf['unit']} " in s)
    print(" first FREE answer:", {x: kf.get(x) for x in ("turn", "unit", "from", "why")}, "decided", {x: dec.get(x) for x in ("n", "tu", "mode", "act", "from", "to")})
    show(base, int(kf["turn"]), kf["unit"])
    show(fixed, int(kf["turn"]), kf["unit"])


main()
