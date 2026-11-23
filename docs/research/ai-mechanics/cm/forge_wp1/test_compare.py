"""AI FORGE WP1: the relative comparison must still catch a real difference. Real log of R5, one thing changed at a time."""
import re
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0] if "\\" in __file__ else __file__.rsplit("/", 1)[0])
import AIForgeReplayRunner as rr
import scheduler_integrity_check as sic

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
base = sic.read_log(*rr.source_of("R5"))
real_read = sic.read_log
fps = [i for i, s in enumerate(base) if s.startswith("[FORGE] ") and " ev=fp " in s]
mid = fps[len(fps) // 2]


def run(lines):
    sic.read_log = lambda z, l: base if l == rr.label_of("R5") else lines
    try:
        return rr.compare("R5", "R2")
    finally:
        sic.read_log = real_read


def shifted(lines, by):
    return [rr.CLOCK.sub(lambda m: f" C={int(m.group(1)) + by}", s) for s in lines]


def section(lines, name):
    out = list(lines)
    out[mid] = re.sub(rf" {name}=([0-9a-f])", lambda m: f" {name}=" + ("0" if m.group(1) != "0" else "1"), out[mid], count=1)
    assert out[mid] != lines[mid], name
    return out


ok = True


def check(name, cond):
    global ok
    print("PASS" if cond else "FAIL", name)
    ok = ok and cond


c = run(base)
check("same log: relative identical", c["relative_identical"] and c["chain_identical"])
c = run(shifted(base, 5000))
check("constant shift: raw differs, relative identical, one shift", (not c["chain_identical"]) and c["relative_identical"] and list(c["clock_shifts"]) == ["-5000"])
half = [s if i < mid else rr.CLOCK.sub(lambda m: f" C={int(m.group(1)) + 10}", s) for i, s in enumerate(base)]
c = run(half)
check("clock runs differently from the middle: relative differs", not c["relative_identical"])
readings = [i for i, s in enumerate(base) if s.startswith("[FORGE] ") and rr.CLOCK.search(s)]
at = readings.index(mid)
stretch = list(base)
stretch[readings[at]] = rr.CLOCK.sub(lambda m: f" C={int(m.group(1)) + 10}", base[readings[at]])
c = run(shifted(stretch, 5000))
check("one interval longer, the next shorter by the same, under a shift: relative differs", not c["relative_identical"])
late = [s if i < readings[1] else rr.CLOCK.sub(lambda m: f" C={int(m.group(1)) + 10}", s) for i, s in enumerate(base)]
c = run(late)
check("only the first interval longer: relative differs", not c["relative_identical"])
for name in ("S", "U", "A", "I", "O", "M", "N", "B", "J", "R"):
    c = run(section(shifted(base, 5000), name))
    check(f"section {name} changed under a shift: relative differs", not c["relative_identical"])
ev = next(i for i, s in enumerate(base) if s.startswith("[FORGE] ") and " ev=act " in s)
c = run([s.replace(" to=", " to=9", 1) if i == ev else s for i, s in enumerate(base)])
check("event text changed: relative differs", not c["relative_identical"])
dump = next(i for i, s in enumerate(base) if s.startswith("[FORGEDUMP] ") and " tu=" in s)
c = run([s.replace(" tu=", " tu=9", 1) if i == dump else s for i, s in enumerate(base)])
check("dump changed: relative dump differs", bool(c["relative_dump_first_difference"]))
game = next(i for i, s in enumerate(base) if s.startswith("[AIDECIDE]") and i < mid)
c = run([s + "x" if i == game else s for i, s in enumerate(base)])
check("engine line changed: game differs", not c["game_identical"])
cut = base[:mid + 1] + ['[AIRESULT] how=timeout ms=1 vms=1 turn=1']
c = run(cut)
check("stopped run: prefix, not identical", c["relative_same_prefix"] and not c["relative_identical"] and c["game_before_stop_identical"])
c = run([s + "x" if i == game else s for i, s in enumerate(cut)])
check("stopped run with a changed engine line before the stop: caught", not c["game_before_stop_identical"])
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
