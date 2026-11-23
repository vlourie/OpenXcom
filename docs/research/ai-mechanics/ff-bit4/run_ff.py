"""FF secondary-explosion check on the server: the 20 battles where the D experiment (census/ai3_2026-10-14/ff) found the
enemy blowing up its own side, plus its 3 control battles, on today's stand (clean HEAD 4ee3d1d37 DEV, exe/E).

Arms: E0 - the protocol v1 configuration (as run_c1.py COMMON: the standard bot, FX, the record);
      E  - E0 + OXCE_AI_BLAST_PROBE=1 (every blast and its hits recorded: must play the same as E0);
      F  - E + OXCE_AI_FF_RISK=4 (bit 4 only: no shot along a line past an explosive part whose blast reaches our own side).
Campaign NoCodexCatZ.sav (ai_arena's default, as the D runs), squad 8, 60 turns. Output only under c1run/ (labels ff_*).
Does not touch the station's queue, tasks.json, state.json or stand*/.

  python run_ff.py [--jobs N] [--only E0,E,F] [--log file]
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
ARMS = {"E0": [], "E": ["OXCE_AI_BLAST_PROBE=1"], "F": ["OXCE_AI_BLAST_PROBE=1", "OXCE_AI_FF_RISK=4"],
        # exe/FH: the base + bit 16 in ffLineRisk (the hostile side only); E1 must play as E, FH is the candidate
        "E1": ["OXCE_AI_BLAST_PROBE=1"], "FH": ["OXCE_AI_BLAST_PROBE=1", "OXCE_AI_FF_RISK=20"]}
ENV = {"E1": "env_FH.txt", "FH": "env_FH.txt"}


def battles():
    lines = (HERE / "ff_battles.tsv").read_text(encoding="utf-8-sig").splitlines()
    head = lines[0].split("\t")
    return [dict(zip(head, l.split("\t"))) for l in lines[1:] if l.strip()]


def one(arm, b):
    label = f"ff_{arm}_{b['id']}"
    args = [str(PY), "-u", str(HERE / "envrun.py"), str(HERE / ENV.get(arm, "env_E.txt")), str(HERE / "stand" / "ai_arena.py"),
            "--missions", b["mission"], "--seeds", b["seed"], "--squad", "8", "--turns", "60", "--timeout", "3600",
            "--jobs", "1", "--label", label, "--strict-flags"]
    for kv in COMMON + ARMS[arm]:
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
    ap.add_argument("--only", default="E0,E,F")
    ap.add_argument("--log", default="", help="progress to this file (pythonw has no stdout)")
    a = ap.parse_args()
    (HERE / "logs").mkdir(exist_ok=True)
    if a.log:
        sys.stdout = open(a.log, "w", encoding="utf-8")
    todo = [(arm, b) for b in battles() for arm in a.only.split(",")]
    print(f"runs {len(todo)} jobs {a.jobs}", flush=True)
    t0 = time.time()
    with ThreadPoolExecutor(a.jobs) as pool:
        futs = [pool.submit(one, arm, b) for arm, b in todo]
        for n, fut in enumerate(as_completed(futs), 1):
            label, code, sec = fut.result()
            print(f"{n}/{len(todo)} {label} code={code} {sec:.0f}s total={time.time() - t0:.0f}s", flush=True)
    print("ALL DONE", flush=True)


if __name__ == "__main__":
    main()
