/*
 * TACTICAL TURN SOLVER V0 (bench only, OXCE_AI_TTS=1), see TurnSolver.h.
 * The one dependency it knows: B has no line to T only because its comrade A stands in it, B has no cell of its own to fire from,
 * and A has a free cell to step to. Then: A walks, the solver looks at the real state, B fires if the real line is there.
 */
#include "TurnSolver.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <set>
#include <sstream>
#include <vector>
#include "AiProbe.h"
#include "Pathfinding.h"
#include "TileEngine.h"
#include "../Engine/Logger.h"
#include "../Engine/RNG.h"
#include "../Mod/Armor.h"
#include "../Mod/RuleDamageType.h"
#include "../Mod/RuleItem.h"
#include "../Savegame/BattleItem.h"
#include "../Savegame/BattleUnit.h"
#include "../Savegame/SavedBattleGame.h"
#include "../Savegame/Tile.h"

namespace OpenXcom
{
namespace TurnSolver
{
namespace
{

/// What one unit's best shot at a target is worth: the mode, what it costs, the expected damage of the action.
struct Shot
{
	BattleActionType type = BA_NONE;
	BattleItem *weapon = 0;
	int tu = 0;
	double value = 0;
};

/// The chain under way.
struct Plan
{
	int stage = 0; // 0 none, 1 A is to walk, 2 A walked: look at the real state, 3 B is to fire, 4 B fired: write the result down
	BattleUnit *a = 0, *b = 0, *t = 0;
	Position from, cell;
	int cellTu = 0, tHealth = 0, tArmor = 0;
	double valueA = 0, valueB = 0;
};

Plan plan;
const SavedBattleGame *planSave = 0;
int planTurn = -1;
std::set<std::pair<int, int>> tried; // (B, T) of this turn: a chain or its refusal is not looked for again until the turn ends
long long usTurn = 0, usTotal = 0;
int callsTurn = 0;

std::string pos(const Position &p)
{
	std::ostringstream s;
	s << "[" << p.x << "," << p.y << "," << p.z << "]";
	return s.str();
}

void journal(SavedBattleGame *save, const std::string &body)
{
	Log(LOG_INFO) << "[AITTS] {\"turn\":" << save->getTurn() << ",\"rng\":" << RNG::getSeed() << "," << body << "}";
}

std::string unitNote(const char *name, const BattleUnit *u)
{
	std::ostringstream s;
	s << "\"" << name << "\":{\"id\":" << u->getId() << ",\"pos\":" << pos(u->getPosition()) << ",\"tu\":" << u->getTimeUnits()
		<< ",\"hp\":" << u->getHealth() << "}";
	return s.str();
}

/// Can this unit fire from where it stands, by the two checks the AI's selectNearestTarget makes (sight, then line)?
bool lineNow(SavedBattleGame *save, BattleUnit *from, BattleUnit *t)
{
	TileEngine *te = save->getTileEngine();
	if (!te->visible(from, t->getTile()))
	{
		return false;
	}
	BattleAction a;
	a.actor = from;
	a.target = t->getPosition();
	Position origin = te->getOriginVoxel(a, 0), scan;
	return te->canTargetUnit(&origin, t->getTile(), &scan, from, false);
}

/// The same question with A taken off its tile, or put on the cell if there is one; A is back before it returns.
bool lineIfMoved(SavedBattleGame *save, BattleUnit *from, BattleUnit *t, BattleUnit *a, const Position *cell)
{
	Tile *old = a->getTile();
	const Position oldPos = a->getPosition();
	old->setUnit(0);
	Tile *to = cell ? save->getTile(*cell) : 0;
	if (to)
	{
		to->setUnit(a);
		a->setPosition(*cell, false);
	}
	const bool ok = lineNow(save, from, t);
	if (to)
	{
		to->setUnit(0);
		a->setPosition(oldPos, false);
	}
	old->setUnit(a);
	return ok;
}

/// The best shot this unit's main weapon gives at T: expected hits of one action x what a hit leaves past the front armor (the mean roll).
Shot bestShot(SavedBattleGame *save, BattleUnit *u, BattleUnit *t)
{
	Shot best;
	BattleItem *w = u->getMainHandWeapon(true);
	if (!w || w->getRules()->getBattleType() != BT_FIREARM || !w->haveAnyAmmo())
	{
		return best;
	}
	if (Position::distance2d(u->getPosition(), t->getPosition()) > w->getRules()->getMaxRange())
	{
		return best;
	}
	for (BattleActionType type : { BA_AUTOSHOT, BA_SNAPSHOT, BA_AIMEDSHOT })
	{
		BattleActionCost cost(type, u, w);
		if (!cost.haveTU())
		{
			continue;
		}
		BattleActionAttack attack = BattleActionAttack::GetBeforeShoot(cost);
		if (!attack.damage_item || attack.damage_item->getRules()->getExplosionRadius(attack) != 0)
		{
			continue; // no blasts in V0: its comrades stand close
		}
		const RuleItem *ammo = attack.damage_item->getRules();
		const RuleDamageType *dt = ammo->getDamageType();
		const double hit = std::max(0.0, ammo->getPowerBonus(attack) * (double)t->getArmor()->getDamageModifier(dt->ResistType) - t->getArmor(SIDE_FRONT) * (double)dt->ArmorEffectiveness);
		const int shots = type == BA_AUTOSHOT ? w->getRules()->getConfigAuto()->shots : type == BA_SNAPSHOT ? w->getRules()->getConfigSnap()->shots : w->getRules()->getConfigAimed()->shots;
		const double value = BattleUnit::getFiringAccuracy(attack, save->getMod()) / 100.0 * shots * hit;
		if (best.type == BA_NONE || value > best.value)
		{
			best.type = type;
			best.weapon = w;
			best.tu = cost.Time;
			best.value = value;
		}
	}
	return best;
}

bool ready(const BattleUnit *u)
{
	return u && !u->isOut() && u->getStatus() == STATUS_STANDING && u->getFaction() == FACTION_HOSTILE && u->getOriginalFaction() == FACTION_HOSTILE
		&& u->isSmallUnit() && u->reselectAllowed() && u->getTurnsSinceStunned() != 0;
}

/// A cell of its own B could walk to and still fire from: then B does not depend on A.
bool ownCell(SavedBattleGame *save, BattleUnit *b, BattleUnit *t, const Shot &shot)
{
	BattleActionCost cost(shot.type, b, shot.weapon);
	TileEngine *te = save->getTileEngine();
	for (int index : save->getPathfinding()->findReachable(b, cost))
	{
		const Position c = save->getTileCoords(index);
		Tile *tile = save->getTile(c);
		if (c == b->getPosition() || !tile || tile->getUnit())
		{
			continue;
		}
		Position origin = c.toVoxel() + Position(8, 8, b->getHeight() + b->getFloatHeight() - tile->getTerrainLevel() - 4), scan;
		if (te->canTargetUnit(&origin, t->getTile(), &scan, b, false))
		{
			return true;
		}
	}
	return false;
}

/// Is p within one tile and a half of the line from a to b, between them?
bool nearLine(const Position &p, const Position &a, const Position &b)
{
	const double dx = b.x - a.x, dy = b.y - a.y, len2 = dx * dx + dy * dy;
	if (len2 <= 0)
	{
		return false;
	}
	const double k = ((p.x - a.x) * dx + (p.y - a.y) * dy) / len2;
	if (k <= 0 || k >= 1)
	{
		return false;
	}
	const double ex = a.x + k * dx - p.x, ey = a.y + k * dy - p.y;
	return ex * ex + ey * ey <= 2.25;
}

/// The cheapest free cell of A's reach from which B's line is there with A standing on the cell.
bool findCell(SavedBattleGame *save, BattleUnit *a, BattleUnit *b, BattleUnit *t, Position &cell, int &tu)
{
	Pathfinding *pf = save->getPathfinding();
	const std::vector<int> reach = pf->findReachable(a, BattleActionCost());
	for (int index : reach)
	{
		const Position c = save->getTileCoords(index);
		Tile *tile = save->getTile(c);
		if (c == a->getPosition() || c.z != a->getPosition().z || !tile || tile->getUnit() || tile->getDangerous())
		{
			continue;
		}
		if (lineIfMoved(save, b, t, a, &c))
		{
			cell = c;
			tu = pf->reachedTU(c);
			return true;
		}
	}
	return false;
}

void candidate(SavedBattleGame *save, const BattleUnit *a, const BattleUnit *b, const BattleUnit *t, const char *why, double valueA, double valueB)
{
	std::ostringstream s;
	s << "\"ev\":\"cand\",\"why\":\"" << why << "\"," << unitNote("A", a) << "," << unitNote("B", b) << "," << unitNote("T", t)
		<< ",\"valueA\":" << valueA << ",\"valueB\":" << valueB << ",\"us\":" << usTurn;
	journal(save, s.str());
}

/// Looks over the side for one chain worth starting.
bool search(SavedBattleGame *save)
{
	std::vector<BattleUnit*> known;
	std::vector<BattleUnit*> side;
	for (BattleUnit *u : *save->getUnits())
	{
		if (u->getFaction() == FACTION_HOSTILE && !u->isOut())
		{
			side.push_back(u);
			known.insert(known.end(), u->getVisibleUnits()->begin(), u->getVisibleUnits()->end()); // what the side's own eyes see now, nothing else
		}
	}
	std::sort(known.begin(), known.end(), [](const BattleUnit *x, const BattleUnit *y) { return x->getId() < y->getId(); });
	known.erase(std::unique(known.begin(), known.end()), known.end());
	for (BattleUnit *b : side)
	{
		if (!ready(b))
		{
			continue;
		}
		for (BattleUnit *t : known)
		{
			if (t->isOut() || t->getFaction() == FACTION_HOSTILE || tried.count({ b->getId(), t->getId() }))
			{
				continue;
			}
			const Shot shotB = bestShot(save, b, t);
			if (shotB.type == BA_NONE || lineNow(save, b, t))
			{
				continue;
			}
			for (BattleUnit *a : side)
			{
				if (a == b || !ready(a) || a->getTimeUnits() <= 0 || !nearLine(a->getPosition(), b->getPosition(), t->getPosition()) || !lineIfMoved(save, b, t, a, 0))
				{
					continue;
				}
				tried.insert({ b->getId(), t->getId() });
				const Shot shotA = bestShot(save, a, t);
				if (ownCell(save, b, t, shotB))
				{
					candidate(save, a, b, t, "b_own_cell", shotA.value, shotB.value);
					break;
				}
				Position cell;
				int tu = 0;
				if (!findCell(save, a, b, t, cell, tu))
				{
					candidate(save, a, b, t, "a_no_cell", shotA.value, shotB.value);
					break;
				}
				if (shotB.value <= shotA.value)
				{
					candidate(save, a, b, t, "a_worth_more", shotA.value, shotB.value);
					break;
				}
				plan = Plan();
				plan.stage = 1;
				plan.a = a;
				plan.b = b;
				plan.t = t;
				plan.from = a->getPosition();
				plan.cell = cell;
				plan.cellTu = tu;
				plan.valueA = shotA.value;
				plan.valueB = shotB.value;
				plan.tHealth = t->getHealth();
				plan.tArmor = t->getArmor(SIDE_FRONT);
				candidate(save, a, b, t, "plan", shotA.value, shotB.value);
				return true;
			}
		}
	}
	return false;
}

Result stepInner(SavedBattleGame *save, BattleUnit *unit, BattleAction *action, BattleUnit **other)
{
	if (plan.stage == 4)
	{
		std::ostringstream s;
		s << "\"ev\":\"fired\"," << unitNote("A", plan.a) << "," << unitNote("B", plan.b) << "," << unitNote("T", plan.t) << ",\"tHealthBefore\":" << plan.tHealth
			<< ",\"tDamage\":" << plan.tHealth - plan.t->getHealth();
		journal(save, s.str());
		plan.stage = 0;
	}
	if (plan.stage == 0 && !search(save))
	{
		return PASS;
	}
	if (plan.stage == 1)
	{
		if (!ready(plan.a) || !ready(plan.b) || plan.t->isOut())
		{
			journal(save, "\"ev\":\"drop\",\"why\":\"before_walk\"");
			plan.stage = 0;
			return PASS;
		}
		if (unit != plan.a)
		{
			*other = plan.a;
			return SWITCH;
		}
		action->actor = unit;
		action->type = BA_WALK;
		action->target = plan.cell;
		plan.stage = 2;
		std::ostringstream s;
		s << "\"ev\":\"step_A\"," << unitNote("A", plan.a) << ",\"to\":" << pos(plan.cell) << ",\"tuCost\":" << plan.cellTu << ",\"bLineNow\":" << (lineNow(save, plan.b, plan.t) ? 1 : 0);
		journal(save, s.str());
		return ACT;
	}
	if (plan.stage == 2)
	{
		// A has walked or was stopped: from here on only what is really there counts
		const bool line = !plan.t->isOut() && ready(plan.b) && lineNow(save, plan.b, plan.t);
		const Shot shot = line ? bestShot(save, plan.b, plan.t) : Shot();
		std::ostringstream s;
		s << "\"ev\":\"after_A\"," << unitNote("A", plan.a) << "," << unitNote("B", plan.b) << ",\"from\":" << pos(plan.from) << ",\"arrived\":" << (plan.a->getPosition() == plan.cell ? 1 : 0)
			<< ",\"bLineReal\":" << (line ? 1 : 0) << ",\"mode\":" << (int)shot.type;
		journal(save, s.str());
		if (shot.type == BA_NONE)
		{
			plan.stage = 0;
			return PASS;
		}
		plan.stage = 3;
	}
	if (plan.stage == 3)
	{
		if (unit != plan.b)
		{
			*other = plan.b;
			return SWITCH;
		}
		const Shot shot = bestShot(save, plan.b, plan.t);
		if (shot.type == BA_NONE || !lineNow(save, plan.b, plan.t))
		{
			journal(save, "\"ev\":\"drop\",\"why\":\"before_shot\"");
			plan.stage = 0;
			return PASS;
		}
		action->actor = unit;
		action->type = shot.type;
		action->weapon = shot.weapon;
		action->target = plan.t->getPosition();
		plan.stage = 4;
		std::ostringstream s;
		s << "\"ev\":\"shot_B\"," << unitNote("B", plan.b) << "," << unitNote("T", plan.t) << ",\"mode\":" << (int)shot.type << ",\"weapon\":\"" << shot.weapon->getRules()->getType() << "\",\"tuCost\":" << shot.tu
			<< ",\"value\":" << shot.value;
		journal(save, s.str());
		return ACT;
	}
	return PASS;
}

} // namespace

Result step(SavedBattleGame *save, BattleUnit *unit, BattleAction *action, BattleUnit **other)
{
	static const bool on = AiProbe::param("OXCE_AI_TTS", 0) == 1;
	if (!on || save->getSide() != FACTION_HOSTILE || unit->getFaction() != FACTION_HOSTILE)
	{
		return PASS;
	}
	const auto t0 = std::chrono::steady_clock::now();
	if (planSave != save || planTurn != save->getTurn())
	{
		if (planTurn >= 0)
		{
			std::ostringstream s;
			s << "\"ev\":\"turn_end\",\"calls\":" << callsTurn << ",\"us\":" << usTurn << ",\"usTotal\":" << usTotal;
			journal(save, s.str());
		}
		planSave = save;
		planTurn = save->getTurn();
		plan = Plan();
		tried.clear();
		usTurn = 0;
		callsTurn = 0;
	}
	const uint64_t rng = RNG::getSeed();
	const Result r = stepInner(save, unit, action, other);
	if (RNG::getSeed() != rng)
	{
		journal(save, "\"ev\":\"rng_touched\""); // must never be written: the solver rolls no dice
	}
	const long long us = std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now() - t0).count();
	usTurn += us;
	usTotal += us;
	++callsTurn;
	return r;
}

}
}
