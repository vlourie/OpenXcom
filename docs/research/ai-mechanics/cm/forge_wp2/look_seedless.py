"""AI FORGE WP2: how the auxiliary generator moved through the battle, A1 against S1. Reads logs only."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import AIForgeCounterfactualRunner as rr

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
for name in ("A1", "S1"):
    run = rr.Run(name)
    fp = [(n, d) for n, _, _, d in run.events() if d.get("ev") == "fp"]
    ls = [d["L"] for _, d in fp]
    moves = [(fp[i][0], fp[i][1]["t"], fp[i][1]["s"]) for i in range(1, len(fp)) if ls[i] != ls[i - 1]]
    print(name, "fingerprints", len(fp), "distinct L", len(set(ls)), "moved between", len(moves), "first", moves[:6], "last", moves[-3:])
    print(" L first", ls[0], "last", ls[-1], "V first", fp[0][1]["V"], "V last", fp[-1][1]["V"], "distinct V", len({d["V"] for _, d in fp}))
