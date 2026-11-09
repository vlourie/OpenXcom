"""AI FORGE WP3: the monitor's notes in a batch: what they are. args: batch"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import AIForgeStochasticOracle as o

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
for arm in o.BATCH[sys.argv[1]]:
    if o.ARMS[arm][0] is None:
        continue
    c = o.sic.check(o.Run(arm).lines)
    if c["notes"]:
        print(arm, c["notes"], c["first_notes"], {k: v for k, v in c["counts"].items() if k.startswith("tu") or k.startswith("sel")})
print("done")
