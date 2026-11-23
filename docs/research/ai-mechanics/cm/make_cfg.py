"""COORDINATED_ENGAGEMENT_V1: options.cfg of the D0 configuration (P0 vs P1, pvrun.py write_cfgs, variant base) from the stand's
own config on this machine - the BetterAI keys explicit (BetterAI OFF, Fixes ON, Ai3 OFF) and the autosave keys pvrun set.
Writes cmrun/cfg/base.cfg and prints its sha256; the stand's config is only read.

  python make_cfg.py"""
import hashlib
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
STAND_CFG = Path(r"C:\OXCE_AIWorker\game\user\builds\piratez\options.cfg")
KEYS = {"oxceBetterAi": "false", "oxceBetterAiFixes": "true", "oxceBetterAiAi3": "false",
        "autosave": "true", "autosaveFrequency": "1", "autosaveSlots": "1", "skipNextTurnScreen": "true"}

t = STAND_CFG.read_text(encoding="utf-8-sig")
added = []
for k, v in KEYS.items():
    t, n = re.subn(rf"(?m)^(\s*){k}: .*$", rf"\g<1>{k}: {v}", t)
    if not n:
        added.append(f"  {k}: {v}")
if added:
    t = re.sub(r"(?m)^options:\s*$", "options:\n" + "\n".join(added), t, count=1)
out = HERE / "cfg" / "base.cfg"
out.parent.mkdir(exist_ok=True)
out.write_bytes(t.encode("utf-8"))
print("base.cfg", hashlib.sha256(out.read_bytes()).hexdigest(), "added", added or "-")
for k in KEYS:
    m = re.search(rf"(?m)^\s*{k}: .*$", t)
    print(" ", m.group(0).strip() if m else f"{k}: MISSING")
