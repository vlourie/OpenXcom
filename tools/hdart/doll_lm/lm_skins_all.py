"""Четыре группы кожи подряд одним заданием карты: lm_flux.py skin_<группа> 1,2 на основе LM_BASE."""
import os
import subprocess
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
for g in ("green", "pink", "beige", "brown"):
    r = subprocess.run([sys.executable, "-X", "utf8", os.path.join(HERE, "lm_flux.py"), "skin_" + g, "1,2"])
    print(g, "код", r.returncode, flush=True)
    if r.returncode:
        sys.exit(r.returncode)
