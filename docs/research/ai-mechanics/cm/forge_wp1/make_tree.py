"""AI FORGE WP1: the isolated tree forge/tree from sfc/tree (git archive 07680cadb + al + al3 + the director): the director and its hooks taken back out, so the base is exactly D0. CRLF kept. args: sfc tree, new tree"""
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
src = Path(sys.argv[1])
dst = Path(sys.argv[2])
shutil.copytree(src, dst, dirs_exist_ok=True)
root = dst / "src"


def sub(path, old, new):
    p = root / path
    b = p.read_bytes().decode("utf-8", errors="surrogateescape")
    crlf = "\r\n" in b
    if crlf:
        old = old.replace("\n", "\r\n")
        new = new.replace("\n", "\r\n")
    assert b.count(old) == 1, (path, old[:60], b.count(old))
    p.write_bytes(b.replace(old, new).encode("utf-8", errors="surrogateescape"))


G = "Battlescape/BattlescapeGame.cpp"
GATE = "_AIActionCounter >= AiProbe::maxActions(unit) || !unit->reselectAllowed() || unit->getTurnsSinceStunned() == 0"
b = (root / G).read_bytes().decode("utf-8", errors="surrogateescape")
crlf = "\r\n" in b
t = b.replace("\r\n", "\n")
a = t.index("	// SIDE-FIRST COMBAT (bench, OXCE_AI_SCD)")
e = t.index("	if (!scdLeads && (" + GATE + "))")
t = t[:a] + "	if (" + GATE + ")" + t[e + len("	if (!scdLeads && (" + GATE + "))"):]
(root / G).write_bytes((t.replace("\n", "\r\n") if crlf else t).encode("utf-8", errors="surrogateescape"))
sub(G, '''	if (scd == SideCombatDirector::ACT)
	{
		const int number = action.number;
		action = scdAction;
		action.number = number;
		ai->clearReserve();
	}
	else
	{
		unit->think(&action);
	}

	if (action.type == BA_RETHINK)''', '''	unit->think(&action);

	if (action.type == BA_RETHINK)''')
sub(G, "	if (!scdLeads && (!weapon || !weapon->haveAnyAmmo()))", "	if (!weapon || !weapon->haveAnyAmmo())")
sub(G, '''	if (scd != SideCombatDirector::ACT && SideCombatDirector::afterThink(_save, unit, &action, scd, scdAction))
	{
		ai->clearReserve();
	}
''', "")
sub(G, '''#include "SideCombatDirector.h"
''', "")
sub("CMakeLists.txt", '''  Battlescape/SideCombatDirector.cpp
''', "")
sub("Battlescape/AIModule.h", '''	/// SIDE-FIRST COMBAT (bench): the director's action follows no reservation of an earlier think.
	void clearReserve() { _reserve = BA_NONE; }
''', "")
for f in ("SideCombatDirector.h", "SideCombatDirector.cpp"):
    (root / "Battlescape" / f).unlink()
print("tree ready")
