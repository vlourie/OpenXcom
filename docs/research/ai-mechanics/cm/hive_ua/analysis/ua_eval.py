"""UNIFIED ARMY CONTROL V0, read only: what one active run came to, from its [HIVEUA] lines and the engine's own [AIDECIDE] against a base run. Usage: ua_eval.py <run> [base run]"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read, victims  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ATT = set(range(4, 21))
LAST = 8


def modes(run):
    """Per-run counts of the AI side's decisions up to the last common turn: mode, action, seeing an enemy or not, idle with time units."""
    out = {"n": 0, "mode": Counter(), "act": Counter(), "seen": Counter(), "seen_att": 0, "units": set(), "turns": set(), "idle_tu": 0}
    for s in read(run):
        if not s.startswith("[AIDECIDE]"):
            continue
        k = kv(s)
        if k.get("side") != "1" or int(k["turn"]) > LAST:
            continue
        out["n"] += 1
        out["mode"][k["mode"]] += 1
        act = int(k["act"])
        out["act"][act] += 1
        out["units"].add(k["unit"])
        out["turns"].add(int(k["turn"]))
        if k.get("seen", "-") != "-":
            out["seen"][k["mode"]] += 1
            out["seen_att"] += act in ATT
        if act == 0:
            out["idle_tu"] += int(k.get("tu", 0))
    return out


def casualties(run):
    return {f: len(v) for f, v in victims(read(run), LAST).items()}


def main():
    run = sys.argv[1]
    ev = defaultdict(list)
    init = ""
    for s in read(run):
        if s.startswith("[HIVEUA]"):
            k = kv(s)
            ev[k["event"]].append(k)
        elif s.startswith("[HIVEINIT]"):
            init = s
    print(run)
    print(" ", init[:170])
    print("  events", {k: len(v) for k, v in sorted(ev.items())})
    print("  org", Counter(k["area"].split(":")[0] for k in ev["ORG"]))
    by = defaultdict(Counter)
    inside = defaultdict(lambda: [0, 0])
    for k in ev["SQUADTURN"]:
        by[int(k["turn"])][k["kind"]] += 1
        inside[int(k["turn"])][0] += int(k["inside"])
        inside[int(k["turn"])][1] += int(k["alive"])
    for t in sorted(by):
        print(f"  turn {t}: {dict(by[t])} in place {inside[t][0]}/{inside[t][1]}")
    ch = ev["CHOICE"]
    n = len(ch)
    if n:
        print(f"  CHOICE {n}: changed {sum(k['changed'] == '1' for k in ch)} fallback {sum(k['fallback'] == '1' for k in ch)} chosen inside {sum(k['inside'] == '1' for k in ch)} free inside {sum(k['free_inside'] == '1' for k in ch)}")
        print("   by kind", Counter(k["kind"] for k in ch), "rung", sorted(Counter(k["rung"] for k in ch).items()), "fit", sum(int(k["fit"]) for k in ch) // n, "changed by kind", Counter(k["kind"] for k in ch if k["changed"] == "1"))
    dec = ev["DECIDED"]
    print("  DECIDED", len(dec), "acts", sorted(Counter(k["act"] for k in dec).items()), "on_choice", sum(k["on_choice"] == "1" for k in dec), "changed walks", sum(k["changed"] == "1" for k in dec))
    res = ev["RESULT"]
    wr = [k for k in res if k["changed"] == "1"]
    print(f"  RESULT {len(res)}: walked on changed {len(wr)}: inside {sum(k['inside'] == '1' for k in wr)} closer {sum(k['closer'] == '1' for k in wr)} moved {sum(k['moved'] == '1' for k in wr)} squads {len({k['squad'] for k in wr})} by kind {dict(Counter(k['kind'] for k in wr))}")
    print("  KEPT_DROP", len(ev["KEPT_DROP"]), "KEPT_BACK", len(ev["KEPT_BACK"]))
    print("  OBJECTIVE why", Counter(k["why"] for k in ev["OBJECTIVE"]))
    for k in ev["OBJECTIVE"]:
        if k["why"] in ("contact", "contact_moved"):
            print("   ", k["turn"], "squad", k["squad"], k["from"], "->", k["to"], k["why"], "contact", k.get("contact"), "dist", k.get("dist"))
    for k in ev["RETURN"]:
        print("    RETURN turn", k["turn"], "squad", k["squad"], k["from"], "contact", k["contact"], "since", k["since"], "objective", k["objective"])
    runs = [run] + sys.argv[2:3]
    for r in runs:
        m = modes(r)
        c = casualties(r)
        print(f"  {r}: decisions {m['n']} units {len(m['units'])} turns {max(m['turns'])} modes {sorted(m['mode'].items())} seen-by-mode {sorted(m['seen'].items())} attacks-when-seen {m['seen_att']} attacks {sum(v for a, v in m['act'].items() if a in ATT)} walk {m['act'][2]} none {m['act'][0]} idle_tu {m['idle_tu']} casualties {dict(c)}")


main()
