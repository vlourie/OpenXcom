"""Commander stage on the work machine (rabota, C:/OXCE_AIWorker/cmrun; Vitali 29.10: «на рабочей машине можешь начать»).

Arm A of protocol v1: DEV from HEAD 07680cadb (exe/CM), the standard bot, FX (OXCE_AI_OXCE_FIXES=1), the record. An arm B
adds the candidate's flag (enemy only) - none yet, only after Vitali's decision on the first brick. One ai_arena.py run per
arm, scenario and seed (its own label); stand/ - stand2's ai_arena.py / ai_probe.py (as C1/AS) with scenario/ and missions/ of stand2,
envrun.py - the station's copy. Does not touch the station's queue, tasks.json, state.json, control.json, stand*/ or
others' folders; output only under cmrun/.

  python run_cm.py [--jobs N] [--arms A] [--scen M1,L4] [--seeds 1] [--prefix cm0] [--bflag OXCE_AI_X=1] [--log f]
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
# COORDINATED_ENGAGEMENT_V1 (GO Vitali 29.10): the D0 configuration of P0 vs P1 - the release AI on the stand
# (OXCE_AI_RELEASE_BASE=1, options base: BetterAI OFF, Fixes ON, Ai3 OFF - env file's OXCE_AI_CFG), only the speed flags, plus the
# record (log lines only)
COMMON_D0 = [
    "OXCE_AI_FAST=1", "OXCE_AI_LIGHTSKIP=1", "OXCE_AI_AMBUSH_MEMO=1", "OXCE_AI_ESCAPE_REACH_FIRST=1", "OXCE_AI_WALKFOV_SKIP=1",
    "OXCE_AI_RELEASE_BASE=1", "OXCE_AI_RECORD=1", "OXCE_AI_KEEP_DECIDE=1",
]
# TACTICAL STAGE 2: turn 2, target 520; 1000028 aimed+snap, 1000042 snap+snap, 1000055 aimed+snap, 1000057 aimed+aimed (BA_* 9/8)
ORDER_FIRE = "OXCE_AI_ORDER_FIRE=2:520:1000028=9.8,1000042=8.8,1000055=9.8,1000057=9.9"
# arm -> (env file of its exe, extra flags, flag set): A0 - exe CM of the base cm0; A - the candidate's exe (SR: STAGE_RALLY_V1)
# with its flag off, must repeat A0; B - the same with --bflag. D - exe D0 (HEAD + al.diff + al3.diff); C - exe CE (D0 + the
# commander) with its flag off, must repeat D; E - exe CE with the commander on
ARMS = {"A0": ("env_CM.txt", [], COMMON), "A": ("env_SR.txt", [], COMMON),
        "D": ("env_D0.txt", [], COMMON_D0), "C": ("env_CE.txt", [], COMMON_D0),
        "E": ("env_CE.txt", ["OXCE_AI_COORD_ENGAGE=1"], COMMON_D0),
        # AI_TACTICAL_DIRECTOR_V1 (GO Vitali 30.10): exe TD (D0 + the director) with its flag off (O, must repeat D) and on (T)
        "O": ("env_TD.txt", [], COMMON_D0), "T": ("env_TD.txt", ["OXCE_AI_TACTICAL_DIRECTOR=1"], COMMON_D0),
        # SIDE_TURN_ACTION_SCHEDULER stage 2 (GO Vitali 30.10): exe SC (D0 + the scheduler) with its flag off (Q, must repeat D)
        # and on (S)
        "Q": ("env_SC.txt", [], COMMON_D0), "S": ("env_SC.txt", ["OXCE_AI_SCHEDULER=1"], COMMON_D0),
        # stage 3: S plus the battle saved after pick 6 of hostile turn 1 (OXCE_AI_SCHED_SAVEAT, the record as S)
        "V": ("env_SC.txt", ["OXCE_AI_SCHEDULER=1", "OXCE_AI_SCHED_SAVEAT=1:6"], COMMON_D0),
        # stage 3 COVER: S plus at most two covering units per hostile turn (OXCE_AI_SCHED_COVER)
        "K": ("env_SC.txt", ["OXCE_AI_SCHEDULER=1", "OXCE_AI_SCHED_COVER=2"], COMMON_D0),
        # combat pilot (GO Vitali 30.10): exe S2 - the stage 2 scheduler (v4, no COVER code) with the scheduler on; arm A is D
        "N": ("env_S2.txt", ["OXCE_AI_SCHEDULER=1"], COMMON_D0),
        # TACTICAL STAGE 2 (GO Vitali 30.10, only M3 seed 1, enemy turn 2): exe BO (D0 + the experiment's orders); arm A is D.
        # FB - B FIRE CONCENTRATION: the four shooters fire at 520 (plan of TACTICAL_FLANKING_BATTLE_PLAN.md); AC - C DANGEROUS
        # ACTION AVOIDANCE: attacks nil by the rules are not made; FD - D COMBINED; BO - the orders off (must repeat D)
        "FB": ("env_BO.txt", [ORDER_FIRE], COMMON_D0), "AC": ("env_BO.txt", ["OXCE_AI_ORDER_AVOID=2"], COMMON_D0),
        "FD": ("env_BO.txt", [ORDER_FIRE, "OXCE_AI_ORDER_AVOID=2"], COMMON_D0), "BO": ("env_BO.txt", [], COMMON_D0),
        # COUNTERFIRE V0 (GO Vitali 30.10, five battles: M3 s1/s2, M6 s1/s2 and one repeat): exe CF (D0 + the counterfire rule);
        # arm A is D's saved logs (scpa_D_*)
        "CF": ("env_CF.txt", ["OXCE_AI_COUNTERFIRE=1"], COMMON_D0),
        # TACTICAL AI 2.0 STRIKE-V0 (GO Vitali 30.10, at most 12 short battles on): exe SV (D0 + SideContext, StrikeCoordinator,
        # OrderExecutor); SO - off (must repeat D), SH - shadow (every check written, nothing changed: must repeat D too), SN - on
        "SO": ("env_SV.txt", [], COMMON_D0), "SH": ("env_SV.txt", ["OXCE_AI_STRIKE=1"], COMMON_D0),
        "SN": ("env_SV.txt", ["OXCE_AI_STRIKE=2"], COMMON_D0)}
TURNS = 60


def scenarios():
    lines = (HERE / "scen.tsv").read_text(encoding="utf-8-sig").splitlines()
    head = lines[0].split("\t")
    return [dict(zip(head, l.split("\t"))) for l in lines[1:] if l.strip()]


def one(prefix, arm, sc, k):
    # seed k of a scenario: its base seed + k - 1 (k = 1 is the seed of scen.tsv, the same battle as C1/AS arm A)
    seed = str(int(sc["seed"]) + k - 1)
    label = f"{prefix}_{arm}_{sc['id']}_s{k}"
    envfile, extra, common = ARMS[arm]
    args = [str(PY), "-u", str(HERE / "envrun.py"), str(HERE / envfile), str(HERE / "stand" / "ai_arena.py"),
            "--missions", sc["mission"], "--seeds", seed, "--campaign", str(HERE / "saves" / sc["campaign"]),
            "--squad", "8", "--turns", str(TURNS), "--timeout", "3600", "--jobs", "1", "--label", label, "--strict-flags"]
    for kv in common + extra + [f"OXCE_AI_RACE={sc['race']}"]:
        args += ["--env", kv]
    out = HERE / "logs" / f"{label}.out"
    t0 = time.time()
    with open(out, "w", encoding="utf-8") as f:
        # CREATE_NO_WINDOW: started by pythonw from a task in the user's session, no console may show on the machine's screen
        code = subprocess.call(args, stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, cwd=str(HERE),
                               creationflags=0x08000000)
    return label, code, time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=19)
    ap.add_argument("--arms", default="A")
    ap.add_argument("--scen", default="")
    ap.add_argument("--seeds", default="1", help="seed numbers k per scenario, e.g. 1 or 1,2")
    ap.add_argument("--prefix", default="cm0", help="one prefix, or one per arm in the order of --arms (d0p,ce0)")
    ap.add_argument("--bflag", default="", help="the candidate's flag in arm B, OXCE_AI_*=value")
    ap.add_argument("--log", default="", help="progress to this file (pythonw has no stdout)")
    ap.add_argument("--turns", type=int, default=60, help="battle turn limit (short functional check: 8)")
    ap.add_argument("--pairs", default="", help="only these scenario:seed pairs, e.g. M10:1,L2:2 (instead of --scen x --seeds)")
    a = ap.parse_args()
    global TURNS
    TURNS = a.turns
    if a.bflag:
        if not a.bflag.startswith("OXCE_AI_") or "=" not in a.bflag:
            raise SystemExit(f"--bflag {a.bflag}: OXCE_AI_*=value")
        ARMS["B"] = ("env_SR.txt", [a.bflag], COMMON)
    arms = a.arms.split(",")
    if any(x not in ARMS for x in arms):
        raise SystemExit(f"--arms {a.arms}: known {sorted(ARMS)}")
    pres = a.prefix.split(",")
    if len(pres) not in (1, len(arms)):
        raise SystemExit(f"--prefix {a.prefix}: one, or one per arm of {a.arms}")
    prefix_of = dict(zip(arms, pres if len(pres) > 1 else pres * len(arms)))
    (HERE / "logs").mkdir(exist_ok=True)
    if a.log:
        sys.stdout = open(HERE / a.log, "a", encoding="utf-8")
    want = set(filter(None, a.scen.split(",")))
    ks = [int(x) for x in a.seeds.split(",") if x]
    todo = [(arm, sc, k) for sc in scenarios() if not want or sc["id"] in want for k in ks for arm in arms]
    if a.pairs:
        pairs = [(p.split(":")[0], int(p.split(":")[1])) for p in a.pairs.split(",") if p]
        by_id = {sc["id"]: sc for sc in scenarios()}
        if any(s not in by_id for s, _ in pairs):
            raise SystemExit(f"--pairs {a.pairs}: unknown scenario")
        todo = [(arm, by_id[s], k) for s, k in pairs for arm in arms]
    print(time.strftime("%Y-%m-%d %H:%M:%S"), f"prefix {a.prefix} arms {a.arms} bflag {a.bflag or '-'} turns {TURNS} runs {len(todo)} "
          f"jobs {a.jobs}", flush=True)
    t0 = time.time()
    with ThreadPoolExecutor(a.jobs) as pool:
        futs = [pool.submit(one, prefix_of[arm], arm, sc, k) for arm, sc, k in todo]
        for n, fut in enumerate(as_completed(futs), 1):
            label, code, sec = fut.result()
            print(f"{n}/{len(todo)} {label} code={code} {sec:.0f}s total={time.time() - t0:.0f}s", flush=True)
    print("ALL DONE", flush=True)


if __name__ == "__main__":
    if sys.stdout:
        sys.stdout.reconfigure(encoding="utf-8")
    main()
