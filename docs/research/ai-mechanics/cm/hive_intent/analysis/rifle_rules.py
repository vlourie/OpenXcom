"""Read only: the rifle's rules and the damage type behind it, from the Piratez ruleset, and how armour wear is defined for it. Usage: rifle_rules.py <item type> [<armor type>...]"""
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
R = Path("E:/OpenXCom/Пиратки/Dioxine_XPiratez/user/mods/Piratez/Ruleset")
want = sys.argv[1:]
for f in R.glob("*.rul"):
    lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
    for i, s in enumerate(lines):
        for w in want:
            if re.fullmatch(r"\s*- (type|name): " + re.escape(w) + r"\s*", s):
                ind = len(s) - len(s.lstrip())
                out = [s.strip()]
                for t in lines[i + 1 : i + 90]:
                    if t.strip() and len(t) - len(t.lstrip()) <= ind:
                        break
                    if re.search(r"(power|damageType|damageAlter|ToArmor|ToHealth|RandomType|ArmorEffect|FixRadius|frontArmor|sideArmor|leftArmor|rearArmor|underArmor|ammo|compatibleAmmo|clipSize|tuAimed|tuSnap|tuAuto|Range|ResistType|FireThreshold)", t):
                        out.append(t.strip())
                print(f.name, i + 1, " | ".join(out)[:700])
