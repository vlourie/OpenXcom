// AI FORGE WP2.1: every refusal of an alternative, with no battle. Each case takes a fully legal shot and breaks one fact.
#include <cstdio>
#include <cstring>
#include "ForgeLegal.h"

using OpenXcom::ForgeLegal::Facts;
using OpenXcom::ForgeLegal::refusal;

static int fails = 0;

static Facts legal()
{
	Facts f;
	f.stateSame = f.sameUnit = f.planned = f.sameTarget = f.sameWeapon = f.unitFree = f.isShot = f.weaponHeld = true;
	f.costTime = 23;
	f.needsAmmo = f.hasAmmo = f.haveTU = f.enemyThere = f.seen = f.inRange = f.lineOfFire = f.kneelByRule = true;
	return f;
}

static void expect(const char *name, const Facts &f, const char *why, const char *wantFair = nullptr)
{
	const char *fair = "?";
	const char *got = refusal(f, fair);
	const bool ok = !strcmp(got, why) && (!wantFair || !strcmp(fair, wantFair));
	fails += ok ? 0 : 1;
	printf("%s %s: %s fair=%s\n", ok ? "ok  " : "FAIL", name, got[0] ? got : "legal", fair);
}

#define BREAK(name, stmt, why) { Facts f = legal(); stmt; expect(name, f, why); }

int main()
{
	expect("a legal shot, target seen", legal(), "", "seen");
	{ Facts f = legal(); f.seen = false; f.spotted = true; expect("a legal shot, target spotted by the side", f, "", "spotted"); }
	{ Facts f = legal(); f.needsAmmo = false; f.hasAmmo = false; expect("a weapon that needs no ammo", f, "", "seen"); }
	BREAK("the state after think() differs", f.stateSame = false, "state_differs");
	BREAK("another unit decides", f.sameUnit = false, "another_unit");
	BREAK("think() chose another action", f.planned = false, "not_the_planned_action");
	BREAK("think() chose another target", f.sameTarget = false, "another_target");
	BREAK("think() chose another weapon", f.sameWeapon = false, "another_weapon");
	BREAK("dontReselect, out or not its side's turn", f.unitFree = false, "unit_cannot_act");
	BREAK("the new mode is not a shot (walk, throw, psi, melee)", f.isShot = false, "not_a_shot");
	BREAK("the weapon is not in hand", f.weaponHeld = false, "weapon_not_held");
	BREAK("the weapon has no such mode", f.costTime = 0, "no_such_mode");
	BREAK("no ammo for the mode", f.hasAmmo = false, "no_ammo");
	BREAK("not enough time units", f.haveTU = false, "no_time_units");
	BREAK("no living enemy on the tile", f.enemyThere = false, "no_enemy_there");
	{ Facts f = legal(); f.seen = false; f.spotted = false; expect("FAIR: the target is hidden from it", f, "target_not_known", ""); }
	BREAK("out of range", f.inRange = false, "out_of_range");
	BREAK("no line of fire", f.lineOfFire = false, "no_line_of_fire");
	BREAK("think()'s kneel does not follow its rule", f.kneelByRule = false, "kneel_not_by_rule");
	// the order: the state check comes before anything else; the planned mode before the mode's own rules
	{ Facts f; expect("nothing holds: the state first", f, "state_differs"); }
	{ Facts f = legal(); f.planned = false; f.haveTU = false; expect("think() chose otherwise and no TU: the choice first", f, "not_the_planned_action"); }
	{ Facts f = legal(); f.seen = false; f.lineOfFire = false; expect("hidden and no line: FAIR first", f, "target_not_known", ""); }
	printf("FAILS %d\n", fails);
	return fails ? 1 : 0;
}
