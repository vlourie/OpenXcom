"""SIDE-FIRST COMBAT: the isolated tree sfc/tree from tts/tree (git archive 07680cadb + al + al3 + TTS): the solver and its hooks taken back out, so the base is exactly D0, then the director's hooks. CRLF kept. args: tts tree, new tree"""
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
src = Path(sys.argv[1])
dst = Path(sys.argv[2])
if not dst.exists():
    shutil.copytree(src, dst)
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
GATE = "_AIActionCounter >= AiProbe::maxActions(unit) || !unit->reselectAllowed() || unit->getTurnsSinceStunned() == 0)) //stun check"
# 1. back to D0
sub(G, '''	// TACTICAL TURN SOLVER (bench, OXCE_AI_TTS): one brain over the side's turn says before the unit's think whose step comes next and what it is
	BattleAction ttsAction;
	BattleUnit *ttsOther = 0;
	const TurnSolver::Result tts = TurnSolver::step(_save, unit, &ttsAction, &ttsOther);
	if (tts == TurnSolver::SWITCH)
	{
		_AIActionCounter = 0;
		_save->setSelectedUnit(ttsOther);
		_parentState->updateSoldierInfo();
		getMap()->getCamera()->focusOn(ttsOther->getPosition());
		return;
	}
	if (tts == TurnSolver::ACT)
	{
		_AIActionCounter = 0;
	}
	if (tts != TurnSolver::ACT && (''' + GATE,
    '''	if (_AIActionCounter >= AiProbe::maxActions(unit) || !unit->reselectAllowed() || unit->getTurnsSinceStunned() == 0) //stun check''')
sub(G, '''	if (tts == TurnSolver::ACT)
	{
		const int number = action.number;
		action = ttsAction;
		action.number = number;
	}
	else
	{
		unit->think(&action);
	}

	if (action.type == BA_RETHINK)''', '''	unit->think(&action);

	if (action.type == BA_RETHINK)''')
sub(G, '''	if (tts != TurnSolver::ACT && (!weapon || !weapon->haveAnyAmmo()))''', '''	if (!weapon || !weapon->haveAnyAmmo())''')
sub(G, '''#include "BattlescapeGame.h"
#include "TurnSolver.h"
''', '''#include "BattlescapeGame.h"
''')
sub("CMakeLists.txt", '''  Battlescape/TurnSolver.cpp
''', '')
for f in ("TurnSolver.h", "TurnSolver.cpp"):
    (root / "Battlescape" / f).unlink()

# 2. the director's hooks
sub(G, '''	if (_AIActionCounter >= AiProbe::maxActions(unit) || !unit->reselectAllowed() || unit->getTurnsSinceStunned() == 0) //stun check''',
    '''	// SIDE-FIRST COMBAT (bench, OXCE_AI_SCD): one choice over the whole side - who acts next and what it does - before any unit thinks for itself
	BattleAction scdAction;
	BattleUnit *scdOther = 0;
	const SideCombatDirector::Result scd = SideCombatDirector::step(_save, unit, &scdAction, &scdOther);
	if (scd == SideCombatDirector::SWITCH)
	{
		_AIActionCounter = 0;
		_save->setSelectedUnit(scdOther);
		_parentState->updateSoldierInfo();
		getMap()->getCamera()->focusOn(scdOther->getPosition());
		return;
	}
	const bool scdLeads = scd == SideCombatDirector::ACT || scd == SideCombatDirector::CONSULT;
	if (scdLeads)
	{
		_AIActionCounter = 0;
	}
	if (!scdLeads && (_AIActionCounter >= AiProbe::maxActions(unit) || !unit->reselectAllowed() || unit->getTurnsSinceStunned() == 0)) //stun check''')
sub(G, '''	unit->think(&action);

	if (action.type == BA_RETHINK)
	{
		_parentState->debug("Rethink");''',
    '''	if (scd == SideCombatDirector::ACT)
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

	if (action.type == BA_RETHINK)
	{
		_parentState->debug("Rethink");''')
sub(G, '''	if (!weapon || !weapon->haveAnyAmmo())
	{
		if (unit->getOriginalFaction() != FACTION_PLAYER)
		{
			if ((unit->getOriginalFaction() == FACTION_HOSTILE && unit->getVisibleUnits()->empty()) || pickUpWeaponsMoreActively)''',
    '''	if (!scdLeads && (!weapon || !weapon->haveAnyAmmo()))
	{
		if (unit->getOriginalFaction() != FACTION_PLAYER)
		{
			if ((unit->getOriginalFaction() == FACTION_HOSTILE && unit->getVisibleUnits()->empty()) || pickUpWeaponsMoreActively)''')
sub(G, '''	AiProbe::logDecision(_save, unit, action);
	AiProbe::blockedStepDecide(_save, unit);''',
    '''	if (scd != SideCombatDirector::ACT && SideCombatDirector::afterThink(_save, unit, &action, scd, scdAction))
	{
		ai->clearReserve();
	}
	AiProbe::logDecision(_save, unit, action);
	AiProbe::blockedStepDecide(_save, unit);''')
sub(G, '''#include "BattlescapeGame.h"
''', '''#include "BattlescapeGame.h"
#include "SideCombatDirector.h"
''')
sub("CMakeLists.txt", '''  Battlescape/AiProbe.cpp
''', '''  Battlescape/AiProbe.cpp
  Battlescape/SideCombatDirector.cpp
''')
sub("Battlescape/AIModule.h", '''	BattleActionType getReserveMode();
''', '''	BattleActionType getReserveMode();
	/// SIDE-FIRST COMBAT (bench): the director's action follows no reservation of an earlier think.
	void clearReserve() { _reserve = BA_NONE; }
''')
print("tree ready")
