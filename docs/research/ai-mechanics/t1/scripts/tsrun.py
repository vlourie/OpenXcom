"""AI-T1 TARGET SELECTION (GO Vitali 27.10): the hostile's attack target by its expected effect (OXCE_AI_TARGET_EV) against P0/D0.

All battles: the DEV stand with the release AI, BetterAI OFF (exe T1 = exe AL of P0/P1 + patch_t1, OXCE_AI_RELEASE_BASE=1,
options base) - P0/D0 of REAL_AI_P0_VS_P1; the bot plays the player's side as there.
  log   - E1: OXCE_AI_TARGET_EV=1 (the record only, decisions as D0), 24 scenarios, seed 1; E0: the flag absent, M1 and L4,
          seed 1 (the default path of the new exe). Both must repeat the archived D0 battles decision for decision.
  pilot - E2: OXCE_AI_TARGET_EV=2 (the pick), 24 scenarios x seeds 1 and 2 (the seeds of D0), against the archived D0.

  pythonw tsrun.py --log logs/run_<phase>.txt --phase log|pilot [--jobs 24]

Everything under C:/OXCE_AIWorker/tsrun; the station's queue, tasks.json, state.json, stand*/ and c1run untouched.
"""
import argparse
import hashlib
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = Path(r"C:\OXCE_AIWorker\python\python.exe")
GAME = Path(r"C:\OXCE_AIWorker\game")
STAND_CFG = GAME / "user" / "builds" / "piratez" / "options.cfg"
DLL = r"C:\OXCE_AIWorker\bench\dll"
EXE = HERE / "exe" / "T1" / "openxcom.exe"
BASE = {"oxceBetterAi": "false", "oxceBetterAiFixes": "true", "oxceBetterAiAi3": "false"}
RB = {"OXCE_AI_RELEASE_BASE": "1"}
FLAG = {"E0": {}, "E1": {"OXCE_AI_TARGET_EV": "1"}, "E2": {"OXCE_AI_TARGET_EV": "2"}}
LOG = sys.stdout


def say(text):
    print(time.strftime("%H:%M:%S ") + text, file=LOG, flush=True)


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def write_cfg():
    """options.cfg base: the stand's config with the BetterAI keys explicit, as P0/P1 (pvrun.write_cfgs)."""
    (HERE / "cfg").mkdir(exist_ok=True)
    t = STAND_CFG.read_text(encoding="utf-8-sig")
    keys = {**BASE, "autosave": "true", "autosaveFrequency": "1", "autosaveSlots": "1", "skipNextTurnScreen": "true"}
    added = []
    for k, v in keys.items():
        t, n = re.subn(rf"(?m)^(\s*){k}: .*$", rf"\g<1>{k}: {v}", t)
        if not n:
            added.append(f"  {k}: {v}")
    if added:
        t = re.sub(r"(?m)^options:\s*$", "options:\n" + "\n".join(added), t, count=1)
    (HERE / "cfg" / "base.cfg").write_bytes(t.encode("utf-8"))


def scen_rows():
    lines = (HERE / "scen.tsv").read_text(encoding="utf-8-sig").splitlines()
    head = lines[0].split("\t")
    return [dict(zip(head, l.split("\t"))) for l in lines[1:] if l.strip()]


def env_for(extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("OXCE_AI_", "OXCE_HD_", "OXCE_U0_"))}
    env["PATH"] = DLL + os.pathsep + env.get("PATH", "")
    env.update({"OXCE_AI_GAME": str(GAME), "OXCE_AI_WORK": str(HERE / "work"), "OXCE_AI_EXE": str(EXE),
                "OXCE_AI_CFG": str(HERE / "cfg" / "base.cfg")})
    env.update(extra)
    return env


def battle(cfg, sc, k):
    seed = str(int(sc["seed"]) + k - 1)
    name = f"{cfg}_{sc['id']}_s{k}"
    env = env_for({**RB, **FLAG[cfg], "OXCE_AI_RACE": sc["race"]})
    (HERE / "logs").mkdir(exist_ok=True)
    t0 = time.time()
    with open(HERE / "logs" / f"{name}.out", "w", encoding="utf-8") as f:
        code = subprocess.call([str(PY), "-u", str(HERE / "pvone.py"), "battle", name, sc["id"], seed, sc["mission"], sc["race"],
                                sc["campaign"]], env=env, stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                               cwd=str(HERE), creationflags=0x08000000)
    return name, code, time.time() - t0


def done(name):
    p = HERE / "out" / name / "run.txt"
    return p.is_file() and "result [AIRESULT]" in p.read_text(encoding="utf-8")


def main():
    global LOG
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=24)
    ap.add_argument("--phase", default="log")
    ap.add_argument("--log", default="")
    a = ap.parse_args()
    if a.log:
        LOG = open(HERE / a.log, "a", encoding="utf-8")
    write_cfg()
    rows = scen_rows()
    with open(HERE / "manifest.txt", "a", encoding="utf-8") as m:
        m.write(f"# {time.strftime('%Y-%m-%d %H:%M:%S')} phase={a.phase}\n")
        for p in sorted([EXE, HERE / "cfg" / "base.cfg", HERE / "pvone.py", HERE / "tsrun.py", HERE / "scen.tsv",
                         HERE / "stand" / "ai_probe.py", STAND_CFG] + list((HERE / "saves").glob("*.sav"))):
            m.write(f"{sha(p)} *{p}\n")
    if a.phase == "log":
        jobs = [("E1", sc, 1) for sc in rows] + [("E0", sc, 1) for sc in rows if sc["id"] in ("M1", "L4")]
    else:
        jobs = [("E2", sc, k) for k in (1, 2) for sc in rows]
    jobs = [j for j in jobs if not done(f"{j[0]}_{j[1]['id']}_s{j[2]}")]
    say(f"phase {a.phase} jobs {len(jobs)} parallel {a.jobs}")
    t0 = time.time()
    with ThreadPoolExecutor(a.jobs) as pool:
        futs = [pool.submit(battle, c, sc, k) for c, sc, k in jobs]
        for n, fut in enumerate(as_completed(futs), 1):
            name, code, sec = fut.result()
            say(f"{n}/{len(jobs)} {name} code={code} {sec:.0f}s total={time.time() - t0:.0f}s")
    say("ALL DONE")


if __name__ == "__main__":
    main()
