"""DECISION ENGINE FOUNDATION, read only, over the D0 logs at hand: (1) how many lawful alternatives one decision holds (the slots think() has filled); (2) friendly fire: by what, how much, did the victim walk there this turn; (3) whole unit-turns lost, and who stood next to the soldier."""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
RUNS = sys.argv[1:] or ["scpa_D_M3_s1", "scpa_D_M3_s2", "scpa_D_M6_s2", "scpa_D_M8_s1", "d25_DO_M6_s1"]
AOE = ("GRENADE", "ROCKET", "MORTAR", "BOMB", "LAUNCH", "MISSILE", "EXPLOS", "CANNON", "RPG", "NADE", "CHARGE")
ACT = {0: "none", 2: "walk", 5: "throw", 6: "auto", 7: "snap", 8: "snap", 9: "aimed", 10: "hit", 11: "launch", 12: "psi"}
for run in RUNS:
    L = read(run)
    print("=====", run)
    recs = {}
    seq = []
    for i, s in enumerate(L):
        if s.startswith("[AIDECIDE]"):
            seq.append({"i": i, "k": kv(s)})
        elif s.startswith("[AIREC]"):
            j = json.loads(s[8:])
            if seq:
                seq[-1]["rec"] = j
        elif s.startswith("[AIEXEC]"):
            j = json.loads(s[9:])
            if seq and str(j.get("unit")) == seq[-1]["k"]["unit"]:
                seq[-1]["ex"] = j
    H = [d for d in seq if d["k"].get("side") == "1"]
    # (1) the slots
    slots = Counter()
    nalt = Counter()
    bymode = defaultdict(Counter)
    for d in H:
        r = d.get("rec")
        if not r or not r.get("base"):
            continue
        b = r["base"]
        props = b.get("reason", {}).get("props") or []
        have = {p.get("s") for p in props}
        have.add(b.get("slot"))
        have.discard(None)
        for s in have:
            slots[s] += 1
        nalt[len(have)] += 1
        bymode[d["k"]["mode"]][len(have)] += 1
    print(" decisions", len(H), "slots", dict(slots), "number of slots filled", dict(sorted(nalt.items())))
    print(" by mode", {m: dict(sorted(c.items())) for m, c in bymode.items()})
    # (2) friendly fire
    fd = Counter()
    fdn = Counter()
    dm = Counter()
    for d in H:
        ex = d.get("ex")
        if not ex:
            continue
        w = d["k"].get("weapon", "-")
        a = d["k"].get("act")
        dm[(a)] += ex.get("dmg", 0)
        if ex.get("fdmg", 0) or ex.get("fdowned", 0):
            fd[(ACT.get(int(a), a), w)] += ex.get("fdmg", 0)
            fdn[(ACT.get(int(a), a), w)] += ex.get("fdowned", 0)
    print(" to the enemy by act", dict(dm), "friendly damage total", sum(fd.values()), "downed", sum(fdn.values()))
    for k, v in fd.most_common(10):
        print("   ", k, "fdmg", v, "fdowned", fdn[k])
    # casualties of own side by own side: did the victim walk this turn, on the line?
    walked = defaultdict(list)  # (turn,unit) -> lines of walks that moved
    for d in H:
        ex = d.get("ex")
        if ex and d["k"].get("act") == "2" and ex.get("spent", 0) > 0:
            walked[(d["k"]["turn"], d["k"]["unit"])].append(d["i"])
    cas = []
    for i, s in enumerate(L):
        if s.startswith("[AICASUALTY]"):
            k = kv(s)
            if k.get("vfaction") == "1" and k.get("kfaction") == "1" and k.get("victim") != k.get("killer"):
                w = walked.get((k["turn"], k["victim"]), [])
                cas.append((k["turn"], k["victim"], k.get("killer"), k.get("weapon"), k.get("dist"), k.get("how"), sum(x < i for x in w)))
    print(" own side downed by own side:", len(cas), "victim had walked earlier this turn:", sum(c[6] > 0 for c in cas))
    for c in cas[:12]:
        print("    ", c)
    # (3) whole unit-turns lost
    ut = defaultdict(list)
    for d in H:
        ut[(int(d["k"]["turn"]), d["k"]["unit"])].append(d)
    lost = []
    for (t, u), v in ut.items():
        if sum(x.get("ex", {}).get("spent", 0) for x in v) == 0 and int(v[0]["k"]["tu"]) > 0:
            lost.append((t, u, v[0]["k"]["from"], "m" + v[0]["k"]["mode"], "a" + v[0]["k"]["act"], v[0]["k"]["tu"]))
    print(" unit-turns", len(ut), "nothing spent", len(lost), "tu lost", sum(int(x[5]) for x in lost), "of turns' tu", sum(int(v[0]["k"]["tu"]) for v in ut.values()))
    print("   by unit", Counter(x[1] for x in lost).most_common(8))
