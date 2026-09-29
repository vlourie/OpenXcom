/*
 * Copyright 2010-2026 OpenXcom Developers.
 *
 * This file is part of OpenXcom.
 *
 * OpenXcom is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * OpenXcom is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with OpenXcom.  If not, see <http://www.gnu.org/licenses/>.
 */
#include "AiCandidates.h"
#include <algorithm>
#include <cstdlib>
#include <set>
#include "BattlescapeGame.h"
#include "Pathfinding.h"
#include "TileEngine.h"
#include "../Mod/Armor.h"
#include "../Mod/RuleItem.h"
#include "../Savegame/BattleItem.h"
#include "../Savegame/BattleUnit.h"
#include "../Savegame/Node.h"
#include "../Savegame/SavedBattleGame.h"
#include "../Savegame/Tile.h"

namespace OpenXcom
{

namespace AiCandidates
{

namespace
{

/// FNV-1a, the same as the state fingerprint (AiProbe.cpp).
struct Fnv
{
	uint64_t h = 1469598103934665603ULL;
	void add(long long v)
	{
		for (int i = 0; i < 8; ++i)
		{
			h ^= (uint64_t)((v >> (i * 8)) & 0xff);
			h *= 1099511628211ULL;
		}
	}
	void add(const std::string &s)
	{
		for (unsigned char c : s)
		{
			h ^= c;
			h *= 1099511628211ULL;
		}
		add((long long)s.size());
	}
};

bool isAttack(int type)
{
	return type == BA_AUTOSHOT || type == BA_SNAPSHOT || type == BA_AIMEDSHOT || type == BA_HIT || type == BA_THROW
		|| type == BA_LAUNCH || type == BA_MINDCONTROL || type == BA_PANIC;
}

/// Turning steps from one direction to another, the short way round.
int turnSteps(int from, int to)
{
	int d = std::abs(from - to) % 8;
	return d > 4 ? 8 - d : d;
}

void addAttack(Set &set, SavedBattleGame *save, BattleUnit *unit, BattleItem *weapon, BattleActionType type, BattleUnit *target)
{
	BattleActionCost cost(type, unit, weapon);
	if (cost.Time <= 0)
	{
		return; // the weapon has no such mode
	}
	if (weapon->needsAmmoForAction(type) && !static_cast<const BattleItem*>(weapon)->getAmmoForAction(type))
	{
		return;
	}
	Candidate c;
	c.kind = ATTACK;
	c.type = type;
	c.tile = target->getPosition();
	c.target = target->getId();
	c.weapon = weapon->getRules()->getType();
	c.tu = cost.Time;
	c.dist = (int)Position::distance2d(unit->getPosition(), target->getPosition());
	c.chance = BattleUnit::getFiringAccuracy(BattleActionAttack::GetBeforeShoot(cost), save->getMod());
	TileEngine *te = save->getTileEngine();
	Tile *targetTile = save->getTile(target->getPosition());
	if (type == BA_HIT)
	{
		c.lof = te->validMeleeRange(unit, target, te->getDirectionTo(unit->getPosition(), target->getPosition())) ? 1 : 0;
	}
	else if (type == BA_MINDCONTROL || type == BA_PANIC)
	{
		c.lof = 1;
	}
	else if (targetTile)
	{
		BattleAction action;
		action.type = type;
		action.actor = unit;
		action.weapon = weapon;
		action.target = target->getPosition();
		Position origin = te->getOriginVoxel(action, nullptr);
		if (type == BA_THROW)
		{
			// aimed as AIModule aims a throw
			Position targetVoxel = target->getPosition().toVoxel() + Position(8, 8, 2 + -targetTile->getTerrainLevel());
			c.lof = te->validateThrow(action, origin, targetVoxel, save->getDepth()) ? 1 : 0;
		}
		else
		{
			Position scan;
			c.lof = te->canTargetUnit(&origin, targetTile, &scan, unit, false) ? 1 : 0;
		}
	}
	c.id = actionId(c.kind, unit->getId(), c.type, c.tile, c.weapon);
	set.acts.push_back(c);
}

}

uint64_t actionId(Kind kind, int actor, int type, Position tile, const std::string &weapon)
{
	Fnv f;
	f.add((long long)kind);
	f.add(actor);
	f.add(type);
	f.add(tile.x);
	f.add(tile.y);
	f.add(tile.z);
	f.add(weapon);
	return f.h;
}

Set generate(SavedBattleGame *save, BattleUnit *unit)
{
	Set set;
	const int id = unit->getId();
	const Position pos = unit->getPosition();

	// the enemies it knows of: seen by itself, or by its side no longer ago than its intelligence (as AIModule counts them)
	std::vector<BattleUnit*> enemies;
	for (auto *bu : *save->getUnits())
	{
		if (bu->isOut() || bu->getFaction() == unit->getFaction())
			continue;
		const auto &seen = *unit->getVisibleUnits();
		if (std::find(seen.begin(), seen.end(), bu) != seen.end()
			|| bu->getTurnsSinceSpottedByFaction(unit->getFaction()) <= unit->getIntelligence())
			enemies.push_back(bu);
	}

	// attacks: every weapon the unit can use now, every mode, every enemy it knows of
	std::vector<BattleItem*> weapons;
	auto addWeapon = [&](BattleItem *item)
	{
		if (!item || std::find(weapons.begin(), weapons.end(), item) != weapons.end())
			return;
		// one grenade of a kind is enough: the id holds the item type, not the item
		for (const auto *w : weapons)
		{
			if (w->getRules() == item->getRules() && item->getRules()->isGrenadeOrProxy())
				return;
		}
		weapons.push_back(item);
	};
	addWeapon(unit->getRightHandWeapon());
	addWeapon(unit->getLeftHandWeapon());
	addWeapon(unit->getSpecialWeapon(BT_FIREARM));
	addWeapon(unit->getSpecialWeapon(BT_MELEE));
	addWeapon(unit->getSpecialWeapon(BT_PSIAMP));
	for (auto *item : *unit->getInventory())
	{
		if (item->getRules()->isGrenadeOrProxy())
			addWeapon(item);
	}
	for (auto *weapon : weapons)
	{
		const BattleType bt = weapon->getRules()->getBattleType();
		for (auto *target : enemies)
		{
			if (bt == BT_FIREARM)
			{
				addAttack(set, save, unit, weapon, BA_SNAPSHOT, target);
				addAttack(set, save, unit, weapon, BA_AUTOSHOT, target);
				addAttack(set, save, unit, weapon, BA_AIMEDSHOT, target);
			}
			// a melee weapon strikes any enemy it knows of: the AI charges and strikes in one decision (lof 0 until adjacent);
			// a gun's butt only an adjacent one
			if (bt == BT_MELEE
				|| (bt == BT_FIREARM && Position::distance2d(pos, target->getPosition()) <= 1 + (unit->getArmor()->getSize() - 1) + (target->getArmor()->getSize() - 1)))
			{
				addAttack(set, save, unit, weapon, BA_HIT, target);
			}
			if (weapon->getRules()->isGrenadeOrProxy())
			{
				addAttack(set, save, unit, weapon, BA_THROW, target);
			}
			if (bt == BT_PSIAMP)
			{
				addAttack(set, save, unit, weapon, BA_PANIC, target);
				addAttack(set, save, unit, weapon, BA_MINDCONTROL, target);
				addAttack(set, save, unit, weapon, BA_HIT, target);
			}
		}
	}

	// kneel or stand up
	if (unit->getArmor()->allowsKneeling(unit->getType() == "SOLDIER") && !unit->isFloating())
	{
		Candidate c;
		c.kind = KNEEL;
		c.type = BA_KNEEL;
		c.tile = pos;
		c.tu = unit->getKneelChangeCost();
		c.id = actionId(c.kind, id, c.type, c.tile, "");
		set.acts.push_back(c);
	}

	// turn to face each of the other seven directions
	for (int dir = 0; dir < 8; ++dir)
	{
		if (dir == unit->getDirection())
			continue;
		Candidate c;
		c.kind = TURN;
		c.type = BA_TURN;
		c.tile = Position(dir, 0, 0);
		c.tu = unit->getTurnCost() * turnSteps(unit->getDirection(), dir);
		c.id = actionId(c.kind, id, c.type, c.tile, "");
		set.acts.push_back(c);
	}

	// stop here
	{
		Candidate c;
		c.kind = END;
		c.type = BA_NONE;
		c.tile = pos;
		c.id = actionId(c.kind, id, c.type, c.tile, "");
		set.acts.push_back(c);
	}

	// every tile it can walk to this turn
	Pathfinding *pf = save->getPathfinding();
	Fnv moves;
	for (int index : pf->findReachable(unit, BattleActionCost()))
	{
		const Position to = save->getTileCoords(index);
		if (to == pos)
			continue;
		Candidate c;
		c.kind = MOVE;
		c.type = BA_WALK;
		c.tile = to;
		c.tu = pf->reachedTU(to);
		c.id = actionId(c.kind, id, c.type, c.tile, "");
		moves.add(to.x);
		moves.add(to.y);
		moves.add(to.z);
		moves.add(c.tu);
		set.moves.push_back(c);
	}
	// where it may head beyond this turn's reach (tu -1): the map's nodes, as a patrol goes, and the enemies it knows of
	std::vector<Position> far;
	for (const auto *node : *save->getNodes())
	{
		far.push_back(node->getPosition());
	}
	for (const auto *bu : enemies)
	{
		far.push_back(bu->getPosition());
	}
	std::set<int> listed;
	listed.insert(save->getTileIndex(pos));
	for (const auto &m : set.moves)
	{
		listed.insert(save->getTileIndex(m.tile));
	}
	for (const Position &to : far)
	{
		if (!save->getTile(to) || !listed.insert(save->getTileIndex(to)).second)
			continue;
		Candidate c;
		c.kind = MOVE;
		c.type = BA_WALK;
		c.tile = to;
		c.tu = -1;
		c.id = actionId(c.kind, id, c.type, c.tile, "");
		moves.add(to.x);
		moves.add(to.y);
		moves.add(to.z);
		moves.add(c.tu);
		set.moves.push_back(c);
	}
	set.movesHash = moves.h;

	Fnv order;
	std::vector<uint64_t> ids;
	for (const auto *list : { &set.acts, &set.moves })
	{
		for (const auto &c : *list)
		{
			order.add((long long)c.id);
			ids.push_back(c.id);
		}
	}
	std::sort(ids.begin(), ids.end());
	Fnv sorted;
	for (uint64_t i : ids)
	{
		sorted.add((long long)i);
	}
	set.orderHash = order.h;
	set.setHash = sorted.h;
	return set;
}

uint64_t chosenId(SavedBattleGame *save, const BattleUnit *unit, const BattleAction &action, Kind *kind)
{
	Kind k = OTHER;
	Position tile = action.target;
	std::string weapon;
	int type = action.type;
	if (action.type == BA_WALK)
	{
		// a walk with no destination (target -1) moves nowhere: not a move candidate
		k = save->getTile(action.target) ? MOVE : OTHER;
	}
	else if (isAttack(action.type))
	{
		k = ATTACK;
		weapon = action.weapon ? action.weapon->getRules()->getType() : std::string();
		// any tile of a large unit stands for the unit: its candidates are stored at its position
		const Tile *t = save->getTile(action.target);
		if (t && t->getUnit())
			tile = t->getUnit()->getPosition();
	}
	else if (action.type == BA_KNEEL)
	{
		k = KNEEL;
		tile = unit->getPosition();
	}
	else if (action.type == BA_TURN)
	{
		k = TURN;
		// the direction the engine will turn to (UnitTurnBState)
		tile = Position(save->getTileEngine()->getDirectionTo(unit->getPosition(), action.target), 0, 0);
	}
	else if (action.type == BA_NONE)
	{
		k = END;
		tile = unit->getPosition();
	}
	if (kind)
		*kind = k;
	return actionId(k, unit->getId(), type, tile, weapon);
}

}

}
