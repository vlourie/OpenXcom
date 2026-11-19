"""COORDINATED OPERATION, phase C: controls of all runs. Decision by decision: OFF against the archived D0, shadow against OFF, active against OFF up to the first difference. For each run: code, turns, the tags of errors and FAIR lines, TU never negative or above the maximum in any state line, spent never above the decision's TU, escape decisions kept, [HIVEOP] states. Read only. Run after extracting scpa_D_M3_s2 (see extract in this file)."""
import io
import json
import sys
import zipfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "mc"))
from lib import OUT, kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ARCH = Path("E:/OXCE_AIWorker/battles_archive/side_turn_scheduler_pilot_2026-10-30")
FIELDS = ("turn", "side", "unit", "n", "from", "tu", "act", "to", "aim", "hr", "hu")


def ensure(run):
    if (OUT / run / "openxcom.log.gz").exists():
        return
    for z in sorted(ARCH.glob("res_*.zip")):
        zf = zipfile.ZipFile(z)
        names = [n for n in zf.namelist() if f"/{run}/" in n and n.endswith("log.gz")]
        if names:
            (OUT / run).mkdir(parents=True, exist_ok=True)
            (OUT / run / "openxcom.log.gz").write_bytes(zf.read(names[0]))
            print("extracted", run, "from", z.name)
            return
    raise SystemExit(f"no {run}")


def decs(L):
    return [kv(s) for s in L if s.startswith("[AIDECIDE]")]


def cmp(name, a, b):
    da, db = decs(read(a)), decs(read(b))
    n = 0
    for x, y in zip(da, db):
        if any(x.get(f) != y.get(f) for f in FIELDS):
            print(f"{name}: {a} vs {b}: decisions {len(da)} and {len(db)}, FIRST DIFFERENCE at {n}, turn {x.get('turn')}")
            print("    ", {f: x.get(f) for f in FIELDS})
            print("    ", {f: y.get(f) for f in FIELDS})
            return n
        n += 1
    print(f"{name}: {a} vs {b}: decisions {len(da)} and {len(db)}, identical over {n}", "(lengths differ)" if len(da) != len(db) else "")
    return None


ensure("scpa_D_M3_s1")
ensure("scpa_D_M3_s2")
cmp("OFF = D0", "op2_OO_M3_s1", "scpa_D_M3_s1")
cmp("shadow = OFF", "op3_OS_M3_s1", "op2_OO_M3_s1")
RUNS = ["op1_OA_M3_s1", "op4_OA_M3_s1", "op5_OG_M3_s1", "op6_OG_M3_s2"]
cmp("active 4", "op4_OA_M3_s1", "op2_OO_M3_s1")
cmp("general s1", "op5_OG_M3_s1", "op2_OO_M3_s1")
cmp("general s2", "op6_OG_M3_s2", "scpa_D_M3_s2")
for run in ["op2_OO_M3_s1", "op3_OS_M3_s1"] + RUNS + ["scpa_D_M3_s1", "scpa_D_M3_s2"]:
    L = read(run)
    tags = Counter(s.split(" ", 1)[0] for s in L if s.startswith("[") and ("FAIR" in s[:14] or "ERROR" in s[:14]))
    bad_tu = over_tu = 0
    for s in L:
        if s.startswith("[AISTATE]"):
            k = kv(s)
            if int(k.get("tu", 0)) < 0 or ("tumax" in k and int(k["tu"]) > int(k["tumax"])):
                bad_tu += 1
    recs = {}
    cur = None
    for s in L:
        if s.startswith("[AIDECIDE]"):
            cur = kv(s)
        elif s.startswith("[AIREC]") and cur:
            try:
                recs[json.loads(s[8:])["rec"]] = cur
            except ValueError:
                pass
        elif s.startswith("[AIEXEC]"):
            try:
                j = json.loads(s[9:])
            except ValueError:
                continue
            d = recs.get(j.get("rec"))
            if d and j.get("spent", 0) > int(d["tu"]):
                over_tu += 1
    modes = Counter(kv(s).get("mode") for s in L if s.startswith("[AIDECIDE]") and " side=1 " in s)
    states = [kv(s).get("state") + ":" + kv(s).get("why", "") for s in L if s.startswith("[HIVEOP] event=STATE")]
    res = [s for s in L if s.startswith("[AIRESULT]")]
    r = kv(res[-1]) if res else {}
    fatal = [s[:120] for s in L if "FATAL" in s or "Exception" in s]
    print(f"{run}: lines {len(L)} result {r.get('how')} turn {r.get('turn')} liveS {r.get('livesoldiers')} liveA {r.get('livealiens')} pdead {r.get('pdead')} modes {dict(modes)} tags {dict(tags)} bad_tu {bad_tu} spent>tu {over_tu} fatal {len(fatal)}")
    print("    states", states)
