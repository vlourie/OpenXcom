"""AI FORGE WP2.1: the comparisons must catch a real difference and only it. A real log (WP2 A1) with one thing changed at a time; no new battle."""
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import AIForgeCounterfactualRunner as rr
import scheduler_integrity_check as sic

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
raw = sic.read_log(rr.ARCHIVE_WP2_A1, "fwA1_WA_L8_s1")
print("normalised on WP2 A1:", rr.normalised_fields(raw))

base = list(raw)
decide = next(i for i, s in enumerate(base) if " ev=decide " in s and s.endswith(f" d={rr.N}") or f" ev=decide " in s and f" d={rr.N} " in s)
actline = next(i for i in range(decide, len(base)) if base[i].startswith("[FORGE] ") and " ev=act " in base[i])
next_decide = next(i for i in range(actline, len(base)) if base[i].startswith("[FORGE] ") and " ev=decide " in base[i])
row = f"u={rr.UNIT} type=X fac=1 st=0 pos=1,1,1 dir=0 tu=98 en=1 hp=9 stun=0 mor=9 mana=0 fire=0 wounds=0 noresel=0 hide=0 charge=-1 seen=1 uh=a ai=b inv=c right=W ammo=9 kneel=0 vis=1,- spot=-"
after = row.replace("tu=98", "tu=67")
pre = "[FORGEBRANCH] d=49 phase=pre mode=act chain=aa state=bb rng=cc actor=1000006 type=7 to=12,17,0 weapon=W time=31 number=1 kneel=0"
post = "[FORGEBRANCH] d=49 phase=post from=7 to=8 fair=seen time_before=31 time_after=23 kneel_before=0 kneel_after=0 rng=cc"
# in the order the engine writes them: the intervention before the action line, the after dump at the next decision
base[next_decide + 1:next_decide + 1] = ["[FORGEDUMP] at=700 why=after_branch S=1", f"[FORGEDUMP] at=700 {after}", "[FORGEDUMP] at=700 floor=0 map=aa", "[FORGEDUMP] at=700 tile=1,1,0 was=x now=y", "[FORGEDUMP] at=700 tiles_changed=1"]
base[actline:actline] = [pre, "[FORGEDUMP] at=600 why=intervene S=1 U=2", f"[FORGEDUMP] at=600 {row}", "[FORGEDUMP] at=600 floor=0 map=aa"]
actline += 4
next_decide += 4
logs = {}
sic.read_log = lambda z, l=None: logs[l]
rr.PLAN.update({"A": ("XA", ""), "B": ("XB", "")})
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


def b_action(lines):
    """B's action line: only its type and, as a chain does, its h."""
    out = list(lines)
    out[actline] = re.sub(r" h=[0-9a-f]+", " h=abc", out[actline], count=1).replace(" type=7 ", " type=8 ", 1)
    out.insert(actline, post)
    return out


with_(list(base))
x = rr.aa("A", "B")
expect("same log: A/A identical", x["verdict"], "IDENTICAL")
expect("same log: no raw difference", x["raw_differences"]["lines"], 0)
mid = next(i for i, s in enumerate(base) if i > len(base) // 2 and s.startswith("[FORGE] ") and " ev=fp " in s)
for sec in ("U", "M", "R", "S", "A"):
    m = re.search(rf" {sec}=([0-9a-f]+)", base[mid])
    with_(changed(mid, f" {sec}={m.group(1)}", f" {sec}=0{m.group(1)}"))
    expect(f"section {sec} changed: DIFFERENT", rr.aa("A", "B")["verdict"], "DIFFERENT")
gi = next(i for i, s in enumerate(base) if s.startswith("[AIDECIDE]"))
with_(changed(gi, "[AIDECIDE]", "[AIDECIDE] x=1"))
expect("an engine line: DIFFERENT", rr.aa("A", "B")["verdict"], "DIFFERENT")
MS = rr.NORMALISED["[AIRESULT] ms="]
msi = next(i for i, s in enumerate(base) if s.startswith("[AIRESULT]") and MS.search(s))
with_([s if i != msi else MS.sub(" ms=123456", s) for i, s in enumerate(base)])
x = rr.aa("A", "B")
expect("[AIRESULT] ms= alone: IDENTICAL", x["verdict"], "IDENTICAL")
expect("[AIRESULT] ms= alone: the raw difference kept", x["raw_differences"]["lines"], 1)
with_([s if i != gi else s + " ms=5" for i, s in enumerate(base)])
expect("ms= on any other line: DIFFERENT", rr.aa("A", "B")["verdict"], "DIFFERENT")
vi = next((i for i, s in enumerate(base) if " vms=" in s), None)
with_([s if i != vi else re.sub(r" vms=\d+", " vms=7", s) for i, s in enumerate(base)])
expect("vms= (game clock): DIFFERENT", rr.aa("A", "B")["verdict"], "DIFFERENT")
with_([s if not s.startswith("[FORGEBRANCH]") else s.replace("state=bb", "state=bc") for s in base])
expect("the state at the intervention: DIFFERENT", rr.aa("A", "B")["verdict"], "DIFFERENT")
with_([s if not s.startswith("[FORGELEGAL]") else s for s in base] + ["[FORGELEGAL] case=x why=y"])
expect("a legality line: DIFFERENT", rr.aa("A", "B")["verdict"], "DIFFERENT")

# an intervention that does only its own job
with_(b_action(base))
x = rr.iso("A", "B")
expect("iso: prefix identical", x["prefix_chain_identical"], True)
expect("iso: engine lines up to the action identical", x["prefix_game_identical"], True)
expect("iso: state before identical", x["pre_all_same"], True)
expect("iso: dump before identical", x["dump_identical"], True)
expect("iso: the first difference is the action", x["chain_first_difference_is_the_action"], True)
expect("iso: only the type in the action's fields", sorted(x["act_fields_differ"]), ["type"])
expect("iso: post line found", x["post"], post)
expect("iso: RNG the same when it is", x["first_rng_difference"], None)
# anything else in the state, the action, or before the action
bad = b_action(base)
bad[actline - 3] = bad[actline - 3].replace("state=bb", "state=bc") if "state=bb" in bad[actline - 3] else bad[actline - 3]
p = next(i for i, s in enumerate(bad) if " phase=pre " in s)
with_([s if i != p else s.replace("state=bb", "state=bc") for i, s in enumerate(bad)])
expect("state hash differs: refused", rr.iso("A", "B")["pre_all_same"], False)
with_([s if i != p else s.replace("number=1", "number=2") for i, s in enumerate(b_action(base))])
expect("another field of the action before: refused", rr.iso("A", "B")["pre_all_same"], False)
with_([s if "tu=98" not in s else s.replace("tu=98", "tu=97") for s in b_action(base)])
expect("TU in the dump differs: not identical", rr.iso("A", "B")["dump_identical"], False)
early = b_action(base)
fe = next(i for i in range(decide) if early[i].startswith("[FORGE] ") and " ev=tu " in early[i])
early[fe] = re.sub(r" now=\d+", " now=1", early[fe])
with_(early)
x = rr.iso("A", "B")
expect("a chain line before the action: prefix not identical", x["prefix_chain_identical"], False)
expect("a chain line before the action: not the first difference", x["chain_first_difference_is_the_action"], False)
two = b_action(base)
two[actline + 1] = two[actline + 1].replace(" run=0 ", " run=5 ", 1)
with_(two)
x = rr.iso("A", "B")
expect("another field in the action line: shown", "run" in x["act_fields_differ"], True)
d2 = b_action(base)
k = next(i for i in range(actline + 2, len(d2)) if d2[i].startswith("[FORGE] "))
d2[k] = re.sub(r" rng=[0-9a-f]+", " rng=ffff", d2[k], count=1)
with_(d2)
expect("the first RNG difference is the next event", rr.iso("A", "B")["first_rng_difference"]["events_after_act"], 1)
ef = rr.effects(rr.Run("A"))
expect("effects: the actor's TU since the intervention", ef["units"][0]["fields"]["tu"], ["98", "67"])
expect("effects: the tile named", ef["tiles"], ["tile=1,1,0 was=x now=y"])
expect("one_dump: the first of two under one number", rr.one_dump(["why=a", "u=1", "why=b", "u=2"]), ["why=a", "u=1"])
expect("first_floor: the first differing", rr.first_floor(["floor=0 map=a", "floor=1 map=b"], ["floor=0 map=a", "floor=1 map=x"]), "floor=1")
print("FAILS", fails)
sys.exit(1 if fails else 0)
