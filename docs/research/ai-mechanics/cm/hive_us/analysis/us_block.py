"""UNIFIED ARMY SAFETY, read only: when the guards' reach opened and who stood on the upper level then; the idle of 1000050 on M3 turn 1: OFF against ON, and how often a node of the condition with reach fails the engine's own path. Writes block.txt next to this file. Usage: us_block.py"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

HERE = Path(__file__).parent
NONE = "(-1,-1,-1)"
out = open(HERE / "block.txt", "w", encoding="utf-8-sig")
sys.stdout.reconfigure(encoding="utf-8")


def p(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    out.write(s + "\n")


G = ("1000021", "1000038", "1000039")
for run in ("us5_QS_M6_s1", "us1_QN_M6_s1"):
    t = defaultdict(list)
    for s in read(run):
        if s.startswith("[HIVEREACH]"):
            k = kv(s)
            if k["unit"] in G:
                t[k["unit"]].append((int(k["turn"]), int(k["tiles"])))
    for u in G:
        p(run, u, "reach by field (turn, tiles):", t[u][:14])

p("===== who stood on the upper level (z=2) outside the guards' room at the last decision of each side's turn, turns 1..3")
for run in ("us4_QO_M6_s1", "us1_QN_M6_s1"):
    last = {}
    for s in read(run):
        if s.startswith("[AIDECIDE]"):
            k = kv(s)
            if k["side"] == "1" and int(k["turn"]) <= 3:
                last[(int(k["turn"]), k["unit"])] = k["from"] if k["act"] != "2" else k["to"]
    for t in (1, 2, 3):
        p(run, "t", t, sorted((u, w) for (tt, u), w in last.items() if tt == t and w.endswith(",2)")))

p("===== the condition's nodes and the engine's path: try by try. A node is taken only with reach>0; fail = the next try of the same think follows")
for run in ("us1_QN_M6_s1", "us6_QN_M6_s1", "us2_QN_M3_s1", "us3_QN_M8_s1"):
    L = [kv(s) for s in read(run) if s.startswith("[HIVEUA] event=CHOICE")]
    got = fail = 0
    who = Counter()
    for a, b in zip(L, L[1:] + [{"unit": "", "try": "1", "turn": "0"}]):
        if a["chosen"] == NONE:
            continue
        got += 1
        if b["unit"] == a["unit"] and b["turn"] == a["turn"] and int(b["try"]) == int(a["try"]) + 1:
            fail += 1
            who[a["unit"]] += 1
    free_f = sum(1 for a, b in zip(L, L[1:]) if a["chosen"] == NONE and b["unit"] == a["unit"] and b["turn"] == a["turn"] and int(b["try"]) == int(a["try"]) + 1)
    free_n = sum(a["chosen"] == NONE for a in L)
    p(run, "condition's node tried", got, "path failed", fail, dict(who), "| free node tried", free_n, "failed", free_f)

p("===== 1000050 and 1000027 on M3, turn 1: decisions")
for run in ("ua6_UO_M3_s1", "us2_QN_M3_s1"):
    for u in ("1000050", "1000027"):
        p(run, u, [(k["from"], "m" + k["mode"], "a" + k["act"], k["to"]) for k in (kv(s) for s in read(run) if s.startswith("[AIDECIDE]") and f" unit={u} " in s) if k["turn"] == "1"])
    L = read(run)
    for u in ("1000050", "1000027"):
        p("   reach", u, [(kv(s)["turn"], kv(s)["tiles"]) for s in L if s.startswith("[HIVEREACH]") and f" unit={u} " in s][:3])
out.close()
