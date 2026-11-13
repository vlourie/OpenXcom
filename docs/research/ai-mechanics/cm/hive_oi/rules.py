"""OPERATIONAL INTELLIGENCE, step 1: rule fields of named items from all rulesets of the mod, in load order, last field wins per file listing. Read only: the installed game is not changed.
Usage: rules.py NAME [NAME ...]"""
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path("E:/OpenXCom/Пиратки/Dioxine_XPiratez/user/mods/Piratez/Ruleset")
FIELDS = ("power", "damageType", "damageAlter", "RandomType", "ResistType", "ArmorEffectiveness", "ToArmorPre", "ToArmor", "ToHealth", "ToStun", "ToWound", "FixRadius", "blastRadius", "compatibleAmmo", "ammo", "clipSize", "battleType", "tuSnap", "tuAuto", "tuAimed", "tuMelee", "meleePower", "meleeType", "meleeAlter", "accuracySnap", "accuracyAuto", "accuracyAimed", "accuracyMelee", "autoShots", "shots", "snapRange", "aimRange", "autoRange", "dropoff", "maxRange", "costMelee", "time", "FireThreshold", "strengthApplied", "skillApplied", "damageBonus", "meleeBonus")
files = sorted(ROOT.glob("*.rul"))
texts = {f: f.read_text(encoding="utf-8", errors="replace").split("\n") for f in files}
for name in sys.argv[1:]:
    print("==", name)
    pat = re.compile(r"^  - (type|name|delete): " + re.escape(name) + r"\s*(#.*)?$")
    for f, L in texts.items():
        for i, s in enumerate(L):
            if pat.match(s):
                out = []
                j = i + 1
                while j < len(L) and j < i + 200 and not L[j].startswith("  - ") and (L[j].startswith(" ") or not L[j].strip()):
                    t = L[j].strip()
                    head = t.split(":")[0]
                    if head in FIELDS:
                        val = t.split(":", 1)[1].split("#")[0].strip()
                        if head == "compatibleAmmo":
                            am = []
                            k = j + 1
                            while k < len(L) and L[k].strip().startswith("- "):
                                am.append(L[k].strip()[2:].split("#")[0].strip())
                                k += 1
                            val = ",".join(am) or val
                        out.append(f"{head}={val}")
                    j += 1
                print(f"  {f.name}:{i + 1} " + " ".join(out))
