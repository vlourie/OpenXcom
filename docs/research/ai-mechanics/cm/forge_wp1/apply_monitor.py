"""AI FORGE WP1: the monitor into the isolated tree: its two files (CRLF, as the sources) and the read-only hooks. --files: the two files only. args: tree [--files]"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
tree = Path(sys.argv[1])
root = tree / "src"
for f in ("SchedulerIntegrityMonitor.h", "SchedulerIntegrityMonitor.cpp"):
    t = (HERE / "mon" / f).read_text(encoding="utf-8")
    (root / "Battlescape" / f).write_bytes(t.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"))
if "--files" in sys.argv:
    print("files copied")
    raise SystemExit


def sub(path, old, new):
    p = root / path
    b = p.read_bytes().decode("utf-8", errors="surrogateescape")
    if "\r\n" in b:
        old = old.replace("\n", "\r\n")
        new = new.replace("\n", "\r\n")
    assert b.count(old) == 1, (path, old[:70], b.count(old))
    p.write_bytes(b.replace(old, new).encode("utf-8", errors="surrogateescape"))


INC = '#include "../Battlescape/SchedulerIntegrityMonitor.h"\n'
sub("CMakeLists.txt", "  Battlescape/AiProbe.cpp\n", "  Battlescape/AiProbe.cpp\n  Battlescape/SchedulerIntegrityMonitor.cpp\n")

# the unit: the mark, hiding, time units
U = "Savegame/BattleUnit.cpp"
sub("Savegame/BattleUnit.h", "	void dontReselect();\n", "	void dontReselect(const char *by = __builtin_FUNCTION(), int line = __builtin_LINE());\n")
sub("Savegame/BattleUnit.h", "	void allowReselect();\n", "	void allowReselect(const char *by = __builtin_FUNCTION(), int line = __builtin_LINE());\n")
sub("Savegame/BattleUnit.h", "	void setHiding(bool hiding) { _hidingForTurn = hiding; };\n",
    "	void setHiding(bool hiding, const char *by = __builtin_FUNCTION(), int line = __builtin_LINE());\n")
sub(U, '''void BattleUnit::dontReselect()
{
	_dontReselect = true;
}
''', '''void BattleUnit::dontReselect(const char *by, int line)
{
	SchedulerIntegrityMonitor::mark(this, true, by, line);
	_dontReselect = true;
}
''')
sub(U, '''void BattleUnit::allowReselect()
{
	_dontReselect = false;
}
''', '''void BattleUnit::allowReselect(const char *by, int line)
{
	SchedulerIntegrityMonitor::mark(this, false, by, line);
	_dontReselect = false;
}

/**
 * Sets the unit's hiding flag.
 */
void BattleUnit::setHiding(bool hiding, const char *by, int line)
{
	if (hiding != _hidingForTurn)
	{
		SchedulerIntegrityMonitor::hide(this, hiding, by, line);
	}
	_hidingForTurn = hiding;
}
''')
sub(U, '''	_hitByFire = false;
	_dontReselect = false;
	_aiMedikitUsed = false;
''', '''	_hitByFire = false;
	if (_dontReselect)
	{
		SchedulerIntegrityMonitor::mark(this, false, "prepareNewTurn", __LINE__);
	}
	_dontReselect = false;
	_aiMedikitUsed = false;
''')
sub(U, '''	if (tu <= _tu)
	{
		_tu -= tu;
''', '''	if (tu <= _tu)
	{
		SchedulerIntegrityMonitor::tu(this, _tu, _tu - tu, "spend");
		_tu -= tu;
''')
sub(U, '''void BattleUnit::spendCost(const RuleItemUseCost& cost)
{
	_tu -= cost.Time;
''', '''void BattleUnit::spendCost(const RuleItemUseCost& cost)
{
	SchedulerIntegrityMonitor::tu(this, _tu, _tu - cost.Time, "cost");
	_tu -= cost.Time;
''')
sub(U, '''void BattleUnit::clearTimeUnits()
{
	_tu = 0;
''', '''void BattleUnit::clearTimeUnits()
{
	SchedulerIntegrityMonitor::tu(this, _tu, 0, "clear");
	_tu = 0;
''')
sub(U, '''	_tu = Clamp(tu, 0, (int)_stats.tu);
''', '''	SchedulerIntegrityMonitor::tu(this, _tu, Clamp(tu, 0, (int)_stats.tu), "set");
	_tu = Clamp(tu, 0, (int)_stats.tu);
''')
sub(U, '#include "BattleUnit.h"\n', '#include "BattleUnit.h"\n' + INC)

# the battle's engine: read-only getters and the points of the AI activation
G = "Battlescape/BattlescapeGame.cpp"
sub("Battlescape/BattlescapeGame.h", "	int getAIActionCounter() const { return _AIActionCounter; }\n",
    "	int getAIActionCounter() const { return _AIActionCounter; }\n"
    "	/// AI FORGE WP1: what the next decision reads and only this class holds.\n"
    "	bool forgeSecondMove() const { return _AISecondMove; }\n"
    "	bool forgeAggroSound() const { return _playedAggroSound; }\n"
    "	int forgeGuardedTurn() const { return _guardedTurn; }\n"
    "	const std::vector<int> &forgeGuardedUnits() const { return _guardedUnits; }\n")
sub(G, '''	AiProbe::passStartNote(_save, unit); // P0-D: the first unit of a side's turn - where its traversal began
''', '''	SchedulerIntegrityMonitor::tick(_save, unit, _AIActionCounter, _AISecondMove);
	AiProbe::passStartNote(_save, unit); // P0-D: the first unit of a side's turn - where its traversal began
''')
sub(G, '''does not attack after waking up even having full TU
	{
		if (carefulGuard(unit))
''', '''does not attack after waking up even having full TU
	{
		SchedulerIntegrityMonitor::gate(unit, _AIActionCounter, AiProbe::maxActions(unit));
		if (carefulGuard(unit))
''')
sub(G, '''	_guardedUnits.push_back(unit->getId());
''', '''	_guardedUnits.push_back(unit->getId());
	SchedulerIntegrityMonitor::guard(unit);
''')
sub(G, '''	action.number = _AIActionCounter;
	AiProbe::beforeThink(_save, unit);
''', '''	action.number = _AIActionCounter;
	SchedulerIntegrityMonitor::decide(_save, unit, _AIActionCounter, _AISecondMove);
	AiProbe::beforeThink(_save, unit);
''')
sub(G, '''	if (status != STATUS_PANICKING && status != STATUS_BERSERK) return false;
	_save->setSelectedUnit(unit);
''', '''	if (status != STATUS_PANICKING && status != STATUS_BERSERK) return false;
	_save->setSelectedUnit(unit);
	SchedulerIntegrityMonitor::panic(unit);
''')
sub(G, '#include "AiProbe.h"\n', '#include "AiProbe.h"\n#include "SchedulerIntegrityMonitor.h"\n')

# the stand: frame, stop, end, what it holds, the decision, the walk's end, a casualty; the flags stay out of a record's cfg
P = "Battlescape/AiProbe.cpp"
sub(P, '''	releaseSave = save;
	if (!active() || phase == FINISHED)
	{
		return;
	}
	// the camera's floor''', '''	releaseSave = save;
	if (!active() || phase == FINISHED)
	{
		return;
	}
	SchedulerIntegrityMonitor::frame(save);
	if (SchedulerIntegrityMonitor::stopRequested())
	{
		logResult(save, "timeout");
		phase = FINISHED;
		state->getGame()->quit();
		return;
	}
	// the camera's floor''')
sub(P, '''void logResult(SavedBattleGame *save, const char *how)
{
''', '''void logResult(SavedBattleGame *save, const char *how)
{
	SchedulerIntegrityMonitor::finish(save, how);
''')
sub(P, '''void logDecision(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action)
{
	if (!active())
	{
		return;
	}
''', '''void logDecision(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action)
{
	if (!active())
	{
		return;
	}
	SchedulerIntegrityMonitor::act(save, unit, action);
''')
sub(P, '''void postWalkBegin(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action, bool aiBranch)
{
	if (!active())
	{
		return;
	}
''', '''void postWalkBegin(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action, bool aiBranch)
{
	if (!active())
	{
		return;
	}
	SchedulerIntegrityMonitor::walkEnd(unit, action, aiBranch);
''')
sub(P, '''	bool dead, int hitSide, bool terrain)
{
	if (!active())
	{
		return;
	}
''', '''	bool dead, int hitSide, bool terrain)
{
	if (!active())
	{
		return;
	}
	SchedulerIntegrityMonitor::casualty(victim, dead);
''')
sub(P, '"OXCE_AI_SEED", "OXCE_AI_RECORD",', '"OXCE_AI_FORGE", "OXCE_AI_FORGE_DUMP", "OXCE_AI_FORGE_STOP", "OXCE_AI_SEED", "OXCE_AI_RECORD",')
sub(P, '''void battleOver(BattlescapeState *state, SavedBattleGame *save, bool abort)
{
	if (!active() || phase == FINISHED)''', '''/// AI FORGE WP1: what the stand itself holds between decisions and the next decision can read.
unsigned long long forgeHash()
{
	unsigned long long h = 1469598103934665603ULL;
	for (long long v : { counterUnit, counterTurn, counterSide, passStartTurn, passStartSide, passStartIdx, panicTurn, panicSide, panicValue,
		turnsPlayed, turnAtEnd, aiStartLogged, playerStartLogged, postWalkMeleeUnit })
	{
		h = (h ^ (unsigned long long)v) * 1099511628211ULL;
	}
	return h;
}

void battleOver(BattlescapeState *state, SavedBattleGame *save, bool abort)
{
	if (!active() || phase == FINISHED)''')
sub(P, '''bool secondPassWrapped(SavedBattleGame *, const BattleUnit *left, const BattleUnit''', '''unsigned long long forgeHash() { return 0; }
bool secondPassWrapped(SavedBattleGame *, const BattleUnit *left, const BattleUnit''')
sub(P, '#include "AiProbe.h"\n', '#include "AiProbe.h"\n#include "SchedulerIntegrityMonitor.h"\n')
sub("Battlescape/AiProbe.h", "namespace AiProbe\n{\n", "namespace AiProbe\n{\n\n/// AI FORGE WP1: what the stand holds between decisions, as one number.\nunsigned long long forgeHash();\n")

# the rest of the path: a reaction granted, a unit converted
sub("Battlescape/TileEngine.cpp", '''			// nice shot, kid. don't get cocky.
			result = true;
''', '''			// nice shot, kid. don't get cocky.
			SchedulerIntegrityMonitor::reaction(reactor->unit, unit);
			result = true;
''')
sub("Battlescape/TileEngine.cpp", '#include "TileEngine.h"\n', '#include "TileEngine.h"\n#include "SchedulerIntegrityMonitor.h"\n')
S = "Savegame/SavedBattleGame.cpp"
sub(S, '''	newUnit->dontReselect();
	return newUnit;
''', '''	SchedulerIntegrityMonitor::converted(unit, newUnit);
	newUnit->dontReselect();
	return newUnit;
''')
sub(S, '#include "SavedBattleGame.h"\n', '#include "SavedBattleGame.h"\n' + INC)
print("hooks in")
