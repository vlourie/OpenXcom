"""MISSION-LEVEL TACTICS STAGE 2, fact 2: the levels of the base's map blocks, vanilla against the mod, read from the MAP headers (read only).
A MAP file: 3 bytes - rows, columns, levels."""
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
for name, folder, pat in (("vanilla xcom1 XBASE", "E:/OpenXCom/Пиратки/Dioxine_XPiratez/standard/xcom1/MAPS", "XBASE_*.MAP"), ("Piratez XBR", "E:/OpenXCom/Пиратки/Dioxine_XPiratez/user/mods/Piratez/MAPS", "XBR_*.MAP")):
    c = Counter()
    for f in sorted(Path(folder).glob(pat)):
        h = f.read_bytes()[:3]
        c[(h[0], h[1], h[2])] += 1
    print(name, "(rows, columns, levels):", c.most_common())
