"""CONTACT_COORDINATION_V0, run 7: the battle save of run 6 (arena_<label>_w0/piratez/<save>) loaded and played on by ai_probe with the player bot, arm CL.
--strip takes the hive line out of a copy first: an older save. Its own work folder arena_<prefix>_CL_M3_s1_w0 (pack_logs.py picks it up), output only under cmrun/.

  python load_hh.py <save label> <save file> <prefix> [--strip] [--turns 8] [--log f]"""
import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = Path(r"C:\OXCE_AIWorker\python\python.exe")
W = HERE / "work" / "oxce_ai_probe"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("label")
    ap.add_argument("save")
    ap.add_argument("prefix")
    ap.add_argument("--strip", action="store_true")
    ap.add_argument("--turns", type=int, default=8)
    ap.add_argument("--log", default="")
    a = ap.parse_args()
    (HERE / "logs").mkdir(exist_ok=True)
    if a.log:
        sys.stdout = open(HERE / a.log, "a", encoding="utf-8")
    src = W / f"arena_{a.label}_w0" / "piratez" / a.save
    keep = HERE / "logs" / f"{a.prefix}_{a.save}"
    text = src.read_bytes()
    removed = 0
    if a.strip:
        text, removed = re.subn(rb"(?m)^[ \t]*hive:[^\n]*\n", b"", text)
    keep.write_bytes(text)
    print(time.strftime("%Y-%m-%d %H:%M:%S"), f"save {src} -> {keep.name}, strip {a.strip}, removed {removed}, turns {a.turns}", flush=True)
    name = f"arena_{a.prefix}_CL_M3_s1_w0"
    args = [str(PY), "-u", str(HERE / "envrun.py"), str(HERE / "env_CL.txt"), str(HERE / "stand" / "ai_probe.py"), str(keep),
            "--bot", "--turns", str(a.turns), "--name", name, "--timeout", "900"]
    t0 = time.time()
    with open(HERE / "logs" / f"{name}.out", "w", encoding="utf-8") as f:
        code = subprocess.call(args, stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, cwd=str(HERE), creationflags=0x08000000)
    print(f"{name} code={code} {time.time() - t0:.0f}s", flush=True)
    print("ALL DONE", flush=True)


if __name__ == "__main__":
    if sys.stdout:
        sys.stdout.reconfigure(encoding="utf-8")
    main()
