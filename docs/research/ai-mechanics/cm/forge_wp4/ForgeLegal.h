#pragma once
/*
 * AI FORGE WP4 (offline arena only): may the planned attack stand in for the attack think() chose?
 * The decision alone, from facts the monitor reads through the engine's own rules, so that every refusal can be tested without a battle (test_legal.cpp).
 */

namespace OpenXcom
{
namespace ForgeLegal
{

struct Facts
{
	bool sameUnit = false;    // the planned unit, and the action is its own
	bool planned = false;     // think() chose the type the plan starts from
	bool sameTarget = false;  // the tile the plan starts from
	bool sameWeapon = false;  // the weapon the plan starts from
	bool unitFree = false;    // its side's turn, not out, not marked dontReselect
	bool isAttack = false;    // the new action is a shot, a blow or a psi attack; never a throw, a walk
	bool weaponHeld = false;  // the new weapon is in a hand or built in
	int costTime = 0;         // the new action's cost in time units, 0: the weapon has no such action
	bool needsAmmo = false;
	bool hasAmmo = false;
	bool haveTU = false;
	bool useDelayOver = false; // the item's rule for the AI: not before this turn
	bool enemyThere = false;  // a living enemy on the new tile
	bool seen = false;        // in the unit's own visible list
	bool spotted = false;     // its side spotted it no longer ago than its intelligence
	bool inRange = false;     // the weapon's range; a blow: nothing beyond the reach below
	bool lineOfFire = false;  // a shot: the line of fire; a blow: the melee reach; psi: the line of sight, if the item asks for it
	bool targetAllowed = true; // psi only: the rules the player's own psi goes through and the AI's own limits
	bool inList = false;      // the engine's own list of candidates holds exactly this action, with a line of fire and this cost
	bool kneelByRule = false; // think()'s own rule accounts for the kneel it chose, so the same rule can be applied to the new action
};

/// Empty if the new action may stand; otherwise why not. fair: what the unit may know of the target.
inline const char *refusal(const Facts &f, const char *&fair)
{
	fair = "";
	if (!f.sameUnit) return "another_unit";
	if (!f.planned) return "not_the_planned_action";
	if (!f.sameTarget) return "another_target";
	if (!f.sameWeapon) return "another_weapon";
	if (!f.unitFree) return "unit_cannot_act";
	if (!f.isAttack) return "not_an_attack";
	if (!f.weaponHeld) return "weapon_not_held";
	if (f.costTime <= 0) return "no_such_action";
	if (f.needsAmmo && !f.hasAmmo) return "no_ammo";
	if (!f.haveTU) return "no_time_units";
	if (!f.useDelayOver) return "use_delay";
	if (!f.enemyThere) return "no_enemy_there";
	if (f.seen) fair = "seen";
	else if (f.spotted) fair = "spotted";
	else return "target_not_known";
	if (!f.inRange) return "out_of_range";
	if (!f.lineOfFire) return "no_line_of_fire";
	if (!f.targetAllowed) return "target_not_allowed";
	if (!f.inList) return "not_in_the_engine_list";
	if (!f.kneelByRule) return "kneel_not_by_rule";
	return "";
}

}
}
