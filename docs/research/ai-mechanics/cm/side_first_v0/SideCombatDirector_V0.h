#pragma once
/*
 * SIDE-FIRST COMBAT AI (bench only, OXCE_AI_SCD: 0 off, 1 shadow - every choice written, nothing changed, 2 on).
 * The hostile side's turn as one loop: what the side lawfully knows (BattleState), what each of its units could do (ActionGenerator), one
 * choice of who acts next and what it does (SidePlanner), the engine's own states to do it and a look at what really happened
 * (ActionExecutor), then the choice again. What it has no action for stays with the unit's own think: throws, psi, walks to melee,
 * escape, patrol, picking up weapons.
 */

namespace OpenXcom
{

class SavedBattleGame;
class BattleUnit;
struct BattleAction;

namespace SideCombatDirector
{

/// PASS - the unit thinks for itself; SWITCH - select *other and come back; ACT - do *action instead of thinking;
/// CONSULT - think first, a special action (throw, psi) of the unit's own goes before *action.
enum Result { PASS, SWITCH, ACT, CONSULT };

/// Before a hostile unit thinks.
Result step(SavedBattleGame *save, BattleUnit *unit, BattleAction *action, BattleUnit **other);
/// After the unit thought (PASS, CONSULT): the planned action in place of a consulted plain one, no shot that hurts the side more than the enemy.
/// @return true if the action is now the director's.
bool afterThink(SavedBattleGame *save, BattleUnit *unit, BattleAction *action, Result result, const BattleAction &planned);

}
}
