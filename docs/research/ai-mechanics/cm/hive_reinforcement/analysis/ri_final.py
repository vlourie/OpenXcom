"""REINFORCEMENT INTELLIGENCE V0, the closing numbers: the load run against the save run, where each pair first differs, the arrivals with a line and the TU for a shot, the helpers' fate in the first turns of the pair, the idle helpers. Read only."""
import gzip
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
OUT = Path(__file__).parent.parent / "res" / "out"
ATT = set(range(4, 21))
PAIRS = (("ri2_RN_M6_s1", "cc8_CC_M6_s1"), ("ri3_RN_M6_s2", "cc5_CC_M6_s2"), ("ri4_RV_M3_s1", "cc6_CV_M3_s1"))

print("== save and load")
v, l = read("ri4_RV_M3_s1"), read("ri5_RL_M3_s1")
saved = next(s for s in v if s.startswith("[HIVESAVE]"))
text = saved.split(" text=")[1]
recs = text.split(";")
print("saved", kv(saved).get("turn"), "squads", sum(r.startswith("S,") for r in recs), "orders", sum(r.startswith("O,") for r in recs), "roles", sum(r.startswith("R,") for r in recs), [r for r in recs if r.startswith("R,")][:6])
ld = next((s for s in l if s.startswith("[HIVELOAD] parsed=1")), None)
print("loaded text equal", ld.split(" text=")[1] == text, "same", kv(ld).get("same"))
sc = [kv(s) for s in l if s.startswith("[HIVESAVECHECK]")]
print("savecheck", len(sc), "same", sum(x["same"] == "1" for x in sc), "new army lines", sum(s.startswith("[HIVESQUAD] id=") for s in l), "orders after load", sum(s.startswith("[HIVECC]") and "event=ORDER" in s for s in l), "help results", sum(s.startswith("[HIVECC]") and "event=HELP_RESULT" in s for s in l))

print("== first difference of the pair")
for a, b in PAIRS:
    A = [s for s in read(a) if s.startswith("[AIDECIDE]")]
    B = [s for s in read(b) if s.startswith("[AIDECIDE]")]
    same = 0
    for x, y in zip(A, B):
        if x != y:
            break
        same += 1
    print(a, b, "same decisions", same, "first differ turn", kv(A[same])["turn"] if same < len(A) else None, "unit", kv(A[same])["unit"], "|", kv(B[same])["unit"], "side", kv(A[same])["side"])

print("== helper arrivals and cancels")
pos = Counter()
for a, _ in PAIRS:
    for s in read(a):
        if s.startswith("[HIVECC]") and "event=HELP_RESULT" in s:
            k = kv(s)
            if k["kind"] == "POSITION":
                pos["arrived"] += 1
                pos["line"] += k["line"] == "1"
                pos["line+tu"] += k["line"] == "1" and int(k["tu"]) >= int(k["shot"])
                print("  ", a[:3], "t" + k["turn"], "unit", k["unit"], "line", k["line"], "tu", k["tu"], "shot", k["shot"])
            elif k["kind"] == "CANCEL":
                pos["cancel:" + k["why"]] += 1
            elif k["kind"] == "ATTACK":
                pos["attack_records"] += 1
print(dict(pos))

print("== first squad of each pair: the units CC sent on turn 1, turns 1-3 in both")
for a, b in PAIRS:
    Lb = read(b)
    first = next(kv(s) for s in Lb if s.startswith("[HIVECC]") and "event=ASSIGN" in s and "to=REINFORCE" in s)
    us = {kv(s)["unit"] for s in Lb if s.startswith("[HIVECC]") and "event=ORDER" in s and "role=REINFORCE" in s and kv(s)["turn"] == first["turn"]}
    for name in (b, a):
        at = walk = idle = dmg = 0
        fell = set()
        act = Counter()
        for s in read(name):
            if s.startswith("[AIDECIDE]"):
                k = kv(s)
                if k["unit"] in us and k["side"] == "1" and int(k["turn"]) <= 3:
                    act[("attack" if int(k["act"]) in ATT else "walk" if k["act"] == "2" else "none")] += 1
            elif s.startswith("[AICASUALTY]"):
                k = kv(s)
                if k.get("victim") in us and int(k["turn"]) <= 4:
                    fell.add(k["victim"])
        print(name, "assign turn", first["turn"], "contact", first["contact"], "units", len(us), dict(act), "fell by turn 4:", len(fell))

print("== share over the whole list")
tot = Counter()
for a, b in PAIRS:
    for tag, name in (("RI", a), ("CC", b)):
        for s in read(name):
            if s.startswith("[HIVECC]") and "event=ORDER" in s and "role=REINFORCE" in s:
                tot[tag + "_helper_turns"] += int(kv(s)["turn"]) <= 8
print(dict(tot))
