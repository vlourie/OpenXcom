"""AI FORGE WP1: does the check catch what it must? Made-up logs only, no battles: a clean activation passes, each planted breach is found, a changed line breaks the chain."""
import sys

import scheduler_integrity_check as sic

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def log(events):
    h = 0xCBF29CE484222325
    out = []
    for n, body in enumerate(events, 1):
        text = f" rng=abc t=1 s=1 {body}"
        h = sic.chain_step(h, text)
        out.append(f"[FORGE] n={n} h={h:x}{text}")
    return out


U = "unit=7 fac=1 st=0 tu=40 noresel="
CLEAN = [
    "ev=sel unit=7 from=-1 again=0 noresel=0 fac=1 st=0 tu=40",
    f"ev=tick {U}0 hide=0 counter=0 second=0 pos=1,1,0 hp=10 en=10",
    f"ev=decide {U}0 hide=0 number=1 second=0",
    f"ev=act {U}0 hide=0 type=1 to=2,2,0 weapon=- fa=1 run=0 number=1 ai=0",
    f"ev=tu kind=spend was=40 now=30 {U}0 hide=0",
    f"ev=mark set=1 was=0 by=postPathProcedures:529 {U}0 hide=0",
    f"ev=walk_end {U}1 hide=0 fa=1 ai=1 charge=-1",
    f"ev=tu kind=spend was=30 now=28 {U}1 hide=0",  # the turn at the end of its own walk
    f"ev=tick {U}1 hide=0 counter=1 second=0 pos=2,2,0 hp=10 en=10",
    f"ev=gate {U}1 hide=0 counter=1 max=2 stunned=0",
    "ev=sel unit=8 from=7 again=0 noresel=0 fac=1 st=0 tu=30",
    "ev=decide unit=8 fac=1 st=0 tu=30 noresel=0 hide=0 number=1 second=0",
    "ev=tu kind=spend was=5 now=1 unit=7 fac=0 st=0 tu=5 noresel=1 hide=0",  # another side's reaction, marked
    "ev=mark set=0 was=1 by=prepareNewTurn:2937 unit=7 fac=1 st=0 tu=5 noresel=1 hide=0",
    "ev=decide unit=7 fac=1 st=0 tu=40 noresel=0 hide=0 number=1 second=0",
]


def expect(name, events, kind):
    r = sic.check(events)
    kinds = [v[0] for v in r["first_violations"]]
    ok = (kind in kinds) if kind else r["violations"] == 0
    print(("PASS" if ok else "FAIL"), name, "->", kinds or "no findings")
    return ok


def main():
    ok = True
    ok &= expect("a clean activation", log(CLEAN), None)
    # the V0/V0.1 breach: a decision of a unit marked this turn, no clearing in between
    breach = CLEAN[:11] + [f"ev=decide {U}1 hide=0 number=1 second=0"]
    ok &= expect("decision after the mark", log(breach), "decide_after_mark")
    ok &= expect("action after the mark", log(CLEAN[:11] + [f"ev=act {U}1 hide=0 type=4 to=2,2,0 weapon=X fa=0 run=0 number=1 ai=0"]), "act_after_mark")
    ok &= expect("time units after the mark, in another's chain", log(CLEAN[:12] + [f"ev=tu kind=spend was=28 now=20 {U}1 hide=0"]), "tu_after_mark")
    # a mark cleared by nobody known
    ok &= expect("mark cleared by an unknown hand", log(CLEAN[:11] + [f"ev=mark set=0 was=1 by=somethingNew:1 {U}1 hide=0"]), "clear_by_unknown")
    # a mark changed past the hooks: the engine's word and the events disagree
    ok &= expect("mark changed past the hooks", log(CLEAN[:7] + [f"ev=tick {U}0 hide=0 counter=1 second=0 pos=2,2,0 hp=10 en=10"]), "mark_bypass")
    ok &= expect("the engine's own alarm", log(CLEAN[:3] + ["ev=VIOLATION kind=rng_touched where=decide"]), "rng_touched")
    # the log itself: a line changed, a line removed
    changed = log(CLEAN)
    changed[4] = changed[4].replace("now=30", "now=31")
    ok &= expect("a line changed afterwards", changed, "chain_hash")
    removed = log(CLEAN)
    del removed[5]
    ok &= expect("a line removed afterwards", removed, "chain_number")
    print("ALL PASS" if ok else "SOME FAIL")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
