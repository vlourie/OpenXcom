"""Головы LAMIA подряд одним заданием карты. Аргументы: внешность=основа через запятую (основа - имя в images/ без .png), сиды.
Для каждой: lm_flux.py head_<внешность> с LM_BASE = основа группы кожи."""
import os
import subprocess
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
IMG = r"E:\tmp\doll_ingame\lm\images"
seeds = sys.argv[2] if len(sys.argv) > 2 else "1,2"
for pair in sys.argv[1].split(","):
    look, base = pair.split("=")
    env = dict(os.environ, LM_BASE=os.path.join(IMG, base + ".png"))
    r = subprocess.run([sys.executable, "-X", "utf8", os.path.join(HERE, "lm_flux.py"), "head_" + look, seeds], env=env)
    print(look, base, "код", r.returncode, flush=True)
    if r.returncode:
        sys.exit(r.returncode)
