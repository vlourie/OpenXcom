"""AI FORGE WP2: the comparisons must catch a real difference and only it. A real log (WP1 R5) with one thing changed at a time; no new battle.
Also the list of fields the runner takes out of the engine's lines."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import AIForgeCounterfactualRunner as rr
import scheduler_integrity_check as sic

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
raw = sic.read_log(rr.ARCHIVE_R5, "fgR5_FGS_L8_s1")
print("normalised on R5:", rr.normalised_fields(raw))
print("lines outside [AI and [FORGE:", sum(1 for s in raw if not s.startswith(("[AI", "[FORGE"))))
for a, b in (("wp1:R2_FGS_M3", "wp1:R3_FGR_M3"), ("wp1:R4_FGO_L8", "wp1:R5_FGS_L8")):
    x = rr.game_compare(a, b)
    print("only [AIRESULT] ms= out, WP1 pair", a, b, x["game_lines"], x["identical"], x["first_difference"])

# the new log's shape: d= on the decisions, the dump at N and after it
base = []
d = 0
at = None
for s in raw:
    if s.startswith("[FORGE] ") and " ev=decide " in s:
        d += 1
        s += f" d={d}"
    base.append(s)
fp_n = next(i for i, s in enumerate(base) if " ev=decide " in s and s.endswith(f" d={rr.N}"))
fp_at = next(i for i in range(fp_n, len(base)) if base[i].startswith("[FORGE] ") and " ev=fp " in base[i])
next_fp = next(i for i in range(fp_at + 1, len(base)) if base[i].startswith("[FORGE] ") and " ev=fp " in base[i])
row = f"u={rr.UNIT} type=X fac=1 st=0 pos=1,1,1 dir=0 tu=98 en=1 hp=9 stun=0 mor=9 mana=0 fire=0 wounds=0 noresel=0 hide=0 charge=-1 seen=1 uh=a ai=b inv=c right=W ammo=9"
base[fp_at + 1:fp_at + 1] = [f"[FORGEDUMP] at=606 why=branch S=1", f"[FORGEDUMP] at=606 {row}", "[FORGEDUMP] at=606 floor=0 map=aa"]
next_fp += 3
base[next_fp + 1:next_fp + 1] = [f"[FORGEDUMP] at=700 why=after_branch S=1", f"[FORGEDUMP] at=700 {row}", "[FORGEDUMP] at=700 floor=0 map=aa"]
logs = {}
real = sic.read_log
sic.read_log = lambda z, l=None: logs[l]
rr.PLAN.update({"A": ("WA", ""), "B": ("WB", "")})
rr.RES = Path(".")
label = rr.label_of
logs[label("A")] = base
fails = 0


def expect(name, got, want):
    global fails
    ok = got == want
    fails += 0 if ok else 1
    print(("ok  " if ok else "FAIL"), name, got if not ok else "")


def with_(lines):
    logs[label("B")] = lines
    return lines


def changed(i, old, new):
    out = list(base)
    assert old in out[i], (old, out[i][:200])
    out[i] = out[i].replace(old, new, 1)
    return out


with_(list(base))
expect("same log: A/A identical", rr.aa("A", "B")["verdict"], "IDENTICAL")
mid = next(i for i, s in enumerate(base) if i > len(base) // 2 and s.startswith("[FORGE] ") and " ev=fp " in s)
for sec in ("U", "M", "R", "S"):
    m = re.search(rf" {sec}=([0-9a-f]+)", base[mid])
    with_(changed(mid, f" {sec}={m.group(1)}", f" {sec}=0{m.group(1)}"))
    x = rr.aa("A", "B")
    expect(f"section {sec} changed: A/A different", x["verdict"], "DIFFERENT")
    expect(f"section {sec}: fingerprints flagged", x["fingerprints"]["identical"], False)
tui = next(i for i, s in enumerate(base) if s.startswith("[FORGE] ") and " ev=tu " in s and i > mid)
m = re.search(r" now=(\d+)", base[tui])
with_(changed(tui, f" now={m.group(1)}", f" now={int(m.group(1)) + 1}"))
expect("a TU change: flagged", rr.aa("A", "B")["tu_changes"]["identical"], False)
gi = next(i for i, s in enumerate(base) if s.startswith("[AIDECIDE]"))
with_(changed(gi, "[AIDECIDE]", "[AIDECIDE] x=1"))
expect("an engine line: A/A different", rr.aa("A", "B")["verdict"], "DIFFERENT")
# a real-time field is not a difference; the game clock is
MS = rr.NORMALISED["[AIRESULT] ms="]
msi = next(i for i, s in enumerate(base) if s.startswith("[AIRESULT]") and MS.search(s))
with_([s if i != msi else MS.sub(" ms=123456", s) for i, s in enumerate(base)])
expect("[AIRESULT] ms= alone: no difference", rr.aa("A", "B")["verdict"], "IDENTICAL")
gm = next(i for i, s in enumerate(base) if s.startswith("[AIDECIDE]"))
with_([s if i != gm else s + " ms=5" for i, s in enumerate(base)])
expect("ms= on any other line: a difference", rr.aa("A", "B")["verdict"], "DIFFERENT")
# the one field added after the plan: out under the new list, a difference under the plan's; the count beside it stays in
ri = next(i for i, s in enumerate(base) if s.startswith("[AIREUSE]") and " fallback_us=" in s)
FU = rr.NORMALISED_AFTER_PLAN["[AIREUSE] fallback_us="]
with_([s if i != ri else FU.sub(" fallback_us=123456", s) for i, s in enumerate(base)])
x = rr.aa("A", "B")
expect("[AIREUSE] fallback_us= alone: no difference", x["verdict"], "IDENTICAL")
expect("[AIREUSE] fallback_us= alone: a difference under the plan's list", x["verdict_plan_list"], "DIFFERENT")
with_([s if i != ri else re.sub(r" fallback=\d+", " fallback=9", s) for i, s in enumerate(base)])
expect("[AIREUSE] fallback= (how many): a difference", rr.aa("A", "B")["verdict"], "DIFFERENT")
with_([s if i != gm else s + " fallback_us=5" for i, s in enumerate(base)])
expect("fallback_us= on any other line: a difference", rr.aa("A", "B")["verdict"], "DIFFERENT")
vi = next((i for i, s in enumerate(base) if " vms=" in s), None)
if vi is not None:
    with_([s if i != vi else re.sub(r" vms=\d+", " vms=7", s) for i, s in enumerate(base)])
    expect("vms= (game clock): a difference", rr.aa("A", "B")["verdict"], "DIFFERENT")
c_ = re.search(r" C=(\d+)", base[mid])
with_(changed(mid, f" C={c_.group(1)}", f" C={int(c_.group(1)) + 10}"))
expect("the clock in the chain: not normalised, a difference", rr.aa("A", "B")["verdict"], "DIFFERENT")

# the branch: the same to N, another line right after
b = list(base)
b[fp_at + 4] = "[FORGE] n=999 h=abc rng=1 t=1 s=1 ev=branch unit=1000006 fac=1 st=0 tu=98 noresel=0 hide=0 type=8 to=12,17,0 weapon=W target=324 fair=seen time=23 kneel=0"
with_(b)
x = rr.ab("A", "B")
expect("branch: prefix identical", x["prefix_chain_identical"], True)
expect("branch: engine lines to N identical", x["prefix_game_identical"], True)
expect("branch: dump at N identical", x["dump_at_N_identical"], True)
expect("branch: the first difference is the branch", " ev=branch " in x["first_difference"]["b"], True)
bad = changed(fp_n - 2, " tu=", " tu=1") if " tu=" in base[fp_n - 2] else None
if bad:
    bad[fp_at + 4] = b[fp_at + 4]
    with_(bad)
    x = rr.ab("A", "B")
    expect("a difference before N: prefix not identical", x["prefix_chain_identical"], False)
d2 = list(b)
d2[fp_at + 2] = d2[fp_at + 2].replace("tu=98", "tu=97")
with_(d2)
expect("TU at N differs in the dump: not identical", rr.ab("A", "B")["dump_at_N_identical"], False)
# two dumps under one event number (a frozen chain): only the first is the dump at N
two = ["why=branch S=1", "u=1 tu=9", "floor=0 map=a", "why=shot.1 S=2", "u=1 tu=8", "floor=0 map=b"]
expect("one_dump: the first of two under one number", rr.one_dump(two), two[:3])
expect("one_dump: a single dump untouched", rr.one_dump(two[:3]), two[:3])
# the floor hash is cumulative: the first differing floor, not how many
expect("first_floor: the first differing", rr.first_floor(["floor=0 map=a", "floor=1 map=b", "floor=2 map=c"], ["floor=0 map=a", "floor=1 map=x", "floor=2 map=y"]), "floor=1")
expect("first_floor: none", rr.first_floor(["floor=0 map=a"], ["floor=0 map=a"]), None)
# the auxiliary generator: L and V may differ, nothing else
s1 = [re.sub(r"( ev=fp .*)$", r"\1 L=1 V=2", s) if s.startswith("[FORGE] ") else s for s in base]
s2 = [re.sub(r"( ev=fp .*)$", r"\1 L=3 V=4", s) if s.startswith("[FORGE] ") else s for s in base]
logs[label("A")] = s1
with_(s2)
x = rr.seedless_compare("A", "B")
expect("seedless: only L, V differ", (x["events_identical_without_L_V"], x["game_identical"], x["L_differs"] > 0), (True, True, True))
s3 = list(s2)
i3 = next(i for i, s in enumerate(s3) if " ev=act " in s and i > mid)
s3[i3] = s3[i3].replace(" type=", " type=9")
with_(s3)
expect("seedless: an action moved, seen", rr.seedless_compare("A", "B")["events_identical_without_L_V"], False)
print("FAILS", fails)
sys.exit(1 if fails else 0)
