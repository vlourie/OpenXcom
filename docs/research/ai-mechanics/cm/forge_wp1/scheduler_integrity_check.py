"""AI FORGE WP1: SchedulerIntegrityMonitor, the offline half: checks the [FORGE] chain of a battle's log against the life of an activation.

  new <zip> <label> | new <file.log>      a new log: the chain is intact, the marks rebuilt from events agree with the engine's word, no action after a mark
  legacy <zip:prefix:arm:missions> ...    logs without [FORGE] (D0, V0, V0.1 archives): the mark from [AIPOSTWALK], later [AIDECIDE] of that unit in that turn

An action after a mark: a decision or an action of a marked unit, or its time units spent outside its own chain. Allowed by the engine's own
meaning and counted apart: the end of the chain that set the mark (the turn after a walk, a charge's blow, the bench bot's guard turn),
a reaction (the unit is not of the active side), a panicking or berserk unit (it acts outside handleAI). A mark is cleared only by a new turn or a
mind control (allowReselect in TileEngine); the player's button and debug do not happen in a bench battle, so here they would be findings."""
import gzip
import io
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path

KV = re.compile(r"(\w+)=([^ ]*)")
LEGAL_CLEAR = {"prepareNewTurn", "psiAttack"}
LINE = re.compile(r"^\[FORGE\] n=(\d+) h=([0-9a-f]+)( .*)$")


def read_log(src, label=None):
    if label is None:
        raw = Path(src).read_text(encoding="utf-8", errors="replace").splitlines()
    else:
        with zipfile.ZipFile(src) as z:
            raw = gzip.open(io.BytesIO(z.read(f"out/{label}/openxcom.log.gz")), "rt", encoding="utf-8", errors="replace").read().splitlines()
    return [s.split("\t")[-1] for s in raw]


def chain_step(h, text):
    for c in text.encode("utf-8", errors="surrogateescape"):
        h = ((h ^ c) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return h


def check(lines):
    """The findings of one log: every one names the event; zero findings in [violations] is the invariant."""
    h = 0xCBF29CE484222325
    expect = 1
    marks = {}
    actor = None
    side = None
    c = Counter()
    violations = []
    notes = []
    clears = Counter()
    sets = Counter()
    events = []
    for s in lines:
        m = LINE.match(s)
        if not m:
            continue
        n, hh, text = int(m.group(1)), m.group(2), m.group(3)
        if n != expect:
            violations.append(("chain_number", n, f"expected {expect}"))
            expect = n
        expect += 1
        h = chain_step(h, text)
        if f"{h:x}" != hh:
            violations.append(("chain_hash", n, text[:80]))
            h = int(hh, 16)
        d = dict(KV.findall(text))
        events.append((n, d, text))
    if not events:
        violations.append(("no_events", 0, "no [FORGE] lines"))
    last_tu = {}
    for i, (n, d, text) in enumerate(events):
        ev = d.get("ev")
        c[f"ev.{ev}"] += 1
        unit = d.get("unit")
        # time units that fell with no event to account for them: a path the hooks do not see (a new turn only raises them or is seen at the next line)
        if unit and "tu" in d and unit != "-1":
            shown = int(d["was"]) if ev == "tu" else int(d["tu"])
            if shown < last_tu.get(unit, shown):
                c["tu_past_hooks"] += 1
                notes.append(("time units fell past the hooks", n, text[:110]))
            last_tu[unit] = int(d["now"]) if ev == "tu" else shown
        side = d.get("s")
        said = d.get("noresel")
        was_marked = marks.get(unit, False)
        # the engine's word against the marks rebuilt from events: a mark changed past the hooks would show here
        if unit and said is not None and ev not in ("convert",) and (said == "1") != was_marked:
            if not (ev == "mark"):
                violations.append(("mark_bypass", n, f"unit {unit} engine says {said}, events say {int(was_marked)}: {text[:90]}"))
                marks[unit] = said == "1"
                was_marked = marks[unit]
        if ev == "VIOLATION":
            violations.append((d.get("kind", "engine"), n, text[:120]))
        elif ev == "mark":
            setting = d["set"] == "1"
            by = d["by"].split(":")[0]
            if setting:
                c["marks_set"] += 1
                sets[d["by"]] += 1
            else:
                c["marks_cleared"] += 1
                clears[d["by"]] += 1
                if by not in LEGAL_CLEAR:
                    violations.append(("clear_by_unknown", n, text[:120]))
            marks[unit] = setting
        elif ev == "sel" and unit != "-1":
            if int(d.get("again", 0)) > 0:
                c["reselected"] += 1
            if said == "1":
                nxt = events[i + 1][1] if i + 1 < len(events) else {}
                # the engine selects the first unit inside the change of side and clears the marks right after: no decision in between
                cleared = False
                for _, later, _ in events[i + 1:]:
                    if later.get("ev") in ("decide", "tick", "act"):
                        break
                    if later.get("ev") == "mark" and later.get("unit") == unit and later.get("set") == "0" and later["by"].startswith("prepareNewTurn"):
                        cleared = True
                        break
                if nxt.get("ev") == "panic" and nxt.get("unit") == unit:
                    c["sel_marked_panic"] += 1
                elif cleared:
                    c["sel_marked_turn_start"] += 1
                else:
                    c["sel_marked_passing"] += 1
                    notes.append(("selected while marked (no decision follows unless reported)", n, text[:110]))
        elif ev == "tick":
            pass
        elif ev == "decide":
            c["decisions"] += 1
            actor = unit
            if was_marked:
                violations.append(("decide_after_mark", n, text[:120]))
        elif ev == "act":
            c[f"act.{d.get('type')}"] += 1
            if was_marked and d.get("type") != "0":
                violations.append(("act_after_mark", n, text[:120]))
        elif ev in ("panic", "guard"):
            actor = unit
            c[f"chain.{ev}"] += 1
        elif ev == "react":
            c["reactions"] += 1
        elif ev == "convert":
            c["conversions"] += 1
        elif ev == "tu":
            if d["kind"] in ("spend", "cost") and was_marked:
                if d.get("fac") != side:
                    c["tu_marked_reaction"] += 1
                elif d.get("st") in ("PANIC", "BERSERK") or unit == actor:
                    c["tu_marked_own_chain"] += 1
                else:
                    violations.append(("tu_after_mark", n, f"chain of {actor}: {text[:110]}"))
    return {"events": len(events), "chain_last": events[-1][2][:0] + (f"{h:x}" if events else ""), "counts": dict(sorted(c.items())),
            "sets": dict(sets.most_common()), "clears": dict(clears.most_common()),
            "violations": len(violations), "first_violations": violations[:12], "notes": len(notes), "first_notes": notes[:4]}


def legacy_battle(lines, c):
    """Logs before the monitor: a mark is known only from [AIPOSTWALK] (noresel=1), so the counts are a lower bound."""
    marked = set()
    actors = set()
    for s in lines:
        if s.startswith("[AIPOSTWALK] "):
            d = dict(KV.findall(s))
            if d.get("noresel") == "1":
                marked.add((d.get("side"), d["turn"], d["unit"]))
                c[f"marks_seen.side{d.get('side')}"] += 1
        elif s.startswith("[AIDECIDE] "):
            d = dict(KV.findall(s.split(" hu=")[0]))
            k = (d.get("side"), d.get("turn"), d.get("unit"))
            if k in marked:
                c[f"decisions_after_mark.side{d.get('side')}"] += 1
                actors.add(k)
        elif s.startswith("[AISCD] "):
            j = json.loads(s[8:])
            if j.get("ev") == "act" and ("1", str(j["turn"]), str(j["actor"])) in marked:
                c["director_acts_after_mark"] += 1
    c["unit_turns_after_mark"] += len(actors)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    mode = sys.argv[1]
    if mode == "new":
        lines = read_log(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
        print(json.dumps(check(lines), ensure_ascii=False, indent=1))
    elif mode == "legacy":
        for a in sys.argv[2:]:
            zp, prefix, arm, missions = a.rsplit(":", 3)
            total = Counter()
            for mission in missions.split(","):
                c = Counter()
                for k in (1, 2, 3, 4):
                    legacy_battle(read_log(zp, f"{prefix}_{arm}_{mission}_s{k}"), c)
                total.update(c)
                print(f"{prefix} {arm} {mission}: {dict(sorted(c.items()))}")
            print(f"{prefix} {arm} ALL: {dict(sorted(total.items()))}")


if __name__ == "__main__":
    main()
