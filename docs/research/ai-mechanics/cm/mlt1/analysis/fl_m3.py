"""MISSION_DIRECTOR_V0: the chain of one battle: identity with D0 when asked, MISSION OBJECTIVE > GROUP PLAN > ASSIGNED TASK > ACTUAL ACTION > OBJECTIVE RESULT.

  py -3.13 -I fl_m3.py <battle dir> [<D0 battle dir>]"""
import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")
TAGS = ("[AIDECIDE] ", "[AISTATE] ", "[AICASUALTY] ", "[AIRESULT] ")
TIME = re.compile(r" v?ms=\d+")


def body(d):
    with gzip.open(Path(d) / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            yield raw.rstrip("\n").split("\t", 2)[-1]


rows = list(body(sys.argv[1]))
if len(sys.argv) > 2:
    a = [TIME.sub("", s) for s in body(sys.argv[2]) if s.startswith(TAGS)]
    b = [TIME.sub("", s) for s in rows if s.startswith(TAGS)]
    first = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), None)
    print(f"identity with D0: lines {len(a)} / {len(b)}, " + ("the same" if first is None and len(a) == len(b) else f"DIFFERENT from line {first}"))
    if first is not None:
        print(" D0:", re.sub(r" hu=.*", "", a[first])[:230])
        print(" this:", re.sub(r" hu=.*", "", b[first])[:230])
res = [s for s in rows if s.startswith("[AIRESULT]")]
if res:
    d = dict(KV.findall(res[-1]))
    print("result:", {k: d.get(k) for k in ("how", "turn", "livesoldiers", "livealiens", "player", "pdead", "pout", "phplost", "hostile", "hdead", "hout", "hmoves", "hattacks", "pattacks", "ms")})

aims = []
print("--- objective / plan / done / release:")
for s in rows:
    if s.startswith(("[AIMISSION] what=objective", "[AIMISSION] what=plan", "[AIMISSION] what=done", "[AIMISSION] what=noplan", "[AIMISSION] what=release")):
        print(" ", s[12:][:190])
    if s.startswith("[AIMISSION] what=aim"):
        aims.append(dict(KV.findall(s)))
print(f"--- D0's protocol aims: {len(aims)}; no line of fire to the target: {sum(d['lof'] == '0' for d in aims)}; a legal alternative in the same room at that moment: {sum(d.get('alt', '-') != '-' for d in aims)}; both: {sum(d['lof'] == '0' and d.get('alt', '-') != '-' for d in aims)}")
for d in aims[:8]:
    print(f"  t{d['turn']} {d['unit']} {d['from']} > {d['target']} lof{d['lof']} l{d['line']} impact {d['impact']} alt {d.get('alt')} armor {d.get('altarmor')}")
nm = [dict(KV.findall(s)) for s in rows if s.startswith("[AIMISSION] what=nomodule")]
print(f"--- nomodule (on a target node, nothing at z=1): {len(nm)}; with a legal alternative: {sum(d.get('alt', '-') != '-' for d in nm)}")
for d in nm[:8]:
    print(f"  t{d['turn']} {d['unit']} {d['from']} alt {d.get('alt')} armor {d.get('altarmor')}")

tasks = [dict(KV.findall(s)) for s in rows if s.startswith("[AIMISSION] what=task")]
print("--- tasks by unit and kind:", sorted(Counter((d["unit"], d["kind"]) for d in tasks).items())[:24])

# task > the decision after it > the hits and the spending of its execution
pend = {}
cur = None
done = []
for s in rows:
    if s.startswith("[AIMISSION] what=task"):
        d = dict(KV.findall(s))
        pend[d["unit"]] = d
    elif s.startswith("[AIDECIDE] "):
        d = dict(KV.findall(s.split(" hu=")[0]))
        if d["side"] == "1":
            cur = {"task": pend.pop(d["unit"], None), "dec": d, "hits": []}
    elif s.startswith("[AIMISSION] what=hit") and cur is not None:
        d = dict(KV.findall(s))
        if d["unit"] == cur["dec"]["unit"]:
            cur["hits"].append(d)
    elif s.startswith("[AIEXEC] ") and cur is not None:
        x = json.loads(s[9:])
        if str(x["unit"]) == cur["dec"]["unit"]:
            cur["exec"] = x
            if cur["task"]:
                done.append(cur)
            cur = None
print("--- chain: turn unit task > actual (mode act to spent) | hits")
kinds = Counter()
by = defaultdict(Counter)
for c in done:
    t, d, x = c["task"], c["dec"], c.get("exec", {})
    act, mode = int(d["act"]), int(d["mode"])
    want = t["kind"]
    spent = x.get("spent") or 0
    obeyed = (want == "shoot" and mode == 0 and act == 8 and d["to"].strip("()") == t.get("tile") and spent > 0) or (want == "walk" and mode == 0 and act == 2 and d["to"].strip("()") == t.get("node") and spent > 0)
    u = t["unit"]
    k = "obeyed" if obeyed else f"other mode{mode} act{act}" + (" notpaid" if spent == 0 else "")
    kinds[(want, k)] += 1
    by[u][want if obeyed else "other"] += 1
    if want == "shoot":
        mod = sum(i["module"] == "1" and i["part"] == "3" for i in c["hits"])
        brk = sum(i["module"] == "1" and i["part"] == "3" and int(i["tdmg"]) >= int(i["partarmor"]) for i in c["hits"])
        by[u]["module_hits"] += mod
        by[u]["broke"] += brk
        kinds[("shot landed", "module" if mod else "unit" if c["hits"] and all(i["part"] == "4" for i in c["hits"]) else "other terrain" if c["hits"] else "nothing logged")] += 1 if obeyed else 0
for c in done[:40]:
    t, d, x = c["task"], c["dec"], c.get("exec", {})
    h = " ".join(f"{i['tile']}:p{i['part']}:{i['tdmg']}/{i['partarmor']}:m{i['module']}" for i in c["hits"])
    print(f"  t{t['turn']} {t['unit']} {t['kind']} {t.get('tile', t.get('node'))} ({t['from']}) > m{d['mode']} a{d['act']} {d['to']} sp{x.get('spent')} | {h}"[:170])
print("--- how tasks went:", sorted(kinds.items()))
print("--- by fighter:", {u: dict(c) for u, c in by.items()})

hits = [dict(KV.findall(s)) for s in rows if s.startswith("[AIMISSION] what=hit")]
hm = [d for d in hits if d["side"] == "1" and d["module"] == "1" and d["part"] == "3"]
print(f"--- hostile hits on module objects {len(hm)}, breaking {sum(int(d['tdmg']) >= int(d['partarmor']) for d in hm)}; blasts {sum(s.startswith('[AIMISSION] what=blast') for s in rows)}")
grids = [s for s in rows if s.startswith("[AIMISSION] what=grid")]
facs = {dict(KV.findall(s))["at"]: dict(KV.findall(s))["type"].replace("STR_", "") for s in rows if s.startswith("[AIMISSION] what=fac")}
if grids:
    last = grids[-1].split("left: ")[-1].split()
    tot, zero, lost = 0, [], 0
    first = 0
    for g in last:
        k, v = g.split("=")
        l, f = map(int, v.split("/"))
        tot += l
        first += f
        if l == 0 and k in facs:
            zero.append(f"{k}:{facs[k]}")
    print(f"--- OBJECTIVE RESULT at {grids[-1][12:40]}: module tiles {first} > {tot} (lost {first - tot}); facilities demolished: {len(zero)} {zero}")
