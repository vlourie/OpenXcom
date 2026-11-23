"""TACTICAL TURN SOLVER V0: one run of the declared list. A save of saves_tts/ loaded and played by ai_probe, arm ZD (exe D0) or ZS (exe TS, the solver on).
Its own work folder arena_<prefix>_<arm>_<scen>_s<seed>_w0 (pack_logs.py picks it up), output only under cmrun/.

  python load_tts.py <arm> <save file> <prefix> <scen> <seed> <turns> <bot 0/1> [--log f]"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = Path(r"C:\OXCE_AIWorker\python\python.exe")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("arm", choices=["ZD", "ZS"])
    ap.add_argument("save")
    ap.add_argument("prefix")
    ap.add_argument("scen")
    ap.add_argument("seed")
    ap.add_argument("turns", type=int)
    ap.add_argument("bot", type=int)
    ap.add_argument("--log", default="")
    a = ap.parse_args()
    (HERE / "logs").mkdir(exist_ok=True)
    if a.log:
        sys.stdout = open(HERE / a.log, "a", encoding="utf-8")
    keep = HERE / "logs" / f"{a.prefix}_{a.save}"
    keep.write_bytes((HERE / "saves_tts" / a.save).read_bytes())
    name = f"arena_{a.prefix}_{a.arm}_{a.scen}_s{a.seed}_w0"
    print(time.strftime("%Y-%m-%d %H:%M:%S"), f"{name}: save {a.save}, turns {a.turns}, bot {a.bot}", flush=True)
    args = [str(PY), "-u", str(HERE / "envrun.py"), str(HERE / f"env_{a.arm}.txt"), str(HERE / "stand" / "ai_probe.py"), str(keep)]
    if a.bot:
        args.append("--bot")
    args += ["--turns", str(a.turns), "--name", name, "--timeout", "900"]
    t0 = time.time()
    with open(HERE / "logs" / f"{name}.out", "w", encoding="utf-8") as f:
        code = subprocess.call(args, stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, cwd=str(HERE), creationflags=0x08000000)
    print(f"{name} code={code} {time.time() - t0:.0f}s", flush=True)
    print("ALL DONE", flush=True)


if __name__ == "__main__":
    if sys.stdout:
        sys.stdout.reconfigure(encoding="utf-8")
    main()
