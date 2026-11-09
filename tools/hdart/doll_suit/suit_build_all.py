"""Собрать k=4 для всех 46 одиночных костюмов: hd_v1 из сида 1, hd_v2 из сида 2."""
import os
import sys
sys.stdout.reconfigure(encoding="utf-8")
from suit_flux import WHAT, OUT
from suit_build import build

for seed in (1, 2):
    out = os.path.join(OUT, "hd_v%d" % seed)
    for n in WHAT:
        build(n, seed, out)
    print(out, len(os.listdir(out)))
