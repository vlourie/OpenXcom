"""P0 vs P1 (GO Vitali 27.10, REAL AI COMPARISON): one full bot battle on the DEV stand. Started by pvrun.py with the run's
environment (exe AL, OXCE_AI_RELEASE_BASE=1, options.cfg base or better, OXCE_AI_RACE).

  pvone.py battle <name> <id> <seed> <mission> <race> <campaign>

Output: out/<name>/ (openxcom.log.gz - the whole battle log, run.txt). The game runs on the hidden desktop with SDL dummy
drivers, below normal priority (ai_probe.Hidden)."""
import gzip
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "stand"))
import ai_probe

OUT = HERE / "out"


def battle(name, sid, seed, mission, race, campaign):
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    for f in d.iterdir():
        if f.is_file():
            f.unlink()
    r = ai_probe.run(None, 60, name=name, timeout=3600, bot=True, seed=int(seed), campaign=str(HERE / "saves" / campaign),
                     mission=mission, squad=8)
    if r.log and Path(r.log).is_file():
        with open(r.log, "rb") as src, gzip.open(d / "openxcom.log.gz", "wb") as dst:
            shutil.copyfileobj(src, dst)
    res = r.tagged("[AIRESULT]")
    stuck = r.tagged("[AIPROBE] stuck")
    with open(d / "run.txt", "w", encoding="utf-8") as f:
        f.write(f"battle {sid} seed={seed} mission={mission} race={race} campaign={campaign} finished={r.finished} "
                f"seconds={r.seconds:.1f}\n")
        f.write(f"result {res[0] if res else '-'}\n")
        f.write(f"stuck {stuck[0] if stuck else '-'}\n")
    return 0 if res else 3


if __name__ == "__main__":
    if sys.argv[1] != "battle":
        raise SystemExit(f"unknown kind {sys.argv[1]}")
    sys.exit(battle(*sys.argv[2:8]))
