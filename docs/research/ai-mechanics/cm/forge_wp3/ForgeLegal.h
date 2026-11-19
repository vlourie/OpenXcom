#pragma once
/*
 * AI FORGE WP2.1 (offline arena only): may the planned mode of a shot stand in for the mode think() chose?
 * The decision alone, from facts the monitor reads through the engine's own rules, so that every refusal can be tested without a battle (test_legal.cpp).
 */

namespace OpenXcom
{
namespace ForgeLegal
{

struct Facts
{
	bool stateSame = false;   // the chain and the state after think() are what the control A/A found
	bool sameUnit = false;    // the planned unit, and the action is its own
	bool planned = false;     // think() chose the mode the plan starts from
	bool sameTarget = false;  // the same tile
	bool sameWeapon = false;  // the same weapon
	bool unitFree = false;    // its side's turn, not out, not marked dontReselect
	bool isShot = false;      // the new mode is a shot
	bool weaponHeld = false;  // the weapon is in a hand or built in
	int costTime = 0;         // the new mode's cost in time units, 0: the weapon has no such mode
	bool needsAmmo = false;
	bool hasAmmo = false;
	bool haveTU = false;
	bool enemyThere = false;  // a living enemy on that tile
	bool seen = false;        // in the unit's own visible list
	bool spotted = false;     // its side spotted it no longer ago than its intelligence
	bool inRange = false;
	bool lineOfFire = false;
	bool kneelByRule = false; // think()'s own rule accounts for the kneel it chose, so the same rule can be applied to the new mode
};

/// Empty if the new mode may stand; otherwise why not. fair: what the unit may know of the target.
inline const char *refusal(const Facts &f, const char *&fair)
{
	fair = "";
	if (!f.stateSame) return "state_differs";
	if (!f.sameUnit) return "another_unit";
	if (!f.planned) return "not_the_planned_action";
	if (!f.sameTarget) return "another_target";
	if (!f.sameWeapon) return "another_weapon";
	if (!f.unitFree) return "unit_cannot_act";
	if (!f.isShot) return "not_a_shot";
	if (!f.weaponHeld) return "weapon_not_held";
	if (f.costTime <= 0) return "no_such_mode";
	if (f.needsAmmo && !f.hasAmmo) return "no_ammo";
	if (!f.haveTU) return "no_time_units";
	if (!f.enemyThere) return "no_enemy_there";
	if (f.seen) fair = "seen";
	else if (f.spotted) fair = "spotted";
	else return "target_not_known";
	if (!f.inRange) return "out_of_range";
	if (!f.lineOfFire) return "no_line_of_fire";
	if (!f.kneelByRule) return "kneel_not_by_rule";
	return "";
}

}
}
