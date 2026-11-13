"""TACTICAL TURN SOLVER: the three hooks in handleAI and the build list, on the isolated tree. CRLF kept. arg: tree"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
root = Path(sys.argv[1]) / "src"


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
sub(G, '''	if (_AIActionCounter >= AiProbe::maxActions(unit) || !unit->reselectAllowed() || unit->getTurnsSinceStunned() == 0) //stun check''',
    '''	// TACTICAL TURN SOLVER (bench, OXCE_AI_TTS): one brain over the side's turn says before the unit's think whose step comes next and what it is
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
	if (tts != TurnSolver::ACT && (_AIActionCounter >= AiProbe::maxActions(unit) || !unit->reselectAllowed() || unit->getTurnsSinceStunned() == 0)) //stun check''')
sub(G, '''	unit->think(&action);

	if (action.type == BA_RETHINK)
	{
		_parentState->debug("Rethink");''',
    '''	if (tts == TurnSolver::ACT)
	{
		const int number = action.number;
		action = ttsAction;
		action.number = number;
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
    '''	if (tts != TurnSolver::ACT && (!weapon || !weapon->haveAnyAmmo()))
	{
		if (unit->getOriginalFaction() != FACTION_PLAYER)
		{
			if ((unit->getOriginalFaction() == FACTION_HOSTILE && unit->getVisibleUnits()->empty()) || pickUpWeaponsMoreActively)''')
sub(G, '''#include "BattlescapeGame.h"
''', '''#include "BattlescapeGame.h"
#include "TurnSolver.h"
''')
sub("CMakeLists.txt", '''  Battlescape/AiProbe.cpp
''', '''  Battlescape/AiProbe.cpp
  Battlescape/TurnSolver.cpp
''')
print("patched")
