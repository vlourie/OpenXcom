"""Stage 0B AI BASELINE ALIGNMENT (GO Vitali 27.10): fixtures, then one enemy turn per fixture on each configuration.

Everything under C:/OXCE_AIWorker/b0run; the station's queue, tasks.json, state.json, stand*/ and c1run are not touched.

  pythonw b0run.py --log logs/run.txt [--jobs 12] [--phase fx,run] [--only P0,D0] [--scen M1]
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
EXE = {"AL": HERE / "exe" / "AL" / "openxcom.exe", "E": HERE / "exe" / "E" / "openxcom.exe",
       "P": HERE / "exe" / "P" / "openxcom_hd.exe", "U": HERE / "exe" / "U0" / "openxcom.exe"}
# the 12 scenarios chosen before the runs: every non-UFO battle of the C1 list (a UFO battle of the arena can't be saved);
# M9 is the spare, used only when a fixture can't be made
SCEN = ["M1", "M2", "M3", "M5", "M8", "M10", "M11", "L4", "L5", "L10", "L11", "L12"]
SPARE = ["M9"]
FX_TURN = 3
# the protocol stand of the C1/C2/FF series (run_c1.py COMMON)
COMMON = {"OXCE_AI_FAST": "1", "OXCE_AI_LIGHTSKIP": "1", "OXCE_AI_AMBUSH_MEMO": "1", "OXCE_AI_ESCAPE_REACH_FIRST": "1",
          "OXCE_AI_WALKFOV_SKIP": "1", "OXCE_AI_LOADOUT_FIX": "1", "OXCE_AI_PANIC_TURN_FIX": "1",
          "OXCE_AI_PATROL_STUN_PREFIX": "1", "OXCE_AI_POSTWALK_FIX": "1", "OXCE_AI_OXCE_FIXES": "1", "OXCE_AI_RECORD": "1",
          "OXCE_AI_KEEP_DECIDE": "1"}
ACCEL0 = {"OXCE_AI_FAST": "0", "OXCE_AI_LIGHTSKIP": "0", "OXCE_AI_AMBUSH_MEMO": "0", "OXCE_AI_ESCAPE_REACH_FIRST": "0",
          "OXCE_AI_WALKFOV_SKIP": "0"}
CFGS = {"base": {"oxceBetterAi": "false", "oxceBetterAiFixes": "true", "oxceBetterAiAi3": "false"},
        "better": {"oxceBetterAi": "true", "oxceBetterAiFixes": "true", "oxceBetterAiAi3": "false"},
        "better3": {"oxceBetterAi": "true", "oxceBetterAiFixes": "true", "oxceBetterAiAi3": "true"}}
RB = {"OXCE_AI_RELEASE_BASE": "1"}
# name: (kind, exe, cfg, env)
CONFIGS = {
    "P0": ("release", "P", "base", {}), "P0b": ("release", "P", "base", {}),
    "P1": ("release", "P", "better", {}), "P1A": ("release", "P", "better3", {}),
    "D0": ("harness", "AL", "base", RB), "D0b": ("harness", "AL", "base", RB),
    "D0n": ("harness", "AL", "base", {**RB, **ACCEL0}), "D1": ("harness", "AL", "better", RB),
    "DH": ("harness", "AL", "base", {}), "DS": ("harness", "AL", "base", COMMON), "DSE": ("harness", "E", "base", COMMON),
    "U0": ("u0", "U", "base", {}), "U0b": ("u0", "U", "base", {}),
}
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
    """options.cfg variants: the stand's config, BetterAI keys explicit, the turn autosave on (only the player exe and
    v8.7.1 use it: the harness never autosaves)."""
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
    return {r["id"]: r for r in (dict(zip(head, l.split("\t"))) for l in lines[1:] if l.strip())}


def env_for(exe, cfg, extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("OXCE_AI_", "OXCE_HD_", "OXCE_U0_"))}
    env["PATH"] = DLL + os.pathsep + env.get("PATH", "")
    env.update({"OXCE_AI_GAME": str(GAME), "OXCE_AI_WORK": str(HERE / "work"), "OXCE_AI_EXE": str(EXE[exe]),
                "OXCE_AI_CFG": str(HERE / "cfg" / f"{cfg}.cfg")})
    env.update(extra)
    return env


def call(args, env, name):
    (HERE / "logs").mkdir(exist_ok=True)
    t0 = time.time()
    with open(HERE / "logs" / f"{name}.out", "w", encoding="utf-8") as f:
        code = subprocess.call([str(PY), "-u", str(HERE / "b0one.py")] + args, env=env, stdout=f, stderr=subprocess.STDOUT,
                               stdin=subprocess.DEVNULL, cwd=str(HERE), creationflags=0x08000000)
    return name, code, time.time() - t0


def fixture(sc, turn):
    name = f"fx_{sc['id']}_t{turn}"
    r = call(["fx", name, sc["id"], sc["seed"], sc["mission"], sc["race"], sc["campaign"], str(turn)],
             env_for("AL", "base", {}), name)
    got = HERE / "out" / name / "fixture.sav"
    if got.is_file():
        (HERE / "fixtures").mkdir(exist_ok=True)
        dst = HERE / "fixtures" / f"{sc['id']}.sav"
        dst.write_bytes(got.read_bytes())
    return r


def phase_fx(rows, ids, jobs):
    todo = [rows[i] for i in ids if not (HERE / "fixtures" / f"{i}.sav").is_file()]
    say(f"fixtures to make {len(todo)}")
    with ThreadPoolExecutor(jobs) as pool:
        for fut in as_completed([pool.submit(fixture, sc, FX_TURN) for sc in todo]):
            say("fx %s code=%d %.0fs" % fut.result())
    # a battle over before turn 3: turn 2
    late = [rows[i] for i in ids if not (HERE / "fixtures" / f"{i}.sav").is_file()]
    with ThreadPoolExecutor(jobs) as pool:
        for fut in as_completed([pool.submit(fixture, sc, 2) for sc in late]):
            say("fx %s code=%d %.0fs" % fut.result())
    have = [i for i in ids if (HERE / "fixtures" / f"{i}.sav").is_file()]
    say(f"fixtures {len(have)}: {' '.join(have)}")
    return have


def one(cfg, sid):
    kind, exe, cfgname, extra = CONFIGS[cfg]
    name = f"{cfg}_{sid}"
    fx = str(HERE / "fixtures" / f"{sid}.sav")
    if kind == "harness":
        extra = {**extra, "OXCE_AI_AUTOSAVE": "1"}  # exe AL: the player's turn autosave too (E does not know it)
    return call([kind, name, fx], env_for(exe, cfgname, extra), name)


def main():
    global LOG
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=12)
    ap.add_argument("--phase", default="fx,run")
    ap.add_argument("--only", default=",".join(CONFIGS))
    ap.add_argument("--scen", default="")
    ap.add_argument("--log", default="")
    a = ap.parse_args()
    if a.log:
        LOG = open(HERE / a.log, "a", encoding="utf-8")
    write_cfgs()
    rows = scen_rows()
    ids = [s for s in a.scen.split(",") if s] or SCEN
    with open(HERE / "manifest.txt", "a", encoding="utf-8") as m:
        m.write(f"# {time.strftime('%Y-%m-%d %H:%M:%S')} phase={a.phase} only={a.only}\n")
        for p in sorted(list(EXE.values()) + list((HERE / "cfg").glob("*.cfg")) + list((HERE / "saves").glob("*.sav"))
                        + [HERE / "b0one.py", HERE / "b0run.py", HERE / "stand" / "ai_probe.py", STAND_CFG]):
            m.write(f"{sha(p)} *{p}\n")
    if "fx" in a.phase:
        have = phase_fx(rows, ids, a.jobs)
        if len(have) < len(ids) and not a.scen:
            spare = phase_fx(rows, SPARE, a.jobs)
            say(f"spare fixtures: {spare}")
    if "run" in a.phase:
        fxs = [i for i in ids + SPARE if (HERE / "fixtures" / f"{i}.sav").is_file()][:len(ids)]
        with open(HERE / "manifest.txt", "a", encoding="utf-8") as m:
            for i in fxs:
                m.write(f"{sha(HERE / 'fixtures' / f'{i}.sav')} *fixtures/{i}.sav\n")
        todo = [(c, i) for i in fxs for c in a.only.split(",")]
        say(f"runs {len(todo)} jobs {a.jobs}")
        t0 = time.time()
        with ThreadPoolExecutor(a.jobs) as pool:
            for k, fut in enumerate(as_completed([pool.submit(one, c, i) for c, i in todo]), 1):
                say("%d/%d %s code=%d %.0fs" % ((k, len(todo)) + fut.result()))
        say(f"runs done {time.time() - t0:.0f}s")
    say("ALL DONE")


if __name__ == "__main__":
    main()
