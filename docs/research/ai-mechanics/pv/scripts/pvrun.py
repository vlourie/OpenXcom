"""P0 vs P1 REAL AI COMPARISON (GO Vitali 27.10): 24 scenarios x 2 seeds x 2 configurations = 96 full bot battles.

D0 - the DEV stand with the release AI, BetterAI OFF (exe AL, OXCE_AI_RELEASE_BASE=1, options base);
D1 - the same with BetterAI ON (options better). The bot plays the player's side the same way in both (patch_al3).
Seeds fixed before the runs: the scenario's seed (scen.tsv) and seed + 1.

  pythonw pvrun.py --log logs/run.txt --phase check|main [--jobs 24]

check: M1 and L4, seed 1, D0 and D1 (4 battles of the 96: the main phase does not repeat them) plus save/load - a D0 / D1
fixture at player turn 3 loaded by the player's exe (P0 / P1) for one enemy turn (b0one.py, 4 runs outside the 96).
Everything under C:/OXCE_AIWorker/pvrun; the station's queue, tasks.json, state.json, stand*/, c1run and b0run untouched.
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
EXE = {"AL": HERE / "exe" / "AL" / "openxcom.exe", "P": HERE / "exe" / "P" / "openxcom_hd.exe"}
CFGS = {"base": {"oxceBetterAi": "false", "oxceBetterAiFixes": "true", "oxceBetterAiAi3": "false"},
        "better": {"oxceBetterAi": "true", "oxceBetterAiFixes": "true", "oxceBetterAiAi3": "false"}}
RB = {"OXCE_AI_RELEASE_BASE": "1"}
CONFIGS = {"D0": "base", "D1": "better"}
CHECK = ["M1", "L4"]
LOG = sys.stdout


def say(text):
    print(time.strftime("%H:%M:%S ") + text, file=LOG, flush=True)


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def write_cfgs():
    """options.cfg variants: the stand's config with the BetterAI keys explicit (as stage 0B)."""
    (HERE / "cfg").mkdir(exist_ok=True)
    base = STAND_CFG.read_text(encoding="utf-8-sig")
    for name, keys in CFGS.items():
        t = base
        keys = {**keys, "autosave": "true", "autosaveFrequency": "1", "autosaveSlots": "1", "skipNextTurnScreen": "true"}
        added = []
        for k, v in keys.items():
            t, n = re.subn(rf"(?m)^(\s*){k}: .*$", rf"\g<1>{k}: {v}", t)
            if not n:
                added.append(f"  {k}: {v}")
        if added:
            t = re.sub(r"(?m)^options:\s*$", "options:\n" + "\n".join(added), t, count=1)
        (HERE / "cfg" / f"{name}.cfg").write_bytes(t.encode("utf-8"))


def scen_rows():
    lines = (HERE / "scen.tsv").read_text(encoding="utf-8-sig").splitlines()
    head = lines[0].split("\t")
    return [dict(zip(head, l.split("\t"))) for l in lines[1:] if l.strip()]


def env_for(exe, cfg, extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("OXCE_AI_", "OXCE_HD_", "OXCE_U0_"))}
    env["PATH"] = DLL + os.pathsep + env.get("PATH", "")
    env.update({"OXCE_AI_GAME": str(GAME), "OXCE_AI_WORK": str(HERE / "work"), "OXCE_AI_EXE": str(EXE[exe]),
                "OXCE_AI_CFG": str(HERE / "cfg" / f"{cfg}.cfg")})
    env.update(extra)
    return env


def call(script, args, env, name):
    (HERE / "logs").mkdir(exist_ok=True)
    t0 = time.time()
    with open(HERE / "logs" / f"{name}.out", "w", encoding="utf-8") as f:
        code = subprocess.call([str(PY), "-u", str(HERE / script)] + args, env=env, stdout=f, stderr=subprocess.STDOUT,
                               stdin=subprocess.DEVNULL, cwd=str(HERE), creationflags=0x08000000)
    return name, code, time.time() - t0


def battle(cfg, sc, k):
    seed = str(int(sc["seed"]) + k - 1)
    name = f"{cfg}_{sc['id']}_s{k}"
    env = env_for("AL", CONFIGS[cfg], {**RB, "OXCE_AI_RACE": sc["race"]})
    return call("pvone.py", ["battle", name, sc["id"], seed, sc["mission"], sc["race"], sc["campaign"]], env, name)


def saveload(cfg, sc):
    """A D0/D1 fixture at player turn 3 (seed 1), then the player's exe with the same BetterAI setting loads it."""
    fx = f"sl_fx_{cfg}_{sc['id']}"
    env = env_for("AL", CONFIGS[cfg], {**RB, "OXCE_AI_RACE": sc["race"]})
    r1 = call("b0one.py", ["fx", fx, sc["id"], sc["seed"], sc["mission"], sc["race"], sc["campaign"], "3"], env, fx)
    got = HERE / "out" / fx / "fixture.sav"
    if not got.is_file():
        return [r1]
    rel = f"sl_rel_{cfg}_{sc['id']}"
    return [r1, call("b0one.py", ["release", rel, str(got)], env_for("P", CONFIGS[cfg], {}), rel)]


def done(name):
    return (HERE / "out" / name / "run.txt").is_file() and "result [AIRESULT]" in (HERE / "out" / name / "run.txt").read_text(encoding="utf-8")


def main():
    global LOG
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=24)
    ap.add_argument("--phase", default="check")
    ap.add_argument("--log", default="")
    a = ap.parse_args()
    if a.log:
        LOG = open(HERE / a.log, "a", encoding="utf-8")
    write_cfgs()
    rows = scen_rows()
    with open(HERE / "manifest.txt", "a", encoding="utf-8") as m:
        m.write(f"# {time.strftime('%Y-%m-%d %H:%M:%S')} phase={a.phase}\n")
        for p in sorted(list(EXE.values()) + list((HERE / "cfg").glob("*.cfg")) + list((HERE / "saves").glob("*.sav"))
                        + [HERE / "pvone.py", HERE / "pvrun.py", HERE / "b0one.py", HERE / "scen.tsv",
                           HERE / "stand" / "ai_probe.py", STAND_CFG]):
            m.write(f"{sha(p)} *{p}\n")
    jobs = []
    if a.phase == "check":
        for sc in rows:
            if sc["id"] in CHECK:
                jobs += [("b", c, sc, 1) for c in CONFIGS]
        jobs += [("sl", "D0", next(s for s in rows if s["id"] == "M1"), 0),
                 ("sl", "D1", next(s for s in rows if s["id"] == "L4"), 0)]
    else:
        for k in (1, 2):
            for sc in rows:
                for c in CONFIGS:
                    if not done(f"{c}_{sc['id']}_s{k}"):
                        jobs.append(("b", c, sc, k))
    say(f"phase {a.phase} jobs {len(jobs)} parallel {a.jobs}")
    t0 = time.time()
    with ThreadPoolExecutor(a.jobs) as pool:
        futs = [pool.submit(battle, c, sc, k) if kind == "b" else pool.submit(saveload, c, sc) for kind, c, sc, k in jobs]
        for n, fut in enumerate(as_completed(futs), 1):
            r = fut.result()
            for name, code, sec in (r if isinstance(r, list) else [r]):
                say(f"{n}/{len(jobs)} {name} code={code} {sec:.0f}s total={time.time() - t0:.0f}s")
    say("ALL DONE")


if __name__ == "__main__":
    main()
