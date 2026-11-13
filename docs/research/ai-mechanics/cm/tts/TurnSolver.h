#pragma once
/*
 * TACTICAL TURN SOLVER V0 (bench only, OXCE_AI_TTS=1): one brain over one turn of the hostile side.
 * It looks at who could do what, picks a unit and an action together (A clears the line of B, B fires), hands the first step
 * to the engine and looks again at what really happened. No random numbers, no bonuses, nothing changed after think().
 */

namespace OpenXcom
{

class SavedBattleGame;
class BattleUnit;
struct BattleAction;

namespace TurnSolver
{

enum Result
{
	PASS,   ///< nothing to do: the unit thinks as ever
	SWITCH, ///< the next step belongs to *other: select it and come back
	ACT,    ///< *action holds the step of this unit, instead of its think
};

/// The solver's say before the unit's think. Off (no OXCE_AI_TTS) it returns PASS and touches nothing.
Result step(SavedBattleGame *save, BattleUnit *unit, BattleAction *action, BattleUnit **other);

}

}
