"""(Copy of run_c1.py with the FF pilot's arms PE / PF, see ARMS.)
C1 COVER_STEP_V1 functional pilot on the server (GO Vitali 27.10: 24 scenarios x 1 seed x 3 arms = 72 battles).

Arms: E - DEV from HEAD 4ee3d1d37 without C1 (exe/E), A - DEV with C1, flag off (exe/C1), B - the same with
OXCE_AI_COVER_STEP=1. All: the standard bot (no --careful), FX (OXCE_AI_OXCE_FIXES=1), the record (OXCE_AI_RECORD=1).
One ai_arena.py run per arm and scenario (its own label), copies of the station's stand2 ai_arena.py / ai_probe.py
(with scenario/ and missions/) in stand/ and of envrun.py here. Does not touch the station's queue, tasks.json, state.json or stand*/; output only under c1run/.

  python run_c1.py [--jobs N] [--only E,A,B] [--scen M1,L4]
"""
import argparse
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = Path(r"C:\OXCE_AIWorker\python\python.exe")
COMMON = [
    "OXCE_AI_FAST=1", "OXCE_AI_LIGHTSKIP=1", "OXCE_AI_AMBUSH_MEMO=1", "OXCE_AI_ESCAPE_REACH_FIRST=1", "OXCE_AI_WALKFOV_SKIP=1",
    "OXCE_AI_LOADOUT_FIX=1", "OXCE_AI_PANIC_TURN_FIX=1", "OXCE_AI_PATROL_STUN_PREFIX=1", "OXCE_AI_POSTWALK_FIX=1",
    "OXCE_AI_OXCE_FIXES=1", "OXCE_AI_RECORD=1", "OXCE_AI_KEEP_DECIDE=1",
]
ARMS = {"E": ("env_E.txt", []), "A": ("env_C1.txt", []), "B": ("env_C1.txt", ["OXCE_AI_COVER_STEP=1"]),
        # FF pilot (run with --prefix pf --only PE,PF): PE - the clean HEAD with the blast record (passive, E0 = E 23/23),
        # PF - exe/FH (bit 16: the hostile side only) with OXCE_AI_FF_RISK=20, the same record
        "PE": ("env_E.txt", ["OXCE_AI_BLAST_PROBE=1"]), "PF": ("env_FH.txt", ["OXCE_AI_BLAST_PROBE=1", "OXCE_AI_FF_RISK=20"])}
PREFIX = "c1"


def set_series(prefix, c1env, bflag="OXCE_AI_COVER_STEP=1"):
    """The series' label prefix, the env file of the candidate exe (arms A and B) and the flag of arm B
    (C2 pilot: OXCE_AI_PREATTACK_COVER=1); E stays the clean HEAD."""
    global PREFIX
    PREFIX = prefix
    ARMS["A"] = (c1env, [])
    ARMS["B"] = (c1env, [bflag])


def scenarios():
    lines = (HERE / "scen.tsv").read_text(encoding="utf-8-sig").splitlines()
    head = lines[0].split("\t")
    return [dict(zip(head, l.split("\t"))) for l in lines[1:] if l.strip()]


def one(arm, sc):
    envfile, extra = ARMS[arm]
    label = f"{PREFIX}_{arm}_{sc['id']}"
    args = [str(PY), "-u", str(HERE / "envrun.py"), str(HERE / envfile), str(HERE / "stand" / "ai_arena.py"),
            "--missions", sc["mission"], "--seeds", sc["seed"], "--campaign", str(HERE / "saves" / sc["campaign"]),
            "--squad", "8", "--turns", "60", "--timeout", "3600", "--jobs", "1", "--label", label, "--strict-flags"]
    for kv in COMMON + extra + [f"OXCE_AI_RACE={sc['race']}"]:
        args += ["--env", kv]
    out = HERE / "logs" / f"{label}.out"
    t0 = time.time()
    with open(out, "w", encoding="utf-8") as f:
        # CREATE_NO_WINDOW: started by pythonw from a task in the user's session, no console may show on the station's screen
        code = subprocess.call(args, stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, cwd=str(HERE),
                               creationflags=0x08000000)
    return label, code, time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=24)
    ap.add_argument("--only", default="E,A,B")
    ap.add_argument("--scen", default="")
    ap.add_argument("--log", default="", help="progress to this file (pythonw has no stdout)")
    ap.add_argument("--prefix", default="c1", help="label prefix of the series (c1 - the first, c1v2 - the corrected C1)")
    ap.add_argument("--c1env", default="env_C1.txt", help="env file of the C1 exe for arms A and B")
    ap.add_argument("--bflag", default="OXCE_AI_COVER_STEP=1", help="the candidate's flag in arm B")
    a = ap.parse_args()
    if not a.bflag.startswith("OXCE_AI_") or "=" not in a.bflag:
        raise SystemExit(f"--bflag {a.bflag}: OXCE_AI_*=value")
    set_series(a.prefix, a.c1env, a.bflag)
    (HERE / "logs").mkdir(exist_ok=True)
    if a.log:
        sys.stdout = open(a.log, "w", encoding="utf-8")
    want = set(filter(None, a.scen.split(",")))
    todo = [(arm, sc) for sc in scenarios() if not want or sc["id"] in want for arm in a.only.split(",")]
    print(f"runs {len(todo)} jobs {a.jobs}", flush=True)
    t0 = time.time()
    with ThreadPoolExecutor(a.jobs) as pool:
        futs = [pool.submit(one, arm, sc) for arm, sc in todo]
        for n, fut in enumerate(as_completed(futs), 1):
            label, code, sec = fut.result()
            print(f"{n}/{len(todo)} {label} code={code} {sec:.0f}s total={time.time() - t0:.0f}s", flush=True)
    print("ALL DONE", flush=True)


if __name__ == "__main__":
    if sys.stdout:
        sys.stdout.reconfigure(encoding="utf-8")
    main()
