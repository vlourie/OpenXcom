"""TACTICAL TURN SOLVER V0: the numbers of the report from the logs. Scene: per run what happened to T and A, the chain lines; natural battle: first divergence of ZS from ZD
against the first solver step, candidates by why, solver time. args: res dir"""
import gzip
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
res = Path(sys.argv[1])
A, B, T = "1000012", "1000031", "115"


def lines(label, pre=None):
    p = res / "out" / label / "openxcom.log.gz"
    if not p.is_file():
        return None
    return gzip.decompress(p.read_bytes()).decode("utf-8", errors="replace").split("\n")


def body(s):
    return s.split("\t", 2)[-1]


def scene(label, L):
    print("==", label)
    if L is None:
        print("no log")
        return
    rec = {"dmg": 0, "stunned": 0, "fdmg": 0, "fdowned": 0, "shots": 0}
    for s in L:
        b = body(s)
        if b.startswith("[AIEXEC]"):
            j = json.loads(b[9:])
            for k in ("dmg", "stunned", "fdmg", "fdowned"):
                rec[k] += j.get(k) or 0
        if b.startswith("[AIDECIDE]"):
            m = re.search(r"unit=(\d+) n=(-?\d+) from=(\S+) tu=(\d+) mode=(\d+) act=(\d+) to=(\S+)", b)
            print("  decide", m.group(1), "from", m.group(3), "tu", m.group(4), "act", m.group(6), "to", m.group(7))
        if b.startswith("[AITTS]"):
            j = json.loads(b[8:])
            print("  tts", j["ev"], {k: v for k, v in j.items() if k not in ("ev", "turn", "rng")}, "rng", j["rng"])
        if b.startswith("[AICASUALTY]"):
            print("  " + b[:150])
        if b.startswith("[AISTATE] after"):
            m = re.search(r"unit=(\d+) type=(\S+) .*?pos=(\S+) .*?tu=(\d+) hp=(\S+) stun=(\d+)", b)
            print("  end", m.group(1), m.group(2), m.group(3), "tu", m.group(4), "hp", m.group(5), "stun", m.group(6))
    print("  exec sums", rec, "rng_touched", sum("rng_touched" in s for s in L))


for label in ("tts1_ZD_SC_s1", "tts2_ZS_SC_s1", "tts3_ZD_SC_s2", "tts4_ZS_SC_s2"):
    if label == "tts1_ZD_SC_s1":
        L = None
        p = res / "r1" / "openxcom.log"
        if p.is_file():
            L = p.read_text(encoding="utf-8", errors="replace").split("\n")
    else:
        L = lines(label)
    scene(label, L)

D = lines("tts5_ZD_M10_s1")
S = lines("tts6_ZS_M10_s1")
print("== natural", D is not None, S is not None)
if D and S:
    def seq(L):
        out = []
        for s in L:
            b = body(s)
            if b.startswith("[AIDECIDE]"):
                out.append(re.sub(r" hu=.*$", "", b))
            elif b.startswith("[AITTS]"):
                out.append(b)
        return out

    def tot(L):
        c = Counter()
        for s in L:
            b = body(s)
            if b.startswith("[AIEXEC]"):
                j = json.loads(b[9:])
                c["execs"] += 1
                for k in ("dmg", "fdmg", "downed", "fdowned"):
                    c[k] += j.get(k) or 0
            if b.startswith("[AICASUALTY]"):
                c["casualty"] += 1
            if b.startswith("[AIRESULT]"):
                print("  result", b[:220])
        return c

    a, b = seq(D), seq(S)
    print("  decisions ZD", sum(x.startswith("[AIDECIDE]") for x in a), "ZS", sum(x.startswith("[AIDECIDE]") for x in b))
    a2 = [x for x in a if x.startswith("[AIDECIDE]")]
    b2 = [x for x in b if x.startswith("[AIDECIDE]")]
    n = 0
    while n < min(len(a2), len(b2)) and a2[n] == b2[n]:
        n += 1
    print("  common prefix of decisions", n)
    if n < len(a2):
        print("  ZD next", a2[n][:130])
    if n < len(b2):
        print("  ZS next", b2[n][:130])
    tts = [json.loads(x[8:]) for x in b if x.startswith("[AITTS]")]
    print("  tts lines", len(tts), Counter(j["ev"] for j in tts), Counter(j.get("why") for j in tts if j["ev"] == "cand"))
    print("  first steps", [(j["turn"], j["ev"], j.get("why")) for j in tts[:6]])
    first = next((i for i, x in enumerate(b) if '"ev":"step_A"' in x), None)
    if first is not None:
        print("  decisions before the first step_A", sum(x.startswith("[AIDECIDE]") for x in b[:first]))
    for j in tts:
        if j["ev"] in ("step_A", "after_A", "shot_B", "fired", "drop") or j.get("why") == "plan":
            print("  ", {k: v for k, v in j.items() if k != "rng"})
    for j in tts:
        if j["ev"] == "turn_end":
            print("   turn_end", j["turn"], j["calls"], j["us"], j["usTotal"])
    print("  ZD", dict(tot(D)))
    print("  ZS", dict(tot(S)))
    print("  rng_touched", sum("rng_touched" in s for s in S))
