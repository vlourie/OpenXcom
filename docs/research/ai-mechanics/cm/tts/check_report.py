"""TACTICAL TURN SOLVER V0: the report's numbers against the logs, stops on any mismatch. args: res dir, report"""
import gzip
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
res, rep = Path(sys.argv[1]), Path(sys.argv[2]).read_text(encoding="utf-8-sig")


def L(label):
    p = res / "out" / label / "openxcom.log.gz"
    raw = gzip.decompress(p.read_bytes()).decode("utf-8", "replace") if p.is_file() else (res / "r1" / "openxcom.log").read_text(encoding="utf-8", errors="replace")
    return [s.split("\t", 2)[-1] for s in raw.split("\n")]


def state(lines, unit):
    for s in lines:
        m = re.search(rf"\[AISTATE\] after turn=\d+ unit={unit} .*? hp=(\d+)/(\d+) stun=(\d+)", s)
        if m:
            return tuple(map(int, m.groups()))
    return None


def ex(lines):
    t = {"dmg": 0, "stunned": 0, "fdmg": 0, "fdowned": 0}
    for s in lines:
        if s.startswith("[AIEXEC]"):
            j = json.loads(s[9:])
            for k in t:
                t[k] += j.get(k) or 0
    return t


def dec(lines, unit):
    return [re.search(r"from=(\S+) tu=\d+ mode=\d+ act=(\d+) to=(\S+)", s).groups() for s in lines if s.startswith("[AIDECIDE]") and f"unit={unit} " in s]


def tts(lines, ev):
    return [json.loads(s[8:]) for s in lines if s.startswith("[AITTS]") and f'"ev":"{ev}"' in s]


r1, r2, r3, r4 = L("tts1_ZD_SC_s1"), L("tts2_ZS_SC_s1"), L("tts3_ZD_SC_s2"), L("tts4_ZS_SC_s2")
r5, r6 = L("tts5_ZD_M10_s1"), L("tts6_ZS_M10_s1")
A, B, T = "1000012", "1000031", "115"
checks = [
    ("s1 D0 T", state(r1, T)[:2] == (107, 107)),
    ("s1 D0 dmg 0, fdmg 35", ex(r1)["dmg"] == 0 and ex(r1)["fdmg"] == 35),
    ("s1 D0 A killed by B", any("[AICASUALTY]" in s and f"victim={A}" in s and f"killer={B}" in s for s in r1)),
    ("s1 D0 B two snaps", sum(1 for d in dec(r1, B) if d[1] == "8") == 2),
    ("s1 TS T 105", state(r2, T)[:2] == (105, 107) and ex(r2)["dmg"] == 2 and ex(r2)["fdmg"] == 0),
    ("s1 TS A 36", state(r2, A)[:2] == (36, 36)),
    ("s2 D0 T", state(r3, T)[:2] == (107, 107) and ex(r3)["dmg"] == 0 and ex(r3)["fdmg"] == 0),
    ("s2 D0 B only walks", all(d[1] == "2" for d in dec(r3, B))),
    ("s2 D0 A 35", state(r3, A)[:2] == (35, 36)),
    ("s2 TS T 50", state(r4, T)[:2] == (50, 107) and ex(r4)["dmg"] == 54 and ex(r4)["stunned"] == 21 and ex(r4)["fdmg"] == 0),
    ("s2 TS A 36", state(r4, A)[:2] == (36, 36)),
    ("chain s2", tts(r4, "step_A")[0]["tuCost"] == 4 and tts(r4, "after_A")[0]["A"]["tu"] == 77 and tts(r4, "after_A")[0]["B"]["tu"] == 74 and tts(r4, "after_A")[0]["bLineReal"] == 1
     and tts(r4, "shot_B")[0]["tuCost"] == 51 and tts(r4, "shot_B")[0]["mode"] == 9 and tts(r4, "fired")[0]["B"]["tu"] == 23 and tts(r4, "fired")[0]["T"]["hp"] == 53 and tts(r4, "fired")[0]["tDamage"] == 54),
    ("rng same s2 before shot", len({j["rng"] for ev in ("step_A", "after_A", "shot_B") for j in tts(r4, ev)}) == 1),
    ("rng same s1 before shot", len({j["rng"] for ev in ("step_A", "after_A", "shot_B") for j in tts(r2, ev)}) == 1),
    ("value", tts(r4, "shot_B")[0]["value"] == 4.992 and tts(r2, "shot_B")[0]["value"] == 4.992),
    ("D0 first A decision", dec(r1, A)[0][2] == "(28,29,0)" and dec(r3, A)[0][2] == "(28,29,0)"),
    ("s2 TS A comes back to the line", any(d[2] == "(28,29,0)" for d in dec(r4, A))),
    ("no rng_touched", not any("rng_touched" in s for x in (r2, r4, r6) for s in x)),
]
for tag, n in (("[AIDECIDE]", 924), ("[AIEXEC]", 924), ("[AICASUALTY]", 36), ("[AISTATE]", 723)):
    a, b = [s for s in r5 if s.startswith(tag)], [s for s in r6 if s.startswith(tag)]
    checks.append((f"natural {tag}", a == b and len(a) == n))
c = [j for s in r6 if s.startswith("[AITTS]") for j in [json.loads(s[8:])] if j["ev"] == "cand"]
checks.append(("natural cand", len(c) == 28 and sum(j["why"] == "b_own_cell" for j in c) == 26 and sum(j["why"] == "a_worth_more" for j in c) == 2 and sum(j["why"] == "plan" for j in c) == 0))
checks.append(("natural zero values", all(j["valueA"] == 0 and j["valueB"] == 0 for j in c if j["why"] == "a_worth_more")))
e = tts(r6, "turn_end")
checks.append(("time", len(e) == 7 and sum(j["calls"] for j in e) == 1110 and e[-1]["usTotal"] == 6545501 and max(j["us"] for j in e) == 2286403))
for text in ("1 110", "6,55 с", "2,29 с", "924, 924, 36, 723", "4,99"):
    checks.append((f"text {text}", text in rep))
bad = [n for n, ok in checks if not ok]
print(len(checks), "checks,", "all ok" if not bad else f"FAILED: {bad}")
sys.exit(1 if bad else 0)
