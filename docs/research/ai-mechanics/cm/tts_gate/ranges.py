"""NATURAL GATE, read only: range keys of the weapons in the candidates, from the installed Piratez rules; every file that defines them. Arg: Piratez root."""
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
W = ["STR_SONIC_PISTOL", "STR_HEAVY_CANNON", "STR_UAC_RIFLE", "STR_UAC_CARBINE", "STR_CHAINGUN", "STR_HEAVY_LASER", "STR_HEAVY_GAUSS", "STR_CD_RIFLE", "STR_ABC_GUN", "STR_SHOTGUN_PA", "STR_UAC_HEAVY_NAILGUN"]
K = re.compile(r"^\s+(aimRange|snapRange|autoRange|maxRange|minRange|dropoff|accuracyAimed|accuracySnap|accuracyAuto|power|damageType|shotgunPellets|confAimed|confSnap|confAuto|range):")
ROOT = Path(sys.argv[1]) / "user" / "mods" / "Piratez" / "Ruleset"
for f in sorted(ROOT.rglob("*.rul")):
    L = f.read_text(encoding="utf-8", errors="replace").splitlines()
    for i, s in enumerate(L):
        m = re.match(r"^\s*- type: (\S+)\s*$", s)
        if not m or m.group(1) not in W:
            continue
        keys = []
        for t in L[i + 1:i + 90]:
            if re.match(r"^\s*- type: ", t) or re.match(r"^\S", t):
                break
            if K.match(t):
                keys.append(t.strip())
        if any(k.split(":")[0] in ("aimRange", "snapRange", "autoRange", "maxRange", "minRange", "dropoff", "accuracySnap", "accuracyAimed", "power") for k in keys):
            print(f.name, i + 1, m.group(1), "; ".join(keys))
