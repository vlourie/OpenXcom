"""TACTICAL TURN SOLVER V0: natural battle, the checks the report rests on. Full decision lines with their hashes ZD against ZS; each candidate of ZS: did B fire at T later in the same turn all the same;
the two a_worth_more cases; the journals of the chain into files. args: res dir, out dir"""
import gzip
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
res, out = Path(sys.argv[1]), Path(sys.argv[2])


def lines(label):
    return [s.split("\t", 2)[-1] for s in gzip.decompress((res / "out" / label / "openxcom.log.gz").read_bytes()).decode("utf-8", errors="replace").split("\n")]


D, S = lines("tts5_ZD_M10_s1"), lines("tts6_ZS_M10_s1")
for tag in ("[AIDECIDE]", "[AIEXEC]", "[AIAFTER]", "[AICASUALTY]", "[AISTATE]"):
    a = [x for x in D if x.startswith(tag)]
    b = [x for x in S if x.startswith(tag)]
    print(tag, len(a), len(b), "identical" if a == b else "DIFFER")

ev = [(i, json.loads(x[8:])) for i, x in enumerate(S) if x.startswith("[AITTS]")]
why = Counter()
for i, j in ev:
    if j["ev"] != "cand":
        continue
    bid, tid, turn = j["B"]["id"], j["T"]["id"], j["turn"]
    fired = other = moved = 0
    for x in S[i:]:
        if x.startswith("[AIDECIDE]"):
            m = re.search(r"turn=(\d+) side=(\d+) unit=(\d+) n=\S+ from=\S+ tu=\d+ mode=\d+ act=(\d+) to=\S+ run=\d+ kneel=\d+ aim=(-?\d+)", x)
            if int(m.group(1)) != turn or m.group(2) != "1":
                if int(m.group(1)) > turn or m.group(2) != "1":
                    break
                continue
            if int(m.group(3)) == bid:
                if m.group(4) in ("7", "8", "9", "10"):
                    if int(m.group(5)) == tid:
                        fired += 1
                    else:
                        other += 1
                elif m.group(4) == "2":
                    moved += 1
    r = "fired at T" if fired else "attacked another" if other else "only walked" if moved else "nothing"
    why[(j["why"], r)] += 1
    if j["why"] == "a_worth_more":
        print("a_worth_more", {k: v for k, v in j.items() if k not in ("rng", "ev", "why")}, r)
print(sorted(why.items()))
print("distance B-T in candidates", Counter(max(abs(j["B"]["pos"][0] - j["T"]["pos"][0]), abs(j["B"]["pos"][1] - j["T"]["pos"][1])) // 5 * 5 for _, j in ev if j["ev"] == "cand"))
ends = [j for _, j in ev if j["ev"] == "turn_end"]
print("turn_end calls", sum(j["calls"] for j in ends), "us", ends[-1]["usTotal"], "max us of a side turn", max(j["us"] for j in ends), "max us per call", max(j["us"] / j["calls"] for j in ends))

for label, f in (("tts2_ZS_SC_s1", "chain_s1.txt"), ("tts4_ZS_SC_s2", "chain_s2.txt")):
    L = lines(label)
    keep = [x for x in L if x.startswith(("[AITTS]", "[AIDECIDE]", "[AIEXEC]", "[AICASUALTY]", "[AISTATE] after"))]
    (out / f).write_text("\n".join(re.sub(r" hu=.*$", "", x) for x in keep) + "\n", encoding="utf-8")
    print(f, len(keep))
