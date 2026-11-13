"""SIDE_TURN_ACTION_SCHEDULER stage 3, step 1: the battle saved in the middle of the hostile turn (arm V: OXCE_AI_SCHED_SAVEAT,
work/oxce_ai_probe/arena_<label>_w0/piratez/sched_<turn>_<pick>.asav) loaded and played on by ai_probe with the player bot:
arm S - exe SC with the scheduler, arm Q - the same exe without it (D0). Its own work folders arena_<prefix>_<arm>_<scen>_s1_w0
(pack_logs.py picks them up), output only under cmrun/.

  python run cm_load.py <save label> <save file> <prefix> [--turns 2] [--log f]"""
import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = Path(r"C:\OXCE_AIWorker\python\python.exe")
W = HERE / "work" / "oxce_ai_probe"
ARMS = {"S": "env_SL.txt", "Q": "env_QL.txt"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("label")
    ap.add_argument("save")
    ap.add_argument("prefix")
    ap.add_argument("--turns", type=int, default=2)
    ap.add_argument("--log", default="")
    a = ap.parse_args()
    (HERE / "logs").mkdir(exist_ok=True)
    if a.log:
        sys.stdout = open(HERE / a.log, "a", encoding="utf-8")
    src = W / f"arena_{a.label}_w0" / "piratez" / a.save
    scen = a.label.split("_")[2]
    keep = HERE / "logs" / f"{a.label}_{a.save}"
    shutil.copyfile(src, keep)  # the save itself stays with the logs: the work folder of the arena is reused
    print(time.strftime("%Y-%m-%d %H:%M:%S"), f"save {src} -> {keep.name}, prefix {a.prefix}, turns {a.turns}", flush=True)
    for arm, envfile in ARMS.items():
        name = f"arena_{a.prefix}_{arm}_{scen}_s1_w0"
        args = [str(PY), "-u", str(HERE / "envrun.py"), str(HERE / envfile), str(HERE / "stand" / "ai_probe.py"), str(keep),
                "--bot", "--turns", str(a.turns), "--name", name, "--timeout", "900"]
        t0 = time.time()
        with open(HERE / "logs" / f"{name}.out", "w", encoding="utf-8") as f:
            code = subprocess.call(args, stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, cwd=str(HERE),
                                   creationflags=0x08000000)
        print(f"{arm} {name} code={code} {time.time() - t0:.0f}s", flush=True)
    print("ALL DONE", flush=True)


if __name__ == "__main__":
    if sys.stdout:
        sys.stdout.reconfigure(encoding="utf-8")
    main()
