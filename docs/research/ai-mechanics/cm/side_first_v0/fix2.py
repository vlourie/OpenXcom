"""SIDE-FIRST COMBAT V0.1: the hand-back counter in the director's journal. arg: SideCombatDirector.cpp"""
import sys
from pathlib import Path

p = Path(sys.argv[1])
s = p.read_text(encoding="utf-8")
pairs = [
    ("keptSpecial = 0, vetoes = 0, switches = 0, overBudget = 0;", "keptSpecial = 0, vetoes = 0, switches = 0, overBudget = 0, backs = 0;"),
    ("consults = keptSpecial = vetoes = switches = overBudget = 0;", "consults = keptSpecial = vetoes = switches = overBudget = backs = 0;"),
    ('<< ",\\"banned\\":" << bs.banned.size();', '<< ",\\"banned\\":" << bs.banned.size() << ",\\"backs\\":" << backs;'),
]
for a, b in pairs:
    assert s.count(a) == 1, a
    s = s.replace(a, b)
p.write_text(s, encoding="utf-8")
print("ok")
