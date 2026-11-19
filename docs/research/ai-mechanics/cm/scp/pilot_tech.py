"""SIDE_TURN_ACTION_SCHEDULER combat pilot: technical safety per scenario and seed.
1) arm A (D0) against the archived P0 baseline d0p: the record (AIDECIDE/AIEXEC/AISCHED/AICASUALTY) must be IDENTICAL -
   the baseline is the real one and deterministic;
2) arm B against arm A (sc_check.py): the engine's limits (activations per unit and turn within the engine's bound, no repeat
   in a first-pass round or in the second pass, time units never rising, decisions per activation), LIMITS OK or VIOLATED.

  py -3.13 -I pilot_tech.py <out dir> <prefix A> <prefix B> <baseline prefix> <detail out>"""
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT, PA, PB, P0, DET = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], Path(sys.argv[5])
HERE = Path(__file__).resolve().parent
PY = sys.executable
labels = sorted(p.name[len(PA) + 3:] for p in Path(OUT).glob(f"{PA}_D_*"))
ident = limits = 0
with open(DET, "w", encoding="utf-8-sig") as det:
    for sk in labels:
        a, b, z = f"{PA}_D_{sk}", f"{PB}_N_{sk}", f"{P0}_D_{sk}"
        c = subprocess.run([PY, "-I", str(HERE / "sc_cost.py"), OUT, z, a], capture_output=True, text=True, encoding="utf-8").stdout
        same = "IDENTICAL" in c
        ident += same
        k = subprocess.run([PY, "-I", str(HERE / "sc_check.py"), OUT, b, a], capture_output=True, text=True, encoding="utf-8").stdout
        ok = "LIMITS OK" in k
        limits += ok
        keep = [l for l in k.splitlines() if any(w in l for w in ("pass integrity", "activations over", "TU rise", "decisions at TU", "LIMITS", "picks out of"))]
        det.write(f"== {sk}: A vs {P0} {'IDENTICAL' if same else 'DIFFERENT'}\n{c}" + "\n".join(keep) + "\n\n")
        print(f"{sk}: A=={P0} {'IDENTICAL' if same else 'DIFFERENT'}; B limits {'OK' if ok else 'VIOLATED'}")
print(f"A identical to {P0}: {ident} of {len(labels)}; B LIMITS OK: {limits} of {len(labels)}")
