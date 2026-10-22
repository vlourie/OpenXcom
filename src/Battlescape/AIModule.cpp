/*
 * Copyright 2010-2016 OpenXcom Developers.
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
#include <climits>
#include <chrono>
#include <algorithm>
#include <sstream>
#include "AIModule.h"
#include "../Savegame/BattleItem.h"
#include "../Savegame/Node.h"
#include "../Savegame/SavedBattleGame.h"
#include "../Savegame/SavedGame.h"
#include "TileEngine.h"
#include "BattlescapeState.h"
#include "../Savegame/Tile.h"
#include "Pathfinding.h"
#include "../Engine/RNG.h"
#include "../Engine/Logger.h"
#include "../Engine/Game.h"
#include "../Mod/Armor.h"
#include "../Mod/Mod.h"
#include "../Mod/RuleItem.h"
#include "../Mod/RuleDamageType.h"
#include "../fmath.h"
#include <cmath>
#include "AiProbe.h"

namespace OpenXcom
{

/**
 * Puts the target at the place the deciding side honestly knows (OXCE_AI_FAIR_KNOWLEDGE).
 * Only the unit's own position, tile pointer and facing move; tile occupancy is untouched.
 */
AiKnownPlace::AiKnownPlace(SavedBattleGame *save, BattleUnit *unit, int kind, const Position &pos, int dir) :
	_unit(unit), _pos(), _tile(0), _dir(0), _on(false)
{
	if (kind != 1 || !unit) return;
	Tile *tile = save->getTile(pos);
	if (!tile) return;
	_pos = unit->_pos;
	_tile = unit->_tile;
	_dir = unit->_direction;
	unit->_pos = pos;
	unit->_tile = tile;
	unit->_direction = dir;
	_on = true;
	_moved.push_back(unit);
}

AiKnownPlace::~AiKnownPlace()
{
	if (!_on) return;
	_unit->_pos = _pos;
	_unit->_tile = _tile;
	_unit->_direction = _dir;
	// scopes nest, so the last entry of this unit is this scope's
	for (auto it = _moved.end(); it != _moved.begin(); )
	{
		--it;
		if (*it == _unit)
		{
			_moved.erase(it);
			break;
		}
	}
}

std::vector<BattleUnit *> AiKnownPlace::_moved;

bool AiKnownPlace::trueBody()
{
	static const bool on = AiProbe::param("OXCE_AI_FAIR_TRUEBODY", 0) == 1;
	return on;
}

bool AiKnownPlace::moved(const BattleUnit *unit)
{
	return unit && std::find(_moved.begin(), _moved.end(), unit) != _moved.end();
}

bool AiKnownPlace::atKnown(const SavedBattleGame *save, const BattleUnit *unit, const Tile *tile, bool pokeUp)
{
	const Position &k = unit->getPosition();
	const Position &t = tile->getPosition();
	const int size = unit->getArmor()->getSize();
	if (t.x < k.x || t.x >= k.x + size || t.y < k.y || t.y >= k.y + size)
	{
		return false;
	}
	if (t.z == k.z)
	{
		return true;
	}
	if (!pokeUp || t.z != k.z + 1 || !tile->hasNoFloor(save) || tile->getMapData(O_OBJECT) != nullptr)
	{
		return false;
	}
	const Tile *below = save->getBelowTile(tile);
	return below && unit->getHeight() + unit->getFloatHeight() - below->getTerrainLevel() > static_cast<int>(TUO_NORMAL);
}

BattleUnit *AiKnownPlace::knownOn(const Tile *tile)
{
	const Position &t = tile->getPosition();
	for (auto it = _moved.rbegin(); it != _moved.rend(); ++it)
	{
		const Position &k = (*it)->getPosition();
		const int size = (*it)->getArmor()->getSize();
		if (t.z == k.z && t.x >= k.x && t.x < k.x + size && t.y >= k.y && t.y < k.y + size)
		{
			return *it;
		}
	}
	return nullptr;
}

BattleUnit *AiKnownPlace::knownOverlapping(const SavedBattleGame *save, const Tile *tile)
{
	BattleUnit *bu = knownOn(tile);
	if (!bu && tile->getPosition().z > 0 && tile->hasNoFloor(save) && tile->getMapData(O_OBJECT) == nullptr)
	{
		const Tile *below = save->getBelowTile(tile);
		bu = below ? knownOn(below) : nullptr;
		if (bu && bu->getHeight() + bu->getFloatHeight() - below->getTerrainLevel() <= static_cast<int>(TUO_NORMAL))
		{
			bu = nullptr;
		}
	}
	return bu;
}

BattleUnit *AiKnownPlace::unitOn(const Tile *tile)
{
	BattleUnit *bu = tile->getUnit();
	if (_moved.empty() || trueBody())
	{
		return bu;
	}
	if (bu && moved(bu) && knownOn(tile) != bu)
	{
		bu = nullptr; // the true tile of a unit the AI sees elsewhere
	}
	return bu ? bu : knownOn(tile);
}

/**
 * Where this unit's side honestly knows the target to be.
 * @return 0 - the current place (visible, cheat, flag off); 1 - the last seen place in pos/dir; 2 - never seen.
 */
int AIModule::knownPlace(const BattleUnit *target, const char *cons, Position &pos, int &dir) const
{
	int kind = AiProbe::fairPlace(_save, _unit, target, pos, dir);
	if (kind == 1)
	{
		AiProbe::fairNote(_unit, target, cons, 1, pos, target->getPosition());
	}
	else if (kind == 2)
	{
		AiProbe::fairNote(_unit, target, cons, 2, Position(-1, -1, -1), target->getPosition());
	}
	return kind;
}

/**
 * The grenade-danger mark of the tile where this side knows the target to be.
 */
bool AIModule::knownDangerous(const BattleUnit *target) const
{
	Position kp;
	int kdir = 0;
	int kind = knownPlace(target, "danger", kp, kdir);
	if (kind == 2) return false;
	if (kind == 1)
	{
		Tile *tile = _save->getTile(kp);
		return tile && tile->getDangerous();
	}
	return target->getTile()->getDangerous();
}

/**
 * The unit this side knows to stand on a tile: the one standing there if this side knows it there, else the first one
 * this side remembers there (consumer "blast"); none if it knows nobody there.
 */
BattleUnit *AIModule::fairOccupant(Position at) const
{
	auto covers = [&](const BattleUnit *u, const Position &p)
	{
		const int size = u->getArmor()->getSize();
		return p.z == at.z && at.x >= p.x && at.x < p.x + size && at.y >= p.y && at.y < p.y + size;
	};
	auto knownAt = [&](BattleUnit *u)
	{
		Position kp;
		int kdir = 0;
		const int kind = knownPlace(u, "blast", kp, kdir);
		return kind != 2 && covers(u, kind == 1 ? kp : u->getPosition());
	};
	const Tile *tile = _save->getTile(at);
	BattleUnit *real = tile ? tile->getUnit() : nullptr;
	if (real && knownAt(real))
	{
		return real;
	}
	for (auto *bu : *_save->getUnits())
	{
		if (!bu->isOut() && bu != real && knownAt(bu))
		{
			return bu;
		}
	}
	return nullptr;
}

/**
 * The target's position as this side knows it.
 */
Position AIModule::knownPos(const BattleUnit *target, const char *cons) const
{
	Position kp;
	int kdir = 0;
	const int kind = knownPlace(target, cons, kp, kdir);
	if (kind == 1) return kp;
	if (kind == 2) return Position(-1, -1, -1);
	return target->getPosition();
}

/**
 * Melee reach from a tile to the place this side knows the target to be.
 * Kind 0 is TileEngine::validMeleeRange exactly as the callers made it; kind 1 repeats its geometry against a body
 * standing at kp (which tiles the target covers there), not against the unit the tile really holds.
 */
bool AIModule::knownMeleeRange(Position from, BattleUnit *target, int kind, const Position &kp, int kdir) const
{
	TileEngine *te = _save->getTileEngine();
	if (kind == 0)
	{
		return te->validMeleeRange(from, te->getDirectionTo(from, target->getPosition()), _unit, target, 0);
	}
	if (kind != 1)
	{
		return false;
	}
	int direction = te->getDirectionTo(from, kp);
	if (direction < 0 || direction > 7)
	{
		return false;
	}
	AiKnownPlace known(_save, target, kind, kp, kdir);
	if (!known.on())
	{
		return false;
	}
	const int tsize = target->getArmor()->getSize();
	auto covers = [&](const Position &p) { return p.z == kp.z && p.x >= kp.x && p.x < kp.x + tsize && p.y >= kp.y && p.y < kp.y + tsize; };
	Position p;
	Pathfinding::directionToVector(direction, &p);
	int size = _unit->getArmor()->getSize() - 1;
	int meleeOriginVoxelVerticalOffset = _unit->getArmor()->getMeleeOriginVoxelVerticalOffset();
	for (int x = 0; x <= size; ++x)
	{
		for (int y = 0; y <= size; ++y)
		{
			Tile *origin = _save->getTile(Position(from + Position(x, y, 0)));
			Tile *targetTile = _save->getTile(Position(from + Position(x, y, 0) + p));
			if (!targetTile || !origin)
			{
				continue;
			}
			Tile *aboveTargetTile = _save->getAboveTile(targetTile);
			Tile *belowTargetTile = _save->getBelowTile(targetTile);
			if (origin->getTerrainLevel() <= -16 && aboveTargetTile && !aboveTargetTile->hasNoFloor(_save))
			{
				targetTile = aboveTargetTile;
			}
			else if (belowTargetTile && targetTile->hasNoFloor(_save) && !covers(targetTile->getPosition()) && belowTargetTile->getTerrainLevel() <= -16)
			{
				targetTile = belowTargetTile;
			}
			if (!covers(targetTile->getPosition()))
			{
				continue;
			}
			Position originVoxel = Position(origin->getPosition().toVoxel())
				+ Position(8, 8, _unit->getHeight() + _unit->getFloatHeight() - 4 - origin->getTerrainLevel() + meleeOriginVoxelVerticalOffset);
			Position targetVoxel;
			if (te->canTargetUnit(&originVoxel, targetTile, &targetVoxel, _unit, false, target))
			{
				return true;
			}
		}
	}
	return false;
}

/**
 * Melee reach from a tile to the target where this side knows it to be (consumer "melee").
 */
bool AIModule::knownMeleeFrom(Position from, BattleUnit *target) const
{
	Position kp;
	int kdir = 0;
	const int kind = knownPlace(target, "melee", kp, kdir);
	return knownMeleeRange(from, target, kind, kp, kdir);
}

/**
 * Melee reach from where this unit stands to the target where this side knows it to be.
 */
bool AIModule::knownAdjacent(BattleUnit *target) const
{
	Position kp;
	int kdir = 0;
	const int kind = knownPlace(target, "melee", kp, kdir);
	if (!knownMeleeRange(_unit->getPosition(), target, kind, kp, kdir))
	{
		return false;
	}
	if (kind == 1)
	{
		// the player's rule: a blow at a tile with nobody on it is 'there is no one there' and is not made; the side now
		// knows the target is not at the remembered place (a blow at whoever else stands there is not made either)
		Tile *tile = _save->getTile(kp);
		BattleUnit *occupant = tile ? tile->getUnit() : nullptr;
		if (occupant != target)
		{
			AiProbe::fairProbe(_unit, target, kp, occupant);
			target->forgetAiSeen(_unit->getFaction(), _save, _unit);
			return false;
		}
	}
	return true;
}


/**
 * Sets up a BattleAIState.
 * @param save Pointer to the battle game.
 * @param unit Pointer to the unit.
 * @param node Pointer to the node the unit originates from.
 */
AIModule::AIModule(SavedBattleGame *save, BattleUnit *unit, Node *node) :
	_save(save), _unit(unit), _aggroTarget(0), _knownEnemies(0), _visibleEnemies(0), _spottingEnemies(0),
	_escapeTUs(0), _ambushTUs(0), _walkAbortCounter(0), _weaponPickedUp(false), _rifle(false), _melee(false), _blaster(false), _grenade(false),
	_didPsi(false), _AIMode(AI_PATROL), _closestDist(100), _fromNode(node), _toNode(0), _foundBaseModuleToDestroy(false)
{
	_traceAI = Options::traceAI;

	_reserve = BA_NONE;
	_intelligence = _unit->getIntelligence();
	_escapeAction = BattleAction();
	_ambushAction = BattleAction();
	_attackAction = BattleAction();
	_patrolAction = BattleAction();
	_psiAction = BattleAction();
	_targetFaction = FACTION_PLAYER;
	if (_unit->getOriginalFaction() == FACTION_NEUTRAL)
	{
		_targetFaction = FACTION_HOSTILE;
	}
}

/**
 * Deletes the BattleAIState.
 */
AIModule::~AIModule()
{

}

/**
 * The fingerprint of this module's own state: two runs of one battle with the same world and the same random generator
 * can still decide differently if what the module remembers differs (target, patrol nodes, reachable tiles, who hit it).
 */
unsigned long long AIModule::probeHash() const
{
	unsigned long long h = 1469598103934665603ULL;
	auto add = [&h](long long v)
	{
		for (int i = 0; i < 8; ++i)
		{
			h = (h ^ (unsigned long long)((v >> (i * 8)) & 0xff)) * 1099511628211ULL;
		}
	};
	add(_aggroTarget ? _aggroTarget->getId() : -1);
	add(_knownEnemies); add(_visibleEnemies); add(_spottingEnemies);
	add(_escapeTUs); add(_ambushTUs); add(_walkAbortCounter);
	add(_weaponPickedUp); add(_rifle); add(_melee); add(_blaster); add(_grenade); add(_didPsi);
	add(_AIMode); add(_intelligence); add(_closestDist);
	add(_fromNode ? _fromNode->getID() : -1); add(_toNode ? _toNode->getID() : -1);
	add(_foundBaseModuleToDestroy); add((int)_reserve); add((int)_targetFaction);
	add((long long)_reachable.size());
	for (int i : _reachable) { add(i); }
	add((long long)_reachableWithAttack.size());
	for (int i : _reachableWithAttack) { add(i); }
	for (int i : _wasHitBy) { add(i); }
	if (_patrolSpent != -1)
	{
		// only once the bench rule has spent a patrol: without OXCE_AI_ENERGY_PATROL_END the fingerprint stays as it was
		add(_patrolSpent); add(_patrolSpentAt.x); add(_patrolSpentAt.y); add(_patrolSpentAt.z); add(_patrolSpentEnergy); add(_patrolRetry);
	}
	if (_immRetry != 0)
	{
		add(_immRetry); // AI3-IMM: only once the bench rule has dropped a walk (OXCE_AI_IMMOBILE_NO_WALK)
	}
	if (_retryHaveLast || !_retryBans.empty())
	{
		// AI3-RETRY: only once the bench rule has remembered an action (OXCE_AI_FAILED_RETRY)
		add(_retryHaveLast); add((long long)_retryLast.print); add((long long)_retryBans.size()); add(_retryTurn);
		for (const RetryKey &k : _retryBans) { add(k.type); add(k.target.x); add(k.target.y); add(k.target.z); add(k.weapon); add(k.reserve); add(k.run); add((long long)k.print); }
	}
	if (_fpBlocked || _fpInvalidated)
	{
		// only once the bench rule has recorded a blocked firepoint (OXCE_AI_FIREPOINT_BLOCKED)
		add(_fpBlocked); add(_fpBlockedPoint.x); add(_fpBlockedPoint.y); add(_fpBlockedPoint.z); add(_fpBlockedDir);
		add(_fpBlockedFrom.x); add(_fpBlockedFrom.y); add(_fpBlockedFrom.z); add(_fpBlockedTu); add(_fpBlockedTurn);
		add(_fpBlockedAggro); add((long long)_fpBlockedRev); add(_fpInvalidated);
	}
	return h;
}

/**
 * The action slot of the bench's decision record: p patrol, a ambush, e escape, s psi, x attack.
 */
const BattleAction &AIModule::probeAction(char slot) const
{
	return slot == 'p' ? _patrolAction : slot == 'a' ? _ambushAction : slot == 'e' ? _escapeAction : slot == 's' ? _psiAction : _attackAction;
}

/**
 * AI3-RETRY (bench): the unit's state an action's outcome depends on - where it stands and faces, its time units, energy,
 * health, stun, kneeling, the reserve the last think set, the units it sees and its own side where they stand. Own side and
 * visible units only (FAIR_KNOWLEDGE). An action carried out changes at least time units, energy, place or facing.
 */
unsigned long long AIModule::retryPrint() const
{
	unsigned long long h = 1469598103934665603ULL;
	auto add = [&h](long long v)
	{
		for (int i = 0; i < 8; ++i)
		{
			h = (h ^ (unsigned long long)((v >> (i * 8)) & 0xff)) * 1099511628211ULL;
		}
	};
	const Position p = _unit->getPosition();
	add(p.x); add(p.y); add(p.z); add(_unit->getDirection()); add(_unit->getTimeUnits()); add(_unit->getEnergy());
	add(_unit->getHealth()); add(_unit->getStunlevel()); add(_unit->isKneeled()); add((int)_reserve);
	for (const BattleUnit *v : *_unit->getVisibleUnits())
	{
		const Position q = v->getPosition();
		add(v->getId()); add(q.x); add(q.y); add(q.z);
	}
	// AI3-RETRY (bench): where the own side stands - a mate that moved off the path (or opened a door) lets the same walk
	// step where it stopped before (h9c: patrol walk stopped by the reserve, the next pass stepped once the others had moved)
	for (const BattleUnit *u : *_save->getUnits())
	{
		if (u != _unit && u->getFaction() == _unit->getFaction() && !u->isOut())
		{
			const Position q = u->getPosition();
			add(u->getId()); add(q.x); add(q.y); add(q.z);
		}
	}
	return h;
}

/**
 * AI3-RETRY (bench): called by handleAI before a selection's think. A new unit-turn forgets everything; the action handed on
 * last that left the state as it was is banned in this state.
 */
void AIModule::retryBegin()
{
	if (_retryTurn != unitTurn())
	{
		_retryTurn = unitTurn();
		_retryBans.clear();
		_retryHaveLast = false;
	}
	_retryNow = retryPrint();
	if (_retryHaveLast && _retryLast.print == _retryNow)
	{
		bool known = false;
		for (const RetryKey &k : _retryBans)
		{
			known = known || (k.type == _retryLast.type && k.target == _retryLast.target && k.weapon == _retryLast.weapon
				&& k.reserve == _retryLast.reserve && k.run == _retryLast.run && k.print == _retryNow);
		}
		if (!known)
		{
			_retryBans.push_back(_retryLast);
		}
	}
	_retryHaveLast = false;
}

/**
 * AI3-RETRY (bench): the ban's why if this action failed before in the state retryBegin saw, 0 otherwise.
 */
char AIModule::retryBanned(const BattleAction &action) const
{
	const int weapon = action.weapon ? action.weapon->getId() : -1;
	for (const RetryKey &k : _retryBans)
	{
		if (k.print == _retryNow && k.type == (int)action.type && k.target == action.target && (action.type == BA_WALK || k.weapon == weapon)
			&& k.reserve == (int)_reserve && k.run == action.run)
		{
			return k.why;
		}
	}
	return 0;
}

/**
 * AI3-RETRY (bench): the walk or attack handleAI hands on, with the state it was decided in; the next retryBegin finds out
 * whether it was carried out.
 */
void AIModule::retryRemember(const BattleAction &action, char why)
{
	const BattleActionType t = action.type;
	_retryHaveLast = t == BA_WALK || t == BA_SNAPSHOT || t == BA_AUTOSHOT || t == BA_AIMEDSHOT || t == BA_THROW || t == BA_HIT
		|| t == BA_MINDCONTROL || t == BA_USE || t == BA_PANIC || t == BA_LAUNCH;
	if (_retryHaveLast)
	{
		_retryLast = { (int)t, action.target, action.weapon ? action.weapon->getId() : -1, (int)_reserve, action.run, why, _retryNow };
	}
}

AIModule::ProbeMark AIModule::probeMark(char slot) const
{
	const BattleAction &a = probeAction(slot);
	return { a.type, a.target, a.weapon };
}

/**
 * Tells the decision record (OXCE_AI_RECORD) which rule filled a slot, if the rule that just ran changed it.
 */
void AIModule::probeSlot(char slot, const char *source, const ProbeMark &before)
{
	const BattleAction &a = probeAction(slot);
	if (AiProbe::active() && a.type != BA_RETHINK && a.type != BA_NONE
		&& (a.type != before.type || a.target != before.target || a.weapon != before.weapon))
	{
		AiProbe::propose(_unit, slot, _probeSource ? _probeSource : source, _probeScore, a);
	}
	_probeScore = INT_MIN;
	_probeSource = nullptr;
}

/**
 * Sets the target faction.
 */
void AIModule::setTargetFaction(UnitFaction f)
{
	_targetFaction = f;
}

/**
 * Resets the unsaved AI state.
 */
void AIModule::reset()
{
	// these variables are not saved in save() and also not initiated in think()
	_escapeTUs = 0;
	_ambushTUs = 0;

	// temp counter to prevent infinite loops, reset every turn
	_walkAbortCounter = 0;
}

/**
 * Loads the AI state from a YAML file.
 * @param node YAML node.
 */
void AIModule::load(const YAML::YamlNodeReader& reader)
{
	int fromNodeID = reader["fromNode"].readVal(-1);
	int toNodeID = reader["toNode"].readVal(-1);
	_AIMode = reader["AIMode"].readVal(AI_PATROL);
	reader.tryRead("wasHitBy", _wasHitBy);
	reader.tryRead("weaponPickedUp", _weaponPickedUp);
	reader.tryRead("targetFaction", _targetFaction);

	// TODO: Figure out why AI are sometimes left with junk nodes
	if (fromNodeID >= 0 && (size_t)fromNodeID < _save->getNodes()->size())
	{
		_fromNode = _save->getNodes()->at(fromNodeID);
	}
	if (toNodeID >= 0 && (size_t)toNodeID < _save->getNodes()->size())
	{
		_toNode = _save->getNodes()->at(toNodeID);
	}
}

/**
 * Saves the AI state to a YAML file.
 * @return YAML node.
 */
void AIModule::save(YAML::YamlNodeWriter writer) const
{
	writer.setAsMap();
	writer.setFlowStyle();
	writer.write("fromNode", _fromNode ? _fromNode->getID() : -1);
	writer.write("toNode", _toNode ? _toNode->getID() : -1);
	writer.write("AIMode", _AIMode);
	writer.write("wasHitBy", _wasHitBy);
	if (_weaponPickedUp)
		writer.write("weaponPickedUp", _weaponPickedUp);
	if (_unit->getOriginalFaction() == FACTION_HOSTILE && _unit->getFaction() == FACTION_NEUTRAL && _targetFaction == FACTION_HOSTILE)
	{
		writer.write("targetFaction", _targetFaction);
	}
}

/**
 * Mindless charge strategy. For mindless units.
 * Consists of running around and charging nearest visible enemy.
 * @param action (possible) AI action to execute after thinking is done.
 */
void AIModule::dont_think(BattleAction *action)
{
	_melee = false;
	action->weapon = _unit->getUtilityWeapon(BT_MELEE);

	if (_traceAI)
	{
		Log(LOG_INFO) << "LEEROY: Unit " << _unit->getId() << " of type " << _unit->getType() << " is Leeroy...";
	}
	if (action->weapon)
	{
		if (action->weapon->getRules()->getBattleType() == BT_MELEE)
		{
			if (_save->canUseWeapon(action->weapon, _unit, false, BA_HIT))
			{
				_melee = true;
			}
		}
		else
		{
			action->weapon = 0;
		}
	}

	bool canRun = _melee && _unit->getArmor()->allowsRunning(false) && _unit->getEnergy() > _unit->getBaseStats()->stamina * 0.4f;
	int visibleEnemiesToAttack = selectNearestTargetLeeroy(canRun);
	if (_traceAI)
	{
		Log(LOG_INFO) << "LEEROY: visibleEnemiesToAttack: " << visibleEnemiesToAttack << " _melee: " << _melee << (canRun ? " run" : "");
	}
	bool leeroy = (visibleEnemiesToAttack > 0) && _melee;
	if (leeroy)
	{
		if (_traceAI)
		{
			Log(LOG_INFO) << "LEEROY: LEEROYIN' at someone!";
		}
		const ProbeMark mark = probeMark('x');
		const int rejected = meleeActionLeeroy(canRun);
		probeSlot('x', "leeroy", mark);
		if (rejected > 0 && _aggroTarget == 0)
		{
			// AI2-A1: AI2-A rejected every candidate, so meleeActionLeeroy built nothing and the attack slot still holds the
			// previous decision's action. Upstream never gets here (the target selectNearestTargetLeeroy found stays a candidate):
			// drop that action and take upstream's no-target branch, as if no leeroy target was seen.
			static const bool fix = AiProbe::param("OXCE_AI_LEEROY_STALE_FIX", 1) != 0;
			if (AiProbe::active()) // the bench's line; the player's AI3 (BetterAI) does not write it
			{
				Log(LOG_INFO) << "[AITRACE] {\"ai2a\":\"leeroy_none\",\"rec\":" << AiProbe::nextRec() << ",\"turn\":" << _save->getTurn()
					<< ",\"unit\":" << _unit->getId() << ",\"side\":" << (int)_unit->getFaction() << ",\"rejected\":" << rejected
					<< ",\"stale\":" << (int)_attackAction.type << ",\"stale_to\":[" << _attackAction.target.x << "," << _attackAction.target.y
					<< "," << _attackAction.target.z << "],\"fix\":" << (fix ? 1 : 0) << "}";
			}
			if (fix)
			{
				_attackAction.type = BA_RETHINK;
				leeroy = false;
			}
		}
		if (leeroy)
		{
			action->type = _attackAction.type;
			action->run = _attackAction.run;
			action->target = _attackAction.target;
			// if this is a firepoint action, set our facing.
			action->finalFacing = _attackAction.finalFacing;
			action->updateTU();
		}
	}
	if (!leeroy)
	{
		if (_traceAI)
		{
			Log(LOG_INFO) << "LEEROY: No one to LEEROY!, patrolling...";
		}
		const ProbeMark mark = probeMark('p');
		setupPatrol();
		probeSlot('p', _patrolAction.type == BA_WALK ? "patrol.node" : "patrol.module", mark);
		AiProbe::chosen(_unit, 'p');
		_unit->setCharging(0);
		_reserve = BA_NONE;
		action->type = _patrolAction.type;
		action->target = _patrolAction.target;
		// a charge's choice has no dice to throw again
		endPatrolIfSpent(action, false);
	}
	// AI3-IMM (bench): a charge or patrol of an armor that cannot move is the same walk think drops (no dice here, so no retry)
	static const bool immobileNoWalk = AiProbe::param("OXCE_AI_IMMOBILE_NO_WALK", 0) != 0;
	if (immobileNoWalk && action->type == BA_WALK && !_unit->getArmor()->allowsMoving())
	{
		AiProbe::note(_unit, leeroy ? "immobile.nowalk.end l" : "immobile.nowalk.end p");
		action->type = BA_NONE;
	}
}

/**
 * Tries to use self-target medikit if needed and desired (used for AI).
 * @return Was it used?
 */
bool AIModule::medikit_think(BattleMediKitType healOrStim)
{
	// 1. sanity checks, division by zero
	BattleUnit* self = _unit;

	if (self->getBaseStats()->stamina <= 0 || self->getBaseStats()->health <= 0)
	{
		return false;
	}

	// 2. quick unit checks (without RNG)
	int totalWounds = self->getFatalWounds();
	int percentHealthLeft = Clamp((self->getHealth() - self->getStunlevel()) * 100 / self->getBaseStats()->health, 0, 100);
	int percentEnergyLeft = Clamp(self->getEnergy() * 100 / self->getBaseStats()->stamina, 0, 100);

	if (healOrStim == BMT_HEAL)
	{
		if (totalWounds <= 0)
			return false;
	}
	else if (healOrStim == BMT_STIMULANT)
	{
		if (self->getStunlevel() <= 0 && percentEnergyLeft >= 40)
			return false;
	}
	else
	{
		// unsupported medikit type
		return false;
	}

	// 3. quick item checks
	std::vector<BattleItem*> usableMedikits;

	for (auto* item : *self->getInventory())
	{
		const RuleItem* itemRule = item->getRules();
		if (itemRule->getBattleType() == BT_MEDIKIT &&
			(itemRule->getMediKitType() == healOrStim || itemRule->getMediKitType() == BMT_NORMAL) &&
			itemRule->getAllowTargetSelf())
		{
			if (_save->getTurn() < itemRule->getAIUseDelay(_save->getMod()))
			{
				// can't use it yet, too soon
				continue;
			}
			usableMedikits.push_back(item);
		}
	}
	if (usableMedikits.empty())
	{
		// no compatible medikits available
		return false;
	}

	// 4. detailed unit checks (with RNG)
	bool wantsToHeal = false;
	bool wantsToStimStun = false;
	bool wantsToStimEnergy = false;

	if (healOrStim == BMT_HEAL)
	{
		if (totalWounds > 0)
		{
			if (self->getStunlevel() + totalWounds >= self->getHealth())
			{
				// going to die or pass out unless we do something, so do something!
				wantsToHeal = true;
			}
			else
			{
				//  0% health left = 120% chance to heal
				// 15% health left =  60% chance to heal
				// 30% health left =   0% chance to heal (actually 5% chance because of random heal wish)
				int chanceToHeal = 120 - (percentHealthLeft * 4);
				if (chanceToHeal <= 0)
				{
					// 5% for random heal wish (it's not urgent, but you know damage accumulates over time)
					chanceToHeal = 5;
				}
				wantsToHeal = RNG::percent(chanceToHeal);
			}
		}
		if (!wantsToHeal)
		{
			return false;
		}
	}
	else if (healOrStim == BMT_STIMULANT)
	{
		// 1. do we want to decrease stun level?
		if (self->getStunlevel() > 0)
		{
			if (self->getStunlevel() + totalWounds >= self->getHealth())
			{
				// going to die or pass out unless we do something, so do something!
				wantsToStimStun = true;
			}
			else
			{
				//  0% health left = 140% chance to stim
				// 10% health left =  70% chance to stim
				// 20% health left =   0% chance to stim
				int chanceToStim1 = 140 - (percentHealthLeft * 7);
				wantsToStimStun = chanceToStim1 > 0 ? RNG::percent(chanceToStim1) : false;
			}
		}
		// 2. do we want to increase energy?
		if (percentEnergyLeft < 40)
		{
			//  0% energy left = 120% chance to stim
			// 20% energy left =  60% chance to stim
			// 40% energy left =   0% chance to stim
			int chanceToStim2 = 120 - (percentEnergyLeft * 3);
			wantsToStimEnergy = RNG::percent(chanceToStim2);
		}
		if (!wantsToStimStun && !wantsToStimEnergy)
		{
			return false;
		}
	}

	// 5. let's do it
	bool used = false;

	for (auto* medikit : usableMedikits)
	{
		const RuleItem* medikitRule = medikit->getRules();
		{
			if ((wantsToHeal && medikit->getHealQuantity() > 0) ||
				(wantsToStimStun && medikit->getStimulantQuantity() > 0 && medikitRule->getStunRecovery() > 0) ||
				(wantsToStimEnergy && medikit->getStimulantQuantity() > 0 && medikitRule->getEnergyRecovery() > 0))
			{
				BattleAction medikitAction;
				{
					medikitAction.weapon = medikit;
					medikitAction.type = BA_USE;
					medikitAction.actor = self;

					medikitAction.updateTU();

					// yes, hardcoded 4 TUs
					// AI throwing grenades does that for decades and nobody cares, so calm down
					// also, AI pays this cost each time, even if using the same medikit multiple times in a row
					medikitAction.Time += 4; // 4TUs for picking up the medikit

					// sigh, modders...
					//medikitAction.Health = 0;
					//medikitAction.Stun = 0;
				}
				if (!medikitAction.spendTU())
				{
					// not enough TUs, try next item
					continue;
				}
				else
				{
					switch (healOrStim)
					{
					case BMT_HEAL:
						if (_traceAI)
						{
							Log(LOG_INFO) << "  Using medikit (heal). TU*/HP/Stun/Wounds: " <<
								self->getTimeUnits() << "/" << self->getHealth() << "/" << self->getStunlevel() << "/" << totalWounds;
						}
						for (int i = 0; i < BODYPART_MAX; ++i)
						{
							if (self->getFatalWound((UnitBodyPart)i))
							{
								_save->getTileEngine()->medikitUse(&medikitAction, self, BMA_HEAL, (UnitBodyPart)i);
								_save->getTileEngine()->medikitRemoveIfEmpty(&medikitAction);
								used = true;
								break;
							}
						}
						break;
					case BMT_STIMULANT:
						if (_traceAI)
						{
							if (wantsToStimStun)
							{
								Log(LOG_INFO) << "  Using medikit (-stun). TU*/HP/Stun/Wounds: " <<
									self->getTimeUnits() << "/" << self->getHealth() << "/" << self->getStunlevel() << "/" << totalWounds;
							}
							else
							{
								Log(LOG_INFO) << "  Using medikit (+energy). TU*/Energy: " << self->getTimeUnits() << "/" << self->getEnergy();
							}
						}
						_save->getTileEngine()->medikitUse(&medikitAction, self, BMA_STIMULANT, BODYPART_TORSO);
						_save->getTileEngine()->medikitRemoveIfEmpty(&medikitAction);
						used = true;
						break;
					case BMT_PAINKILLER:
					case BMT_NORMAL:
						// not supported
						break;
					}
				}
			}
		}
		if (used)
		{
			// only one use per attempt
			break;
		}
	}

	// 6. if we used something, let's try again
	return used;
}

/**
 * Runs any code the state needs to keep updating every AI cycle.
 * @param action (possible) AI action to execute after thinking is done.
 */
void AIModule::think(BattleAction *action)
{
	// Workaround: AI freeze
	if (_walkAbortCounter > 200)
	{
		_unit->clearTimeUnits();
	}

	action->type = BA_RETHINK;
	action->actor = _unit;
	action->weapon = _unit->getMainHandWeapon(false);
	_patrolWalk = false;
	_patrolRetry = _patrolRetry == 1 ? 2 : 0;
	_immRetry = _immRetry == 1 ? 2 : 0;
	_firepointChosen = false;
	_fpSuppressedNow = false;
	_ko2FpTarget = _ko2AmbTarget = _ko2FpChosenTarget = 0;
	_ko2FpOld = _ko2AmbOld = _ko2FpRan = _ko2AmbRan = false;
	_ko2FpHits = _ko2AmbHits = 0;
	_ko2WalkTarget = 0;
	_ko2WalkBranch = 0;
	_attackAction.diff = _save->getBattleState()->getGame()->getSavedGame()->getDifficultyCoefficient();
	_attackAction.actor = _unit;
	_attackAction.run = false;
	_attackAction.weapon = action->weapon;
	_attackAction.number = action->number;
	_escapeAction.number = action->number;
	_knownEnemies = countKnownTargets();
	_visibleEnemies = selectNearestTarget();
	_spottingEnemies = getSpottingUnits(_unit->getPosition());
	_melee = (_unit->getUtilityWeapon(BT_MELEE) != 0);
	_rifle = false;
	_blaster = false;
	// KNOWN_OCCUPANT_PATH_V1 (bench): the enemy's paths, from here to the walk's own (BattlescapeGame::handleAI), do not go
	// through the closest known target the side spotted this turn - findFirePoint aims at it where it stands
	if (AiProbe::knownOccupantPath())
	{
		const BattleUnit *occupant = 0;
		_knownOccAge = -1;
		if (_unit->getFaction() == FACTION_HOSTILE)
		{
			occupant = knownOccupant(_knownOccAge);
		}
		_save->getPathfinding()->setKnownOccupant(_unit, occupant);
	}
	_reachable = _save->getPathfinding()->findReachable(_unit, BattleActionCost());
	const bool revived = AiProbe::revive(_save, _unit, action, _reachable);
	if (revived || AiProbe::flee(_save, _unit, action, _reachable))
	{
		AiProbe::propose(_unit, 'b', revived ? "revive" : "flee", INT_MIN, *action);
		AiProbe::chosen(_unit, 'b');
		// walking onto a downed comrade's body (the stimulant goes on the next think) or away from the enemy it cannot fight
		_escapeTUs = 0;
		_ambushTUs = 0;
		if (AiProbe::staleEscapeFix())
			_escapePlan.valid = false; // U3-B: no reserve, no plan (as below, on a walk to another tile)
		return;
	}
	if (!AiProbe::oxceFixes())
	{
		_wasHitBy.clear();
	}
	else if (_wasHitByTurn != _save->getTurn())
	{
		// O14 (BetterAI): who hit the unit is kept to the end of the enemy's turn (TileEngine's reaction, its comment): cleared
		// at the first decision of the unit's turn, not at each - a hit by reaction fire later in this turn is not forgotten
		_wasHitBy.clear();
		_wasHitByTurn = _save->getTurn();
	}
	_foundBaseModuleToDestroy = false;

	if (_unit->getCharging() && _unit->getCharging()->isOut())
	{
		_unit->setCharging(0);
	}

	if (_traceAI)
	{
		if (_unit->getFaction() == FACTION_HOSTILE)
		{
			Log(LOG_INFO) << "Unit has " << _visibleEnemies << "/" << _knownEnemies << " known enemies visible, " << _spottingEnemies << " of whom are spotting him. ";
		}
		else
		{
			Log(LOG_INFO) << "Civilian Unit has " << _visibleEnemies << " enemies visible, " << _spottingEnemies << " of whom are spotting him. ";
		}
		std::string AIMode;
		switch (_AIMode)
		{
		case AI_PATROL:
			AIMode = "Patrol";
			break;
		case AI_AMBUSH:
			AIMode = "Ambush";
			break;
		case AI_COMBAT:
			AIMode = "Combat";
			break;
		case AI_ESCAPE:
			AIMode = "Escape";
			break;
		}
		Log(LOG_INFO) << "Currently using " << AIMode << " behaviour";
	}

	if (_unit->isLeeroyJenkins())
	{
		AiProbe::chosen(_unit, 'l');
		dont_think(action);
		return;
	}

	if (action->weapon)
	{
		const RuleItem *rule = action->weapon->getRules();
		if (_save->canUseWeapon(action->weapon, _unit, false, BA_NONE)) // Note: ammo is not checked here
		{
			if (rule->getBattleType() == BT_FIREARM)
			{
				if (action->weapon->getCurrentWaypoints() != 0)
				{
					_blaster = true;
					reachableWithAttack(BattleActionCost(BA_AIMEDSHOT, _unit, action->weapon));
				}
				else
				{
					_rifle = true;
					reachableWithAttack(BattleActionCost(BA_SNAPSHOT, _unit, action->weapon));
				}
			}
			else if (rule->getBattleType() == BT_MELEE)
			{
				_melee = true;
				reachableWithAttack(BattleActionCost(BA_HIT, _unit, action->weapon));
			}
		}
		else
		{
			action->weapon = 0;
		}
	}

	BattleItem *grenadeItem = _unit->getGrenadeFromBelt(_save);
	_grenade = grenadeItem != 0;

	// the tactical rules need cover reachable with the TU left now, not with those of the turn's start
	const bool tactical = AiProbe::tactics(_unit) || AiProbe::careful(_unit);
	// U3-B ESCAPE RESERVE FRESHNESS (clean1: always in the bench): the reserve is the plan's, so it holds only while the
	// plan's contract does - a broken plan leaves no reserve, as upstream has none without a plan, and the line below
	// recomputes it under fire.
	if (_escapeTUs && AiProbe::staleEscapeFix() && escapePlanBroken())
	{
		_escapeTUs = 0;
	}
	if (_spottingEnemies && (!_escapeTUs || tactical))
	{
		const ProbeMark mark = probeMark('e');
		setupEscape();
		probeSlot('e', "escape", mark);
	}

	if (_knownEnemies && !_melee && !_ambushTUs)
	{
		const ProbeMark mark = probeMark('a');
		setupAmbush();
		probeSlot('a', "ambush", mark);
	}

	setupAttack();
	{
		const ProbeMark mark = probeMark('p');
		setupPatrol();
		probeSlot('p', _patrolAction.type == BA_WALK ? "patrol.node" : "patrol.module", mark);
	}

	if (_psiAction.type != BA_NONE && !_didPsi && _save->getTurn() >= _psiAction.weapon->getRules()->getAIUseDelay(_save->getMod()))
	{
		AiProbe::chosen(_unit, 's');
		_didPsi = true;
		action->type = _psiAction.type;
		action->target = _psiAction.target;
		action->number -= 1;
		action->weapon = _psiAction.weapon;
		action->updateTU();
		return;
	}
	else
	{
		_didPsi = false;
	}

	bool evaluate = false;

	switch (_AIMode)
		{
		case AI_PATROL:
			evaluate = (bool)(_spottingEnemies || _visibleEnemies || _knownEnemies || RNG::percent(10));
			break;
		case AI_AMBUSH:
			evaluate = (!_rifle || !_ambushTUs || _visibleEnemies);
			break;
		case AI_COMBAT:
			evaluate = (_attackAction.type == BA_RETHINK);
			break;
		case AI_ESCAPE:
			evaluate = (!_spottingEnemies || !_knownEnemies);
			break;
			}

	if (_weaponPickedUp)
	{
		evaluate = true;
		_weaponPickedUp = false;
	}
	else if (_spottingEnemies > 2
		|| _unit->getHealth() < 2 * _unit->getBaseStats()->health / 3)
	{
		evaluate = true;
	}


	if (_save->isCheating() && _AIMode != AI_COMBAT)
	{
		evaluate = true;
	}

	if (evaluate)
	{
		evaluateAIMode();
		if (_traceAI)
		{
			std::string AIMode;
			switch (_AIMode)
			{
			case AI_PATROL:
				AIMode = "Patrol";
				break;
			case AI_AMBUSH:
				AIMode = "Ambush";
				break;
			case AI_COMBAT:
				AIMode = "Combat";
				break;
			case AI_ESCAPE:
				AIMode = "Escape";
				break;
			}
			Log(LOG_INFO) << "Re-Evaluated, now using " << AIMode << " behaviour";
		}
	}

	// a shot the evaluator found worth its risk is combat whatever mode the dice gave
	if (_evalChosen)
	{
		_AIMode = AI_COMBAT;
	}

	if (tactical)
	{
		tacticalMode();
	}

	_reserve = BA_NONE;
	// the careful bot kneels by the player's rule (soldiers may), the AI by its own (armor must allow)
	const bool kneelDefault = AiProbe::careful(_unit) && _unit->getType() == "SOLDIER";

	// U3-A STALE ESCAPE PLAN (clean1: always in the bench): the escape plan is reused while its contract holds, computed
	// again here the moment it does not
	if (_AIMode == AI_ESCAPE && AiProbe::staleEscapeFix() && escapePlanBroken() != 0)
	{
		const ProbeMark mark = probeMark('e');
		setupEscape();
		probeSlot('e', "escape.stale", mark);
	}

	// AI3-IMM (bench): an armor that cannot move has no walking mode - patrol, escape and ambush only plan a walk that
	// UnitWalkBState drops at once; a legal attack from where it stands that setupAttack already made is taken instead
	static const bool immobileNoWalk = AiProbe::param("OXCE_AI_IMMOBILE_NO_WALK", 0) != 0;
	const bool immobile = immobileNoWalk && !_unit->getArmor()->allowsMoving();
	if (immobile && _AIMode != AI_COMBAT)
	{
		const BattleActionType modeType = _AIMode == AI_ESCAPE ? _escapeAction.type : _AIMode == AI_PATROL ? _patrolAction.type
			: _AIMode == AI_AMBUSH ? _ambushAction.type : BA_NONE;
		if (modeType == BA_WALK && _attackAction.type != BA_WALK && _attackAction.type != BA_RETHINK && _attackAction.type != BA_NONE)
		{
			AiProbe::note(_unit, (std::string("immobile.attack ") + "paxe"[_AIMode]).c_str());
			_AIMode = AI_COMBAT;
		}
	}

	switch (_AIMode)
	{
	case AI_ESCAPE:
		_unit->setCharging(0);
		action->type = _escapeAction.type;
		action->target = _escapeAction.target;
		// end this unit's turn.
		action->finalAction = true;
		// ignore new targets.
		action->desperate = true;
		// if armor allow runing then run way from there.
		action->run = _escapeAction.run;
		// spin 180 at the end of your route.
		_unit->setHiding(true);
		break;
	case AI_PATROL:
		_unit->setCharging(0);
		if (action->weapon && action->weapon->getRules()->getBattleType() == BT_FIREARM)
		{
			switch (_unit->getAggression())
			{
			case 0:
				_reserve = BA_AIMEDSHOT;
				break;
			case 1:
				_reserve = BA_AUTOSHOT;
				break;
			case 2:
				_reserve = BA_SNAPSHOT;
				break;
			default:
				break;
			}
		}
		action->type = _patrolAction.type;
		action->target = _patrolAction.target;
		endPatrolIfSpent(action, true);
		break;
	case AI_COMBAT:
		action->type = _attackAction.type;
		action->target = _attackAction.target;
		// this may have changed to a grenade.
		action->weapon = _attackAction.weapon;
		if (action->weapon && action->type == BA_THROW && action->weapon->getRules()->isGrenadeOrProxy())
		{
			_unit->spendCost(_unit->getActionTUs(BA_PRIME, action->weapon));
			_unit->spendTimeUnits(4);
		}
		// if this is a firepoint action, set our facing.
		action->finalFacing = _attackAction.finalFacing;
		action->updateTU();
		// if this is a "find fire point" action, don't increment the AI counter.
		if (action->type == BA_WALK && _rifle && _unit->getArmor()->allowsMoving()
			// so long as we can take a shot afterwards.
			&& BattleActionCost(BA_SNAPSHOT, _unit, action->weapon).haveTU())
		{
			action->number -= 1;
		}
		else if (action->type == BA_LAUNCH)
		{
			action->waypoints = _attackAction.waypoints;
		}
		else if (action->type == BA_AIMEDSHOT || action->type == BA_AUTOSHOT)
		{
			action->kneel = _unit->getArmor()->allowsKneeling(kneelDefault);
		}
		if (_evalChosen && action->type != BA_WALK)
		{
			action->kneel = _evalKneel;
		}
		break;
	case AI_AMBUSH:
		_unit->setCharging(0);
		action->type = _ambushAction.type;
		action->target = _ambushAction.target;
		// face where we think our target will appear.
		action->finalFacing = _ambushAction.finalFacing;
		// end this unit's turn.
		action->finalAction = true;
		action->kneel = _unit->getArmor()->allowsKneeling(kneelDefault);
		break;
	default:
		break;
	}
	if (_AIMode >= AI_PATROL && _AIMode <= AI_ESCAPE)
	{
		AiProbe::chosen(_unit, "paxe"[_AIMode]);
	}
	// AI3-IMM (bench): no attack from here - no walk either. The walk it replaces stopped at once and was followed by one more
	// think in the selection (which may roll the sniper's dice): the first drop keeps that think (BA_RETHINK, handleAI runs it
	// at once), a walk chosen again ends the selection, as endPatrolIfSpent does. No time units, no turn, no view change.
	if (immobile && action->type == BA_WALK)
	{
		const char mode = _AIMode >= AI_PATROL && _AIMode <= AI_ESCAPE ? "paxe"[_AIMode] : '?';
		if (_immRetry == 0)
		{
			AiProbe::note(_unit, (std::string("immobile.nowalk.retry ") + mode).c_str());
			_immRetry = 1;
			action->type = BA_RETHINK;
		}
		else
		{
			AiProbe::note(_unit, (std::string("immobile.nowalk.end ") + mode).c_str());
			action->type = BA_NONE;
		}
	}

	// the careful bot on patrol in contact walks half its time units at most and keeps the rest for reaction fire and cover:
	// it ended 77 % of turns with nothing left, 54 % of them in someone's sight (OXCE_AI_HALF)
	if (action->type == BA_WALK && _AIMode == AI_PATROL && AiProbe::halfWalk(_save, _unit))
	{
		BattleActionCost keep;
		keep.Time = _unit->getBaseStats()->tu / 2;
		Position best = _unit->getPosition();
		int bestDist = Position::distanceSq(best, action->target);
		for (int index : _save->getPathfinding()->findReachable(_unit, keep))
		{
			const Position pos = _save->getTileCoords(index);
			const int d = Position::distanceSq(pos, action->target);
			if (d < bestDist)
			{
				bestDist = d;
				best = pos;
			}
		}
		if (best != action->target)
		{
			AiProbe::tally(_unit, best == _unit->getPosition() ? "half.stay" : "half.cut");
			action->target = best;
		}
	}

	if (action->type == BA_WALK)
	{
		// if we're moving, we'll have to re-evaluate our escape/ambush position.
		if (action->target != _unit->getPosition())
		{
			_escapeTUs = 0;
			_ambushTUs = 0;
			// U3-B (clean1: always in the bench): the reserve goes for re-evaluation, so does the plan it was the cost of - a walk
			// that ends without a step (stopped on turning) left the plan valid with no reserve for its path
			if (AiProbe::staleEscapeFix())
				_escapePlan.valid = false;
		}
		else
		{
			AiProbe::note(_unit, "walk.self");
			action->type = BA_NONE;
		}
	}

	// FIREPOINT_BLOCKED_UNIT_STALL (bench): what the think did instead of the skipped point, and a walk to a blocked point
	// another branch chose (not suppressed in V1, only counted)
	const bool firepointWalk = action->type == BA_WALK && _firepointChosen && action->target == _firepointChosenAt;
	// KNOWN_OCCUPANT_PATH_V2 (bench): the walk to the point findFirePoint or setupAmbush chose keeps that branch's T blocked
	if (firepointWalk && _ko2FpChosenTarget)
	{
		_ko2WalkTarget = _ko2FpChosenTarget;
		_ko2WalkBranch = "fp";
		_ko2WalkTo = action->target;
	}
	else if (action->type == BA_WALK && _AIMode == AI_AMBUSH && _ambushAction.type == BA_WALK && action->target == _ambushAction.target
		&& _ko2AmbChosenTarget)
	{
		_ko2WalkTarget = _ko2AmbChosenTarget;
		_ko2WalkBranch = "amb";
		_ko2WalkTo = action->target;
	}
	if (_fpSuppressedNow)
	{
		const char *after = "fpblocked.after.attack";
		if (action->type == BA_WALK)
			after = firepointWalk ? "fpblocked.after.firepoint" : (_AIMode == AI_PATROL ? "fpblocked.after.patrol" : "fpblocked.after.move");
		else if (action->type == BA_NONE)
			after = "fpblocked.after.end";
		else if (action->type == BA_RETHINK)
			after = "fpblocked.after.rethink";
		else if (action->type == BA_TURN)
			after = "fpblocked.after.turn";
		AiProbe::tally(_unit, after);
	}
	if (_fpBlocked && action->type == BA_WALK && !firepointWalk && action->target == _fpBlockedPoint
		&& _unit->getPosition() == _fpBlockedFrom && _unit->getTimeUnits() == _fpBlockedTu && unitTurn() == _fpBlockedTurn)
	{
		AiProbe::tally(_unit, "fpblocked.other_branch");
	}
}


/**
 * The unit-turn now: a unit acts once per turn and side.
 */
int AIModule::unitTurn() const
{
	return _save->getTurn() * 8 + (int)_save->getSide();
}

/**
 * Is this the walk of a patrol to its node, as the last think chose it?
 */
bool AIModule::isPatrolWalk(const BattleAction &action) const
{
	return _patrolWalk && action.type == BA_WALK;
}

/**
 * The tiles the unit can walk to and still attack at, and what they leave for the walk (FIREPOINT_ENERGY_PATH_V1 reads it).
 * @param cost The attack.
 */
void AIModule::reachableWithAttack(const BattleActionCost &cost)
{
	_reachableWithAttack = _save->getPathfinding()->findReachable(_unit, cost);
	// the same budget as findReachable's own
	_reachableTuMax = _unit->getTimeUnits() - cost.Time;
	_reachableEnergyMax = _unit->getEnergy() - cost.Energy;
	if (bestCellBits() & AiProbe::BC_REACHCOST)
	{
		// BEST_CELL REACHCOST (bench): the cost to each tile now, before any other search resets the nodes reachedTU reads
		_reachCost.assign(_save->getMapSizeXYZ(), -1);
		for (int index : _reachableWithAttack)
		{
			_reachCost[index] = _save->getPathfinding()->reachedTU(_save->getTileCoords(index));
		}
	}
}

/**
 * The walk being done stopped at a unit (walk.stop.unit) on the step in dir (FIREPOINT_BLOCKED_UNIT_STALL, bench): if
 * findFirePoint chose it, records the point, the step and the state it was asked in. Nothing of the unit in the way is
 * read - the side may not see it.
 */
void AIModule::firepointWalkBlocked(const BattleAction &action, int dir)
{
	recordFirepointBlockedAttempt(action, dir, false);
}

/**
 * REPEATED_BLOCKED_STEP_V1 suppressed the first step of the walk handleAI calculated and found no way round it
 * (FIREPOINT_BLOCKED_V2_INTEROP, bench): the walk the old code took here stopped at the unit on that step at once, so the
 * record gets the fact walk.stop.unit would have given it. Only the suppressed step is known - nothing of the unit.
 */
void AIModule::firepointStepSuppressed(const BattleAction &action, int dir)
{
	recordFirepointBlockedAttempt(action, dir, true);
}

/**
 * One blocked attempt of the firepoint walk, from a real stop or from V1's suppression: recorded if findFirePoint chose the
 * walk. The tallies tell the two apart (fpblocked.recorded / .retry against fpblocked.v1.recorded / .retry).
 */
void AIModule::recordFirepointBlockedAttempt(const BattleAction &action, int dir, bool v1Suppression)
{
	if (!_firepointChosen || action.type != BA_WALK || action.target != _firepointChosenAt)
	{
		return;
	}
	if (_fpInvalidated && _fpInvalidatedFrom == _unit->getPosition() && _fpInvalidatedDir == dir)
	{
		AiProbe::tally(_unit, v1Suppression ? "fpblocked.v1.retry" : "fpblocked.retry");
	}
	_fpInvalidated = false;
	_fpBlocked = true;
	_fpBlockedPoint = action.target;
	_fpBlockedDir = dir;
	_fpBlockedFrom = _unit->getPosition();
	_fpBlockedTu = _unit->getTimeUnits();
	_fpBlockedTurn = unitTurn();
	_fpBlockedAggro = _aggroTarget ? _aggroTarget->getId() : -1;
	_fpBlockedAggroPos = _aggroTarget ? knownPos(_aggroTarget, "firepoint") : Position(-1, -1, -1);
	_fpBlockedRev = AiProbe::knownRevision(_save, _unit);
	AiProbe::tally(_unit, v1Suppression ? "fpblocked.v1.recorded" : "fpblocked.recorded");
}

/**
 * Does the blocked firepoint's record hold for the ask findFirePoint is making (FIREPOINT_BLOCKED_UNIT_STALL)? The same
 * unit-turn, place, TU, target where it was and the same revision of what the side knows; anything else drops the record
 * with the list of what changed, and the point may be tried again.
 */
bool AIModule::firepointBlockedHolds()
{
	std::string why;
	if (unitTurn() != _fpBlockedTurn) why += ",turn";
	if (_unit->getPosition() != _fpBlockedFrom) why += ",unit_pos";
	if (_unit->getTimeUnits() != _fpBlockedTu) why += ",TU";
	if ((_aggroTarget ? _aggroTarget->getId() : -1) != _fpBlockedAggro) why += ",target";
	else if (_aggroTarget && knownPos(_aggroTarget, "firepoint") != _fpBlockedAggroPos) why += ",target_pos";
	if (why.empty())
	{
		unsigned long long rev = AiProbe::knownRevision(_save, _unit);
		if (AiProbe::firepointBlockedSalt() && _fpSaltTurn != unitTurn())
		{
			// the test of the invalidation: once per unit-turn the revision is seen changed
			_fpSaltTurn = unitTurn();
			rev ^= 1;
		}
		if (rev != _fpBlockedRev) why += ",known_revision";
	}
	if (why.empty())
	{
		return true;
	}
	_fpBlocked = false;
	_fpInvalidated = true;
	_fpInvalidatedFrom = _fpBlockedFrom;
	_fpInvalidatedDir = _fpBlockedDir;
	AiProbe::tally(_unit, "fpblocked.invalidated");
	AiProbe::note(_unit, ("fpblocked.why " + why.substr(1)).c_str());
	return false;
}

/**
 * KNOWN_OCCUPANT_PATH_V1 (bench): the closest known target, as selectClosestKnownEnemy picks it for findFirePoint, if the
 * unit's side spotted it this turn. Its tile is the one the AI already aims at, but Pathfinding::isBlocked takes it for free
 * ground unless the unit itself spotted it. Nothing older and no other target; leaves _aggroTarget alone.
 * @param age How many turns ago the side spotted the closest known target; -1 if there is none.
 * @return The target, or null.
 */
const BattleUnit *AIModule::knownOccupant(int &age) const
{
	const BattleUnit *closest = 0;
	int minDist = 255;
	for (auto* bu : *_save->getUnits())
	{
		if (validTarget(bu, true, false))
		{
			int dist = Position::distance2d(bu->getPosition(), _unit->getPosition());
			if (dist < minDist)
			{
				minDist = dist;
				closest = bu;
			}
		}
	}
	age = closest ? closest->getTurnsSinceSpottedByFaction(_unit->getFaction()) : -1;
	return age == 0 ? closest : 0;
}

/**
 * KNOWN_OCCUPANT_PATH_V1 (bench): the decision is made - whether the thinks' searches took the target's tile as blocked,
 * and the walk that came of it (firepoint, patrol, another walk or none).
 */
void AIModule::knownOccupantDecided(const BattleAction &action)
{
	Pathfinding *pf = _save->getPathfinding();
	const char *walk = "nowalk";
	if (action.type == BA_WALK)
	{
		walk = _firepointChosen && action.target == _firepointChosenAt ? "firepoint" : isPatrolWalk(action) ? "patrol" : "walk_other";
	}
	AiProbe::knownOccupantDecided(_unit, pf->getKnownOccupant(_unit), _knownOccAge, pf->takeKnownOccupantHits(), _aggroTarget, walk);
}

/**
 * KNOWN_OCCUPANT_PATH_V1 (bench): the walk's own path is calculated - whether its search took the target's tile as blocked.
 */
void AIModule::knownOccupantWalked(const BattleAction &action, bool found)
{
	Pathfinding *pf = _save->getPathfinding();
	AiProbe::knownOccupantWalked(_unit, pf->getKnownOccupant(_unit), pf->takeKnownOccupantHits(), action.target, found);
}

/**
 * KNOWN_OCCUPANT_PATH_V2 (bench): the target findFirePoint / setupAmbush just chose (_aggroTarget), if the unit's side spotted
 * it this turn. The caller supplies it to its own path searches only; no search looks for the target by itself.
 * @param old Set if there is a target, but the side did not spot it this turn (the rule holds back).
 * @return The target, or null.
 */
const BattleUnit *AIModule::knownOccupantV2(bool &old) const
{
	old = false;
	if (!AiProbe::knownOccupantPathV2() || _unit->getFaction() != FACTION_HOSTILE || !_aggroTarget)
	{
		return 0;
	}
	if (_aggroTarget->getTurnsSinceSpottedByFaction(_unit->getFaction()) == 0)
	{
		return _aggroTarget;
	}
	old = true;
	return 0;
}

/**
 * KNOWN_OCCUPANT_PATH_V2 (bench): this unit's own path search to pos, with the target's tile blocked for this search only.
 */
void AIModule::calculateKnownOccupantV2(const Position &pos, const BattleUnit *target, int &hits)
{
	Pathfinding *pf = _save->getPathfinding();
	if (!target)
	{
		pf->calculate(_unit, pos, BAM_NORMAL);
		return;
	}
	pf->setKnownOccupant(_unit, target);
	pf->calculate(_unit, pos, BAM_NORMAL);
	pf->setKnownOccupant(0, 0);
	hits += pf->takeKnownOccupantHits();
}

/**
 * KNOWN_OCCUPANT_PATH_V2 (bench): the decision is made - what the two branches' searches blocked this think.
 */
void AIModule::knownOccupantV2Decided(const BattleAction &action)
{
	const bool walk = action.type == BA_WALK && _ko2WalkBranch && action.target == _ko2WalkTo;
	if (_ko2FpRan)
	{
		AiProbe::knownOccupantV2Decided(_unit, "fp", _ko2FpTarget, _ko2FpOld, _ko2FpHits, walk && _ko2WalkBranch[0] == 'f');
	}
	if (_ko2AmbRan)
	{
		AiProbe::knownOccupantV2Decided(_unit, "amb", _ko2AmbTarget, _ko2AmbOld, _ko2AmbHits, walk && _ko2WalkBranch[0] == 'a');
	}
}

/**
 * KNOWN_OCCUPANT_PATH_V2 (bench): the target whose tile the walk's own path search takes as blocked, if this is the walk to the
 * point findFirePoint or setupAmbush chose and the side still has the target spotted this turn.
 */
const BattleUnit *AIModule::knownOccupantV2Walk(const BattleAction &action) const
{
	if (!_ko2WalkTarget || action.type != BA_WALK || action.target != _ko2WalkTo || _ko2WalkTarget->isOut()
		|| _ko2WalkTarget->getTurnsSinceSpottedByFaction(_unit->getFaction()) != 0)
	{
		return 0;
	}
	return _ko2WalkTarget;
}

/**
 * KNOWN_OCCUPANT_PATH_V2 (bench): the walk's own path is calculated with the target's tile blocked.
 */
void AIModule::knownOccupantV2Walked(const BattleAction &action, bool found, int hits)
{
	AiProbe::knownOccupantV2Walked(_unit, _ko2WalkBranch, hits, action.target, found);
}

/**
 * PATROL_REUSE_PROBE (bench): a unit's class as this unit's side sees it - own, ally (player and neutral), or an enemy by
 * how long ago the side spotted it (never: 255, what a unit starts the battle with; a battle is shorter than 255 turns).
 */
const char *AIModule::patrolReuseWho(const BattleUnit *other) const
{
	const UnitFaction own = _unit->getFaction(), f = other->getFaction();
	if (f == own)
	{
		return "own";
	}
	if ((own == FACTION_PLAYER && f == FACTION_NEUTRAL) || (own == FACTION_NEUTRAL && f == FACTION_PLAYER))
	{
		return "ally";
	}
	const int seen = other->getTurnsSinceSpottedByFaction(own);
	return seen == 0 ? "enemy_seen_this_turn" : seen >= 255 ? "enemy_never_seen" : "enemy_known_old";
}

/**
 * PATROL_REUSE_PROBE (bench, passive): setupPatrol keeps the node it stored in an earlier think. What stands on the node,
 * whether this unit's own search reaches it, and the first unit on that path (the search sees only the units the unit
 * spotted, so the path may run through one it did not). The search is the one choosing a node does, aborted as there.
 */
void AIModule::patrolReuseProbe()
{
	const Position node = _toNode->getPosition();
	const int size = _unit->getArmor()->getSize();
	auto unitAt = [&](const Position &p) -> const BattleUnit*
	{
		for (int x = 0; x < size; ++x)
		{
			for (int y = 0; y < size; ++y)
			{
				const Tile *t = _save->getTile(p + Position(x, y, 0));
				const BattleUnit *u = t ? t->getUnit() : 0;
				if (u && u != _unit && !u->isOut())
				{
					return u;
				}
			}
		}
		return 0;
	};
	Pathfinding *pf = _save->getPathfinding();
	pf->calculate(_unit, node, BAM_NORMAL);
	const std::vector<int> path = pf->copyPath();
	const int expanded = pf->getExpanded();
	pf->abortPath();

	const BattleUnit *occ = unitAt(node), *route = 0;
	Position at = _unit->getPosition(), first(-1, -1, -1), routeAt;
	for (auto i = path.rbegin(); i != path.rend(); ++i)
	{
		const PathfindingStep step = pf->getTUCost(at, *i, _unit, 0, BAM_NORMAL);
		if (step.cost.time >= Pathfinding::INVALID_MOVE_COST)
		{
			break;
		}
		at = step.pos;
		if (i == path.rbegin())
		{
			first = at;
		}
		if (!route && (route = unitAt(at)))
		{
			routeAt = at;
		}
	}

	_prNode = node;
	_prRoute.clear();
	if (occ)
	{
		_prClass = std::string("occupied_") + patrolReuseWho(occ);
	}
	else
	{
		_prClass = path.empty() ? "unreachable" : "valid";
		if (!path.empty())
		{
			_prRoute = route ? patrolReuseWho(route) : "free";
		}
	}
	std::ostringstream s;
	s << "patrol.reuse " << _prClass << " node " << node.x << "," << node.y << "," << node.z
		<< " age " << (_toNodeTurn < 0 ? -1 : _save->getTurn() - _toNodeTurn) << " reach " << (path.empty() ? 0 : 1)
		<< " first " << first.x << "," << first.y << "," << first.z << " occ ";
	if (occ)
	{
		s << occ->getId() << "/" << (int)occ->getFaction() << "/s" << occ->getTurnsSinceSpottedByFaction(_unit->getFaction());
	}
	else
	{
		s << "-";
	}
	s << " route ";
	if (route && !occ)
	{
		s << route->getId() << "/" << (int)route->getFaction() << "/s" << route->getTurnsSinceSpottedByFaction(_unit->getFaction())
			<< "@" << routeAt.x << "," << routeAt.y << "," << routeAt.z;
	}
	else
	{
		s << "-";
	}
	// PATROL_NO_PATH_CAUSE (bench, passive): the free node out of reach - the same search with the unit's own side, the units
	// it knows of, both, or every unit not blocking. Unknown units never block isBlocked's floor rule (they are found on the
	// walk), only the big-unit and falling rules, which stop at any unit: what only the last search reaches is that.
	_prCause.clear();
	if (!occ && path.empty() && AiProbe::patrolNoPathProbe())
	{
		const auto fin = pf->finalPositionFor(_unit, node, BAM_NORMAL);
		int eOwn = 0, eSeen = 0, eBoth = 0, eAll = 0;
		const int rOwn = pf->probeReach(_unit, node, Pathfinding::IGNORE_OWN, eOwn);
		const int rSeen = pf->probeReach(_unit, node, Pathfinding::IGNORE_SEEN, eSeen);
		const int rBoth = pf->probeReach(_unit, node, Pathfinding::IGNORE_OWN | Pathfinding::IGNORE_SEEN, eBoth);
		const int rAll = pf->probeReach(_unit, node, Pathfinding::IGNORE_OWN | Pathfinding::IGNORE_SEEN | Pathfinding::IGNORE_ALL_UNITS, eAll);
		// the real search again, so the node flags and the expanded count are those it left
		pf->calculate(_unit, node, BAM_NORMAL);
		pf->abortPath();
		_prCause = rOwn > 0 && rSeen > 0 ? "own_or_seen" : rOwn > 0 ? "own" : rSeen > 0 ? "seen" : rBoth > 0 ? "own_and_seen"
			: rAll > 0 ? "unit_rule" : rAll == 0 ? "geometry" : "geometry_refused";
		s << " nopath " << _prCause << " fin ";
		if (fin)
		{
			s << fin->x << "," << fin->y << "," << fin->z;
		}
		else
		{
			s << "none";
		}
		s << " r " << rOwn << "/" << rSeen << "/" << rBoth << "/" << rAll
			<< " exp " << expanded << "/" << eOwn << "/" << eSeen << "/" << eBoth << "/" << eAll;
	}
	_prTrail = s.str();
}

/**
 * PATROL_REUSE_PROBE (bench): the decision is made - what its last setupPatrol found keeping the stored node, if it kept one.
 */
void AIModule::patrolReuseDecided(const BattleAction &action)
{
	if (_prClass.empty())
	{
		return;
	}
	const bool chosen = action.type == BA_WALK && action.target == _prNode;
	AiProbe::patrolReuseDecided(_unit, _prClass.c_str(), _prRoute.empty() ? 0 : _prRoute.c_str(), chosen, _prTrail);
	if (!_prCause.empty())
	{
		AiProbe::patrolNoPathDecided(_unit, _prCause.c_str(), chosen);
		_prCause.clear();
	}
	_prClass.clear();
}

/**
 * No more patrol walks for the rest of this unit-turn (ENERGY_PATROL_END_V2).
 */
void AIModule::spendPatrol()
{
	_patrolSpent = unitTurn();
	_patrolSpentAt = _unit->getPosition();
	_patrolSpentEnergy = _unit->getEnergy();
}

/**
 * The patrol's walk chosen by think or dont_think (isLeeroyJenkins): marks it for spendPatrol and, if no step is left by
 * energy this unit-turn, drops it (ENERGY_PATROL_END_V2). The empty walk it replaces was followed by another think in the
 * same selection, which may throw the dice for combat; with retry the first drop keeps that think (handleAI runs it at
 * once on BA_RETHINK) and only a patrol chosen again ends the selection.
 */
void AIModule::endPatrolIfSpent(BattleAction *action, bool retry)
{
	_patrolWalk = _patrolAction.type == BA_WALK;
	if (_patrolWalk && _patrolSpent == unitTurn() && _unit->getPosition() == _patrolSpentAt && _unit->getEnergy() <= _patrolSpentEnergy)
	{
		// the walk would stop where it stands
		if (retry && _patrolRetry == 0)
		{
			AiProbe::tally(_unit, "patrol.retry");
			_patrolRetry = 1;
			action->type = BA_RETHINK;
		}
		else
		{
			AiProbe::tally(_unit, "patrol.spent");
			action->type = BA_NONE;
		}
	}
}

/*
 * sets the "was hit" flag to true.
 */
void AIModule::setWasHitBy(BattleUnit *attacker)
{
	if (attacker->getFaction() != _unit->getFaction() && !getWasHitBy(attacker->getId()))
		_wasHitBy.push_back(attacker->getId());
}

/*
 * Sets the "unit picked up a weapon" flag.
 */
void AIModule::setWeaponPickedUp()
{
	_weaponPickedUp = true;
}

/*
 * Gets whether the unit was hit.
 * @return if it was hit.
 */
bool AIModule::getWasHitBy(int attacker) const
{
	return std::find(_wasHitBy.begin(), _wasHitBy.end(), attacker) != _wasHitBy.end();
}
/*
 * Sets up a patrol action.
 * this is mainly going from node to node, moving about the map.
 * handles node selection, and fills out the _patrolAction with useful data.
 */
void AIModule::setupPatrol()
{
	_patrolAction.clearTU();
	_prClass.clear();
	if (_toNode != 0 && _unit->getPosition() == _toNode->getPosition())
	{
		if (_traceAI)
		{
			Log(LOG_INFO) << "Patrol destination reached!";
		}
		// destination reached
		// head off to next patrol node
		_fromNode = _toNode;
		freePatrolTarget();
		_toNode = 0;
		// take a peek through window before walking to the next node
		int dir = _save->getTileEngine()->faceWindow(_unit->getPosition());
		if (dir != -1 && dir != _unit->getDirection())
		{
			_unit->lookAt(dir);
			while (_unit->getStatus() == STATUS_TURNING)
			{
				_unit->turn();
			}
		}
	}

	if (_fromNode == 0)
	{
		// assume closest node as "from node"
		// on same level to avoid strange things, and the node has to match unit size or it will freeze
		int closest = 1000000;
		for (auto* node : *_save->getNodes())
		{
			if (node->isDummy())
			{
				continue;
			}
			int d = Position::distanceSq(_unit->getPosition(), node->getPosition());
			if (_unit->getPosition().z == node->getPosition().z
				&& d < closest
				&& (!(node->getType() & Node::TYPE_SMALL) || _unit->getArmor()->getSize() == 1))
			{
				_fromNode = node;
				closest = d;
			}
		}
	}
	int triesLeft = 5;
	// PATROL_REUSE_PROBE (bench, passive): the node stored in an earlier think is kept without a new search
	const bool keptNode = _toNode != 0;
	if (keptNode && AiProbe::patrolReuseProbe())
	{
		patrolReuseProbe();
	}
	// STALE_PATROL_NODE_V1 (bench): the kept node passes the check a new one does below - no path by this unit's own search
	// (which sees only what the unit may know) and it is dropped for a new choice; why there is none is not asked
	const bool staleCheck = keptNode && AiProbe::stalePatrolNode();
	Position staleOld(-1, -1, -1);
	if (staleCheck)
	{
		Pathfinding *pf = _save->getPathfinding();
		// EXACT_STALE_REACH_V1 (bench): the same question answered by Pathfinding::witnessReach where it proves the answer - a
		// path found under the cap, or every reachable tile taken with nothing the cap dropped left unreached; the rest goes
		// to the full search; so does a check with KNOWN_OCCUPANT_PATH_V1's target set, whose hits only calculate counts
		const int exact = AiProbe::staleExact();
		int ans = 2, wexp = 0;
		if (exact && !pf->getKnownOccupant(_unit))
		{
			int wcost = -1;
			const int w = pf->witnessReach(_unit, _toNode->getPosition(), 4, wexp, wcost);
			ans = w == 1 ? 1 : (w == 0 || w == -1) ? 0 : 2; // -1: calculate refuses before searching, no path either
			if (exact == 3 && ans == 1 && wcost > 300)
			{
				ans = 0; // the broken control: a search's own limit taken for no path
			}
		}
		bool noPath = ans == 0;
		int full = -1;
		if (ans == 2 || exact == 2)
		{
			// STALE_REACH_SHADOW (bench, passive): the check's own time, then the same question by other searches
			const bool shadow = AiProbe::staleShadow();
			const auto t0 = shadow ? std::chrono::steady_clock::now() : std::chrono::steady_clock::time_point();
			pf->calculate(_unit, _toNode->getPosition(), BAM_NORMAL);
			const bool fullNoPath = pf->getStartDirection() == -1;
			if (shadow)
			{
				const long long ns = std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - t0).count();
				AiProbe::staleShadowAsk(_save, _unit, _toNode->getPosition(), fullNoPath, pf->getExpanded(), pf->getTotalTUCost(), ns);
			}
			pf->abortPath();
			full = fullNoPath ? 0 : 1;
			if (ans == 2)
			{
				noPath = fullNoPath;
			}
		}
		else
		{
			pf->settleWitness(_unit);
		}
		if (exact)
		{
			AiProbe::staleExactAsked(_unit, _toNode->getPosition(), ans, wexp, full);
		}
		if (noPath)
		{
			staleOld = _toNode->getPosition();
			freePatrolTarget();
			_toNode = 0;
		}
	}
	const int staleAge = _toNodeTurn < 0 ? -1 : _save->getTurn() - _toNodeTurn;
	// O8 (BetterAI): a node with no path is held as allocated for the rest of the tries - else the guard's choice (the
	// highest flags, no chance in it) picks it again and all five tries go to the same node; freed after the loop
	std::vector<Node*> noPathNodes;
	const bool oxceFixes = AiProbe::oxceFixes();

	while (_toNode == 0 && triesLeft)
	{
		triesLeft--;
		// look for a new node to walk towards
		bool scout = true;
		if (_save->getMissionType() != "STR_BASE_DEFENSE")
		{
			// after turn 20 or if the morale is low, everyone moves out the UFO and scout
			// also anyone standing in fire should also probably move
			if (_save->isCheating() || !_fromNode || _fromNode->getRank() == 0 ||
				(_save->getTile(_unit->getPosition()) && _save->getTile(_unit->getPosition())->getFire()))
			{
				scout = true;
			}
			else
			{
				scout = false;
			}
		}

		// in base defense missions, the smaller aliens walk towards target nodes - or if there, shoot objects around them
		else if (_unit->getArmor()->getSize() == 1 && _unit->getOriginalFaction() == FACTION_HOSTILE &&
				_attackAction.weapon &&
				_attackAction.weapon->getRules()->getAccuracySnap() &&
				!_attackAction.weapon->getRules()->getArcingShot() &&
				_attackAction.weapon->getAmmoForAction(BA_SNAPSHOT) &&
				!_attackAction.weapon->getAmmoForAction(BA_SNAPSHOT)->getRules()->getArcingShot() &&
				_attackAction.weapon->getAmmoForAction(BA_SNAPSHOT)->getRules()->getDamageType()->isDirect() &&
				_attackAction.weapon->getAmmoForAction(BA_SNAPSHOT)->getRules()->getDamageType()->ToTile > 0.01f)
		{
			// can i shoot an object?
			if ((!oxceFixes || _fromNode) && _fromNode->isTarget() &&
				_save->canUseWeapon(_attackAction.weapon, _unit, false, BA_SNAPSHOT) &&
				_save->getModuleMap()[_fromNode->getPosition().x / 10][_fromNode->getPosition().y / 10].second > 0)
			{
				// scan this room for objects to destroy
				int x = (_unit->getPosition().x/10)*10;
				int y = (_unit->getPosition().y/10)*10;
				// O12 (BetterAI): the whole 10x10 module, not its first 9x9, and no tile off the map
				const int span = oxceFixes ? 10 : 9;
				for (int i = x; i < x+span; i++)
				for (int j = y; j < y+span; j++)
				{
					if (oxceFixes && !_save->getTile(Position(i, j, 1)))
					{
						continue;
					}
					MapData *md = _save->getTile(Position(i, j, 1))->getMapData(O_OBJECT);
					if (md && md->isBaseModule())
					{
						_patrolAction.actor = _unit;
						_patrolAction.target = Position(i, j, 1);
						_patrolAction.weapon = _attackAction.weapon;
						_patrolAction.type = BA_SNAPSHOT;
						_patrolAction.updateTU();
						_foundBaseModuleToDestroy = _save->getMod()->getAIDestroyBaseFacilities();
						return;
					}
				}
			}
			else
			{
				// find closest high value target which is not already allocated
				int closest = 1000000;
				BattleUnit* nodeunit = nullptr;
				for (auto* node : *_save->getNodes())
				{
					if (node->isDummy())
					{
						continue;
					}

					nodeunit = _save->getTile(node->getPosition())->getUnit();
					if (nodeunit && nodeunit->getFaction() == _unit->getFaction())
					{
						continue;
					}

					if (node->isTarget() && !node->isAllocated() && _save->getModuleMap()[node->getPosition().x / 10][node->getPosition().y / 10].second > 0)
					{
						int d = Position::distanceSq(_unit->getPosition(), node->getPosition());
						if (!_toNode ||  (d < closest && node != _fromNode))
						{
							_toNode = node;
							closest = d;
						}
					}
				}
			}
		}

		if (_toNode == 0)
		{
			_toNode = _save->getPatrolNode(scout, _unit, _fromNode);
			if (_toNode == 0)
			{
				_toNode = _save->getPatrolNode(!scout, _unit, _fromNode);
			}
		}

		if (_toNode != 0)
		{
			_save->getPathfinding()->calculate(_unit, _toNode->getPosition(), BAM_NORMAL);
			if (_save->getPathfinding()->getStartDirection() == -1)
			{
				if (oxceFixes && !_toNode->isAllocated())
				{
					_toNode->allocateNode();
					noPathNodes.push_back(_toNode);
				}
				_toNode = 0;
			}
			_save->getPathfinding()->abortPath();
		}
	}
	for (auto* node : noPathNodes)
	{
		node->freeNode();
	}

	const bool staleCleared = staleOld.x != -1;
	if (_toNode != 0 && (!keptNode || staleCleared))
	{
		_toNodeTurn = _save->getTurn();
	}
	if (staleCheck)
	{
		AiProbe::stalePatrolChecked(_unit, staleCleared, staleOld, staleAge, _toNode ? _toNode->getPosition() : Position(-1, -1, -1));
	}
	if (_toNode != 0)
	{
		_toNode->allocateNode();
		_patrolAction.actor = _unit;
		_patrolAction.type = BA_WALK;
		_patrolAction.target = _toNode->getPosition();
	}
	else
	{
		_patrolAction.type = BA_RETHINK;
	}
}

/**
 * Try to set up an ambush action
 * The idea is to check within a 11x11 tile square for a tile which is not seen by our aggroTarget,
 * but that can be reached by him. we then intuit where we will see the target first from our covered
 * position, and set that as our final facing.
 * Fills out the _ambushAction with useful data.
 */
void AIModule::setupAmbush()
{
	_ambushAction.type = BA_RETHINK;
	int bestScore = 0;
	_ambushTUs = 0;
	std::vector<int> path;
	bool fastPass = false;
	_ko2AmbChosenTarget = 0;

	if (selectClosestKnownEnemy())
	{
		// AI2-H FAIR KNOWLEDGE: the whole ambush estimation (the enemy's eyes, its paths to the nodes, the facing walk) runs with
		// the target where this side knows it to be; no change unless that is not its current place
		Position knownPos;
		int knownDir = 0;
		const int knownKind = knownPlace(_aggroTarget, "ambush", knownPos, knownDir);
		AiKnownPlace known(_save, _aggroTarget, knownKind, knownPos, knownDir);
		// KNOWN_OCCUPANT_PATH_V2 (bench): the target it hides from blocks its own tile for this unit's searches to the nodes;
		// the target's own searches (can it reach the node) are not touched
		bool ko2Old = false;
		const BattleUnit *ko2 = knownOccupantV2(ko2Old);
		if (AiProbe::knownOccupantPathV2() && _unit->getFaction() == FACTION_HOSTILE)
		{
			_ko2AmbRan = true;
			_ko2AmbTarget = ko2;
			_ko2AmbOld = ko2Old;
		}
		const int BASE_SYSTEMATIC_SUCCESS = 100;
		const int COVER_BONUS = 25;
		const int FAST_PASS_THRESHOLD = 80;
		Position origin = _save->getTileEngine()->getSightOriginVoxel(_aggroTarget);
		AiProbe::ambushBegin(_save, _unit, _aggroTarget);
		AiProbe::hypoBegin(_unit, "ambush", _spottingEnemies);
		// AMBUSH_NEGATIVE_MEMO_V2 (bench, AiProbe::ambushMemo): the tiles the enemy's first search of this call that ran out of
		// open nodes closed - everything it can reach from where it stands (Pathfinding::closedTiles); a node whose search would
		// end outside them (Pathfinding::finalPositionFor) has no path from it, and that search is skipped. Empty until such a search; dies with this call, nothing crosses decisions.
		// Invariant (accepted 01.10): only NO_PATH proven by a full A* - open list emptied, no early refusal, no cap hit
		// (closedTiles is empty otherwise) - is remembered; a positive answer is never reused; the memo lives in this call only.
		// Widening any of the three (another search's result, a cap, a longer life) is a new change with its own acceptance:
		// seven streams = against the memo off, mode 2 (verify) with 0 disagreements, fair22 IDENTICAL.
		const int memo = AiProbe::ambushMemo();
		std::vector<char> enemyReach;
		// CELL_PROF (bench, passive): as in findFirePoint; the index counts the nodes that pass the cheap checks
		const bool cellProf = AiProbe::cellProf();
		std::vector<std::pair<int, int>> cellReal;
		int cellIdx = -1, cellBreak = -1;
		const auto cellT0 = cellProf ? std::chrono::steady_clock::now() : std::chrono::steady_clock::time_point();
		// BEST_CELL (bench): LEVELS - the nodes one level below and above too; AMB_BEST - every node of the window, an equal
		// score taken by chance (reservoir over the ties); REACHCOST - a node that cannot beat the best skips both searches
		const int cellBits = bestCellBits();
		const bool ambLevels = (cellBits & AiProbe::BC_LEVELS) != 0;
		const bool ambBest = (cellBits & AiProbe::BC_AMB_BEST) != 0;
		int ambTies = 0;

		// we'll use node positions for this, as it gives map makers a good degree of control over how the units will use the environment.
		for (const auto* node : *_save->getNodes())
		{
			if (node->isDummy())
			{
				continue;
			}
			AiProbe::ambushNode(0);
			Position pos = node->getPosition();
			Tile *tile = _save->getTile(pos);
			if (tile == 0 || Position::distance2d(pos, _unit->getPosition()) > 10
				|| (ambLevels ? std::abs(pos.z - _unit->getPosition().z) > 1 : pos.z != _unit->getPosition().z) || tile->getDangerous() ||
				std::find(_reachableWithAttack.begin(), _reachableWithAttack.end(), _save->getTileIndex(pos))  == _reachableWithAttack.end())
				continue; // just ignore unreachable tiles
			AiProbe::ambushNode(1);
			++cellIdx;

			if (_traceAI)
			{
				// colour all the nodes in range purple.
				tile->setPreview(10);
				tile->setMarkerColor(13);
			}

			// make sure we can't be seen here.
			Position target;
			if (AiProbe::hypoLos())
			{
				// AI2-G HYPO_LOS (bench diagnostics): the same two checks as D1 answers them, for the line only
				AiProbe::HypoOld old;
				Position oldTarget;
				AiProbe::hypoAmbushNode(pos, !_save->getTileEngine()->canTargetUnit(&origin, tile, &oldTarget, _aggroTarget, false, _unit)
					&& !getSpottingUnits(pos));
			}
			if (!_save->getTileEngine()->canTargetUnit(&origin, tile, &target, _aggroTarget, false, _unit) && !getSpottingUnits(pos))
			{
				AiProbe::ambushNode(2);
				const int reach = reachCostAt(pos);
				if (reach >= 0)
				{
					// BEST_CELL REACHCOST: the most this node can score; one that cannot beat the best (or tie it, when ties
					// are drawn) needs neither its own nor the enemy's path search
					const int most = BASE_SYSTEMATIC_SUCCESS - reach + (_save->getTileEngine()->faceWindow(pos) != -1 ? COVER_BONUS : 0);
					if (most < bestScore || (most == bestScore && !(ambBest && bestScore > 0)))
						continue;
				}
				AiProbe::ambushMark();
				calculateKnownOccupantV2(pos, ko2, _ko2AmbHits);
				int ambushTUs = reach >= 0 ? reach : _save->getPathfinding()->getTotalTUCost();
				// make sure we can move here
				const bool ownPath = _save->getPathfinding()->getStartDirection() != -1;
				AiProbe::ambushOwn(ownPath, ambushTUs, _save->getPathfinding()->getExpanded());
				if (ownPath)
				{
					AiProbe::ambushNode(3);
					int score = BASE_SYSTEMATIC_SUCCESS;
					score -= ambushTUs;

					// make sure our enemy can reach here too.
					// V2: the memo is asked about the tile the enemy's search would end on (Pathfinding::finalPositionFor), not the node:
					// a walker's search to a node over empty air goes to the ground under it (GUNS 2352: verify 173, bad 9 under V1).
					// A destination calculate() refuses before searching is no path there as well.
					bool memoNoPath = false;
					if (!enemyReach.empty())
					{
						const auto end = _save->getPathfinding()->finalPositionFor(_aggroTarget, pos, BAM_NORMAL);
						memoNoPath = !end || !enemyReach[_save->getTileIndex(*end)];
					}
					if (memoNoPath && memo == 1)
					{
						AiProbe::ambushMemoNode(pos, true, false, ambushTUs, score, bestScore);
						continue;
					}
					AiProbe::ambushMark();
					_save->getPathfinding()->calculate(_aggroTarget, pos, BAM_NORMAL);

					const bool enemyPath = _save->getPathfinding()->getStartDirection() != -1;
					AiProbe::ambushEnemy(pos, enemyPath, _save->getPathfinding()->getTotalTUCost(), (int)_save->getPathfinding()->getPath().size(),
						_save->getPathfinding()->getExpanded(), ambushTUs, score, bestScore);
					if (memoNoPath)
					{
						AiProbe::ambushMemoNode(pos, false, enemyPath, ambushTUs, score, bestScore);
					}
					else if (memo && !enemyPath && enemyReach.empty())
					{
						enemyReach = _save->getPathfinding()->closedTiles();
					}
					if (enemyPath)
					{
						// ideally we'd like to be behind some cover, like say a window or a low wall.
						const bool cover = _save->getTileEngine()->faceWindow(pos) != -1;
						if (cover)
						{
							score += COVER_BONUS;
						}
						AiProbe::traceTile(_unit, "ambush", pos, score);
						if (cellProf)
						{
							cellReal.emplace_back(_save->getTileIndex(pos), score);
						}
						bool taken = score > bestScore;
						if (ambBest)
						{
							// BEST_CELL AMB_BEST: the k-th node of an equal best score is taken with chance 1/k - each equally likely,
							// not the first in the map file's order
							if (taken)
								ambTies = 1;
							else if (score == bestScore && bestScore > 0)
								taken = RNG::generate(1, ++ambTies) == 1;
						}
						AiProbe::ambushScored(score, cover, taken);
						if (taken)
						{
							path = _save->getPathfinding()->copyPath();
							bestScore = score;
							_ambushTUs = (pos == _unit->getPosition()) ? 1 : ambushTUs;
							_ambushAction.target = pos;
							if (bestScore > FAST_PASS_THRESHOLD && !ambBest)
							{
								fastPass = true;
								cellBreak = cellIdx;
								break;
							}
						}
					}
				}
			}
		}
		if (cellProf)
		{
			AiProbe::CellStat s;
			s.ns = std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - cellT0).count();
			s.threshold = FAST_PASS_THRESHOLD;
			s.scanned = (int)cellReal.size();
			for (const auto &c : cellReal) s.passed += c.second > FAST_PASS_THRESHOLD ? 1 : 0;
			s.breakAt = cellBreak;
			s.chosen = bestScore > 0 ? bestScore : INT_MIN;
			CellCtx c;
			c.ko2 = ko2;
			c.origin = origin;
			cellShadow(s, cellReal, true, c);
			AiProbe::cellSearch(_save, _unit, "amb", s);
		}
		AiProbe::hypoEnd(_unit, "ambush", bestScore > 0, _ambushAction.target, bestScore);

		if (bestScore > 0)
		{
			AiProbe::ambushEnd(true, bestScore, _ambushAction.target, _ambushTUs, fastPass);
			_probeScore = bestScore;
			_ambushAction.type = BA_WALK;
			_ko2AmbChosenTarget = ko2;
			// i should really make a function for this
			origin = _ambushAction.target.toVoxel() +
				// 4 because -2 is eyes and 2 below that is the rifle (or at least that's my understanding)
				Position(8,8, _unit->getHeight() + _unit->getFloatHeight() - _save->getTile(_ambushAction.target)->getTerrainLevel() - 4);
			Position currentPos = _aggroTarget->getPosition();
			_save->getPathfinding()->setUnit(_aggroTarget);
			size_t tries = path.size();
			AiProbe::hypoBegin(_unit, "facing", _spottingEnemies);
			// hypothetically walk the target through the path.
			while (tries > 0)
			{
				currentPos = _save->getPathfinding()->getTUCost(currentPos, path.back(), _aggroTarget, 0, BAM_NORMAL).pos;
				path.pop_back();
				Tile *tile = _save->getTile(currentPos);
				Position target;
				// do a virtual fire calculation
				if (_save->getTileEngine()->canTargetUnit(&origin, tile, &target, _unit, false, _aggroTarget))
				{
					// if we can virtually fire at the hypothetical target, we know which way to face.
					_ambushAction.finalFacing = _save->getTileEngine()->getDirectionTo(_ambushAction.target, currentPos);
					break;
				}
				--tries;
			}
			AiProbe::hypoEnd(_unit, "facing", tries > 0, currentPos, _ambushAction.finalFacing);
			if (_traceAI)
			{
				Log(LOG_INFO) << "Ambush estimation will move to " << _ambushAction.target;
			}
			return;
		}
	}
	AiProbe::ambushEnd(false, bestScore, _ambushAction.target, _ambushTUs, fastPass);
	if (_traceAI)
	{
		Log(LOG_INFO) << "Ambush estimation failed";
	}
}

/**
 * Try to set up a combat action
 * This will either be a psionic, grenade, or weapon attack,
 * or potentially just moving to get a line of sight to a target.
 * Fills out the _attackAction with useful data.
 */
void AIModule::setupAttack()
{
	_attackAction.type = BA_RETHINK;
	_psiAction.type = BA_NONE;
	_evalChosen = false;
	_ffThrow = false;

	bool sniperAttack = false;

	// AI3-F (bench): OXCE_AI_BOT_SPECIAL - PLAYER-BOT special actions (OXCE_AI_CAREFUL): countKnownTargets counts for the
	// hostile side only, so the bot asks psi and the waypoint launcher when its side honestly knows a hostile (seen now, or
	// remembered under FAIR_KNOWLEDGE); asked only with such a weapon, so without one the bot's path is the old one; sniper
	// stays as it was. Off - as before.
	static const bool botSpecialOn = AiProbe::param("OXCE_AI_BOT_SPECIAL", 0) != 0;
	bool botSpecial = false;
	if (botSpecialOn && !_knownEnemies && AiProbe::careful(_unit) && (_blaster || _unit->getUtilityWeapon(BT_PSIAMP)))
	{
		for (auto* bu : *_save->getUnits())
		{
			if (bu->getFaction() != FACTION_HOSTILE || bu->isOut())
			{
				continue;
			}
			Position mem;
			int dir = 0;
			if (bu->getVisible() || (AiProbe::fairKnowledge() && bu->getAiSeen(_unit->getFaction(), mem, dir)))
			{
				botSpecial = true;
				break;
			}
		}
	}

	// if enemies are known to us but not necessarily visible, we can attack them with a blaster launcher or psi or a sniper attack.
	if (_knownEnemies || botSpecial)
	{
		const ProbeMark psiMark = probeMark('s');
		const bool psi = psiAction();
		probeSlot('s', "psi", psiMark);
		if (psi)
		{
			// at this point we can save some time with other calculations - the unit WILL make a psionic attack this turn.
			return;
		}
		if (_blaster)
		{
			const ProbeMark mark = probeMark('x');
			wayPointAction();
			probeSlot('x', "waypoint", mark);
		}
		else if (!botSpecial && _unit->getUnitRules()) // xcom soldiers (under mind control) lack unit rules!
		{
			// don't always act on spotter information unless modder says so
			if (RNG::percent(_unit->getUnitRules()->getSniperPercentage()))
			{
				const ProbeMark mark = probeMark('x');
				sniperAttack = sniperAction();
				probeSlot('x', "sniper", mark);
			}
		}
	}

	// the bench's evaluator weighs every reachable tile itself: neither the nearest-target shot nor findFirePoint after it
	if (!sniperAttack && _rifle && AiProbe::evalFire(_unit))
	{
		const ProbeMark mark = probeMark('x');
		const bool evaluated = evalFireAction();
		probeSlot('x', "eval", mark);
		if (evaluated)
		{
			return;
		}
	}

	// if we CAN see someone, that makes them a viable target for "regular" attacks.
	// This is skipped if sniperAction has already chosen an attack action
	if (!sniperAttack && selectNearestTarget())
	{
		// if we have both types of weapon, make a determination on which to use.
		if (_melee && _rifle)
		{
			selectMeleeOrRanged();
		}
		if (_grenade)
		{
			const ProbeMark mark = probeMark('x');
			grenadeAction();
			probeSlot('x', "grenade", mark);
		}
		if (_melee)
		{
			const ProbeMark mark = probeMark('x');
			// AI3-F (bench): OXCE_AI_BOT_WP_MELEE - a lawful waypoint launch the bot chose (U-71) is not overwritten by a
			// charge: melee wins only with a blow it can strike now (the target adjacent, BA_HIT), else the launch and its
			// target stay as they were (the charge's side effects undone). Off - as before.
			static const bool wpMeleeOn = AiProbe::param("OXCE_AI_BOT_WP_MELEE", 0) != 0;
			const bool keepLaunch = wpMeleeOn && AiProbe::careful(_unit) && _attackAction.type == BA_LAUNCH;
			const BattleAction launch = _attackAction;
			BattleUnit *const launchTarget = _aggroTarget;
			BattleUnit *const charging = _unit->getCharging();
			meleeAction();
			if (keepLaunch)
			{
				if (_attackAction.type == BA_HIT)
				{
					AiProbe::note(_unit, "wpmelee.hit");
				}
				else
				{
					AiProbe::note(_unit, _attackAction.type == BA_LAUNCH ? "wpmelee.keep" : "wpmelee.keep.charge");
					_attackAction = launch;
					_aggroTarget = launchTarget;
					_unit->setCharging(charging);
				}
			}
			probeSlot('x', "melee", mark);
		}
		if (_rifle)
		{
			const ProbeMark mark = probeMark('x');
			projectileAction();
			probeSlot('x', "shot", mark);
		}
		if (_ffThrow)
		{
			ffThrowOrShot();
		}
	}

	if (_attackAction.type != BA_RETHINK)
	{
		if (_traceAI)
		{
			if (_attackAction.type != BA_WALK)
			{
				Log(LOG_INFO) << "Attack estimation desires to shoot at " << _attackAction.target;
			}
			else
			{
				Log(LOG_INFO) << "Attack estimation desires to move to " << _attackAction.target;
			}
		}
		return;
	}
	else if (_spottingEnemies || _unit->getAggression() < RNG::generate(0, 3))
	{
		// if enemies can see us, or if we're feeling lucky, we can try to spot the enemy.
		const ProbeMark mark = probeMark('x');
		const bool found = findFirePoint();
		probeSlot('x', "firepoint", mark);
		if (found)
		{
			if (_traceAI)
			{
				Log(LOG_INFO) << "Attack estimation desires to move to " << _attackAction.target;
			}
			return;
		}
	}
	if (_traceAI)
	{
		Log(LOG_INFO) << "Attack estimation failed";
	}
}

/**
 * Attempts to find cover, and move toward it.
 * The idea is to check within a 11x11 tile square for a tile which is not seen by our aggroTarget.
 * If there is no such tile, we run away from the target.
 * Fills out the _escapeAction with useful data.
 */
void AIModule::setupEscape()
{
	AiProbe::escapeBegin(_unit);
	AiProbe::hypoBegin(_unit, "escape", _spottingEnemies);
	int unitsSpottingMe = getSpottingUnits(_unit->getPosition());
	int currentTilePreference = 15;
	int tries = -1;
	bool coverFound = false;
	selectNearestTarget(true); // AI2-H h8: a remembered target is taken at its remembered place
	_escapeTUs = 0;
	// U3 escape plan contract: every way out of here writes _escapeAction (a walk or BA_RETHINK), so this is its provenance
	_escapePlan.valid = true;
	_escapePlan.turn = _save->getTurn();
	_escapePlan.side = (int)_save->getSide();
	_escapePlan.origin = _unit->getPosition();
	_escapePlan.aggro = _aggroTarget;

	// AI2-H FAIR KNOWLEDGE: the distance to the target where this side knows it to be
	const Position escapeAggroAt = _aggroTarget ? knownPos(_aggroTarget, "escape") : Position(-1, -1, -1);
	int dist = _aggroTarget ? Position::distance2d(_unit->getPosition(), escapeAggroAt) : 0;

	int bestTileScore = -100000;
	int score = -100000;
	Position bestTile(0, 0, 0);
	bool run = false;

	Tile *tile = 0;

	// weights of various factors in choosing a tile to which to withdraw
	const int EXPOSURE_PENALTY = 10;
	const int FIRE_PENALTY = 40;
	const int BASE_SYSTEMATIC_SUCCESS = 100;
	const int BASE_DESPERATE_SUCCESS = 110;
	const int FAST_PASS_THRESHOLD = 100; // a score that's good enough to quit the while loop early; it's subjective, hand-tuned and may need tweaking
	const int GAP_PENALTY = 60; // per enemy seen within 2 tiles of the tile, the careful bot only (OXCE_AI_GAP)
	const int TURRET_PENALTY = 100; // per known turret with a line of fire to the tile at any distance, the careful bot only (OXCE_AI_TURRET)

	std::vector<Position> randomTileSearch = _save->getTileSearch();
	RNG::shuffle(randomTileSearch);
	// CELL_PROF (bench, passive): the loop's time, the tiles it scored, where it quit; no shadow - its later tries are random
	const bool cellProf = AiProbe::cellProf();
	int cellScored = 0, cellPassed = 0;
	const auto cellT0 = cellProf ? std::chrono::steady_clock::now() : std::chrono::steady_clock::time_point();
	// BEST_CELL ESC_BEST (bench): the stay try and the whole window are scored with no quit over the threshold; the random
	// run (tries 121 and on) only while nothing passed it, and it quits on the first that does, as before
	const bool escBest = (bestCellBits() & AiProbe::BC_ESC_BEST) != 0;

	while (tries < 150 && !coverFound)
	{
		if (escBest && tries >= 121 && bestTileScore > FAST_PASS_THRESHOLD)
		{
			coverFound = true;
			break;
		}
		_escapeAction.target = _unit->getPosition(); // start looking in a direction away from the enemy
		// the careful bot runs by the player's rule (small units may), the AI by its own (armor must allow)
		_escapeAction.run = _unit->getArmor()->allowsRunning(AiProbe::careful(_unit) && _unit->isSmallUnit()) && (tries & 1); // every odd try, i.e. roughly 50%

		if (!_save->getTile(_escapeAction.target))
		{
			_escapeAction.target = _unit->getPosition(); // cornered at the edge of the map perhaps?
		}

		score = 0;

		if (tries == -1)
		{
			// you know, maybe we should just stay where we are and not risk reaction fire...
			// or maybe continue to wherever we were running to and not risk looking stupid
			if (_save->getTile(_unit->lastCover) != 0)
			{
				_escapeAction.target = _unit->lastCover;
			}
		}
		else if (tries < 121)
		{
			// looking for cover
			_escapeAction.target.x += randomTileSearch[tries].x;
			_escapeAction.target.y += randomTileSearch[tries].y;
			score = BASE_SYSTEMATIC_SUCCESS;
			if (_escapeAction.target == _unit->getPosition())
			{
				if (unitsSpottingMe > 0)
				{
					// maybe don't stay in the same spot? move or something if there's any point to it?
					_escapeAction.target.x += RNG::generate(-20,20);
					_escapeAction.target.y += RNG::generate(-20,20);
				}
				else
				{
					score += currentTilePreference;
				}
			}
		}
		else
		{
			if (tries == 121)
			{
				if (_traceAI)
				{
					Log(LOG_INFO) << "best score after systematic search was: " << bestTileScore;
				}
			}

			score = BASE_DESPERATE_SUCCESS; // ruuuuuuun
			_escapeAction.target = _unit->getPosition();
			_escapeAction.target.x += RNG::generate(-10,10);
			_escapeAction.target.y += RNG::generate(-10,10);
			_escapeAction.target.z = _unit->getPosition().z + RNG::generate(-1,1);
			if (_escapeAction.target.z < 0)
			{
				_escapeAction.target.z = 0;
			}
			else if (_escapeAction.target.z >= _save->getMapSizeZ())
			{
				_escapeAction.target.z = _unit->getPosition().z;
			}
		}

		tries++;

		// THINK, DAMN YOU
		tile = _save->getTile(_escapeAction.target);
		int distanceFromTarget = _aggroTarget ? Position::distance2d(escapeAggroAt, _escapeAction.target) : 0;
		if (AiProbe::escapeSignFix())
		{
			// U2 SETUPESCAPE DISTANCE SIGN (clean1: always in the bench): farther from the target positive, closer negative,
			// same distance 0; upstream below adds |distanceFromTarget - dist| * 10 in both branches
			score += (distanceFromTarget - dist) * 10;
		}
		else if (dist >= distanceFromTarget)
		{
			score -= (distanceFromTarget - dist) * 10;
		}
		else
		{
			score += (distanceFromTarget - dist) * 10;
		}
		int spotters = 0;
		if (!tile)
		{
			score = -100001; // no you can't quit the battlefield by running off the map.
			AiProbe::escapeProbe(_unit, 2);
		}
		else
		{
			// the escape audit (OXCE_AI_ESCAPEPROF) counts the traces and the time spent on a tile dropped as unreachable right after
			AiProbe::escapeMark();
			const bool inReach = std::find(_reachable.begin(), _reachable.end(), _save->getTileIndex(_escapeAction.target)) != _reachable.end();
			if (!inReach && AiProbe::escapeReachFirst())
			{
				// ESCAPE_REACH_FIRST_V1 (stand only, OXCE_AI_ESCAPE_REACH_FIRST): the unreachable tile is dropped before the enemies'
				// lines of fire to it are traced - getSpottingUnits is const and touches no RNG, the tile would be dropped right after
				// the traces anyway, so the reachable tiles score the same and the same tile is chosen (audit п. 12-13). Without the
				// flag the traces come first, as in OXCE (std::find above is a pure read of _reachable, its place changes nothing)
				AiProbe::escapeSkipped();
				AiProbe::escapeProbe(_unit, 0);
				continue;
			}
			spotters = getSpottingUnits(_escapeAction.target);
			AiProbe::escapeProbe(_unit, inReach ? 1 : 0);
			if (!inReach)
				continue; // just ignore unreachable tiles

			if (_spottingEnemies || spotters)
			{
				if (_spottingEnemies <= spotters)
				{
					score -= (1 + spotters - _spottingEnemies) * EXPOSURE_PENALTY; // that's for giving away our position
				}
				else
				{
					score += (_spottingEnemies - spotters) * EXPOSURE_PENALTY;
				}
			}
			if (tile->getFire())
			{
				score -= FIRE_PENALTY;
			}
			if (tile->getDangerous())
			{
				score -= BASE_SYSTEMATIC_SUCCESS;
			}
			// the careful bot does not take cover next to an enemy it sees: melee comes to the back on the enemy turn (OXCE_AI_GAP)
			score -= AiProbe::closeEnemies(_save, _unit, _escapeAction.target) * GAP_PENALTY;
			score -= AiProbe::turretsSeeing(_save, _unit, _escapeAction.target) * TURRET_PENALTY;

			if (_traceAI)
			{
				tile->setMarkerColor(score < 0 ? 3 : (score < FAST_PASS_THRESHOLD/2 ? 8 : (score < FAST_PASS_THRESHOLD ? 9 : 5)));
				tile->setPreview(10);
				tile->setTUMarker(score);
			}

		}

		if (tile)
		{
			AiProbe::traceTile(_unit, "escape", _escapeAction.target, score);
			++cellScored;
			cellPassed += score > FAST_PASS_THRESHOLD ? 1 : 0;
		}
		if (tile && score > bestTileScore)
		{
			// calculate TUs to tile; we could be getting this from findReachable() somehow but that would break something for sure...
			_save->getPathfinding()->calculate(_unit, _escapeAction.target, _escapeAction.getMoveType());
			if (_escapeAction.target == _unit->getPosition() || _save->getPathfinding()->getStartDirection() != -1)
			{
				bestTileScore = score;
				bestTile = _escapeAction.target;
				run = _escapeAction.run;
				_escapeTUs = _save->getPathfinding()->getTotalTUCost();
				if (_escapeAction.target == _unit->getPosition())
				{
					_escapeTUs = 1;
				}
				if (_traceAI)
				{
					tile->setMarkerColor(score < 0 ? 7 : (score < FAST_PASS_THRESHOLD/2 ? 10 : (score < FAST_PASS_THRESHOLD ? 4 : 5)));
					tile->setPreview(10);
					tile->setTUMarker(score);
				}
			}
			_save->getPathfinding()->abortPath();
			if (bestTileScore > FAST_PASS_THRESHOLD && !(escBest && tries < 121)) coverFound = true; // good enough, gogogo
		}
	}
	if (cellProf)
	{
		AiProbe::CellStat s;
		s.ns = std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - cellT0).count();
		s.threshold = FAST_PASS_THRESHOLD;
		s.window = tries + 1; // the tries made: -1 is the stay/last-cover try, 0-120 the window, 121-149 the random run
		s.scanned = cellScored;
		s.passed = cellPassed;
		s.breakAt = coverFound ? tries : -1;
		s.chosen = bestTileScore > -100000 ? bestTileScore : INT_MIN;
		AiProbe::cellSearch(_save, _unit, "esc", s);
	}
	AiProbe::hypoEnd(_unit, "escape", bestTileScore > -100000, bestTile, bestTileScore);
	if (bestTileScore > -100000 && AiProbe::escapeAlt(_unit))
	{
		// ESCAPE_ALT_PROBE (stand only): the reachable tiles next to the chosen one, read only - getSpottingUnits is const
		AiProbe::escapeAltWrite(_save, _unit, _reachable, bestTile, bestTileScore, _escapeTUs, run,
			[this](const Position &p) { return getSpottingUnits(p); });
	}
	_escapeAction.target = bestTile;
	_escapeAction.run = run;
	if (bestTileScore > -100000)
	{
		if (AiProbe::oxceFixes())
		{
			// O13 (BetterAI): the cover is remembered - the search's first try (tries == -1) weighs going on to it, and nothing
			// ever wrote it
			_unit->lastCover = bestTile;
		}
		const int closeNow = AiProbe::closeEnemies(_save, _unit, _unit->getPosition());
		if (closeNow > 0)
		{
			AiProbe::tally(_unit, AiProbe::closeEnemies(_save, _unit, bestTile) < closeNow ? "gap.away" : "gap.stuck");
		}
		const int turretsNow = AiProbe::turretsSeeing(_save, _unit, _unit->getPosition());
		if (turretsNow > 0)
		{
			AiProbe::tally(_unit, AiProbe::turretsSeeing(_save, _unit, bestTile) < turretsNow ? "turret.away" : "turret.stuck");
		}
	}
	if (_traceAI)
	{
		_save->getTile(_escapeAction.target)->setMarkerColor(13);
	}

	if (bestTileScore <= -100000)
	{
		if (_traceAI)
		{
			Log(LOG_INFO) << "Escape estimation failed.";
		}
		_escapeAction.type = BA_RETHINK; // do something, just don't look dumbstruck :P
		return;
	}
	else
	{
		if (_traceAI)
		{
			Log(LOG_INFO) << "Escape estimation completed after " << tries << " tries, " << Position::distance2d(_unit->getPosition(), bestTile) << " squares or so away.";
		}
		_probeScore = bestTileScore;
		_escapeAction.type = BA_WALK;
	}
}

/**
 * U3 escape plan contract (bench): may the AI_ESCAPE branch hand out _escapeAction as setupEscape left it? One contract for
 * every way a plan goes stale - the terms in their order, the first broken one named. Destination terms hold for a walk to
 * another tile only: BA_RETHINK (no tile found) and a walk to the unit's own tile have no destination to lose.
 * Reads _reachable as think made it this think.
 */
int AIModule::escapePlanBroken() const
{
	if (!_escapePlan.valid)
		return 1;
	if (_escapePlan.turn != _save->getTurn() || _escapePlan.side != (int)_save->getSide())
		return 2;
	if (_escapePlan.origin != _unit->getPosition())
		return 3;
	if (_escapeAction.type == BA_WALK && _escapeAction.target != _unit->getPosition())
	{
		const Tile *tile = _save->getTile(_escapeAction.target);
		if (!tile)
			return 4;
		// a destination taken by a unit this unit knows of is not in _reachable: findReachable blocks it by the pathfinder's own
		// rule of what the side knows (Pathfinding::isBlocked). So term 5 is also "taken so the walk is impossible" (6); a unit
		// it does not know of is no reason - reading Tile::getUnit for it would be knowledge the AI does not have
		const int index = _save->getTileIndex(_escapeAction.target);
		if (std::find(_reachable.begin(), _reachable.end(), index) == _reachable.end())
			return 5;
	}
	if (_escapePlan.aggro && _escapePlan.aggro->isOut())
		return 7;
	return 0;
}

/**
 * Counts how many targets, both xcom and civilian are known to this unit
 * @return how many targets are known to us.
 */
int AIModule::countKnownTargets() const
{
	int knownEnemies = 0;

	if (_unit->getFaction() == FACTION_HOSTILE)
	{
		for (auto* bu : *_save->getUnits())
		{
			if (validTarget(bu, true, true))
			{
				++knownEnemies;
			}
		}
	}
	return knownEnemies;
}

/*
 * counts how many enemies (xcom only) are spotting any given position.
 * @param pos the Position to check for spotters.
 * @return spotters.
 */
int AIModule::getSpottingUnits(const Position& pos) const
{
	// if we don't actually occupy the position being checked, we need to do a virtual LOF check.
	bool checking = pos != _unit->getPosition();
	int tally = 0;
	for (auto* bu : *_save->getUnits())
	{
		if (validTarget(bu, false, false))
		{
			Position kp;
			int kdir = 0;
			int kind = knownPlace(bu, "spotting", kp, kdir);
			if (kind == 2) continue;
			AiKnownPlace known(_save, bu, kind, kp, kdir);
			int dist = Position::distance2d(pos, bu->getPosition());
			if (dist > 20) continue;
			Position originVoxel = _save->getTileEngine()->getSightOriginVoxel(bu);
			originVoxel.z -= 2;
			Position targetVoxel;
			AiProbe::escapeTarget(); // the escape audit counts the traces (OXCE_AI_ESCAPEPROF)
			if (checking)
			{
				if (_save->getTileEngine()->canTargetUnit(&originVoxel, _save->getTile(pos), &targetVoxel, bu, false, _unit))
				{
					tally++;
				}
			}
			else
			{
				if (_save->getTileEngine()->canTargetUnit(&originVoxel, _save->getTile(pos), &targetVoxel, bu, false))
				{
					tally++;
				}
			}
		}
	}
	return tally;
}

/**
 * Selects the nearest known living target we can see/reach and returns the number of visible enemies.
 * This function includes civilians as viable targets.
 * @return viable targets.
 */
int AIModule::selectNearestTarget(bool escape)
{
	int tally = 0;
	_closestDist= 100;
	_aggroTarget = 0;
	Position target;
	const char *cons = escape ? "escape" : "nearest";
	int pickState = AiProbe::FAIR_LEGACY;
	for (auto* bu : *_save->getUnits())
	{
		// AI2-H h8: a geometric ray does not make the side know where a hidden enemy stands now
		int kst = AiProbe::FAIR_LEGACY, kdir = 0, oldPass = -1;
		Position kp;
		const int mode = validTarget(bu, true, true) ? fairNearestMode(bu, escape, cons, kst, kp, kdir, oldPass) : 0;
		AiKnownPlace known(_save, bu, mode == 2 && kp != bu->getPosition() ? 1 : 0, kp, kdir);
		const bool seen = mode != 0 && _save->getTileEngine()->visible(_unit, bu->getTile());
		if (mode == 2)
		{
			AiProbe::fairSel(_unit, bu, cons, kst, oldPass, seen ? 1 : 0, seen ? "mem" : "none", kp);
		}
		if (seen)
		{
			tally++;
			int dist = Position::distance2d(_unit->getPosition(), bu->getPosition());
			if (dist < _closestDist)
			{
				bool valid = false;
				if (_rifle || !_melee)
				{
					BattleAction action;
					action.actor = _unit;
					action.weapon = _attackAction.weapon;
					action.target = bu->getPosition();
					Position origin = _save->getTileEngine()->getOriginVoxel(action, 0);
					valid = _save->getTileEngine()->canTargetUnit(&origin, bu->getTile(), &target, _unit, false);
				}
				else
				{
					if (selectPointNearTarget(bu, _unit->getTimeUnits()))
					{
						valid = knownMeleeFrom(_attackAction.target, bu);
					}
				}
				if (valid)
				{
					_closestDist = dist;
					_aggroTarget = bu;
					pickState = kst;
				}
			}
		}
	}
	if (_aggroTarget)
	{
		AiProbe::fairPick(_unit, _aggroTarget, cons, pickState, pickState == AiProbe::FAIR_LAST_SEEN ? "mem" : "now", tally);
		return tally;
	}

	return 0;
}

/**
 * AI2-H h8 knowledge contract for selectNearestTarget / selectNearestTargetLeeroy (OXCE_AI_FAIR_KNOWLEDGE=1). The ray to the true tile
 * (TileEngine::visible, 360 degrees) decides only for a target the side honestly observes now or knows by the cheat. A direct pick
 * does not take a target the side does not observe now (it has no place to shoot at); the escape takes it at the remembered place.
 * @return 0 - skip, 1 - the old ray to the true tile, 2 - the ray at the remembered place.
 */
int AIModule::fairNearestMode(BattleUnit *bu, bool escape, const char *cons, int &state, Position &mem, int &dir, int &oldPass) const
{
	if (!AiProbe::fairKnowledge() || bu->getFaction() == _unit->getFaction())
	{
		return 1;
	}
	TileEngine *te = _save->getTileEngine();
	if (!escape)
	{
		// the same skip in every state: no ray to the true tile - not taken, whatever the side knows; so the ray is read
		// only where the side may know the place
		if (!te->visible(_unit, bu->getTile()))
		{
			return 0;
		}
		state = AiProbe::fairState(_save, _unit, bu, mem, dir);
		if (state == AiProbe::FAIR_CURRENT || state == AiProbe::FAIR_CHEAT)
		{
			return 1;
		}
		oldPass = 1;
		AiProbe::fairSel(_unit, bu, cons, state, oldPass, 0, "none", mem);
		return 0;
	}
	state = AiProbe::fairState(_save, _unit, bu, mem, dir);
	if (state == AiProbe::FAIR_CURRENT || state == AiProbe::FAIR_CHEAT)
	{
		return 1;
	}
	// diagnostics only: would the old ray have taken it (no AiKnownPlace scope is open, so this reads nothing moved)
	oldPass = AiKnownPlace::any() ? -1 : (te->visible(_unit, bu->getTile()) ? 1 : 0);
	if (state == AiProbe::FAIR_UNKNOWN)
	{
		AiProbe::fairSel(_unit, bu, cons, state, oldPass, 0, "none", mem);
		return 0;
	}
	return 2;
}

/**
 * Selects the nearest known living target we can see/reach and returns the number of visible enemies.
 * This function includes civilians as viable targets.
 * Note: Differs from selectNearestTarget() in calling selectPointNearTargetLeeroy().
 * @return viable targets.
 */
int AIModule::selectNearestTargetLeeroy(bool canRun)
{
	int tally = 0;
	_closestDist = 100;
	_aggroTarget = 0;
	int pickState = AiProbe::FAIR_LEGACY;
	for (auto* bu : *_save->getUnits())
	{
		// AI2-H h8: as selectNearestTarget, a direct pick
		int kst = AiProbe::FAIR_LEGACY, kdir = 0, oldPass = -1;
		Position kp;
		if (validTarget(bu, true, true) && fairNearestMode(bu, false, "leeroy", kst, kp, kdir, oldPass) == 1 &&
			_save->getTileEngine()->visible(_unit, bu->getTile()))
		{
			tally++;
			int dist = Position::distance2d(_unit->getPosition(), bu->getPosition());
			if (dist < _closestDist)
			{
				bool valid = false;
				if (selectPointNearTargetLeeroy(bu, canRun))
				{
					valid = knownMeleeFrom(_attackAction.target, bu);
				}
				if (valid)
				{
					_closestDist = dist;
					_aggroTarget = bu;
					pickState = kst;
				}
			}
		}
	}
	if (_aggroTarget)
	{
		AiProbe::fairPick(_unit, _aggroTarget, "leeroy", pickState, "now", tally);
		return tally;
	}

	return 0;
}

/**
 * Selects the nearest known living Xcom unit.
 * used for ambush calculations
 * @return if we found one.
 */
bool AIModule::selectClosestKnownEnemy()
{
	_aggroTarget = 0;
	int minDist = 255;
	for (auto* bu : *_save->getUnits())
	{
		if (validTarget(bu, true, false))
		{
			Position kp;
			int kdir = 0;
			int kind = knownPlace(bu, "closest", kp, kdir);
			if (kind == 2) continue;
			int dist = Position::distance2d(kind == 1 ? kp : bu->getPosition(), _unit->getPosition());
			if (dist < minDist)
			{
				minDist = dist;
				_aggroTarget = bu;
			}
		}
	}
	return _aggroTarget != 0;
}

/**
 * Selects a random known living Xcom or civilian unit.
 * @return if we found one.
 */
bool AIModule::selectRandomTarget()
{
	int farthest = -100;
	_aggroTarget = 0;

	for (auto* bu : *_save->getUnits())
	{
		if (validTarget(bu, true, true))
		{
			Position kp;
			int kdir = 0;
			int kind = knownPlace(bu, "random", kp, kdir);
			if (kind == 2) continue;
			int dist = RNG::generate(0,20) - Position::distance2d(_unit->getPosition(), kind == 1 ? kp : bu->getPosition());
			if (dist > farthest)
			{
				farthest = dist;
				_aggroTarget = bu;
			}
		}
	}
	return _aggroTarget != 0;
}

/**
 * Selects a point near enough to our target to perform a melee attack.
 * @param target Pointer to a target.
 * @param maxTUs Maximum time units the path to the target can cost.
 * @return True if a point was found.
 */
bool AIModule::selectPointNearTarget(BattleUnit *target, int maxTUs)
{
	Position kp;
	int kdir = 0;
	const int kind = knownPlace(target, "melee", kp, kdir);
	if (kind == 2) return false;
	AiKnownPlace known(_save, target, kind, kp, kdir);
	int size = _unit->getArmor()->getSize();
	int sizeTarget = target->getArmor()->getSize();
	int dirTarget = target->getDirection();
	// Note to self: AI doesn't attack units of the same faction, so we don't need to worry about ignoring melee dodge here
	float dodgeChanceDiff = target->getArmor()->getMeleeDodge(target) * target->getArmor()->getMeleeDodgeBackPenalty() * _attackAction.diff / 160.0f;
	bool returnValue = false;
	int distance = 1000;
	for (int z = -1; z <= 1; ++z)
	{
		for (int x = -size; x <= sizeTarget; ++x)
		{
			for (int y = -size; y <= sizeTarget; ++y)
			{
				if (x || y) // skip the unit itself
				{
					Position checkPath = target->getPosition() + Position (x, y, z);
					if (_save->getTile(checkPath) == 0 || std::find(_reachable.begin(), _reachable.end(), _save->getTileIndex(checkPath))  == _reachable.end())
						continue;
					int dir = _save->getTileEngine()->getDirectionTo(checkPath, target->getPosition());
					bool valid = knownMeleeRange(checkPath, target, kind, kp, kdir);
					bool fitHere = _save->setUnitPosition(_unit, checkPath, true);

					// the determinism hunt (OXCE_AI_TRACE_MELEE, bench builds only): every candidate tile with what decided it
					static const bool trace = AiProbe::param("OXCE_AI_TRACE_MELEE", 0) > 0;
					if (trace && AiProbe::active())
					{
						Log(LOG_INFO) << "[AIMELEE] unit=" << _unit->getId() << " target=" << target->getId() << " tile=" << checkPath
							<< " valid=" << valid << " fit=" << fitHere << " danger=" << _save->getTile(checkPath)->getDangerous()
							<< " dodge=" << dodgeChanceDiff << " maxtu=" << maxTUs;
					}
					if (valid && fitHere && !_save->getTile(checkPath)->getDangerous())
					{
						_save->getPathfinding()->calculate(_unit, checkPath, BAM_NORMAL, 0, maxTUs);

						//for 100% dodge diff and on 4th difficulty it will allow aliens to move 10 squares around to made attack from behind.
						int distanceCurrent = _save->getPathfinding()->getPath().size() - dodgeChanceDiff * _save->getTileEngine()->getArcDirection(dir - 4, dirTarget);
						if (trace && AiProbe::active())
						{
							Log(LOG_INFO) << "[AIMELEE] unit=" << _unit->getId() << " tile=" << checkPath << " path=" << _save->getPathfinding()->getPath().size()
								<< " start=" << _save->getPathfinding()->getStartDirection() << " dist=" << distanceCurrent << " best=" << distance;
						}
						if (_save->getPathfinding()->getStartDirection() != -1 && distanceCurrent < distance)
						{
							_attackAction.target = checkPath;
							returnValue = true;
							distance = distanceCurrent;
						}
						_save->getPathfinding()->abortPath();
					}
				}
			}
		}
	}
	return returnValue;
}

/**
 * Selects a point near enough to our target to perform a melee attack.
 * Note: Differs from selectPointNearTarget() in that it doesn't consider:
 *  - remaining TUs (charge even if not enough TUs to attack)
 *  - dangerous tiles (grenades? pfff!)
 *  - melee dodge (not intelligent enough to attack from behind)
 * @param target Pointer to a target.
 * @return True if a point was found.
 */
bool AIModule::selectPointNearTargetLeeroy(BattleUnit *target, bool canRun)
{
	Position kp;
	int kdir = 0;
	const int kind = knownPlace(target, "melee", kp, kdir);
	if (kind == 2) return false;
	AiKnownPlace known(_save, target, kind, kp, kdir);
	int size = _unit->getArmor()->getSize();
	int targetsize = target->getArmor()->getSize();
	bool returnValue = false;
	unsigned int distance = 1000;
	for (int z = -1; z <= 1; ++z)
	{
		for (int x = -size; x <= targetsize; ++x)
		{
			for (int y = -size; y <= targetsize; ++y)
			{
				if (x || y) // skip the unit itself
				{
					Position checkPath = target->getPosition() + Position(x, y, z);
					if (_save->getTile(checkPath) == 0)
						continue;
					bool valid = knownMeleeRange(checkPath, target, kind, kp, kdir);
					bool fitHere = _save->setUnitPosition(_unit, checkPath, true);

					if (valid && fitHere)
					{
						_save->getPathfinding()->calculate(_unit, checkPath, canRun ? BAM_RUN : BAM_NORMAL, 0, 100000); // disregard unit's TUs.
						if (_save->getPathfinding()->getStartDirection() != -1 && _save->getPathfinding()->getPath().size() < distance)
						{
							_attackAction.target = checkPath;
							returnValue = true;
							distance = _save->getPathfinding()->getPath().size();
						}
						_save->getPathfinding()->abortPath();
					}
				}
			}
		}
	}
	return returnValue;
}

/**
 * Selects a target from a list of units seen by spotter units for out-of-LOS actions and populates _attackAction with the relevant data
 * @return True if we have a target selected
 */
bool AIModule::selectSpottedUnitForSniper()
{
	_aggroTarget = 0;

	// Create a list of spotted targets and the type of attack we'd like to use on each
	std::vector<std::pair<BattleUnit*, BattleAction>> spottedTargets;

	// Get the TU costs for each available attack type
	BattleActionCost costAuto(BA_AUTOSHOT, _attackAction.actor, _attackAction.weapon);
	BattleActionCost costSnap(BA_SNAPSHOT, _attackAction.actor, _attackAction.weapon);
	BattleActionCost costAimed(BA_AIMEDSHOT, _attackAction.actor, _attackAction.weapon);

	BattleActionCost costThrow;
	// Only want to check throwing if we have a grenade, the default constructor (line above) conveniently returns false from haveTU()
	if (_grenade)
	{
		// We know we have a grenade, now we need to know if we have the TUs to throw it
		costThrow.type = BA_THROW;
		costThrow.actor = _attackAction.actor;
		costThrow.weapon = _unit->getGrenadeFromBelt(_save);
		costThrow.updateTU();
		costThrow.Time += 4; // Vanilla TUs for AI picking up grenade from belt
		costThrow += _attackAction.actor->getActionTUs(BA_PRIME, costThrow.weapon);
	}

	for (auto* bu : *_save->getUnits())
	{
		if (validTarget(bu, true, true) && bu->getTurnsLeftSpottedForSnipersByFaction(_unit->getFaction()))
		{
			// AI2-H FAIR KNOWLEDGE: the target is scored where the spotters last saw it
			Position kp;
			int kdir = 0;
			const int kind = knownPlace(bu, "sniper", kp, kdir);
			if (kind == 2)
				continue;
			AiKnownPlace known(_save, bu, kind, kp, kdir);
			// Determine which firing mode to use based on how many hits we expect per turn and the unit's intelligence/aggression
			_aggroTarget = bu;
			_attackAction.type = BA_RETHINK;
			_attackAction.target = bu->getPosition();
			extendedFireModeChoice(costAuto, costSnap, costAimed, costThrow, true);

			BattleAction chosenAction = _attackAction;
			if (chosenAction.type == BA_THROW)
				chosenAction.weapon = costThrow.weapon;

			const bool direct = chosenAction.type == BA_AUTOSHOT || chosenAction.type == BA_SNAPSHOT || chosenAction.type == BA_AIMEDSHOT;
			// AI3-FF (bench): OXCE_AI_FF_RISK bit 4 - the line to the place the spotters saw it (projectileAction's rule)
			static const int ffRisk = (int)AiProbe::param("OXCE_AI_FF_RISK", 0);
			const bool ffSec = (ffRisk & 4) && direct && _attackAction.type != BA_RETHINK && ffLineRisk(kind == 1 ? kp : bu->getPosition());
			if (ffSec && _ffSecRec != AiProbe::nextRec())
			{
				_ffSecRec = AiProbe::nextRec();
				AiProbe::note(_unit, "ff.sec.sniper");
			}
			if (_attackAction.type != BA_RETHINK && !ffSec && !(direct && zeroEffectReject("sniper", chosenAction.type, chosenAction.weapon, bu))
				&& !sniperAoeEfficacyReject(chosenAction, bu))
			{
				std::pair<BattleUnit*, BattleAction> spottedTarget;
				spottedTarget = std::make_pair(bu, chosenAction);
				spottedTargets.push_back(spottedTarget);
			}
		}
	}

	int numberOfTargets = static_cast<int>(spottedTargets.size());

	if (numberOfTargets) // Now that we have a list of valid targets, pick one and return.
	{
		_probeScore = INT_MIN; // each target was scored, the pick is random
		int pick = RNG::generate(0, numberOfTargets - 1);
		_aggroTarget = spottedTargets.at(pick).first;
		_attackAction.target = knownPos(_aggroTarget, "sniper");
		_attackAction.type = spottedTargets.at(pick).second.type;
		_attackAction.weapon = spottedTargets.at(pick).second.weapon;
	}
	else // We didn't find a suitable target
	{
		// Make sure we reset anything we might have changed while testing for targets
		_aggroTarget = 0;
		_attackAction.type = BA_RETHINK;
		_attackAction.weapon = _unit->getMainHandWeapon(false);
	}

	return _aggroTarget != 0;
}

/**
 * Scores a firing mode for a particular target based on a accuracy / TUs ratio
 * @param action Pointer to the BattleAction determining the firing mode
 * @param target Pointer to the BattleUnit we're trying to target
 * @param checkLOF Set to true if you want to check for a valid line of fire
 * @return The calculated score
 */
int AIModule::scoreFiringMode(BattleAction *action, BattleUnit *target, bool checkLOF)
{
	// Sanity check first, if the passed action has no type or weapon, return 0.
	if (!action->type || !action->weapon)
	{
		return 0;
	}
	auto* weapon = action->weapon->getRules();

	// Get base accuracy for the action
	int accuracy = BattleUnit::getFiringAccuracy(BattleActionAttack::GetBeforeShoot(*action), _save->getMod());
	int distanceSq = _unit->distance3dToUnitSq(target);
	int distance = (int)std::ceil(sqrt(float(distanceSq)));

	{
		int upperLimit, lowerLimit;
		int dropoff = weapon->calculateLimits(upperLimit, lowerLimit, _save->getDepth(), action->type);

		if (distance > upperLimit)
		{
			accuracy -= (distance - upperLimit) * dropoff;
		}
		else if (distance < lowerLimit)
		{
			accuracy -= (lowerLimit - distance) * dropoff;
		}
	}

	bool outOfRange = action->type == BA_THROW
		? weapon->isOutOfThrowRange(distanceSq, _save->getDepth())
		: weapon->isOutOfRange(distanceSq);

	if (outOfRange)
	{
		accuracy = 0;
	}

	int numberOfShots = 1;
	if (action->type == BA_AIMEDSHOT)
	{
		numberOfShots = weapon->getConfigAimed()->shots;
	}
	else if (action->type == BA_SNAPSHOT)
	{
		numberOfShots = weapon->getConfigSnap()->shots;
	}
	else if (action->type == BA_AUTOSHOT)
	{
		numberOfShots = weapon->getConfigAuto()->shots;
	}

	int tuCost = _unit->getActionTUs(action->type, action->weapon).Time;
	// Need to include TU cost of getting grenade from belt + priming if we're checking throwing
	if (action->type == BA_THROW && _grenade)
	{
		// FIXME: why not just use action->weapon ?
		auto* grenadeItem = _unit->getGrenadeFromBelt(_save);
		tuCost = _unit->getActionTUs(action->type, grenadeItem).Time;
		tuCost += 4;
		tuCost += _unit->getActionTUs(BA_PRIME, grenadeItem).Time;
	}
	int tuTotal = _unit->getBaseStats()->tu;

	// Return a score of zero if this firing mode doesn't exist for this weapon
	if (!tuCost)
	{
		return 0;
	}

	if (checkLOF)
	{
		Position origin = _save->getTileEngine()->getOriginVoxel((*action), 0);
		Position targetPosition;

		if (action->weapon->getArcingShot(action->type) || action->type == BA_THROW)
		{
			targetPosition = target->getPosition().toVoxel() + Position (8,8, (2 + -target->getTile()->getTerrainLevel()));
			if (!_save->getTileEngine()->validateThrow((*action), origin, targetPosition, _save->getDepth()))
			{
				return 0;
			}
		}
		else
		{
			AiProbe::HypoTag hypoTag("sniper"); // AI2-G: a real target on its own tile - the call must keep D1 semantics
			if (!_save->getTileEngine()->canTargetUnit(&origin, target->getTile(), &targetPosition, _unit, false, target))
			{
				return 0;
			}
		}
	}

	return accuracy * numberOfShots * tuTotal / tuCost;
}

/**
 * AI3-E (bench, OXCE_AI_FIRE_MODE_EV): what a direct firing mode is expected to do to the target this turn - the engine's
 * accuracy with the range dropoff (as scoreFiringMode, capped to 0..100) as the hit chance, times the shots of the mode, times
 * the damage after the armour's ruleset modifier and the ruleset armour of the side the shot comes from (BattleUnit::damage,
 * by the target's place and facing its side honestly knows), times the uses the unit's current time units allow. Read: the
 * attacker's own weapon, ammo and stats, the target's armour rule, the remembered place; not read: current armour, health.
 * @param why The reason when the mode cannot be modelled (the result is then negative).
 * @return The expected damage, -1 when not modelled.
 */
double AIModule::fireModeEffect(BattleAction *action, BattleUnit *target, const char *&why)
{
	why = "";
	if (action->type != BA_AIMEDSHOT && action->type != BA_SNAPSHOT && action->type != BA_AUTOSHOT)
	{
		why = "not_direct";
		return -1.0;
	}
	const RuleItem *weapon = action->weapon->getRules();
	BattleActionAttack attack = BattleActionAttack::GetBeforeShoot(*action);
	if (!attack.damage_item)
	{
		why = "no_ammo";
		return -1.0;
	}
	const RuleItem *item = attack.damage_item->getRules();
	if (item->getExplosionRadius(attack) != 0)
	{
		why = "area";
		return -1.0;
	}
	const RuleDamageType *dt = item->getDamageType();
	if (!dt)
	{
		why = "no_damage_type";
		return -1.0;
	}

	// the target's side as its side knows it: the remembered place and facing (FAIR_KNOWLEDGE), as AiProbe::fairPlace
	Position tpos = target->getPosition();
	int tdir = target->getDirection();
	if (AiProbe::fairKnowledge() && target->getFaction() != _unit->getFaction()
		&& !(_unit->getFaction() == FACTION_HOSTILE && _save->isCheating() && target->getFaction() == FACTION_PLAYER))
	{
		Position seen;
		int seenDir = 0;
		if (!target->getAiSeen(_unit->getFaction(), seen, seenDir))
		{
			why = "side_unknown";
			return -1.0;
		}
		tpos = seen;
		tdir = seenDir;
	}

	int accuracy = BattleUnit::getFiringAccuracy(attack, _save->getMod());
	const int distanceSq = _unit->distance3dToPositionSq(tpos);
	const int distance = (int)std::ceil(sqrt(float(distanceSq)));
	{
		int upperLimit, lowerLimit;
		int dropoff = weapon->calculateLimits(upperLimit, lowerLimit, _save->getDepth(), action->type);
		if (distance > upperLimit)
		{
			accuracy -= (distance - upperLimit) * dropoff;
		}
		else if (distance < lowerLimit)
		{
			accuracy -= (lowerLimit - distance) * dropoff;
		}
	}
	if (weapon->isOutOfRange(distanceSq))
	{
		accuracy = 0;
	}
	const double hit = Clamp(accuracy, 0, 100) / 100.0;

	int shots = 1;
	if (action->type == BA_AIMEDSHOT)
		shots = weapon->getConfigAimed()->shots;
	else if (action->type == BA_SNAPSHOT)
		shots = weapon->getConfigSnap()->shots;
	else
		shots = weapon->getConfigAuto()->shots;

	const int tuCost = _unit->getActionTUs(action->type, action->weapon).Time;
	if (tuCost <= 0)
	{
		why = "no_tu_cost";
		return -1.0;
	}
	const int uses = std::max(1, _unit->getTimeUnits() / tuCost);

	// ExplosionBState::init: the power at this range
	int power = 0;
	if (weapon->getIgnoreAmmoPower())
	{
		power += weapon->getPowerBonus(attack);
		power -= weapon->getPowerRangeReduction(distance * 16);
	}
	else
	{
		power += item->getPowerBonus(attack);
		power -= item->getPowerRangeReduction(distance * 16);
	}
	power = std::max(power, 0);

	// BattleUnit::damage: the side of the hit by the direction from the target to the shooter
	const Armor *armor = target->getArmor();
	double sideArmor = armor->getFrontArmor();
	if (!dt->IgnoreDirection)
	{
		const Position rel = (_unit->getPosition() - tpos) * Position(16, 16, 24);
		if (rel.x == 0 && rel.y == 0 && rel.z <= 0)
		{
			sideArmor = armor->getUnderArmor();
		}
		else
		{
			int relativeDirection;
			const int abs_x = abs(rel.x);
			const int abs_y = abs(rel.y);
			if (abs_y > abs_x * 2)
				relativeDirection = 8 + 4 * (rel.y > 0);
			else if (abs_x > abs_y * 2)
				relativeDirection = 10 + 4 * (rel.x < 0);
			else if (rel.x < 0)
				relativeDirection = rel.y > 0 ? 13 : 15;
			else
				relativeDirection = rel.y > 0 ? 11 : 9;
			const double front = armor->getFrontArmor(), right = armor->getRightSideArmor(), rear = armor->getRearArmor(),
				left = armor->getLeftSideArmor();
			switch ((relativeDirection - tdir) % 8)
			{
			case 0: sideArmor = front; break;
			case 1: sideArmor = (2 * front + right) / 3; break;
			case 2: sideArmor = right; break;
			case 3: sideArmor = (2 * rear + right) / 3; break;
			case 4: sideArmor = rear; break;
			case 5: sideArmor = (2 * rear + left) / 3; break;
			case 6: sideArmor = left; break;
			default: sideArmor = (2 * front + left) / 3; break;
			}
		}
	}

	// the expected damage after the resistance modifier and the armour over the roll (two dice: the triangle)
	const float modifier = armor->getDamageModifier(dt->ResistType);
	const float armorCut = dt->ArmorEffectiveness > 0.0f ? (float)sideArmor * dt->ArmorEffectiveness : 0.0f;
	auto afterArmor = [&](int roll)
	{
		int damage = (int)floor(roll * modifier);
		damage -= armorCut;
		return std::max(damage, 0);
	};
	double perHit = 0.0;
	if (dt->RandomType == DRT_UFO_WITH_TWO_DICE)
	{
		const double n = (double)(power + 1) * (power + 1);
		for (int s = 0; s <= 2 * power; ++s)
		{
			perHit += afterArmor(s) * (std::min(s, 2 * power - s) + 1) / n;
		}
	}
	else
	{
		const int lo = dt->getRandomDamage(power, 1);
		const int hi = dt->getRandomDamage(power, 2);
		for (int d = lo; d <= hi; ++d)
		{
			perHit += afterArmor(d);
		}
		perHit /= (hi - lo + 1);
	}
	return hit * shots * perHit * uses;
}

/**
 * Selects an AI mode based on a number of factors, some RNG and the results of the rest of the determinations.
 */
void AIModule::evaluateAIMode()
{
	if ((_unit->getCharging() && _attackAction.type != BA_RETHINK))
	{
		_AIMode = AI_COMBAT;
		return;
	}
	// don't try to run away as often if we're a melee type, and really don't try to run away if we have a viable melee target, or we still have 50% or more TUs remaining.
	int escapeOdds = 15;
	if (_melee)
	{
		escapeOdds = 12;
	}
	if (_unit->getFaction() == FACTION_HOSTILE && (_unit->getTimeUnits() > _unit->getBaseStats()->tu / 2 || _unit->getCharging()))
	{
		escapeOdds = 5;
	}
	int ambushOdds = 12;
	int combatOdds = 20;
	// we're less likely to patrol if we see enemies.
	int patrolOdds = _visibleEnemies ? 15 : 30;

	// the enemy sees us, we should take retreat into consideration, and forget about patrolling for now.
	if (_spottingEnemies)
	{
		patrolOdds = 0;
		if (_escapeTUs == 0)
		{
			const ProbeMark mark = probeMark('e');
			setupEscape();
			probeSlot('e', "escape", mark);
		}
	}

	// melee/blaster units shouldn't consider ambush
	if (!_rifle || _ambushTUs == 0)
	{
		ambushOdds = 0;
		if (_melee)
		{
			combatOdds *= 1.3;
		}
	}

	// if we KNOW there are enemies around...
	if (_knownEnemies)
	{
		if (_knownEnemies == 1)
		{
			combatOdds *= 1.2;
		}

		if (_escapeTUs == 0)
		{
			if (selectClosestKnownEnemy())
			{
				const ProbeMark mark = probeMark('e');
				setupEscape();
				probeSlot('e', "escape.known", mark);
			}
			else
			{
				escapeOdds = 0;
			}
		}
	}
	else if (_unit->getFaction() == FACTION_HOSTILE)
	{
		combatOdds = 0;
		escapeOdds = 0;
	}

	// take our current mode into consideration
	switch (_AIMode)
	{
	case AI_PATROL:
		patrolOdds *= 1.1;
		break;
	case AI_AMBUSH:
		ambushOdds *= 1.1;
		break;
	case AI_COMBAT:
		combatOdds *= 1.1;
		break;
	case AI_ESCAPE:
		escapeOdds *= 1.1;
		break;
	}

	// take our overall health into consideration
	if (_unit->getHealth() < _unit->getBaseStats()->health / 3)
	{
		escapeOdds *= 1.7;
		combatOdds *= 0.6;
		ambushOdds *= 0.75;
	}
	else if (_unit->getHealth() < 2 * (_unit->getBaseStats()->health / 3))
	{
		escapeOdds *= 1.4;
		combatOdds *= 0.8;
		ambushOdds *= 0.8;
	}
	else if (_unit->getHealth() < _unit->getBaseStats()->health)
	{
		escapeOdds *= 1.1;
	}

	// take our aggression into consideration
	switch (_unit->getAggression())
	{
	case 0:
		escapeOdds *= 1.4;
		combatOdds *= 0.7;
		break;
	case 1:
		ambushOdds *= 1.1;
		break;
	case 2:
		combatOdds *= 1.4;
		escapeOdds *= 0.7;
		break;
	default:
		combatOdds *= Clamp(1.2 + (_unit->getAggression() / 10.0), 0.1, 2.0);
		escapeOdds *= Clamp(0.9 - (_unit->getAggression() / 10.0), 0.1, 2.0);
		break;
	}

	if (_AIMode == AI_COMBAT)
	{
		ambushOdds *= 1.5;
	}

	// factor in the spotters.
	if (_spottingEnemies)
	{
		escapeOdds = 10 * escapeOdds * (_spottingEnemies + 10) / 100;
		combatOdds = 5 * combatOdds * (_spottingEnemies + 20) / 100;
	}
	else
	{
		escapeOdds /= 2;
	}

	// factor in visible enemies.
	if (_visibleEnemies)
	{
		combatOdds = 10 * combatOdds * (_visibleEnemies + 10) /100;
		if (_closestDist < 5)
		{
			ambushOdds = 0;
		}
	}
	// make sure we have an ambush lined up, or don't even consider it.
	if (_ambushTUs)
	{
		ambushOdds *= 1.7;
	}
	else
	{
		ambushOdds = 0;
	}

	// factor in mission type
	if (_save->getMissionType() == "STR_BASE_DEFENSE")
	{
		escapeOdds *= 0.75;
		ambushOdds *= 0.6;
	}

	// no weapons, not psychic? don't pick combat or ambush
	if (!_melee && !_rifle && !_blaster && !_grenade && _unit->getBaseStats()->psiSkill == 0)
	{
		combatOdds = 0;
		ambushOdds = 0;
	}
	// generate a random number to represent our decision.
	int decision = RNG::generate(1, std::max(1, patrolOdds + ambushOdds + escapeOdds + combatOdds));

	if (decision > escapeOdds)
	{
		if (decision > escapeOdds + ambushOdds)
		{
			if (decision > escapeOdds + ambushOdds + combatOdds)
			{
				_AIMode = AI_PATROL;
			}
			else
			{
				_AIMode = AI_COMBAT;
			}
		}
		else
		{
			_AIMode = AI_AMBUSH;
		}
	}
	else
	{
		_AIMode = AI_ESCAPE;
	}

	// if the aliens are cheating, or the unit is charging, enforce combat as a priority.
	if ((_unit->getFaction() == FACTION_HOSTILE && _save->isCheating()) || _unit->getCharging() != 0)
	{
		_AIMode = AI_COMBAT;
	}
	AiProbe::modeOdds(_unit, patrolOdds, ambushOdds, combatOdds, escapeOdds, decision, _AIMode);


	// enforce the validity of our decision, and try fallback behaviour according to priority.
	if (_AIMode == AI_COMBAT)
	{
		auto* xtile = _save->getTile(_attackAction.target);
		bool throwingGrenadeOrProxy = _attackAction.type == BA_THROW && _attackAction.weapon && _attackAction.weapon->getRules()->isGrenadeOrProxy();
		if (xtile && (xtile->getUnit() || throwingGrenadeOrProxy)) // https://openxcom.org/forum/index.php?topic=12145.0
		{
			if (_attackAction.type != BA_RETHINK)
			{
				return;
			}
			const ProbeMark mark = probeMark('x');
			const bool found = findFirePoint();
			probeSlot('x', "firepoint.fallback", mark);
			if (found)
			{
				return;
			}
		}
		else
		{
			const bool picked = selectRandomTarget();
			const ProbeMark mark = probeMark('x');
			const bool found = picked && findFirePoint();
			probeSlot('x', "firepoint.random", mark);
			if (found)
			{
				return;
			}
		}
		_AIMode = AI_PATROL;
	}

	if (_AIMode == AI_PATROL)
	{
		if (_toNode || _foundBaseModuleToDestroy)
		{
			return;
		}
		// base defense mission protocol: patrol action becomes an attack action when base modules are sighted
		if (_patrolAction.type == BA_SNAPSHOT)
		{
			return;
		}
		_AIMode = AI_AMBUSH;
	}

	if (_AIMode == AI_AMBUSH)
	{
		if (_ambushTUs != 0)
		{
			return;
		}
		_AIMode = AI_ESCAPE;
	}
}

/**
 * The bench's tactical rules (docs/AI_ROADMAP.md, Ф2), on only for the smarter enemy (OXCE_AI_TACTICS)
 * and the careful bot (OXCE_AI_CAREFUL): a unit the other side sees either attacks or goes to cover
 * it can reach now, it does not walk around or stand in view; an aimed or auto shot that would leave
 * no TU for cover becomes a snap shot; the careful bot also pulls its wounded out of view.
 */
void AIModule::tacticalMode()
{
	// every exit is counted: a rule that never fires is visible in the result line, not only in the outcome (R-034)
	if (!_spottingEnemies)
	{
		return;
	}
	AiProbe::tally(_unit, "spotted");
	if (_AIMode == AI_ESCAPE)
	{
		AiProbe::tally(_unit, "escaping");
		return;
	}
	// cover is a tile fewer of them see than see us now
	AiProbe::hypoBegin(_unit, "tactical", _spottingEnemies);
	if (_escapeAction.type != BA_WALK || _escapeAction.target == _unit->getPosition()
		|| getSpottingUnits(_escapeAction.target) >= _spottingEnemies)
	{
		AiProbe::hypoEnd(_unit, "tactical", false, _escapeAction.target, 0);
		AiProbe::tally(_unit, "nocover");
		return;
	}
	AiProbe::hypoEnd(_unit, "tactical", true, _escapeAction.target, 0);
	const bool wounded = AiProbe::careful(_unit)
		&& (_unit->getFatalWounds() > 0 || _unit->getHealth() < _unit->getBaseStats()->health / 2);
	if (_AIMode == AI_AMBUSH && !wounded)
	{
		// an ambush holds its time units for reaction fire - the wall the player uses; sending it to cover throws that away
		AiProbe::tally(_unit, "ambush");
		return;
	}
	const bool attacking = _AIMode == AI_COMBAT && _attackAction.type != BA_RETHINK && _attackAction.type != BA_NONE;
	if (attacking && !wounded)
	{
		if ((_attackAction.type == BA_AIMEDSHOT || _attackAction.type == BA_AUTOSHOT) && _attackAction.weapon)
		{
			const int left = _unit->getTimeUnits() - BattleActionCost(_attackAction.type, _unit, _attackAction.weapon).Time;
			BattleActionCost snap(BA_SNAPSHOT, _unit, _attackAction.weapon);
			if (left < _escapeTUs && snap.haveTU() && _unit->getTimeUnits() - snap.Time >= _escapeTUs)
			{
				_attackAction.type = BA_SNAPSHOT;
				AiProbe::tally(_unit, "snap");
			}
		}
		// the careful bot never ends a turn in the open after its shot: no time units left for cover - cover now, shoot next turn
		if (AiProbe::careful(_unit) && _attackAction.weapon && _attackAction.type != BA_WALK
			&& _unit->getTimeUnits() - BattleActionCost(_attackAction.type, _unit, _attackAction.weapon).Time < _escapeTUs)
		{
			_AIMode = AI_ESCAPE;
			AiProbe::tally(_unit, "scoot");
			return;
		}
		AiProbe::tally(_unit, "attack");
		return;
	}
	// which mode gave way to cover: a patrol walking in view, or combat that found nothing to do
	AiProbe::tally(_unit, wounded ? "pullback" : _AIMode == AI_PATROL ? "cover.patrol" : "cover.combat");
	_AIMode = AI_ESCAPE;
}

/**
 * Find a position where we can see our target, and move there.
 * check the 11x11 grid for a position nearby where we can potentially target him.
 * @return True if a possible position was found.
 */
bool AIModule::findFirePoint()
{
	if (!selectClosestKnownEnemy())
		return false;
	// AI2-H FAIR KNOWLEDGE: the whole search (lines to the target, its view sector, the distance, the final facing) runs with
	// the target where this side knows it to be; no change unless that is not its current place
	Position fkPos;
	int fkDir = 0;
	const int fkKind = knownPlace(_aggroTarget, "firepoint", fkPos, fkDir);
	if (fkKind == 2)
		return false;
	// AI2-H5 MELEE FIREPOINT APPROACH (bench): a unit whose only usable attack is a melee blow treats the target as out of
	// attack range while it cannot strike it from where it stands (where the side knows the target to be), so the approach
	// bonus below applies to it as to a weapon out of range. Psi, grenades, any firearm (blaster included) - not melee-only.
	bool meleeApproach = false;
	if (AiProbe::meleeFirepointApproach())
	{
		BattleItem *meleeW = _unit->getUtilityWeapon(BT_MELEE);
		const bool pure = _melee && meleeW && BattleActionCost(BA_HIT, _unit, meleeW).Time > 0
			&& !_rifle && !_blaster && !_grenade
			&& !_unit->getUtilityWeapon(BT_FIREARM) && !_unit->getUtilityWeapon(BT_PSIAMP)
			&& !_unit->getUtilityWeapon(BT_GRENADE) && !_unit->getUtilityWeapon(BT_PROXIMITYGRENADE);
		const bool adj = pure && knownMeleeRange(_unit->getPosition(), _aggroTarget, fkKind, fkPos, fkDir);
		meleeApproach = pure && !adj;
		if (AiProbe::active()) // the bench's line; the player's AI3 (BetterAI) does not write it
		{
			Log(LOG_INFO) << "[AITRACE] {\"ai2h5\":\"mfa\",\"rec\":" << AiProbe::nextRec() << ",\"turn\":" << _save->getTurn()
				<< ",\"unit\":" << _unit->getId() << ",\"target\":" << _aggroTarget->getId() << ",\"kind\":" << fkKind
				<< ",\"pure\":" << (pure ? 1 : 0) << ",\"adj\":" << (adj ? 1 : 0)
				<< ",\"d\":" << Position::distance2d(_unit->getPosition(), fkKind == 1 ? fkPos : _aggroTarget->getPosition()) << "}";
		}
	}
	AiKnownPlace fkKnown(_save, _aggroTarget, fkKind, fkPos, fkDir);
	BattleUnit *fkUnit = fkKnown.on() ? _aggroTarget : nullptr;
	// AI2-A (mode 3): no fire point is sought for a target every direct shot mode of this weapon is proven useless against
	if (zeroEffectMode() >= 1 && _attackAction.weapon)
	{
		int modes = 0, zero = 0, unk = 0, hzero = 0;
		std::string terms;
		for (BattleActionType t : { BA_AIMEDSHOT, BA_SNAPSHOT, BA_AUTOSHOT })
		{
			BattleActionCost c(t, _unit, _attackAction.weapon);
			if (!c.Time)
			{
				continue;
			}
			++modes;
			std::string one;
			const int v1 = zeroEffectVerdict(_save, _unit, t, _attackAction.weapon, _aggroTarget, &one);
			if (zeroHonestMode() >= 1 && zeroHonestLast == AIZ_ZERO)
			{
				++hzero;
			}
			if (v1 == AIZ_ZERO)
			{
				++zero;
			}
			else if (v1 == AIZ_UNKNOWN)
			{
				++unk;
			}
			if (terms.empty())
			{
				terms = one;
			}
		}
		if (modes > 0)
		{
			const bool reject = zeroEffectMode() >= 3 && zero == modes;
			if (AiProbe::active()) // the bench's line; the player's AI3 (BetterAI) does not write it
			{
				Log(LOG_INFO) << "[AITRACE] {\"ai2a\":\"firepoint\",\"rec\":" << AiProbe::nextRec() << ",\"turn\":" << _save->getTurn()
					<< ",\"unit\":" << _unit->getId() << ",\"side\":" << (int)_unit->getFaction() << ",\"target\":" << _aggroTarget->getId()
					<< ",\"modes\":" << modes << ",\"zero\":" << zero << ",\"unk\":" << unk << ",\"tu\":" << _unit->getTimeUnits()
					<< ",\"v\":" << (zero == modes ? (int)AIZ_ZERO : (int)AIZ_POTENTIAL) << ",\"rej\":" << (reject ? 1 : 0) << terms
					<< (zeroHonestMode() >= 1 ? ",\"hzero\":" + std::to_string(hzero) : std::string()) << "}";
			}
			if (reject)
			{
				// AI2-A2: the same outcome as a search that found no point (below), without the search and its shuffle
				_attackAction.type = BA_RETHINK;
				return false;
			}
		}
	}
	// KNOWN_OCCUPANT_PATH_V2 (bench): the target it aims at blocks its own tile for the searches to the points below
	bool ko2Old = false;
	const BattleUnit *ko2 = knownOccupantV2(ko2Old);
	if (AiProbe::knownOccupantPathV2() && _unit->getFaction() == FACTION_HOSTILE)
	{
		_ko2FpRan = true;
		_ko2FpTarget = ko2;
		_ko2FpOld = ko2Old;
	}
	std::vector<Position> randomTileSearch = _save->getTileSearch(); // copy!
	// BEST_CELL (bench): LEVELS - the window on the levels below and above too; FP_BEST - no quit on the threshold;
	// REACHCOST - the score from findReachable's cost, the A* only for a cell that would become the best
	const int cellBits = bestCellBits();
	if (cellBits & AiProbe::BC_LEVELS)
	{
		const size_t flat = randomTileSearch.size();
		for (int dz : { -1, 1 })
		{
			for (size_t i = 0; i < flat; ++i)
			{
				randomTileSearch.push_back(randomTileSearch[i] + Position(0, 0, dz));
			}
		}
	}
	const bool fpBest = (cellBits & AiProbe::BC_FP_BEST) != 0;
	RNG::shuffle(randomTileSearch);
	Position target;
	const int BASE_SYSTEMATIC_SUCCESS = 100;
	const int FAST_PASS_THRESHOLD = 125;
	bool waitIfOutsideWeaponRange = _unit->getGeoscapeSoldier() ? false : _unit->getUnitRules()->waitIfOutsideWeaponRange();
	bool extendedFireModeChoiceEnabled = _save->getMod()->getAIExtendedFireModeChoice();
	int bestScore = 0;
	int droppedByEnergy = 0, overByTu = 0;
	// FIREPOINT_BLOCKED_UNIT_STALL (bench): points by the first step that met a unit, from where it stood, while nothing
	// it may know has changed; the first step of the point chosen instead (same_first_step must stay 0)
	const bool suppress = _fpBlocked && firepointBlockedHolds();
	bool suppressedHere = false;
	int bestDir = -1;
	// FIREPOINT_TARGET_CELL_V1 (bench): not the tile the target stands on - the path there is open only because the target was
	// not spotted this turn (Pathfinding::isBlocked), and the walk stops on it; the target's tile is the one it already aims at
	const bool skipTargetCell = AiProbe::firepointTargetCell();
	bool targetCellRejected = false;
	Position targetCell;
	_attackAction.type = BA_RETHINK;
	AiProbe::hypoBegin(_unit, "firepoint", _spottingEnemies);
	// CELL_PROF (bench, passive): the loop's time, the cells it scored and where it quit; the shadow search after it
	const bool cellProf = AiProbe::cellProf();
	std::vector<std::pair<int, int>> cellReal;
	int cellIdx = -1, cellBreak = -1;
	const auto cellT0 = cellProf ? std::chrono::steady_clock::now() : std::chrono::steady_clock::time_point();
	for (const auto& randomPosition : randomTileSearch)
	{
		++cellIdx;
		Position pos = _unit->getPosition() + randomPosition;
		Tile *tile = _save->getTile(pos);
		if (tile == 0  ||
			std::find(_reachableWithAttack.begin(), _reachableWithAttack.end(), _save->getTileIndex(pos))  == _reachableWithAttack.end())
			continue;
		if (skipTargetCell)
		{
			bool onTarget = false;
			const int size = _unit->getArmor()->getSize();
			for (int x = 0; x < size && !onTarget; ++x)
			{
				for (int y = 0; y < size && !onTarget; ++y)
				{
					const Tile *part = _save->getTile(pos + Position(x, y, 0));
					onTarget = part && part->getUnit() == _aggroTarget;
				}
			}
			if (onTarget)
			{
				targetCellRejected = true;
				targetCell = pos;
				continue;
			}
		}
		int score = 0;
		// i should really make a function for this
		Position origin = pos.toVoxel() +
			// 4 because -2 is eyes and 2 below that is the rifle (or at least that's my understanding)
			Position(8,8, _unit->getHeight() + _unit->getFloatHeight() - tile->getTerrainLevel() - 4);

		if (_save->getTileEngine()->canTargetUnit(&origin, _aggroTarget->getTile(), &target, _unit, false, fkUnit))
		{
			// BEST_CELL REACHCOST (bench): scored by findReachable's cost first; a cell that cannot beat the best so far
			// needs no path search (it would not be taken whatever the path)
			const int reach = reachCostAt(pos);
			int pre = INT_MIN;
			if (reach >= 0)
			{
				pre = firePointTerms(pos, reach, meleeApproach);
				if (pre <= bestScore)
					continue;
			}
			calculateKnownOccupantV2(pos, ko2, _ko2FpHits);
			// can move here
			if (_save->getPathfinding()->getStartDirection() != -1)
			{
				// FIREPOINT_ENERGY_PATH_V1 (bench): the walk goes by this path, not by the one findReachable found the tile by
				const int over = AiProbe::firepointPathOver(_save, _unit, _reachableTuMax, _reachableEnergyMax);
				overByTu += (over & 2) ? 1 : 0;
				if (over & 1)
				{
					++droppedByEnergy;
					continue;
				}
				if (suppress && _save->getPathfinding()->getStartDirection() == _fpBlockedDir)
				{
					// any point by the step that met the unit, not only the point it was walking to: another point by the
					// same step meets it again (the observation seed 1458 - 81 such reselections with the point in the key)
					if (!suppressedHere)
					{
						AiProbe::tally(_unit, "fpblocked.suppressed");
					}
					suppressedHere = true;
					_fpSuppressedNow = true;
					continue;
				}
				if (pre != INT_MIN)
				{
					score = pre; // BEST_CELL REACHCOST: the same terms by findReachable's cost
				}
				else
				{
				score = BASE_SYSTEMATIC_SUCCESS - getSpottingUnits(pos) * 10;
				score += _unit->getTimeUnits() - _save->getPathfinding()->getTotalTUCost();
				if (!_aggroTarget->checkViewSector(pos))
				{
					score += 10;
				}
				AiProbe::hypoPre(pos, score);

				// Extended behavior: if we have a limited-range weapon, bump up the score for getting closer to the target, down for further
				if (!waitIfOutsideWeaponRange && extendedFireModeChoiceEnabled)
				{
					int distanceToTargetSq = _unit->distance3dToUnitSq(_aggroTarget);
					int distanceToTarget = (int)std::ceil(sqrt(float(distanceToTargetSq)));
					if ((_attackAction.weapon && _attackAction.weapon->getRules()->isOutOfRange(distanceToTargetSq)) || meleeApproach) // make sure we can get the ruleset before checking the range
					{
						int proposedDistance = Position::distance2d(pos, _aggroTarget->getPosition());
						proposedDistance = std::max(proposedDistance, 1);
						AiProbe::hypoScale(pos, distanceToTarget, proposedDistance);
						score = score * distanceToTarget / proposedDistance;
					}
				}
				}

				AiProbe::traceTile(_unit, "firepoint", pos, score);
				if (cellProf)
				{
					cellReal.emplace_back(_save->getTileIndex(pos), score);
				}
				if (score > bestScore)
				{
					bestScore = score;
					bestDir = _save->getPathfinding()->getStartDirection();
					_attackAction.target = pos;
					_attackAction.finalFacing = _save->getTileEngine()->getDirectionTo(pos, _aggroTarget->getPosition());
					if (score > FAST_PASS_THRESHOLD && !fpBest)
					{
						cellBreak = cellIdx;
						break;
					}
				}
			}
		}
	}
	if (cellProf)
	{
		AiProbe::CellStat s;
		s.ns = std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - cellT0).count();
		s.threshold = FAST_PASS_THRESHOLD;
		s.scanned = (int)cellReal.size();
		for (const auto &c : cellReal) s.passed += c.second > FAST_PASS_THRESHOLD ? 1 : 0;
		s.breakAt = cellBreak;
		s.chosen = bestScore > 0 ? bestScore : INT_MIN;
		CellCtx c;
		c.fkUnit = fkUnit;
		c.meleeApproach = meleeApproach;
		c.skipDir = suppress ? _fpBlockedDir : -1;
		c.skipTargetCell = skipTargetCell;
		c.ko2 = ko2;
		cellShadow(s, cellReal, false, c);
		// why no line: the centre line from the unit's own cell (the loop's origin) to the target's middle - no random numbers
		Tile *fromTile = _save->getTile(_unit->getPosition());
		Tile *targetTile = _aggroTarget->getTile();
		if (fromTile && targetTile)
		{
			s.dist = (int)std::ceil(std::sqrt((float)_unit->distance3dToUnitSq(_aggroTarget)));
			s.dz = targetTile->getPosition().z - _unit->getPosition().z;
			s.seen = _unit->hasVisibleUnit(_aggroTarget) ? 1 : 0;
			const Position from = _unit->getPosition().toVoxel() +
				Position(8, 8, _unit->getHeight() + _unit->getFloatHeight() - fromTile->getTerrainLevel() - 4);
			const Position to = targetTile->getPosition().toVoxel() +
				Position(8, 8, _aggroTarget->getFloatHeight() - targetTile->getTerrainLevel() + _aggroTarget->getHeight() / 2);
			std::vector<Position> hit;
			const VoxelType v = _save->getTileEngine()->calculateLineVoxel(from, to, false, &hit, _unit);
			s.blk = (int)v;
			if (v != V_EMPTY && !hit.empty())
			{
				const Position at = hit.back().toTile();
				Tile *hitTile = _save->getTile(at);
				s.blkDist = Position::distance2d(_unit->getPosition(), at);
				if (v == V_UNIT && hitTile && hitTile->getUnit() == _aggroTarget)
				{
					s.blk = 6;
				}
				else if (hitTile && v >= V_FLOOR && v <= V_OBJECT && hitTile->getMapData((TilePart)v))
				{
					s.blkArmor = hitTile->getMapData((TilePart)v)->getArmor();
				}
			}
			// what the weapon in hand does to that part: power as ExplosionBState::init at the obstacle's range, the tile
			// damage of one hit at the top of its rolls (TileDamageMethod 1: 3/2 power; detonate: the power itself)
			if (_attackAction.weapon)
			{
				const BattleActionAttack attack = BattleActionAttack::GetBeforeShoot(BattleActionCost(BA_SNAPSHOT, _unit, _attackAction.weapon));
				if (attack.damage_item && attack.damage_item->getRules()->getDamageType())
				{
					const RuleItem *weapon = _attackAction.weapon->getRules();
					const RuleItem *item = attack.damage_item->getRules();
					const RuleDamageType *dt = item->getDamageType();
					const int range = std::max(s.blkDist, 0) * 16;
					int power = weapon->getIgnoreAmmoPower()
						? weapon->getPowerBonus(attack) - weapon->getPowerRangeReduction(range)
						: item->getPowerBonus(attack) - item->getPowerRangeReduction(range);
					power = std::max(power, 0);
					s.power = power;
					s.method = dt->TileDamageMethod;
					s.toTile = (int)std::round(dt->ToTile * 100);
					s.rad = item->getExplosionRadius(attack);
					const int raw = s.rad != 0 ? power : dt->TileDamageMethod == 1 ? 3 * power / 2 : power;
					const int d = (int)std::round(raw * dt->ToTile);
					s.maxTile = dt->TileDamageLimit >= 0 && d > dt->TileDamageLimit ? dt->TileDamageLimit : d;
				}
			}
			for (const BattleItem *it : *_unit->getInventory())
			{
				const BattleType bt = it->getRules()->getBattleType();
				if (bt == BT_GRENADE || bt == BT_PROXIMITYGRENADE)
				{
					s.gren = 1;
					break;
				}
			}
		}
		AiProbe::cellSearch(_save, _unit, "fp", s);
	}
	AiProbe::hypoEnd(_unit, "firepoint", bestScore > 70, _attackAction.target, bestScore);
	if (droppedByEnergy || overByTu)
	{
		AiProbe::firepointDropped(_unit, droppedByEnergy, overByTu);
	}
	if (targetCellRejected)
	{
		AiProbe::firepointTargetCellRejected(_unit, targetCell, bestScore > 70, _attackAction.target);
	}

	if (bestScore > 70)
	{
		_probeScore = bestScore;
		_attackAction.type = BA_WALK;
		_firepointChosen = true;
		_firepointChosenAt = _attackAction.target;
		_ko2FpChosenTarget = ko2;
		if (suppressedHere && bestDir == _fpBlockedDir)
		{
			AiProbe::tally(_unit, "fpblocked.same_first_step");
		}
		if (_traceAI)
		{
			Log(LOG_INFO) << "Firepoint found at " << _attackAction.target << ", with a score of: " << bestScore;
		}
		return true;
	}
	if (_traceAI)
	{
		Log(LOG_INFO) << "Firepoint failed, best estimation was: " << _attackAction.target << ", with a score of: " << bestScore;
	}

	return false;
}

/**
 * findFirePoint's score of a cell from the walk cost to it: the loop's terms, without its bench's diagnostics.
 * @param pos The cell.
 * @param tuCost What the walk there costs.
 * @param meleeApproach A melee-only unit approaches as a weapon out of range does (AI2-H5).
 */
int AIModule::firePointTerms(const Position &pos, int tuCost, bool meleeApproach) const
{
	int score = 100 - getSpottingUnits(pos) * 10;
	score += _unit->getTimeUnits() - tuCost;
	if (!_aggroTarget->checkViewSector(pos))
	{
		score += 10;
	}
	const bool waitIfOutsideWeaponRange = _unit->getGeoscapeSoldier() ? false : _unit->getUnitRules()->waitIfOutsideWeaponRange();
	if (!waitIfOutsideWeaponRange && _save->getMod()->getAIExtendedFireModeChoice())
	{
		int distanceToTargetSq = _unit->distance3dToUnitSq(_aggroTarget);
		int distanceToTarget = (int)std::ceil(sqrt(float(distanceToTargetSq)));
		if ((_attackAction.weapon && _attackAction.weapon->getRules()->isOutOfRange(distanceToTargetSq)) || meleeApproach)
		{
			int proposedDistance = std::max(Position::distance2d(pos, _aggroTarget->getPosition()), 1);
			score = score * distanceToTarget / proposedDistance;
		}
	}
	return score;
}

/**
 * BEST_CELL REACHCOST (bench): the walk cost to a tile as findReachable found it.
 * @return The cost, or -1 if the table is off, not taken yet, or the tile is not reached.
 */
int AIModule::reachCostAt(const Position &pos) const
{
	if (!(bestCellBits() & AiProbe::BC_REACHCOST) || _reachCost.empty())
		return -1;
	const int index = _save->getTileIndex(pos);
	return index >= 0 && index < (int)_reachCost.size() ? _reachCost[index] : -1;
}

/**
 * BEST_CELL (bench): the bits for this unit - with BC_HOSTILE only the hostile side's searches change.
 * @return AiProbe::bestCell, or 0 for a non-hostile unit under BC_HOSTILE.
 */
int AIModule::bestCellBits() const
{
	const int bits = AiProbe::bestCell();
	if ((bits & AiProbe::BC_HOSTILE) && _unit->getFaction() != FACTION_HOSTILE)
		return 0;
	return bits;
}

/**
 * CELL_PROF (bench, passive): findFirePoint's loop for one cell on the audit's own pathfinder - the same checks in the same
 * order, the same score. No RNG, no state of the unit or of the game's pathfinder is touched.
 * @return The score, or INT_MIN where the loop would skip the cell.
 */
int AIModule::firePointScoreAt(Pathfinding *pf, const Position &pos, const CellCtx &c) const
{
	Tile *tile = _save->getTile(pos);
	if (tile == 0)
		return INT_MIN;
	if (c.skipTargetCell)
	{
		const int size = _unit->getArmor()->getSize();
		for (int x = 0; x < size; ++x)
		{
			for (int y = 0; y < size; ++y)
			{
				const Tile *part = _save->getTile(pos + Position(x, y, 0));
				if (part && part->getUnit() == _aggroTarget)
					return INT_MIN;
			}
		}
	}
	Position origin = pos.toVoxel() + Position(8,8, _unit->getHeight() + _unit->getFloatHeight() - tile->getTerrainLevel() - 4);
	Position target;
	if (!_save->getTileEngine()->canTargetUnit(&origin, _aggroTarget->getTile(), &target, _unit, false, c.fkUnit))
		return INT_MIN;
	if (c.ko2)
	{
		pf->setKnownOccupant(_unit, c.ko2);
	}
	pf->calculate(_unit, pos, BAM_NORMAL);
	if (c.ko2)
	{
		pf->setKnownOccupant(0, 0);
		pf->takeKnownOccupantHits();
	}
	if (pf->getStartDirection() == -1)
		return INT_MIN;
	if (AiProbe::firepointPathOver(_save, _unit, _reachableTuMax, _reachableEnergyMax, pf) & 1)
		return INT_MIN;
	if (c.skipDir != -1 && pf->getStartDirection() == c.skipDir)
		return INT_MIN;
	const int reach = reachCostAt(pos); // BEST_CELL REACHCOST scores by the table, as the loop does
	return firePointTerms(pos, reach >= 0 ? reach : pf->getTotalTUCost(), c.meleeApproach);
}

/**
 * CELL_PROF (bench, passive): setupAmbush's loop for one node on the audit's own pathfinder.
 * @return The score, or INT_MIN where the loop would skip the node (seen from the enemy, no path for the unit or for the enemy).
 */
int AIModule::ambushScoreAt(Pathfinding *pf, const Position &pos, const CellCtx &c) const
{
	Tile *tile = _save->getTile(pos);
	if (tile == 0)
		return INT_MIN;
	Position origin = c.origin;
	Position target;
	if (_save->getTileEngine()->canTargetUnit(&origin, tile, &target, _aggroTarget, false, _unit) || getSpottingUnits(pos))
		return INT_MIN;
	if (c.ko2)
	{
		pf->setKnownOccupant(_unit, c.ko2);
	}
	pf->calculate(_unit, pos, BAM_NORMAL);
	if (c.ko2)
	{
		pf->setKnownOccupant(0, 0);
		pf->takeKnownOccupantHits();
	}
	if (pf->getStartDirection() == -1)
		return INT_MIN;
	const int reach = reachCostAt(pos); // BEST_CELL REACHCOST scores by the table, as the loop does
	int score = 100 - (reach >= 0 ? reach : pf->getTotalTUCost());
	pf->calculate(_aggroTarget, pos, BAM_NORMAL);
	if (pf->getStartDirection() == -1)
		return INT_MIN;
	if (_save->getTileEngine()->faceWindow(pos) != -1)
	{
		score += 25;
	}
	return score;
}

/**
 * CELL_PROF (bench, passive): after the real search, every candidate it could have scored - the window it walks (its cells or
 * its nodes), the same window on the map's other levels, and the reach outside the window - scored on the audit's pathfinder.
 * What it says: how far the cell the search took is from the best one, how often the first cell over the threshold wins
 * where a better one exists, and what the other levels and the far reach would give. mismatch - the real loop's score of a
 * cell differs from the shadow's (must stay 0: else the shadow does not score as the loop does).
 */
void AIModule::cellShadow(AiProbe::CellStat &s, const std::vector<std::pair<int, int>> &real, bool ambush, const CellCtx &c)
{
	Pathfinding *pf = AiProbe::cellPathfinding(_save);
	if (!pf)
		return;
	typedef std::chrono::steady_clock Clock;
	const int mapSize = _save->getMapSizeXYZ();
	std::vector<char> reach(mapSize, 0);
	for (int i : _reachableWithAttack)
	{
		if (i >= 0 && i < mapSize)
			reach[i] = 1;
	}
	const Position me = _unit->getPosition();
	std::vector<Position> win, levels, far;
	// OXCE_AI_CELLPROF=2: no far class - the A* to every reachable tile of the map is nearly all of the audit's cost (R-449)
	static const bool noFar = AiProbe::param("OXCE_AI_CELLPROF", 1) == 2;
	if (ambush)
	{
		// the real loop's own filter (any node, not dangerous, reachable), split by its distance and level checks
		for (const auto *node : *_save->getNodes())
		{
			if (node->isDummy())
				continue;
			const Position p = node->getPosition();
			const Tile *t = _save->getTile(p);
			if (t == 0 || t->getDangerous() || !reach[_save->getTileIndex(p)])
				continue;
			if (Position::distance2d(p, me) > 10)
			{
				if (!noFar)
					far.push_back(p);
			}
			else if (p.z == me.z)
				win.push_back(p);
			else
				levels.push_back(p);
		}
	}
	else
	{
		std::vector<char> inWindow(mapSize, 0);
		for (const auto &o : _save->getTileSearch())
		{
			for (int z = 0; z < _save->getMapSizeZ(); ++z)
			{
				const Position p(me.x + o.x, me.y + o.y, z);
				if (_save->getTile(p) == 0)
					continue;
				const int idx = _save->getTileIndex(p);
				inWindow[idx] = 1;
				if (!reach[idx])
					continue;
				if (z == me.z + o.z)
					win.push_back(p);
				else
					levels.push_back(p);
			}
		}
		for (int i = 0; i < mapSize && !noFar; ++i)
		{
			if (reach[i] && !inWindow[i])
				far.push_back(_save->getTileCoords(i));
		}
	}
	auto scoreAt = [&](const Position &p) { return ambush ? ambushScoreAt(pf, p, c) : firePointScoreAt(pf, p, c); };
	const int bar = s.chosen == INT_MIN ? 0 : s.chosen; // the real search starts its best at 0
	std::vector<int> shadow(mapSize, INT_MAX); // INT_MAX - the shadow did not score it (the window and its other levels only)

	Clock::time_point t0 = Clock::now();
	s.window = (int)win.size();
	s.rank = 0; // the window's cells scored over the one taken (-1 stays only when there is no shadow)
	for (const auto &p : win)
	{
		const int sc = scoreAt(p);
		shadow[_save->getTileIndex(p)] = sc;
		if (sc == INT_MIN)
			continue;
		++s.full;
		s.best = std::max(s.best, sc);
		s.fullAbove += sc > s.threshold ? 1 : 0;
		s.rank += sc > bar ? 1 : 0;
	}
	s.nsFull = std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - t0).count();

	t0 = Clock::now();
	s.zCand = (int)levels.size();
	for (const auto &p : levels)
	{
		const int sc = scoreAt(p);
		shadow[_save->getTileIndex(p)] = sc; // BEST_CELL LEVELS: the real loop scores these too
		if (sc == INT_MIN)
			continue;
		++s.zScored;
		s.zBest = std::max(s.zBest, sc);
	}
	s.nsZ = std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - t0).count();

	t0 = Clock::now();
	s.farCand = (int)far.size();
	for (const auto &p : far)
	{
		const int sc = scoreAt(p);
		if (sc == INT_MIN)
			continue;
		++s.farScored;
		s.farBest = std::max(s.farBest, sc);
	}
	s.nsFar = std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - t0).count();
	for (const auto &r : real)
	{
		const int sh = r.first >= 0 && r.first < mapSize ? shadow[r.first] : INT_MAX;
		s.mismatch += sh != r.second ? 1 : 0;
	}
}

/**
 * Decides if it worth our while to create an explosion here.
 * Return value in same range as number affected targets but not equal exactly to that value.
 * @param targetPos The target's position.
 * @param attackingUnit The attacking unit.
 * @param radius How big the explosion will be.
 * @param diff Game difficulty.
 * @param grenade Is the explosion coming from a grenade?
 * @return Value greater than zero if it is worthwhile creating an explosion in the target position. Bigger value better target.
 */
int AIModule::explosiveEfficacy(Position targetPos, BattleUnit *attackingUnit, int radius, int diff, bool grenade) const
{
	Tile *targetTile = _save->getTile(targetPos);
	// AI2-B2: the terms of this call, read only
	const bool probe = AiProbe::blastProbe();
	AiProbe::EffNote note;
	auto done = [&](int result, const char *path)
	{
		if (probe)
		{
			note.unit = attackingUnit->getId();
			note.x = targetPos.x;
			note.y = targetPos.y;
			note.z = targetPos.z;
			note.radius = radius;
			note.grenade = grenade;
			note.targetFaction = (int)_targetFaction;
			note.result = result;
			note.path = path;
			AiProbe::effDone(note);
		}
		return result;
	};

	// don't throw grenades at flying enemies.
	if (grenade && targetPos.z > 0 && targetTile->hasNoFloor(_save))
	{
		return done(false, "fly");
	}

	if (diff == -1)
	{
		diff = _save->getBattleState()->getGame()->getSavedGame()->getDifficultyCoefficient();
	}
	int distance = Position::distance2d(attackingUnit->getPosition(), targetPos);
	int injurylevel = attackingUnit->getBaseStats()->health - attackingUnit->getHealth();
	int desperation = (100 - attackingUnit->getMorale()) / 10;
	int enemiesAffected = 0;
	// if we're below 1/3 health, let's assume things are dire, and increase desperation.
	if (injurylevel > (attackingUnit->getBaseStats()->health / 3) * 2)
		desperation += 3;

	int efficacy = AIW_SCALE * desperation;
	// AI3-FF (bench): OXCE_AI_FF_RISK bit 1 - a blast that reaches our own side (or the thrower) is judged by the weights of
	// the units it reaches alone: desperation and difficulty add to efficacy but cannot buy the trade of ours for theirs.
	// A blast on enemies with none of ours in it is not touched. No RNG.
	static const int ffRisk = (int)AiProbe::param("OXCE_AI_FF_RISK", 0);
	const bool ffTrade = (ffRisk & 1) != 0;
	int ffUnits = 0;
	bool ffOwn = false;
	if (probe)
	{
		note.diff = diff;
		note.desp = desperation;
		note.hurt = injurylevel > (attackingUnit->getBaseStats()->health / 3) * 2;
	}

	// don't go kamikaze unless we're already doomed.
	if (abs(attackingUnit->getPosition().z - targetPos.z) <= Options::battleExplosionHeight && distance <= radius)
	{
		efficacy -= AIW_SCALE * 4;
		ffUnits -= AIW_SCALE * 4;
		ffOwn = true;
		if (probe)
		{
			note.kamikaze = true;
			note.units.push_back({ attackingUnit->getId(), (int)attackingUnit->getFaction(), 0, 6 });
		}
	}

	// allow difficulty to have its influence
	// AI2-B2a V1: OXCE_AI_EFFICACY_NO_DIFF=1 drops only the POSITIVE part of this term (min(0, term)): difficulty 2-4 lose
	// their bonus, the penalty of difficulty 0 and the -50 of reaction fire (diff -1, TileEngine::tryReaction) stay.
	// Desperation, kamikaze and the unit weights stay as they are, and diff keeps its other uses (waypoints, victim choice
	// odds, dodge). No RNG here.
	static const bool noDiff = AiProbe::param("OXCE_AI_EFFICACY_NO_DIFF", 0) != 0;
	const int diffTerm = AIW_SCALE * diff/2;
	if (!noDiff)
	{
		efficacy += diffTerm;
	}
	else
	{
		efficacy += std::min(0, diffTerm);
		if (probe)
		{
			note.noDiff = true;
		}
	}

	// account for the unit we're targetting
	// AI2-H FAIR KNOWLEDGE: the units count where this side knows them to be - the one on the target tile and those around it
	const bool fair = AiProbe::fairKnowledge() != 0;
	BattleUnit *target = fair ? fairOccupant(targetPos) : targetTile->getUnit();
	if (ffTrade && target && getTargetAttackWeight(target) < 0)
	{
		// AI3-FF (bench) bit 1: one of ours on the target tile is no enemy, and a grenaded tile does not shield it
		efficacy += getTargetAttackWeight(target);
		ffUnits += getTargetAttackWeight(target);
		ffOwn = true;
		if (probe)
			note.units.push_back({ target->getId(), (int)target->getFaction(), (int)getTargetAttackWeight(target), 4 });
	}
	else if (target && !targetTile->getDangerous())
	{
		++enemiesAffected;
		efficacy += getTargetAttackWeight(target);
		ffUnits += getTargetAttackWeight(target);
		if (probe)
			note.units.push_back({ target->getId(), (int)target->getFaction(), (int)getTargetAttackWeight(target), 4 });
	}
	else if (probe && target)
	{
		note.units.push_back({ target->getId(), (int)target->getFaction(), (int)getTargetAttackWeight(target), 5 });
	}

	for (auto* bu : *_save->getUnits())
	{
		Position bpos = bu->getPosition();
		if (fair && !bu->isOut() && bu != attackingUnit && bu != target)
		{
			Position kp;
			int kdir = 0;
			const int kind = knownPlace(bu, "blast", kp, kdir);
			if (kind == 2)
			{
				continue;
			}
			if (kind == 1)
			{
				bpos = kp;
			}
		}
		// the body is not where it is counted: moved since seen, or set at the known place by a caller's scope
		const bool hypo = fair && (bpos != bu->getPosition() || _save->getTile(bpos)->getUnit() != bu);
			// don't grenade dead guys
		if (!bu->isOut() &&
			// don't count ourself twice
			bu != attackingUnit &&
			// don't count the target twice
			bu != target &&
			// don't count units that probably won't be affected cause they're out of range
			abs(bpos.z - targetPos.z) <= Options::battleExplosionHeight &&
			Position::distance2d(bpos, targetPos) <= radius)
		{
			if ((bpos == bu->getPosition() ? bu->getTile() : _save->getTile(bpos))->getDangerous()
				// AI3-FF (bench) bit 1: one of ours on a grenaded tile is still hit
				&& !(ffTrade && getTargetAttackWeight(bu) < 0))
			{
				// don't count people who were already grenaded this turn
				if (probe)
					note.units.push_back({ bu->getId(), (int)bu->getFaction(), (int)getTargetAttackWeight(bu), 2 });
				continue;
			}

			auto weight = getTargetAttackWeight(bu);

			if (weight == 0)
			{
				// AI do not know anything about this unit
				if (probe)
					note.units.push_back({ bu->getId(), (int)bu->getFaction(), 0, 3 });
				continue;
			}

			// trace a line from the grenade origin to the unit we're checking against
			Position voxelPosA = Position (targetPos.toVoxel() + TileEngine::voxelTileCenter);
			Position voxelPosB = Position (bpos.toVoxel() + TileEngine::voxelTileCenter);
			std::vector<Position> traj;
			int collidesWith = _save->getTileEngine()->calculateLineVoxel(voxelPosA, voxelPosB, false, &traj, target, bu);

			// a body that is not there is reached when the line comes to its place unhit
			if ((collidesWith == V_UNIT && traj.front().toTile() == bpos) || (hypo && collidesWith == V_EMPTY))
			{
				if (bu->getFaction() == _targetFaction)
				{
					++enemiesAffected;
				}

				efficacy += weight;
				ffUnits += weight;
				ffOwn = ffOwn || weight < 0;
				if (probe)
					note.units.push_back({ bu->getId(), (int)bu->getFaction(), (int)weight, 0 });
			}
			else if (probe)
			{
				note.units.push_back({ bu->getId(), (int)bu->getFaction(), (int)weight, 1 });
			}
		}
	}
	if (probe)
	{
		note.enemies = enemiesAffected;
		note.efficacy = efficacy;
	}
	_ffEnemies = enemiesAffected;
	if (ffTrade && ffOwn && ffUnits <= 0)
	{
		// AI3-FF (bench) bit 1: noted once a decision, when the engine's rules below would have said yes
		const bool engineYes = !(grenade && desperation < 6 && enemiesAffected < 2) && (enemiesAffected >= 10 || efficacy >= AIW_SCALE);
		if (engineYes && _ffNoteRec != AiProbe::nextRec())
		{
			_ffNoteRec = AiProbe::nextRec();
			AiProbe::note(attackingUnit, "ff.trade");
		}
		return done(0, "ff");
	}
	// don't throw grenades at single targets, unless morale is in the danger zone
	// or we're halfway towards panicking while bleeding to death.
	if (grenade && desperation < 6 && enemiesAffected < 2)
	{
		return done(0, "single");
	}

	if (enemiesAffected >= 10)
	{
		// Ignore loses if we can kill lot of enemies.
		return done(enemiesAffected, "mass");
	}
	else if (efficacy > 0)
	{
		// We kill more enemies than allies. Scale back to number of targets, can round down to zero
		return done(efficacy / AIW_SCALE, "sum");
	}
	else
	{
		return done(0, "neg");
	}
}

/**
 * Attempts to take a melee attack/charge an enemy we can see.
 * Melee targetting: we can see an enemy, we can move to it so we're charging blindly toward an enemy.
 */
void AIModule::meleeAction()
{
	BattleActionCost attackCost(BA_HIT, _unit, _unit->getUtilityWeapon(BT_MELEE));
	if (!attackCost.haveTU())
	{
		// cannot make a melee attack - consider some other behaviour, like running away, or standing motionless.
		return;
	}
	if (_aggroTarget != 0 && !_aggroTarget->isOut())
	{
		if (knownAdjacent(_aggroTarget)
			&& !zeroEffectReject("melee_adj", BA_HIT, attackCost.weapon, _aggroTarget))
		{
			meleeAttack();
			return;
		}
	}
	int chargeReserve = std::min(_unit->getTimeUnits() - attackCost.Time, 2 * (_unit->getEnergy() - attackCost.Energy));
	int distance = (chargeReserve / 4) + 1;
	// O9 (BetterAI): distance2d leaves out the floor - a unit a floor above or below counted as adjacent and was charged
	// with no path; an adjacent one is taken only when the blow reaches it, and the first one found stays
	const bool oxceFixes = AiProbe::oxceFixes();
	_aggroTarget = 0;
	for (auto* bu : *_save->getUnits())
	{
		if (!validTarget(bu, true, true))
			continue;
		Position kp;
		int kdir = 0;
		const int kind = knownPlace(bu, "melee", kp, kdir);
		if (kind == 2)
			continue;
		int newDistance = Position::distance2d(_unit->getPosition(), kind == 1 ? kp : bu->getPosition());
		if (newDistance > 20)
			continue;
		//pick closest living unit that we can move to
		if ((newDistance < distance || (newDistance == 1 && (!oxceFixes || !_aggroTarget))) && !bu->isOut())
		{
			if (zeroEffectReject("melee_charge", BA_HIT, attackCost.weapon, bu))
				continue;
			if ((newDistance == 1 && (!oxceFixes || knownAdjacent(bu))) || selectPointNearTarget(bu, chargeReserve))
			{
				_aggroTarget = bu;
				_attackAction.type = BA_WALK;
				_unit->setCharging(_aggroTarget);
				distance = newDistance;
			}

		}
	}
	if (_aggroTarget != 0)
	{
		if (knownAdjacent(_aggroTarget))
		{
			meleeAttack();
		}
	}
	if (_traceAI && _aggroTarget) { Log(LOG_INFO) << "AIModule::meleeAction:" << " [target]: " << (_aggroTarget->getId()) << " at: "  << _attackAction.target; }
	if (_traceAI && _aggroTarget) { Log(LOG_INFO) << "CHARGE!"; }
}

namespace
{
/// AI3-LEEROY (bench, OXCE_AI_LEEROY_TU_FIX=1): Leeroy assigns a melee blow only if the unit can pay for it now,
/// the same check meleeAction() makes; otherwise the standard BA_NONE. Flag 0: no change.
bool leeroyHitUnaffordable(BattleUnit *unit, BattleAction &attack)
{
	static const bool fix = AiProbe::param("OXCE_AI_LEEROY_TU_FIX", 0) != 0;
	if (!fix)
		return false;
	BattleActionCost hit(BA_HIT, unit, unit->getUtilityWeapon(BT_MELEE));
	if (hit.haveTU())
		return false;
	attack.type = BA_NONE;
	AiProbe::note(unit, ("leeroy.unaffordable tu" + std::to_string(unit->getTimeUnits()) + "/" + std::to_string(hit.Time)
		+ " en" + std::to_string(unit->getEnergy()) + "/" + std::to_string(hit.Energy)).c_str());
	return true;
}
}

/**
 * Attempts to take a melee attack/charge an enemy we can see.
 * Melee targetting: we can see an enemy, we can move to it so we're charging blindly toward an enemy.
 * Note: Differs from meleeAction() in calling selectPointNearTargetLeeroy() and ignoring some more checks.
 * @return How many candidates AI2-A rejected as proven ZERO (0 unless OXCE_AI_ZERO_EFFECT >= 2).
 */
int AIModule::meleeActionLeeroy(bool canRun)
{
	int rejected = 0;
	if (_aggroTarget != 0 && !_aggroTarget->isOut())
	{
		if (knownAdjacent(_aggroTarget))
		{
			if (!zeroEffectReject("leeroy_adj", BA_HIT, _unit->getUtilityWeapon(BT_MELEE), _aggroTarget))
			{
				if (leeroyHitUnaffordable(_unit, _attackAction))
					return rejected;
				meleeAttack();
				return rejected;
			}
			++rejected;
		}
	}
	int distance = 1000;
	const bool oxceFixes = AiProbe::oxceFixes(); // O9, as in meleeAction
	_aggroTarget = 0;
	for (auto* bu : *_save->getUnits())
	{
		if (!validTarget(bu, true, true))
			continue;
		Position kp;
		int kdir = 0;
		const int kind = knownPlace(bu, "melee", kp, kdir);
		if (kind == 2)
			continue;
		int newDistance = Position::distance2d(_unit->getPosition(), kind == 1 ? kp : bu->getPosition());
		//pick closest living unit
		if ((newDistance < distance || (newDistance == 1 && (!oxceFixes || !_aggroTarget))) && !bu->isOut())
		{
			if (zeroEffectReject("leeroy_charge", BA_HIT, _unit->getUtilityWeapon(BT_MELEE), bu))
			{
				++rejected;
				continue;
			}
			if ((newDistance == 1 && (!oxceFixes || knownAdjacent(bu))) || selectPointNearTargetLeeroy(bu, canRun))
			{
				_aggroTarget = bu;
				_attackAction.type = BA_WALK;
				_attackAction.run = canRun;
				_unit->setCharging(_aggroTarget);
				distance = newDistance;
			}

		}
	}
	if (_aggroTarget != 0)
	{
		if (knownAdjacent(_aggroTarget))
		{
			if (!leeroyHitUnaffordable(_unit, _attackAction))
				meleeAttack();
		}
	}
	if (_traceAI && _aggroTarget) { Log(LOG_INFO) << "AIModule::meleeAction:" << " [target]: " << (_aggroTarget->getId()) << " at: " << _attackAction.target; }
	if (_traceAI && _aggroTarget) { Log(LOG_INFO) << "CHARGE!"; }
	return rejected;
}

/**
 * Attempts to fire a waypoint projectile at an enemy we, or one of our teammates sees.
 *
 * Waypoint targeting: pick from any units currently spotted by our allies.
 */
void AIModule::wayPointAction()
{
	BattleActionCost attackCost(BA_LAUNCH, _unit, _attackAction.weapon);
	if (!attackCost.haveTU())
	{
		// cannot make a launcher attack - consider some other behaviour, like running away, or standing motionless.
		return;
	}
	// AI3-F (bench): OXCE_AI_BOT_SPECIAL - the bot launches only with BA_LAUNCH ammo loaded, only at a HOSTILE, and only
	// where its side honestly knows it (seen now, or remembered under FAIR_KNOWLEDGE). Off - as before.
	static const bool botSpecialOn = AiProbe::param("OXCE_AI_BOT_SPECIAL", 0) != 0;
	const bool bot = botSpecialOn && AiProbe::careful(_unit);
	if (bot && !_attackAction.weapon->getAmmoForAction(BA_LAUNCH))
	{
		AiProbe::note(_unit, "botwp.no_ammo");
		return;
	}
	_aggroTarget = 0;
	for (auto* bu : *_save->getUnits())
	{
		if (_aggroTarget != 0) break; // loop finished
		if (!validTarget(bu, true, true))
		{
			continue;
		}
		if (bot && (bu->getFaction() != FACTION_HOSTILE || (!AiProbe::fairKnowledge() && !bu->getVisible())))
		{
			continue;
		}
		// AI2-H FAIR KNOWLEDGE: the missile is planned to where this side knows the target to be
		const Position bp = knownPos(bu, "waypoint");
		if (bp.x < 0)
		{
			continue;
		}
		_save->getPathfinding()->calculate(_unit, bp, BAM_MISSILE, bu, -1);
		BattleItem* ammo = _attackAction.weapon->getAmmoForAction(BA_LAUNCH);
		if (_save->getPathfinding()->getStartDirection() != -1 &&
			explosiveEfficacy(bp, _unit, ammo->getRules()->getExplosionRadius({ BA_LAUNCH, _unit, _attackAction.weapon, ammo }), _attackAction.diff))
		{
			_aggroTarget = bu;
		}
		_save->getPathfinding()->abortPath();
	}

	if (_aggroTarget != 0)
	{
		_attackAction.type = BA_LAUNCH;
		_attackAction.updateTU();
		if (!_attackAction.haveTU())
		{
			_attackAction.type = BA_RETHINK;
			return;
		}
		_attackAction.waypoints.clear();

		int PathDirection;
		int CollidesWith;
		int maxWaypoints = _attackAction.weapon->getCurrentWaypoints();
		if (maxWaypoints == -1)
		{
			maxWaypoints = 6 + (_attackAction.diff * 2);
		}
		Position LastWayPoint = _unit->getPosition();
		Position LastPosition = _unit->getPosition();
		Position CurrentPosition = _unit->getPosition();
		Position DirectionVector;

		// AI2-H FAIR KNOWLEDGE: the path ends where this side knows the target to be; when that is not its place, the last
		// waypoint is put there as the target's body would have caught the line there
		const Position wpTarget = knownPos(_aggroTarget, "waypoint");
		// AI3-F: for the bot "hypothetical" is decided by what its side sees, not by the target's true place
		const bool wpHypo = bot ? !_aggroTarget->getVisible() : wpTarget != _aggroTarget->getPosition();
		_save->getPathfinding()->calculate(_unit, wpTarget, BAM_MISSILE, _aggroTarget, -1);
		PathDirection = _save->getPathfinding()->dequeuePath();
		while (PathDirection != -1 && (int)_attackAction.waypoints.size() < maxWaypoints)
		{
			LastPosition = CurrentPosition;
			_save->getPathfinding()->directionToVector(PathDirection, &DirectionVector);
			CurrentPosition = CurrentPosition + DirectionVector;
			Position voxelPosA ((CurrentPosition.x * 16)+8, (CurrentPosition.y * 16)+8, (CurrentPosition.z * 24)+16);
			Position voxelPosb ((LastWayPoint.x * 16)+8, (LastWayPoint.y * 16)+8, (LastWayPoint.z * 24)+16);
			CollidesWith = _save->getTileEngine()->calculateLineVoxel(voxelPosA, voxelPosb, false, nullptr, _unit);
			if (wpHypo && CurrentPosition == wpTarget)
			{
				_attackAction.waypoints.push_back(CurrentPosition);
				LastWayPoint = CurrentPosition;
			}
			else if (CollidesWith > V_EMPTY && CollidesWith < V_UNIT)
			{
				_attackAction.waypoints.push_back(LastPosition);
				LastWayPoint = LastPosition;
			}
			else if (CollidesWith == V_UNIT)
			{
				BattleUnit* target = _save->getTile(CurrentPosition)->getOverlappingUnit(_save);
				if (target == _aggroTarget && !wpHypo)
				{
					_attackAction.waypoints.push_back(CurrentPosition);
					LastWayPoint = CurrentPosition;
				}
			}
			PathDirection = _save->getPathfinding()->dequeuePath();
		}
		if ((bot || AiProbe::oxceFixes()) && _attackAction.waypoints.empty())
		{
			// AI3-F: no waypoint was laid (front() of an empty list); the launch is not made - O10 (BetterAI): for every AI
			AiProbe::note(_unit, "botwp.no_waypoints");
			_attackAction.type = BA_RETHINK;
			return;
		}
		_attackAction.target = _attackAction.waypoints.front();
		if (LastWayPoint != wpTarget)
		{
			_attackAction.type = BA_RETHINK;
		}
		// AI2-B2: the target and the waypoints, read only
		AiProbe::blastWaypoints(_unit, _aggroTarget, _attackAction.waypoints);
	}
}

/**
 * Attempts to fire at an enemy spotted for us.
 *
 */
bool AIModule::sniperAction()
{
	if (_traceAI) { Log(LOG_INFO) << "Attempting sniper action..."; }

	if (selectSpottedUnitForSniper())
	{
		_visibleEnemies = std::max(_visibleEnemies, 1); // Make sure we count at least our target as visible, otherwise we might not shoot!

		if (_traceAI) { Log(LOG_INFO) << "Target for sniper found at (" << _attackAction.target.x << "," << _attackAction.target.y << "," << _attackAction.target.z << ")."; }
		return true;
	}

	if (_traceAI) { Log(LOG_INFO) << "No valid target found or not enough TUs for sniper action."; }
	return false;
}

/**
 * Attempts to fire at an enemy we can see.
 *
 * Regular targeting: we can see an enemy, we have a gun, let's try to shoot.
 */
void AIModule::projectileAction()
{
	_attackAction.target = knownPos(_aggroTarget, "shot");
	auto testEffect = [&](BattleActionCost& cost)
	{
		if (cost.haveTU())
		{
			BattleActionAttack attack = BattleActionAttack::GetBeforeShoot(cost);
			if (attack.damage_item == nullptr)
			{
				cost.clearTU();
			}
			else
			{
				int radius = attack.damage_item->getRules()->getExplosionRadius(attack);
				const int eff = radius != 0 ? explosiveEfficacy(_attackAction.target, _unit, radius, _attackAction.diff) : -1;
				if (radius != 0)
				{
					aoeEfficacyTrace("normal_shot", cost.type, cost.weapon, attack.damage_item, _aggroTarget, _attackAction.target, radius, false, eff, false);
				}
				if (radius != 0 && eff == 0)
				{
					cost.clearTU();
				}
				else if (radius == 0 && zeroEffectReject("shot", cost.type, cost.weapon, _aggroTarget))
				{
					cost.clearTU();
				}
			}
		}
	};

	int distance = Position::distance2d(_unit->getPosition(), _attackAction.target);
	_attackAction.type = BA_RETHINK;

	BattleActionCost costAuto(BA_AUTOSHOT, _attackAction.actor, _attackAction.weapon);
	BattleActionCost costSnap(BA_SNAPSHOT, _attackAction.actor, _attackAction.weapon);
	BattleActionCost costAimed(BA_AIMEDSHOT, _attackAction.actor, _attackAction.weapon);

	testEffect(costAuto);
	testEffect(costSnap);
	testEffect(costAimed);

	// AI3-FF (bench): OXCE_AI_FF_RISK bit 4 - no shot along a line past an explosive part whose blast would reach our own side
	static const int ffRisk = (int)AiProbe::param("OXCE_AI_FF_RISK", 0);
	if ((ffRisk & 4) && (costAuto.haveTU() || costSnap.haveTU() || costAimed.haveTU()) && ffLineRisk(_attackAction.target))
	{
		costAuto.clearTU();
		costSnap.clearTU();
		costAimed.clearTU();
		if (_ffSecRec != AiProbe::nextRec())
		{
			_ffSecRec = AiProbe::nextRec();
			AiProbe::note(_unit, "ff.sec");
		}
	}

	// Is the unit willingly waiting outside of weapon's range (e.g. ninja camouflaged in ambush)?
	bool waitIfOutsideWeaponRange = _unit->getGeoscapeSoldier() ? false : _unit->getUnitRules()->waitIfOutsideWeaponRange();

	// Do we want to use the extended firing mode scoring?
	bool extendedFireModeChoiceEnabled = _save->getMod()->getAIExtendedFireModeChoice();
	if (!waitIfOutsideWeaponRange && extendedFireModeChoiceEnabled)
	{
		// Note: this will also check for the weapon's max range
		BattleActionCost costThrow; // Not actually checked here, just passed to extendedFireModeChoice as a necessary argument
		extendedFireModeChoice(costAuto, costSnap, costAimed, costThrow, false);
		return;
	}

	// Do we want to check if the weapon is in range?
	bool aiRespectsMaxRange = _save->getMod()->getAIRespectMaxRange();
	if (!waitIfOutsideWeaponRange && aiRespectsMaxRange)
	{
		// If we want to check and it's not in range, perhaps we should re-think shooting
		int distanceSq = _unit->distance3dToPositionSq(_attackAction.target);
		if (_attackAction.weapon->getRules()->isOutOfRange(distanceSq))
		{
			return;
		}
	}

	// vanilla
	if (distance < 4)
	{
		if (costAuto.haveTU())
		{
			_attackAction.type = BA_AUTOSHOT;
			return;
		}
		if (!costSnap.haveTU())
		{
			if (costAimed.haveTU())
			{
				_attackAction.type = BA_AIMEDSHOT;
			}
			return;
		}
		_attackAction.type = BA_SNAPSHOT;
		return;
	}


	if (distance > 12)
	{
		if (costAimed.haveTU())
		{
			_attackAction.type = BA_AIMEDSHOT;
			return;
		}
		if (distance < 20 && costSnap.haveTU())
		{
			_attackAction.type = BA_SNAPSHOT;
			return;
		}
	}

	if (costSnap.haveTU())
	{
		_attackAction.type = BA_SNAPSHOT;
		return;
	}
	if (costAimed.haveTU())
	{
		_attackAction.type = BA_AIMEDSHOT;
		return;
	}
	if (costAuto.haveTU())
	{
		_attackAction.type = BA_AUTOSHOT;
	}
}

/**
 * The bench's shot evaluator (OXCE_AI_EVAL, docs/AI_TRAINING.md): every tile the unit can reach and
 * still shoot from, every enemy its side saw this turn, every fire mode standing and kneeling. A shot is
 * worth the share of the target's health it is expected to take (one hit that kills: the chance of at
 * least one hit), by the engine's own accuracy with range dropoff and the target's armor and resistance;
 * the tile costs its exposure after the shot - the seen enemies with a line of fire to it, heavier for a
 * wounded unit and lighter when time units are left to reach cover. A shot must leave the time units for
 * cover (from here the careful bot's escape path); a unit the other side sees does not walk, and a walk
 * costs OXCE_AI_EVAL_WALK. The best positive plan is a shot from here or a walk to its tile (the next
 * think shoots from there); none positive - no attack, cover decides; the careful rules stay the safety net.
 * @return False if the side sees no enemy (the old logic goes on), true if the evaluator decided.
 */
bool AIModule::evalFireAction()
{
	BattleItem *weapon = _attackAction.weapon;
	if (!weapon)
	{
		return false;
	}
	std::vector<BattleUnit*> targets;
	for (auto* bu : *_save->getUnits())
	{
		if (bu->getFaction() == _targetFaction && !bu->isOut() && bu->getTurnsSinceSpottedByFaction(_unit->getFaction()) == 0)
		{
			targets.push_back(bu);
		}
	}
	if (targets.empty())
	{
		return false;
	}

	struct Mode { BattleActionType type; int time; int accuracy; int shots; BattleActionAttack attack; };
	std::vector<Mode> modes;
	const RuleItem *rule = weapon->getRules();
	const int kneelBonus = rule->getKneelBonus(_save->getMod());
	int cheapest = -1;
	BattleActionCost cheapestCost;
	for (BattleActionType type : { BA_AIMEDSHOT, BA_SNAPSHOT, BA_AUTOSHOT })
	{
		BattleActionCost cost(type, _unit, weapon);
		if (!cost.Time || !cost.haveTU())
		{
			continue;
		}
		BattleActionAttack attack = BattleActionAttack::GetBeforeShoot(cost);
		if (attack.damage_item == nullptr)
		{
			continue;
		}
		// accuracy standing: moving stands the unit up, kneeling is weighed as its own option
		int accuracy = BattleUnit::getFiringAccuracy(attack, _save->getMod());
		if (_unit->isKneeled() && kneelBonus > 0)
		{
			accuracy = accuracy * 100 / kneelBonus;
		}
		int shots = type == BA_AIMEDSHOT ? rule->getConfigAimed()->shots : type == BA_SNAPSHOT ? rule->getConfigSnap()->shots : rule->getConfigAuto()->shots;
		modes.push_back({ type, cost.Time, accuracy, std::max(1, shots), attack });
		if (cheapest < 0 || cost.Time < cheapest)
		{
			cheapest = cost.Time;
			cheapestCost = cost;
		}
	}
	if (modes.empty())
	{
		AiProbe::tally(_unit, "eval.nomode");
		return false;
	}

	// tiles the unit reaches with the cheapest shot left, and what the walk costs; cheapest first, a bounded search
	std::vector<std::pair<Position, int>> tiles;
	{
		Pathfinding *pf = _save->getPathfinding();
		std::vector<int> reach = pf->findReachable(_unit, cheapestCost);
		const size_t maxTiles = 250;
		for (size_t i = 0; i < reach.size() && tiles.size() < maxTiles; ++i)
		{
			Position pos = _save->getTileCoords(reach[i]);
			int tu = pf->reachedTU(pos);
			if (tu >= 0)
			{
				tiles.push_back({ pos, tu });
			}
		}
	}

	const double riskPerSpotter = AiProbe::param("OXCE_AI_EVAL_RISK", 0.15);
	const double coverRelief = AiProbe::param("OXCE_AI_EVAL_COVER", 0.5);
	const double coverShare = AiProbe::param("OXCE_AI_EVAL_COVERTU", 0.25);
	const double walkCost = AiProbe::param("OXCE_AI_EVAL_WALK", 0.1);
	const double fragility = 2.0 - (double)_unit->getHealth() / std::max(1, (int)_unit->getBaseStats()->health);
	const bool mayKneel = _unit->getArmor()->allowsKneeling(_unit->getType() == "SOLDIER") && !_unit->isFloating();
	const int timeUnits = _unit->getTimeUnits();
	const int coverTU = (int)(coverShare * _unit->getBaseStats()->tu);

	double bestScore = 0.0;
	Position bestTile, bestTarget;
	BattleActionType bestType = BA_RETHINK;
	bool bestKneel = false;
	int evaluated = 0;
	for (const auto& t : tiles)
	{
		const Position pos = t.first;
		const int walk = t.second;
		// moving in view draws reaction fire: a unit the other side sees shoots from where it stands or not at all (v1 walked 3.5 times per shot, +0.9 dead a battle)
		if (walk > 0 && _spottingEnemies)
		{
			continue;
		}
		// time units that must remain after the shot: the careful bot's cover path from here, a share of the turn elsewhere
		const int need = walk == 0 ? (_spottingEnemies ? _escapeTUs : 0) : coverTU;
		Tile *tile = _save->getTile(pos);
		if (!tile)
		{
			continue;
		}
		Position origin = pos.toVoxel() + Position(8, 8, _unit->getHeight() + _unit->getFloatHeight() - tile->getTerrainLevel() - 4);
		// which seen enemies have a line of fire here - they are the targets and, the other way, the exposure
		std::vector<BattleUnit*> inLine;
		for (auto* e : targets)
		{
			Position scan;
			if (_save->getTileEngine()->canTargetUnit(&origin, e->getTile(), &scan, _unit, false))
			{
				inLine.push_back(e);
			}
		}
		if (inLine.empty())
		{
			continue;
		}
		const double exposure = riskPerSpotter * fragility * inLine.size();
		for (auto* e : inLine)
		{
			const int distanceSq = Position::distanceSq(pos, e->getPosition());
			const int distance = (int)std::ceil(std::sqrt((float)distanceSq));
			if (rule->isOutOfRange(distanceSq))
			{
				continue;
			}
			const int hp = std::max(1, e->getHealth());
			for (const auto& m : modes)
			{
				const RuleItem *ammo = m.attack.damage_item->getRules();
				if (ammo->getExplosionRadius(m.attack) != 0)
				{
					continue; // area damage: the old logic with explosiveEfficacy
				}
				int upper, lower;
				const int dropoff = rule->calculateLimits(upper, lower, _save->getDepth(), m.type);
				int accuracy = m.accuracy;
				if (distance > upper)
				{
					accuracy -= (distance - upper) * dropoff;
				}
				else if (distance < lower)
				{
					accuracy -= (lower - distance) * dropoff;
				}
				const RuleDamageType *type = ammo->getDamageType();
				const int power = e->reduceByResistance(ammo->getPowerBonus(m.attack), type->ResistType);
				const double perHit = std::max(0.0, power - e->getArmor(SIDE_FRONT) * (double)type->ArmorEffectiveness);
				if (perHit <= 0.0)
				{
					continue;
				}
				for (int kneel = 0; kneel < 2; ++kneel)
				{
					if (kneel && !mayKneel)
					{
						continue;
					}
					// staying put keeps the kneel the unit already has; kneeling down costs its time units
					const bool alreadyKneeled = walk == 0 && _unit->isKneeled();
					const int kneelTU = kneel && !alreadyKneeled ? _unit->getKneelDownCost() : 0;
					const int left = timeUnits - walk - m.time - kneelTU;
					if (left < need)
					{
						continue;
					}
					const bool kneeled = kneel || alreadyKneeled;
					const double hit = std::min(1.0, std::max(0.0, (kneeled ? accuracy * kneelBonus / 100.0 : accuracy) / 100.0));
					const double gain = perHit >= hp
						? 1.0 - std::pow(1.0 - hit, m.shots)
						: 0.7 * std::min(1.0, hit * m.shots * perHit / hp);
					const double risk = exposure * (left >= coverTU ? 1.0 - coverRelief : 1.0);
					const double score = gain - risk - (walk > 0 ? walkCost : 0.0) + 0.0005 * left;
					AiProbe::traceTile(_unit, "eval", pos, (int)std::lround(score * 1000));
					++evaluated;
					if (score > bestScore)
					{
						bestScore = score;
						bestTile = pos;
						bestTarget = e->getPosition();
						bestType = m.type;
						bestKneel = kneeled;
					}
				}
			}
		}
	}

	if (bestType == BA_RETHINK)
	{
		AiProbe::tally(_unit, "eval.none");
		_attackAction.type = BA_RETHINK;
		return true;
	}
	_probeScore = (int)std::lround(bestScore * 1000);
	_evalChosen = true;
	if (bestTile == _unit->getPosition())
	{
		_attackAction.type = bestType;
		_attackAction.target = bestTarget;
		_evalKneel = bestKneel;
		AiProbe::tally(_unit, "eval.shot");
	}
	else
	{
		_attackAction.type = BA_WALK;
		_attackAction.target = bestTile;
		_attackAction.finalFacing = _save->getTileEngine()->getDirectionTo(bestTile, bestTarget);
		_evalKneel = false;
		AiProbe::tally(_unit, "eval.walk");
	}
	if (_traceAI)
	{
		Log(LOG_INFO) << "Shot evaluator: " << evaluated << " options on " << tiles.size() << " tiles, best " << bestScore
			<< " - " << (int)bestType << " at " << bestTarget << " from " << bestTile << (bestKneel ? " kneeling" : "");
	}
	return true;
}

void AIModule::extendedFireModeChoice(BattleActionCost& costAuto, BattleActionCost& costSnap, BattleActionCost& costAimed, BattleActionCost& costThrow, bool checkLOF)
{
	std::vector<BattleActionType> attackOptions = { };
	if (costAimed.haveTU())
	{
		attackOptions.push_back(BA_AIMEDSHOT);
	}
	if (costAuto.haveTU())
	{
		attackOptions.push_back(BA_AUTOSHOT);
	}
	if (costSnap.haveTU())
	{
		attackOptions.push_back(BA_SNAPSHOT);
	}
	if (costThrow.haveTU())
	{
		attackOptions.push_back(BA_THROW);
	}

	BattleActionType chosenAction = BA_RETHINK;
	BattleAction testAction = _attackAction;
	int score = 0;

	// AI3-E (bench): OXCE_AI_FIRE_MODE_EV - the modes the old score allows (above 0) are compared by the expected damage this
	// turn (fireModeEffect) instead of accuracy x shots x base TU / cost; the same RNG draws and the AUTO bonus follow. A mode
	// that cannot be modelled (a throw, an area, the side unknown) or no expected damage at all - the old score for the whole
	// choice, so no attack is lost. Off - the old loop as it was.
	// 2 - the negative control of the bench only: the least expected damage wins.
	static const int fireModeEvMode = AiProbe::param("OXCE_AI_FIRE_MODE_EV", 0);
	static const bool fireModeEv = fireModeEvMode != 0;
	std::vector<int> evOld, evNew;
	bool evUse = false;
	int evNewMax = 0;
	const char *evWhy = "";
	if (fireModeEv)
	{
		double evMax = 0.0;
		bool modelled = true;
		for (auto& i : attackOptions)
		{
			testAction.type = i;
			if (i == BA_THROW)
			{
				if (!_grenade)
				{
					evOld.push_back(0);
					evNew.push_back(0);
					continue;
				}
				testAction.weapon = _unit->getGrenadeFromBelt(_save);
			}
			else
			{
				testAction.weapon = _attackAction.weapon;
			}
			const int old = scoreFiringMode(&testAction, _aggroTarget, checkLOF);
			double ev = 0.0;
			if (old > 0 && modelled)
			{
				const char *why = "";
				ev = fireModeEffect(&testAction, _aggroTarget, why);
				if (ev < 0.0)
				{
					modelled = false;
					evWhy = why;
					ev = 0.0;
				}
			}
			evMax = std::max(evMax, ev);
			evOld.push_back(old);
			// thousandths, at least 100 so that the noise (down to 50 %) never zeroes a mode with an effect; capped so that the
			// noise and the AUTO bonus cannot overflow
			const int scaled = ev > 0.0 ? (int)std::min(1000000L, std::max(100L, std::lround(ev * 1000.0))) : 0;
			evNew.push_back(scaled);
			evNewMax = std::max(evNewMax, scaled);
		}
		evUse = modelled && evMax > 0.0;
		if (modelled && !evUse)
		{
			evWhy = "no_effect";
		}
	}
	BattleActionType evOldChosen = BA_RETHINK;
	int evOldScore = 0;
	size_t evIndex = 0;

	for (auto& i : attackOptions)
	{
		const size_t k = evIndex++;
		testAction.type = i;
		if (i == BA_THROW)
		{
			if (_grenade)
			{
				testAction.weapon = _unit->getGrenadeFromBelt(_save);
			}
			else
			{
				continue;
			}
		}
		else
		{
			testAction.weapon = _attackAction.weapon;
		}
		int newScore = fireModeEv ? evOld[k] : scoreFiringMode(&testAction, _aggroTarget, checkLOF);

		// Add a random factor to the firing mode score based on intelligence
		// An intelligence value of 10 will decrease this random factor to 0
		// Default values for and intelligence value of 0 will make this a 50% to 150% roll
		int intelligenceModifier = _save->getMod()->getAIFireChoiceIntelCoeff() * std::max(10 - _unit->getIntelligence(), 0);
		const int noise = 100 + RNG::generate(-intelligenceModifier, intelligenceModifier);
		const int aggro = 100 + (_unit->getAggression() - 1) * _save->getMod()->getAIFireChoiceAggroCoeff();
		if (fireModeEv)
		{
			// the old choice under the same draw, for the record
			int oldScore = newScore * noise / 100;
			if (i == BA_AUTOSHOT)
			{
				oldScore = oldScore * aggro / 100;
			}
			if (oldScore > evOldScore)
			{
				evOldScore = oldScore;
				evOldChosen = i;
			}
			if (evUse)
			{
				newScore = evOld[k] <= 0 ? 0 : fireModeEvMode == 2 ? evNewMax + 100 - evNew[k] : evNew[k];
			}
		}
		newScore = newScore * noise / 100;

		// More aggressive units get a modifier to the score for autoshots
		// Aggression = 0 lowers the score, aggro = 1 is no modifier, aggro > 1 bumps up the score by 5% (configurable) for each increment over 1
		if (i == BA_AUTOSHOT)
		{
			newScore = newScore * aggro / 100;
		}

		if (newScore > score)
		{
			score = newScore;
			chosenAction = i;
		}

		if (_traceAI)
		{
			Log(LOG_INFO) << "Evaluate option " << (int)i << ", score = " << newScore;
		}
	}

	if (fireModeEv && !attackOptions.empty())
	{
		// AI3-E: fmode.ev <chosen> <old choice under the same draw>; fmode.ev.fb <why> - the old score decided
		const std::string evNote = evUse ? "fmode.ev " + std::to_string((int)chosenAction) + " " + std::to_string((int)evOldChosen)
			: std::string("fmode.ev.fb ") + evWhy;
		AiProbe::note(_unit, evNote.c_str());
	}
	_probeScore = score;
	_attackAction.type = chosenAction;
}

/**
 * Evaluates whether to throw a grenade at an enemy (or group of enemies) we can see.
 */
void AIModule::grenadeAction()
{
	// do we have a grenade on our belt?
	BattleItem *grenade = _unit->getGrenadeFromBelt(_save);
	BattleAction action;
	action.weapon = grenade;
	action.type = BA_THROW;
	action.actor = _unit;

	action.updateTU();
	action.Time += 4; // 4TUs for picking up the grenade
	action += _unit->getActionTUs(BA_PRIME, grenade);
	// do we have enough TUs to prime and throw the grenade?
	if (action.haveTU())
	{
		int radius = grenade->getRules()->getExplosionRadius(BattleActionAttack::GetBeforeShoot(action));
		const Position grenadeAt = knownPos(_aggroTarget, "grenade");
		const int eff = grenadeAt.x < 0 ? 0 : explosiveEfficacy(grenadeAt, _unit, radius, _attackAction.diff, true);
		aoeEfficacyTrace("normal_grenade", BA_THROW, grenade, grenade, _aggroTarget, grenadeAt, radius, true, eff, false);
		if (eff)
		{
			action.target = grenadeAt;
		}
		else if (!getNodeOfBestEfficacy(&action, radius))
		{
			return;
		}
		else
		{
			_probeSource = "grenade.node";
		}
		std::vector<std::pair<Position, int>> shifts;
		if (grenade->getRules()->getBattleType() == BT_PROXIMITYGRENADE)
		{
			// let's try to not throw the proxy below xcom's feet, otherwise they'll just throw it straight back :)
			if (action.target.x < _save->getMapSizeX() - 1) shifts.push_back(std::make_pair(Position(1, 0, 0), _unit->distance3dToPositionSq(action.target + Position(1, 0, 0))));
			if (action.target.y < _save->getMapSizeY() - 1) shifts.push_back(std::make_pair(Position(0, 1, 0), _unit->distance3dToPositionSq(action.target + Position(0, 1, 0))));
			if (action.target.x > 0) shifts.push_back(std::make_pair(Position(-1, 0, 0), _unit->distance3dToPositionSq(action.target + Position(-1, 0, 0))));
			if (action.target.y > 0) shifts.push_back(std::make_pair(Position(0, -1, 0), _unit->distance3dToPositionSq(action.target + Position(0, -1, 0))));
			//RNG::shuffle(shifts);
			std::sort(shifts.begin(), shifts.end(), [](auto& left, auto& right) {
				return left.second < right.second;
			});
			// PS: if someone wants to calculate a better target spot (based on multiple enemies, RNG, day of the week or position of the stars), be my guest
		}
		else
		{
			// normal grenade
			shifts.push_back(std::make_pair(Position(0, 0, 0), 0));
		}
		Position originVoxel = _save->getTileEngine()->getOriginVoxel(action, 0);
		for (auto& shift : shifts)
		{
			Position targetTile = action.target + shift.first;
			Position targetVoxel = targetTile.toVoxel() + Position(8,8, (2 + -_save->getTile(targetTile)->getTerrainLevel()));
			// are we within range?
			if (_save->getTileEngine()->validateThrow(action, originVoxel, targetVoxel, _save->getDepth()))
			{
				// AI3-FF (bench): OXCE_AI_FF_RISK bit 2 - the throw waits for the shot (ffThrowOrShot) instead of taking the
				// rifle's place; it still takes the melee's, as before
				static const int ffRisk = (int)AiProbe::param("OXCE_AI_FF_RISK", 0);
				if ((ffRisk & 2) && _rifle)
				{
					_ffThrow = true;
					_ffThrowNode = !eff;
					_ffThrowEnemies = eff ? _ffEnemies : 0;
					_ffThrowAt = targetTile;
					_ffThrowItem = grenade;
					_melee = false;
					break;
				}
				_attackAction.weapon = grenade;
				_attackAction.target = targetTile;
				_attackAction.type = BA_THROW;
				_rifle = false;
				_melee = false;
				break;
			}
		}
	}
}

/**
 * AI3-FF (bench, OXCE_AI_FF_RISK bit 2): the throw grenadeAction found against the shot projectileAction chose, by
 * scoreFiringMode's own terms (accuracy * shots * TU ratio), the throw's counted once per enemy explosiveEfficacy found
 * in its blast. A throw at a node (no seen target in reach) is taken only when there is no shot. No RNG.
 */
void AIModule::ffThrowOrShot()
{
	_ffThrow = false;
	const bool shot = _attackAction.type == BA_AUTOSHOT || _attackAction.type == BA_SNAPSHOT || _attackAction.type == BA_AIMEDSHOT;
	if (shot)
	{
		bool take = false;
		if (!_ffThrowNode)
		{
			BattleAction toss = _attackAction;
			toss.type = BA_THROW;
			toss.weapon = _ffThrowItem;
			long long tossScore = (long long)ffFireScore(toss, _ffThrowAt) * std::max(1, _ffThrowEnemies);
			long long shotScore = ffFireScore(_attackAction, _attackAction.target);
			// AI3-FF (bench): OXCE_AI_FF_RISK bit 8 (with bit 2) - scoreFiringMode's terms know no damage, so a grenade's blast
			// lost to any burst; each side is weighed by the power of what it hits with
			static const int ffRisk = (int)AiProbe::param("OXCE_AI_FF_RISK", 0);
			if (ffRisk & 8)
			{
				tossScore *= ffPower(toss);
				shotScore *= ffPower(_attackAction);
			}
			take = tossScore > shotScore;
		}
		if (!take)
		{
			AiProbe::note(_unit, _ffThrowNode ? "ff.shot.node" : "ff.shot");
			return;
		}
		AiProbe::note(_unit, "ff.throw");
	}
	const ProbeMark mark = probeMark('x');
	_attackAction.weapon = _ffThrowItem;
	_attackAction.target = _ffThrowAt;
	_attackAction.type = BA_THROW;
	_rifle = false;
	_melee = false;
	_probeSource = _ffThrowNode ? "grenade.node" : nullptr;
	probeSlot('x', "grenade", mark);
}

/**
 * AI3-FF (bench): scoreFiringMode's score without the line-of-fire check and its RNG-free part only, the distance taken to
 * a place - the target's place this side knows (projectileAction's target) or the throw's tile.
 */
int AIModule::ffFireScore(const BattleAction &action, Position at) const
{
	if (!action.type || !action.weapon || at.x < 0)
	{
		return 0;
	}
	auto* weapon = action.weapon->getRules();
	int accuracy = BattleUnit::getFiringAccuracy(BattleActionAttack::GetBeforeShoot(action), _save->getMod());
	const int distanceSq = _unit->distance3dToPositionSq(at);
	const int distance = (int)std::ceil(sqrt(float(distanceSq)));
	{
		int upperLimit, lowerLimit;
		int dropoff = weapon->calculateLimits(upperLimit, lowerLimit, _save->getDepth(), action.type);
		if (distance > upperLimit)
		{
			accuracy -= (distance - upperLimit) * dropoff;
		}
		else if (distance < lowerLimit)
		{
			accuracy -= (lowerLimit - distance) * dropoff;
		}
	}
	if (action.type == BA_THROW ? weapon->isOutOfThrowRange(distanceSq, _save->getDepth()) : weapon->isOutOfRange(distanceSq))
	{
		accuracy = 0;
	}
	int numberOfShots = 1;
	if (action.type == BA_AIMEDSHOT)
	{
		numberOfShots = weapon->getConfigAimed()->shots;
	}
	else if (action.type == BA_SNAPSHOT)
	{
		numberOfShots = weapon->getConfigSnap()->shots;
	}
	else if (action.type == BA_AUTOSHOT)
	{
		numberOfShots = weapon->getConfigAuto()->shots;
	}
	int tuCost = _unit->getActionTUs(action.type, action.weapon).Time;
	if (action.type == BA_THROW)
	{
		tuCost += 4 + _unit->getActionTUs(BA_PRIME, action.weapon).Time;
	}
	if (!tuCost)
	{
		return 0;
	}
	return accuracy * numberOfShots * _unit->getBaseStats()->tu / tuCost;
}

/**
 * AI3-FF (bench, OXCE_AI_FF_RISK bit 8): the power the action hits with - the ammo's (the grenade's for a throw), or the
 * weapon's when it ignores the ammo's power, bonuses included (RuleItem::getPowerBonus), before resistances. No RNG.
 */
int AIModule::ffPower(const BattleAction &action) const
{
	if (!action.weapon)
	{
		return 0;
	}
	const BattleActionAttack attack = BattleActionAttack::GetBeforeShoot(action);
	const RuleItem *rule = action.weapon->getRules();
	if (!rule->getIgnoreAmmoPower() && attack.damage_item)
	{
		rule = attack.damage_item->getRules();
	}
	return std::max(0, rule->getPowerBonus(attack));
}

/**
 * AI3-FF (bench, OXCE_AI_FF_RISK bit 4): is there a tile part with explosive, in the shooter's view, within 1.5 tiles
 * of the line of fire (from the shooter up to a fifth past the target, the floors between them +-1), whose blast (power / 10
 * tiles, as ExplosionBState sets it) reaches our own side - the shooter weighed as explosiveEfficacy's kamikaze - for no gain
 * by the unit weights: our own where they stand, enemies only those the shooter sees now (FAIR_KNOWLEDGE). No RNG.
 */
bool AIModule::ffLineRisk(Position target) const
{
	if (target.x < 0)
	{
		return false;
	}
	const Position from = _unit->getPosition();
	const int ax = target.x - from.x, ay = target.y - from.y;
	const int len2 = ax * ax + ay * ay;
	if (len2 == 0)
	{
		return false;
	}
	auto blastBad = [&](Position c, int radius)
	{
		int sum = 0;
		bool own = false;
		if (abs(from.z - c.z) <= Options::battleExplosionHeight && Position::distance2d(from, c) <= radius)
		{
			sum -= AIW_SCALE * 4;
			own = true;
		}
		for (auto* bu : *_save->getUnits())
		{
			if (bu->isOut() || bu == _unit)
			{
				continue;
			}
			const int weight = getTargetAttackWeight(bu);
			if (weight == 0 || (weight > 0 && !_unit->hasVisibleUnit(bu)))
			{
				continue;
			}
			const Position bp = bu->getPosition();
			if (abs(bp.z - c.z) <= Options::battleExplosionHeight && Position::distance2d(bp, c) <= radius)
			{
				sum += weight;
				own = own || weight < 0;
			}
		}
		return own && sum <= 0;
	};
	const int xLo = std::max(0, std::min(from.x, target.x) - 2), xHi = std::min(_save->getMapSizeX() - 1, std::max(from.x, target.x) + 2);
	const int yLo = std::max(0, std::min(from.y, target.y) - 2), yHi = std::min(_save->getMapSizeY() - 1, std::max(from.y, target.y) + 2);
	const int zLo = std::max(0, std::min(from.z, target.z) - 1), zHi = std::min(_save->getMapSizeZ() - 1, std::max(from.z, target.z) + 1);
	for (int z = zLo; z <= zHi; ++z)
	{
		for (int y = yLo; y <= yHi; ++y)
		{
			for (int x = xLo; x <= xHi; ++x)
			{
				const int px = x - from.x, py = y - from.y;
				const int along = px * ax + py * ay;
				const int across = px * ay - py * ax;
				// along the line from the shooter to 1.2 of the target's distance, at most 1.5 tiles aside
				if (along <= 0 || along * 5 > len2 * 6 || across * across * 4 > len2 * 9)
				{
					continue;
				}
				Tile *tile = _save->getTile(Position(x, y, z));
				if (!tile)
				{
					continue;
				}
				bool seen = false;
				for (int part = O_FLOOR; part < O_MAX; ++part)
				{
					const MapData *md = tile->getMapData((TilePart)part);
					if (!md || md->getExplosive() <= 0)
					{
						continue;
					}
					if (!seen)
					{
						// in the shooter's view: within view distance and the tile line reaches it (calculateTilesInFOV keeps
						// seen tiles for FACTION_PLAYER only, so hasVisibleTile never answers for the other sides)
						const Position at(x, y, z);
						if (Position::distance2dSq(from, at) > _save->getTileEngine()->getMaxViewDistanceSq())
						{
							break;
						}
						std::vector<Position> line;
						if (_save->getTileEngine()->calculateLineTile(from, at, line) > 127 && (line.empty() || line.back() != at))
						{
							break;
						}
						seen = true;
					}
					// ExplosionBState: 0 HE, 5 incendiary, 6 stun; anything else is smoke
					const int type = md->getExplosiveType();
					if ((type == 0 || type == 5 || type == 6) && blastBad(Position(x, y, z), md->getExplosive() / 10))
					{
						return true;
					}
				}
			}
		}
	}
	return false;
}

/**
 * Attempts a psionic attack on an enemy we "know of".
 *
 * Psionic targetting: pick from any of the "exposed" units.
 * Exposed means they have been previously spotted, and are therefore "known" to the AI,
 * regardless of whether we can see them or not, because we're psychic.
 * @return True if a psionic attack is performed.
 */
bool AIModule::psiAction()
{
	BattleItem *item = _unit->getUtilityWeapon(BT_PSIAMP);
	if (!item)
	{
		return false;
	}

	const int costLength = 3;
	BattleActionCost cost[costLength] =
	{
		BattleActionCost(BA_USE, _unit, item),
		BattleActionCost(BA_PANIC, _unit, item),
		BattleActionCost(BA_MINDCONTROL, _unit, item),
	};
	bool have = false;
	for (int j = 0; j < costLength; ++j)
	{
		if (cost[j].Time > 0)
		{
			cost[j].Time += _escapeTUs;
			cost[j].Energy += _escapeTUs / 2;
			have |= cost[j].haveTU();
		}
	}
	bool LOSRequired = item->getRules()->isLOSRequired();
	static const bool botSpecialOn = AiProbe::param("OXCE_AI_BOT_SPECIAL", 0) != 0;
	const bool botPsi = botSpecialOn && AiProbe::careful(_unit);

	_aggroTarget = 0;
		// don't let mind controlled soldiers mind control other soldiers.
	if (_unit->getOriginalFaction() == _unit->getFaction()
		// and we have the required 25 TUs and can still make it to cover
		&& have
		// and we didn't already do a psi action this round
		&& !_didPsi)
	{
		int weightToAttack = 0;
		BattleActionType typeToAttack = BA_NONE;

		for (auto* bu : *_save->getUnits())
		{
			// don't target tanks
			if (bu->getArmor()->getSize() == 1 &&
				validTarget(bu, true, false) &&
				// they must be player units
				bu->getOriginalFaction() != _unit->getFaction() &&
				(!LOSRequired || AiProbe::upstreamSees(_unit, bu, 0)) && // UPSTREAM_VIS (bench, upstream 613ec4a28)
				// AI3-F (bench): OXCE_AI_BOT_SPECIAL - the bot's psi only at a target it sees, which the amp may target
				(!botPsi || (bu->getVisible() && item->getRules()->isTargetAllowed(bu->getFaction(), _unit->getFaction()))))
			{
				BattleUnit *victim = bu;
				// AI2-H FAIR KNOWLEDGE: the victim is weighed where this side knows it to be
				Position kp;
				int kdir = 0;
				const int kind = knownPlace(victim, "psi", kp, kdir);
				if (kind == 2)
				{
					continue;
				}
				AiKnownPlace known(_save, victim, kind, kp, kdir);
				if (item->getRules()->isOutOfRange(_unit->distance3dToUnitSq(victim)))
				{
					continue;
				}
				for (int j = 0; j < costLength; ++j)
				{
					// can't use this attack.
					if (!cost[j].haveTU())
					{
						continue;
					}

					int weightToAttackMe = _save->getTileEngine()->psiAttackCalculate({ cost[j].type, _unit, item, item }, victim);

					// low chance we hit this target.
					if (weightToAttackMe < 0)
					{
						continue;
					}

					// different bonus per attack.
					if (cost[j].type == BA_MINDCONTROL)
					{
						// target cannot be mind controlled
						if (victim->getUnitRules() && !victim->getUnitRules()->canBeMindControlled()) continue;

						int controlOdds = 40;
						int morale = victim->getMorale();
						int bravery = victim->reduceByBravery(10);
						if (bravery > 6)
							controlOdds -= 15;
						if (bravery < 4)
							controlOdds += 15;
						if (morale >= 40)
						{
							if (morale - 10 * bravery < 50)
								controlOdds -= 15;
						}
						else
						{
							controlOdds += 15;
						}
						if (!morale)
						{
							controlOdds = 100;
						}
						if (RNG::percent(controlOdds))
						{
							weightToAttackMe += 60;
						}
						else
						{
							continue;
						}
					}
					else if (cost[j].type == BA_USE)
					{
						if (RNG::percent(80 - _attackAction.diff * 10)) // Star gods have mercy on us.
						{
							continue;
						}
						BattleActionAttack attack = BattleActionAttack{ BA_USE, _unit, item, item };
						int radius = item->getRules()->getExplosionRadius(attack);
						if (radius > 0)
						{
							int efficity = explosiveEfficacy(victim->getPosition(), _unit, radius, _attackAction.diff);
							if (efficity)
							{
								weightToAttackMe += 2 * efficity * _intelligence; //bonus for boom boom.
							}
							else
							{
								continue;
							}
						}
						else
						{
							weightToAttackMe += item->getRules()->getPowerBonus(attack);
						}
					}
					else if (cost[j].type == BA_PANIC)
					{
						// target cannot be panicked
						if (victim->getUnitRules() && !victim->getUnitRules()->canPanic()) continue;

						weightToAttackMe += 40;
					}

					if (weightToAttackMe > weightToAttack)
					{
						typeToAttack = cost[j].type;
						weightToAttack = weightToAttackMe;
						_aggroTarget = victim;
					}
				}
			}
		}

		if (!_aggroTarget || !weightToAttack) return false;

		if (_visibleEnemies && _attackAction.weapon)
		{
			BattleActionType actions[] = {
				BA_AIMEDSHOT,
				BA_AUTOSHOT,
				BA_SNAPSHOT,
				BA_HIT,
			};
			for (BattleActionType action : actions)
			{
				auto* ammo = _attackAction.weapon->getAmmoForAction(action);
				if (!ammo)
				{
					continue;
				}

				int weightPower = ammo->getRules()->getPowerBonus({ action, _attackAction.actor, _attackAction.weapon, ammo });
				if (action == BA_HIT)
				{
					// prefer psi over melee
					weightPower /= 2;
				}
				else
				{
					// prefer machine guns
					weightPower *= _attackAction.weapon->getActionConf(action)->shots;
				}
				if (weightPower >= weightToAttack)
				{
					return false;
				}
			}
		}
		else if (RNG::generate(35, 155) >= weightToAttack)
		{
			return false;
		}

		if (_traceAI)
		{
			Log(LOG_INFO) << "making a psionic attack this turn";
		}

		_probeScore = weightToAttack;
		_psiAction.type = typeToAttack;
		_psiAction.target = knownPos(_aggroTarget, "psi");
		_psiAction.weapon = item;
		return true;
	}
	return false;
}

/**
 * Performs a melee attack action.
 */
void AIModule::meleeAttack()
{
	Position kp;
	int kdir = 0;
	const Position at = knownPlace(_aggroTarget, "melee", kp, kdir) == 1 ? kp : _aggroTarget->getPosition();
	_unit->lookAt(at + Position(_unit->getArmor()->getSize()-1, _unit->getArmor()->getSize()-1, 0), false);
	while (_unit->getStatus() == STATUS_TURNING)
		_unit->turn();
	if (_traceAI) { Log(LOG_INFO) << "Attack unit: " << _aggroTarget->getId(); }
	_attackAction.target = at;
	_attackAction.type = BA_HIT;
	_attackAction.weapon = _unit->getUtilityWeapon(BT_MELEE);
}


/**
 *
 * @param target
 * @return
 */
AIAttackWeight AIModule::getTargetAttackWeight(BattleUnit* target) const
{
	AIAttackWeight weight = AIW_IGNORED;

	if (target->getFaction() == _unit->getFaction())
	{
		// friendly target have negative weight, used for AoE attacks.
		weight = target->getAITargetWeightAsFriendly(_save->getMod());
	}
	else if (
		_intelligence < target->getTurnsSinceSpottedByFaction(_unit->getFaction()) &&
		(!_unit->isSniper() || !target->getTurnsLeftSpottedForSnipersByFaction(_unit->getFaction())))
	{
		// ignore units that we don't "know" about...
		// ... unless we are a sniper and the spotters know about them
		weight = AIW_IGNORED;
	}
	else if (target->getFaction() == FACTION_HOSTILE || _unit->getFaction() == FACTION_HOSTILE)
	{
		if (target->getFaction() == _targetFaction)
		{
			// enemy unit, full weight
			weight = target->getAITargetWeightAsHostile(_save->getMod());
		}
		else
		{
			// if its not xcom unit then its civilian, less value that xcom
			weight = target->getAITargetWeightAsHostileCivilians(_save->getMod());
		}
	}
	else if (target->getFaction() == FACTION_NEUTRAL || _unit->getFaction() == FACTION_NEUTRAL)
	{
		// if its not alien then its xcom or civilian, humans do not shoot each other, usually...
		weight = target->getAITargetWeightAsNeutral(_save->getMod());
	}

	weight = (AIAttackWeight)ModScript::scriptFunc2<ModScript::AiCalculateTargetWeight>(
		_unit->getArmor(),
		weight, weight,
		_unit, target, _save
	);

	return weight;
}

/**
 * Validates a target.
 * @param target the target we want to validate.
 * @param assessDanger do we care if this unit was previously targetted with a grenade?
 * @param includeCivs do we include civilians in the threat assessment?
 * @return whether this target is someone we would like to kill.
 */
bool AIModule::validTarget(BattleUnit *target, bool assessDanger, bool includeCivs) const
{
	// ignore units that:
	// 1. are dead/unconscious
	// 2. are dangerous (they have been grenaded)
	// 3. are hostile/neutral units marked as ignored by the AI
	if (target->isOut() ||
		(assessDanger && knownDangerous(target)) ||
		(target->getFaction() != FACTION_PLAYER && target->isIgnoredByAI()))
	{
		return false;
	}

	if (includeCivs)
	{
		return  getTargetAttackWeight(target) > AIW_IGNORED;
	}
	else
	{
		return  getTargetAttackWeight(target) > _save->getMod()->getAITargetWeightThreatThreshold();
	}
}

/**
 * Checks the alien's reservation setting.
 * @return the reserve setting.
 */
BattleActionType AIModule::getReserveMode()
{
	return _reserve;
}

/**
 * We have a dichotomy on our hands: we have a ranged weapon and melee capability.
 * let's make a determination on which one we'll be using this round.
 */
void AIModule::selectMeleeOrRanged()
{
	BattleItem *range = _attackAction.weapon;
	BattleItem *melee = _unit->getUtilityWeapon(BT_MELEE);

	if (!melee || !melee->haveAnyAmmo())
	{
		// no idea how we got here, but melee is definitely out of the question.
		_melee = false;
		return;
	}
	if (!range || !range->haveAnyAmmo())
	{
		_rifle = false;
		return;
	}

	const RuleItem *meleeRule = melee->getRules();

	int meleeOdds = 10;

	int dmg = _aggroTarget->reduceByResistance(meleeRule->getPowerBonus(BattleActionAttack::GetBeforeShoot(BA_HIT, _unit, melee)), meleeRule->getDamageType()->ResistType);

	if (dmg > 50)
	{
		meleeOdds += (dmg - 50) / 2;
	}
	if ( _visibleEnemies > 1 )
	{
		meleeOdds -= 20 * (_visibleEnemies - 1);
	}

	if (meleeOdds > 0 && _unit->getHealth() >= 2 * _unit->getBaseStats()->health / 3)
	{
		if (_unit->getAggression() == 0)
		{
			meleeOdds -= 20;
		}
		else if (_unit->getAggression() > 1)
		{
			meleeOdds += 10 * _unit->getAggression();
		}

		if (RNG::percent(meleeOdds))
		{
			_rifle = false;
			_attackAction.weapon = melee;
			reachableWithAttack(BattleActionCost(BA_HIT, _unit, melee));
			return;
		}
	}
	_melee = false;
}

/**
 * Checks nearby nodes to see if they'd make good grenade targets
 * @param action contains our details one weapon and user, and we set the target for it here.
 * @return if we found a viable node or not.
 */
bool AIModule::getNodeOfBestEfficacy(BattleAction *action, int radius)
{
	int bestScore = 2;
	Position originVoxel = _save->getTileEngine()->getSightOriginVoxel(_unit);
	Position targetVoxel;
	for (const auto* node : *_save->getNodes())
	{
		if (node->isDummy())
		{
			continue;
		}
		int dist = Position::distance2d(node->getPosition(), _unit->getPosition());
		if (dist <= 20 && dist > radius &&
			_save->getTileEngine()->canTargetTile(&originVoxel, _save->getTile(node->getPosition()), O_FLOOR, &targetVoxel, _unit, false))
		{
			int nodePoints = 0;
			for (auto* bu : *_save->getUnits())
			{
				// AI2-H FAIR KNOWLEDGE: the units around the node are counted where this side knows them to be
				if (bu->isOut())
				{
					continue;
				}
				Position kp;
				int kdir = 0;
				const int kind = knownPlace(bu, "node", kp, kdir);
				if (kind == 2)
				{
					continue;
				}
				AiKnownPlace known(_save, bu, kind, kp, kdir);
				dist = Position::distance2d(node->getPosition(), bu->getPosition());
				// O11 (BetterAI): a unit on the blast's edge is in it, as explosiveEfficacy counts (<=)
				if (!bu->isOut() && (dist < radius || (dist == radius && AiProbe::oxceFixes())))
				{
					Position targetOriginVoxel = _save->getTileEngine()->getSightOriginVoxel(bu);
					if (_save->getTileEngine()->canTargetTile(&targetOriginVoxel, _save->getTile(node->getPosition()), O_FLOOR, &targetVoxel, bu, false))
					{
						if ((_unit->getFaction() == FACTION_HOSTILE && bu->getFaction() != FACTION_HOSTILE) ||
							(_unit->getFaction() == FACTION_NEUTRAL && bu->getFaction() == FACTION_HOSTILE))
						{
							if (bu->getTurnsSinceSpottedByFaction(_unit->getFaction()) <= _intelligence)
							{
								nodePoints++;
							}
						}
						else
						{
							nodePoints -= 2;
						}
					}
				}
			}
			if (nodePoints > bestScore)
			{
				bestScore = nodePoints;
				action->target = node->getPosition();
			}
		}
	}
	return bestScore > 2;
}

BattleUnit* AIModule::getTarget()
{
	return _aggroTarget;
}

void AIModule::freePatrolTarget()
{
	if (_toNode)
	{
		_toNode->freeNode();
	}
}

/**
 * AI2-A DAMAGE FEASIBILITY: the bench flag OXCE_AI_ZERO_EFFECT, read once (0 in a release build).
 * 0 off, 1 shadow (verdicts logged, play unchanged), 2 reject ZERO melee/shot/sniper, 3 also skip findFirePoint.
 */
int AIModule::zeroEffectMode()
{
	static const int mode = (int)AiProbe::param("OXCE_AI_ZERO_EFFECT", 0);
	return mode;
}

/**
 * AI2-B1 SNIPER EXPLOSIVE EFFICACY PARITY: the bench flag OXCE_AI_SNIPER_AOE_EFFICACY, read once (0 in a release build).
 * 0 off (AI2_BASELINE_A2), 1 shadow (verdicts logged, play unchanged), 2 reject.
 */
int AIModule::sniperAoeMode()
{
	static const int mode = (int)AiProbe::param("OXCE_AI_SNIPER_AOE_EFFICACY", 0);
	return mode;
}

/**
 * AI2-B1 V0: an area attack picked by selectSpottedUnitForSniper passes the same explosiveEfficacy check the regular
 * branch passes: a throw as in grenadeAction (target = the unit's position, radius of the grenade's BA_THROW attack,
 * grenade = true), a shot as in projectileAction (radius of the shot's GetBeforeShoot attack, grenade = false).
 * Only the verdict is new here: no fallback node, no other mode, the candidate is just not offered.
 * Nothing is changed and no RNG is used; true only in mode 2 when the check says 0.
 */
bool AIModule::sniperAoeEfficacyReject(const BattleAction &chosen, BattleUnit *target)
{
	const int mode = sniperAoeMode();
	if (mode < 1 || !target || !chosen.weapon)
	{
		return false;
	}
	const bool grenade = chosen.type == BA_THROW;
	if (!grenade && chosen.type != BA_AUTOSHOT && chosen.type != BA_SNAPSHOT && chosen.type != BA_AIMEDSHOT)
	{
		return false;
	}
	int radius = 0;
	BattleItem *damageItem = nullptr;
	if (grenade)
	{
		BattleActionCost cost(BA_THROW, _unit, chosen.weapon);
		radius = chosen.weapon->getRules()->getExplosionRadius(BattleActionAttack::GetBeforeShoot(cost));
		damageItem = chosen.weapon;
	}
	else
	{
		BattleActionCost cost(chosen.type, _unit, chosen.weapon);
		BattleActionAttack attack = BattleActionAttack::GetBeforeShoot(cost);
		if (attack.damage_item == nullptr)
		{
			return false; // as in projectileAction: no ammo is not this check's business
		}
		radius = attack.damage_item->getRules()->getExplosionRadius(attack);
		damageItem = attack.damage_item;
	}
	if (radius == 0)
	{
		return false; // direct attack: unchanged, A2's zeroEffectReject already judged it
	}
	const Position tpos = target->getPosition();
	const int eff = explosiveEfficacy(tpos, _unit, radius, _attackAction.diff, grenade);
	const bool reject = mode >= 2 && eff == 0;
	aoeEfficacyTrace("sniper_aoe", chosen.type, chosen.weapon, damageItem, target, tpos, radius, grenade, eff, reject);
	return reject;
}

/**
 * AI2-B1 diagnostics (mode >= 1 only): one [AITRACE] line per explosiveEfficacy verdict of an area attack, the same
 * fields from the sniper path and from the regular branches, so the verdicts can be matched. Plain reads, no RNG.
 */
void AIModule::aoeEfficacyTrace(const char *site, BattleActionType type, BattleItem *weapon, BattleItem *damageItem, BattleUnit *target,
	Position tpos, int radius, bool grenade, int eff, bool reject)
{
	// the bench's line only: the player's AI3 (BetterAI) plays the mode without writing it to the log
	if (sniperAoeMode() < 1 || !weapon || !AiProbe::active())
	{
		return;
	}
	// who stands inside the radius by the check's own distance/height rule
	std::ostringstream inr;
	bool first = true;
	for (auto* bu : *_save->getUnits())
	{
		if (!bu->isOut() && bu != _unit && abs(bu->getPosition().z - tpos.z) <= Options::battleExplosionHeight
			&& Position::distance2d(bu->getPosition(), tpos) <= radius)
		{
			inr << (first ? "" : ",") << "[" << bu->getId() << "," << (int)bu->getFaction() << "]";
			first = false;
		}
	}
	const bool selfIn = abs(_unit->getPosition().z - tpos.z) <= Options::battleExplosionHeight
		&& Position::distance2d(_unit->getPosition(), tpos) <= radius;
	Log(LOG_INFO) << "[AITRACE] {\"ai2b\":\"" << site << "\",\"rec\":" << AiProbe::nextRec() << ",\"turn\":" << _save->getTurn()
		<< ",\"unit\":" << _unit->getId() << ",\"side\":" << (int)_unit->getFaction() << ",\"target\":" << (target ? target->getId() : -1)
		<< ",\"t\":" << (int)type << ",\"w\":\"" << weapon->getRules()->getType() << "\",\"di\":\""
		<< (damageItem ? damageItem->getRules()->getType() : std::string()) << "\",\"r\":" << radius << ",\"g\":" << (grenade ? 1 : 0) << ",\"tpos\":[" << tpos.x << "," << tpos.y << "," << tpos.z
		<< "],\"diff\":" << _attackAction.diff << ",\"mor\":" << _unit->getMorale() << ",\"hp\":" << _unit->getHealth()
		<< ",\"self\":" << (selfIn ? 1 : 0) << ",\"tu\":" << _unit->getTimeUnits() << ",\"eff\":" << eff
		<< ",\"rej\":" << (reject ? 1 : 0) << ",\"inr\":[" << inr.str() << "]}";
}

namespace
{

/// AI2-A: how many global events a script slot runs around its own script (ScriptWorkerBase::execute walks the same list).
int ai2aEvents(const ScriptContainerEventsBase &c)
{
	int n = 0;
	const ScriptContainerBase *p = c.dataEvents();
	if (p)
	{
		while (*p) { ++n; ++p; }
		++p;
		while (*p) { ++n; ++p; }
	}
	return n;
}

/// AI2-A: a script tag's value, 0 when the mod has no such tag.
template<typename T, typename V>
int ai2aTag(const Mod *mod, const char *name, const V &values)
{
	auto tag = mod->getScriptGlobal()->getTag<ScriptTag<T>>(std::string(name));
	return tag ? (int)values.get(tag) : 0;
}

/// AI2-A: a power bonus that reads a stat the attack itself changes (TU and energy are spent, morale and stun move) or a
/// bonus script: its value at the decision is no bound for the value at the hit.
bool ai2aDynamicBonus(const RuleStatBonus *bonus, std::string &which)
{
	if (bonus->isModded() && bonus->getBonusRaw()->empty())
	{
		which = "script";
		return true;
	}
	for (const auto &b : *bonus->getBonusRaw())
	{
		const std::string &n = b.first;
		if (n.find("Current") != std::string::npos || n.find("Normalized") != std::string::npos || n == "fatalWounds" || n == "energyRegen")
		{
			which = n;
			return true;
		}
	}
	return false;
}

}

/**
 * AI2-A: can this direct shot or blow change the target at all? Follows ExplosionBState::init, TileEngine::hit / hitUnit and
 * BattleUnit::damage with the largest damage roll; reads only, no RNG. ZERO only when every step is proven: power, resistance,
 * armour on its weakest side, armour wear before armour, fire, self-destruct, transformation, spawns, extinguishing and every
 * script that could add to it (Piratez globals by count, tags that switch them on). Anything else is UNKNOWN, never ZERO.
 */
int AIModule::zeroEffectVerdictB2(SavedBattleGame *save, BattleUnit *attacker, BattleActionType type, BattleItem *weapon, const BattleUnit *target, std::string *terms)
{
	std::ostringstream w;
	auto done = [&](int v, const char *why)
	{
		if (terms)
		{
			w << ",\"why\":\"" << why << "\"";
			*terms = w.str();
		}
		return v;
	};
	if (!save || !attacker || !weapon || !target)
	{
		return done(AIZ_UNKNOWN, "no_input");
	}
	const Mod *mod = save->getMod();
	const RuleItem *wrule = weapon->getRules();
	w << ",\"w\":\"" << wrule->getType() << "\",\"tgt\":\"" << target->getType() << "\",\"arm\":\"" << target->getArmor()->getType() << "\"";
	if (type != BA_HIT && type != BA_SNAPSHOT && type != BA_AUTOSHOT && type != BA_AIMEDSHOT)
	{
		return done(AIZ_UNKNOWN, "not_direct_action");
	}
	if (target->isOut() || target->getHealth() <= 0)
	{
		return done(AIZ_UNKNOWN, "target_out");
	}
	BattleActionAttack attack = BattleActionAttack::GetBeforeShoot(type, attacker, weapon);
	if (!attack.damage_item)
	{
		return done(AIZ_UNKNOWN, "no_damage_item");
	}
	const RuleItem *item = attack.damage_item->getRules();
	w << ",\"di\":\"" << item->getType() << "\",\"bt\":" << (int)item->getBattleType();

	// ExplosionBState::init: which power and damage type the hit uses
	const bool hit = type == BA_HIT;
	const RuleStatBonus *bonus = nullptr;
	const RuleDamageType *dt = nullptr;
	int power = 0;
	float rangeRaw = 0.0f;
	const char *path = "";
	if (hit && item->getBattleType() != BT_MELEE)
	{
		path = "melee_bonus";
		bonus = item->getMeleeBonusRaw();
		power = item->getMeleeBonus(attack);
		dt = item->getMeleeType();
	}
	else
	{
		if (!hit && item->getBattleType() != BT_FIREARM && item->getBattleType() != BT_AMMO)
		{
			return done(AIZ_UNKNOWN, "not_firearm");
		}
		if (wrule->getIgnoreAmmoPower())
		{
			path = "weapon_power";
			bonus = wrule->getDamageBonusRaw();
			power = wrule->getPowerBonus(attack);
			rangeRaw = wrule->getPowerRangeReductionRaw();
		}
		else
		{
			path = hit ? "melee_item" : "ammo_power";
			bonus = item->getDamageBonusRaw();
			power = item->getPowerBonus(attack);
			rangeRaw = item->getPowerRangeReductionRaw();
		}
		dt = item->getDamageType();
		if (!hit && item->getExplosionRadius(attack) != 0)
		{
			return done(AIZ_UNKNOWN, "area");
		}
	}
	w << ",\"path\":\"" << path << "\",\"P\":" << power;
	if (!dt)
	{
		return done(AIZ_UNKNOWN, "no_damage_type");
	}
	w << ",\"rt\":" << (int)dt->ResistType << ",\"rnd\":" << (int)dt->RandomType;
	std::string dyn;
	if (ai2aDynamicBonus(bonus, dyn))
	{
		w << ",\"dyn\":\"" << dyn << "\"";
		return done(AIZ_UNKNOWN, "dynamic_bonus");
	}
	if (rangeRaw < 0.0f)
	{
		return done(AIZ_UNKNOWN, "range_adds_power");
	}

	// what the hit can do besides the damage: spawns (ExplosionBState::explode), transformation, extinguishing, self-destruct
	if (item->getSpawnUnit() || item->getSpawnItem())
	{
		return done(AIZ_UNKNOWN, "spawn");
	}
	const Armor *armor = target->getArmor();
	if (!item->getZombieUnit(target).empty() && !armor->getZombiImmune())
	{
		return done(AIZ_UNKNOWN, "transform");
	}
	if (target->getFire() > 0 && (wrule->isFireExtinguisher() || item->isFireExtinguisher()))
	{
		return done(AIZ_UNKNOWN, "extinguish");
	}
	if ((target->getSpecialAbility() == SPECAB_EXPLODEONDEATH || target->getSpecialAbility() == SPECAB_BURN_AND_EXPLODE) && target->isOutThresholdExceed())
	{
		return done(AIZ_UNKNOWN, "self_destruct");
	}

	// scripts: the armour's and the ammo's own must be absent, the globals exactly the audited Piratez set (or none)
	const int evHit = ai2aEvents(armor->getScript<ModScript::HitUnit>());
	const int evDmg = ai2aEvents(armor->getScript<ModScript::DamageUnit>());
	const int evSpec = ai2aEvents(armor->getScript<ModScript::DamageSpecialUnit>());
	const int evAmmo = ai2aEvents(item->getScript<ModScript::HitUnitAmmo>()) + ai2aEvents(item->getScript<ModScript::DamageUnitAmmo>())
		+ ai2aEvents(item->getScript<ModScript::DamageSpecialUnitAmmo>());
	w << ",\"ev\":\"" << evHit << "/" << evDmg << "/" << evSpec << "/" << evAmmo << "\"";
	const bool known = (evHit == 7 && evDmg == 5 && evSpec == 2) || (evHit == 0 && evDmg == 0 && evSpec == 0);
	if (!known || evAmmo != 0)
	{
		return done(AIZ_UNKNOWN, "script_set");
	}
	if (armor->getScript<ModScript::HitUnit>().data() || armor->getScript<ModScript::DamageUnit>().data()
		|| armor->getScript<ModScript::DamageSpecialUnit>().data() || item->getScript<ModScript::HitUnitAmmo>().data()
		|| item->getScript<ModScript::DamageUnitAmmo>().data() || item->getScript<ModScript::DamageSpecialUnitAmmo>().data())
	{
		return done(AIZ_UNKNOWN, "own_script");
	}
	// tags that switch the Piratez globals on: energy shields (unit, hand items), unit resistance, remote control, shield
	// breaker, setting fire (Yankes_Scripts.rul hitUnit / damageUnit)
	if (ai2aTag<BattleUnit>(mod, "Tag.UNIT_ENERGY_SHIELD_HP", target->getScriptValuesRaw()) > 0)
	{
		return done(AIZ_UNKNOWN, "tag_shield_hp");
	}
	for (const BattleItem *hand : { target->getLeftHandWeapon(), target->getRightHandWeapon() })
	{
		if (hand && ai2aTag<RuleItem>(mod, "Tag.ITEM_ENERGY_SHIELD_CAPACITY", hand->getRules()->getScriptValuesRaw()) != 0)
		{
			return done(AIZ_UNKNOWN, "tag_shield_item");
		}
	}
	const std::string resistTag = "Tag.UNIT_RESIST_TYPE_" + std::to_string((int)dt->ResistType);
	if (ai2aTag<BattleUnit>(mod, resistTag.c_str(), target->getScriptValuesRaw()) != 0)
	{
		return done(AIZ_UNKNOWN, "tag_unit_resist");
	}
	for (const RuleItem *r : { wrule, item })
	{
		if (ai2aTag<RuleItem>(mod, "Tag.ITEM_RC_FLAG", r->getScriptValuesRaw()) == 1
			&& ai2aTag<Armor>(mod, "Tag.ARMOR_RC_FLAG", armor->getScriptValuesRaw()) == 1)
		{
			return done(AIZ_UNKNOWN, "tag_remote_control");
		}
		if (ai2aTag<RuleItem>(mod, "Tag.ITEM_SHIELD_BREAKER_FLAG", r->getScriptValuesRaw()) == 1)
		{
			return done(AIZ_UNKNOWN, "tag_shield_breaker");
		}
		if (ai2aTag<RuleItem>(mod, "Tag.ITEM_SETTING_FIRE_FLAG", r->getScriptValuesRaw()) > 0)
		{
			return done(AIZ_UNKNOWN, "tag_setting_fire");
		}
	}

	// BattleUnit::damage with the largest roll
	const float modifier = armor->getDamageModifier(dt->ResistType);
	w << ",\"mod\":" << modifier << ",\"fth\":" << dt->FireThreshold;
	if (modifier < 0.0f)
	{
		return done(AIZ_UNKNOWN, "negative_modifier");
	}
	if (dt->FireThreshold <= 0 && modifier > 0.0f)
	{
		return done(AIZ_UNKNOWN, "fire_at_zero");
	}
	if (power <= 0)
	{
		return done(AIZ_ZERO, "power");
	}
	const int dmax = dt->getRandomDamage(power, 2);
	const int resisted = (int)floor(dmax * modifier); // BattleUnit::reduceByResistance
	w << ",\"D\":" << dmax << ",\"R\":" << resisted;
	if (resisted <= 0)
	{
		return done(AIZ_ZERO, "resistance");
	}
	w << ",\"eff\":" << dt->ArmorEffectiveness << ",\"pre\":" << dt->ToArmorPre;
	if (dt->ArmorEffectiveness <= 0.0f)
	{
		return done(AIZ_POTENTIAL, "ignores_armor");
	}
	if (dt->ToArmorPre < 0.0f)
	{
		return done(AIZ_UNKNOWN, "armor_pre_negative");
	}
	if ((int)std::round(resisted * dt->ToArmorPre) > 0)
	{
		return done(AIZ_POTENTIAL, "armor_wear");
	}
	// the weakest side: the side roll on a diagonal, the direction and a script's side change all stay within these five
	int armorMin = INT_MAX;
	for (UnitSide side : { SIDE_FRONT, SIDE_LEFT, SIDE_RIGHT, SIDE_REAR, SIDE_UNDER })
	{
		armorMin = std::min(armorMin, target->getArmor(side));
	}
	int through = resisted;
	through -= armorMin * dt->ArmorEffectiveness; // the same int -= float as BattleUnit::damage
	w << ",\"amin\":" << armorMin << ",\"left\":" << through;
	if (through > 0)
	{
		return done(AIZ_POTENTIAL, "through_armor");
	}
	return done(AIZ_ZERO, "armor");
}

int AIModule::zeroHonestLast = AIModule::AIZ_UNKNOWN;

/**
 * AI2-A HONEST: the bench flag OXCE_AI_ZERO_HONEST, read once (0 in a release build).
 * 0 off (AI2_BASELINE_B2), 1 shadow (B2 decides, the honest verdict logged beside it), 2 the honest verdict decides.
 */
int AIModule::zeroHonestMode()
{
	static const int mode = (int)AiProbe::param("OXCE_AI_ZERO_HONEST", 0);
	return mode;
}

namespace
{

/// AI2-A HONEST: can an item of this mod raise the damage of this resistance type above the armour's ruleset value?
/// YSCRIPT_ITEMS_OF_RESISTANCE (Yankes_Scripts.rul newTurnItem) sets the unit's tag to res - (res - min) * (100 - coeff) / 100,
/// and YSCRIPT_ITEMS_OF_RESISTANCE_EFFECT multiplies the power by tag / res: only coeff > 100 raises it (with min != 0, the
/// script's switch). Ruleset only, the same for every target; cached per mod.
bool ai2aItemMayRaise(const Mod *mod, int resistType)
{
	static const Mod *cachedMod = nullptr;
	static std::map<int, bool> cache;
	if (cachedMod != mod)
	{
		cachedMod = mod;
		cache.clear();
	}
	auto it = cache.find(resistType);
	if (it != cache.end())
	{
		return it->second;
	}
	const std::string minTag = "Tag.ITEM_MINIMUM_RESIST_TYPE_" + std::to_string(resistType);
	const std::string coeffTag = "Tag.ITEM_RESIST_TYPE_" + std::to_string(resistType);
	bool raise = false;
	for (const std::string &id : mod->getItemsList())
	{
		const RuleItem *r = mod->getItem(id);
		if (r && ai2aTag<RuleItem>(mod, minTag.c_str(), r->getScriptValuesRaw()) != 0
			&& ai2aTag<RuleItem>(mod, coeffTag.c_str(), r->getScriptValuesRaw()) > 100)
		{
			raise = true;
			break;
		}
	}
	cache[resistType] = raise;
	return raise;
}

}

/**
 * AI2-A HONEST: the B2 verdict with nothing hidden read. Allowed inputs: the visible target type (its armour rule, unit rule,
 * special ability), whether it is down or burning, the items in its hands, the ruleset, the attacker's own weapon, ammo and
 * stats. Not read: current armour (soldier bonuses, wear), shield HP, the unit's resistance tags (inventory items), health and
 * stun. Changes against B2: target_out without health; a self-destructing type is UNKNOWN (no out threshold); an armour with a
 * ruleset energy shield is UNKNOWN (no shield HP); no resistance tag - instead a ZERO by resistance needs a modifier of 0 or no
 * item in the mod that raises that type; after the resistance step the armour decides, and the current armour is hidden:
 * UNKNOWN (the ruleset value would be a false ZERO on worn armour, a minimum of 0 cannot prove it).
 */
int AIModule::zeroEffectVerdictHonest(SavedBattleGame *save, BattleUnit *attacker, BattleActionType type, BattleItem *weapon, const BattleUnit *target, std::string *terms, bool full)
{
	std::ostringstream w;
	std::ostringstream h;
	auto done = [&](int v, const char *why)
	{
		if (terms)
		{
			if (full)
			{
				w << ",\"why\":\"" << why << "\",\"hon\":1";
				*terms = w.str();
			}
			else
			{
				*terms = ",\"hv\":" + std::to_string(v) + ",\"hwhy\":\"" + why + "\"" + h.str();
			}
		}
		return v;
	};
	if (!save || !attacker || !weapon || !target)
	{
		return done(AIZ_UNKNOWN, "no_input");
	}
	const Mod *mod = save->getMod();
	const RuleItem *wrule = weapon->getRules();
	w << ",\"w\":\"" << wrule->getType() << "\",\"tgt\":\"" << target->getType() << "\",\"arm\":\"" << target->getArmor()->getType() << "\"";
	if (type != BA_HIT && type != BA_SNAPSHOT && type != BA_AUTOSHOT && type != BA_AIMEDSHOT)
	{
		return done(AIZ_UNKNOWN, "not_direct_action");
	}
	if (target->isOut())
	{
		return done(AIZ_UNKNOWN, "target_out");
	}
	BattleActionAttack attack = BattleActionAttack::GetBeforeShoot(type, attacker, weapon);
	if (!attack.damage_item)
	{
		return done(AIZ_UNKNOWN, "no_damage_item");
	}
	const RuleItem *item = attack.damage_item->getRules();
	w << ",\"di\":\"" << item->getType() << "\",\"bt\":" << (int)item->getBattleType();

	// ExplosionBState::init: which power and damage type the hit uses
	const bool hit = type == BA_HIT;
	const RuleStatBonus *bonus = nullptr;
	const RuleDamageType *dt = nullptr;
	int power = 0;
	float rangeRaw = 0.0f;
	const char *path = "";
	if (hit && item->getBattleType() != BT_MELEE)
	{
		path = "melee_bonus";
		bonus = item->getMeleeBonusRaw();
		power = item->getMeleeBonus(attack);
		dt = item->getMeleeType();
	}
	else
	{
		if (!hit && item->getBattleType() != BT_FIREARM && item->getBattleType() != BT_AMMO)
		{
			return done(AIZ_UNKNOWN, "not_firearm");
		}
		if (wrule->getIgnoreAmmoPower())
		{
			path = "weapon_power";
			bonus = wrule->getDamageBonusRaw();
			power = wrule->getPowerBonus(attack);
			rangeRaw = wrule->getPowerRangeReductionRaw();
		}
		else
		{
			path = hit ? "melee_item" : "ammo_power";
			bonus = item->getDamageBonusRaw();
			power = item->getPowerBonus(attack);
			rangeRaw = item->getPowerRangeReductionRaw();
		}
		dt = item->getDamageType();
		if (!hit && item->getExplosionRadius(attack) != 0)
		{
			return done(AIZ_UNKNOWN, "area");
		}
	}
	w << ",\"path\":\"" << path << "\",\"P\":" << power;
	if (!dt)
	{
		return done(AIZ_UNKNOWN, "no_damage_type");
	}
	w << ",\"rt\":" << (int)dt->ResistType << ",\"rnd\":" << (int)dt->RandomType;
	std::string dyn;
	if (ai2aDynamicBonus(bonus, dyn))
	{
		w << ",\"dyn\":\"" << dyn << "\"";
		return done(AIZ_UNKNOWN, "dynamic_bonus");
	}
	if (rangeRaw < 0.0f)
	{
		return done(AIZ_UNKNOWN, "range_adds_power");
	}

	// what the hit can do besides the damage: spawns, transformation, extinguishing, self-destruct (by type only)
	if (item->getSpawnUnit() || item->getSpawnItem())
	{
		return done(AIZ_UNKNOWN, "spawn");
	}
	const Armor *armor = target->getArmor();
	if (!item->getZombieUnit(target).empty() && !armor->getZombiImmune())
	{
		return done(AIZ_UNKNOWN, "transform");
	}
	if (target->getFire() > 0 && (wrule->isFireExtinguisher() || item->isFireExtinguisher()))
	{
		return done(AIZ_UNKNOWN, "extinguish");
	}
	if (target->getSpecialAbility() == SPECAB_EXPLODEONDEATH || target->getSpecialAbility() == SPECAB_BURN_AND_EXPLODE)
	{
		return done(AIZ_UNKNOWN, "self_destruct_type");
	}

	// scripts: the armour's and the ammo's own must be absent, the globals exactly the audited Piratez set (or none)
	const int evHit = ai2aEvents(armor->getScript<ModScript::HitUnit>());
	const int evDmg = ai2aEvents(armor->getScript<ModScript::DamageUnit>());
	const int evSpec = ai2aEvents(armor->getScript<ModScript::DamageSpecialUnit>());
	const int evAmmo = ai2aEvents(item->getScript<ModScript::HitUnitAmmo>()) + ai2aEvents(item->getScript<ModScript::DamageUnitAmmo>())
		+ ai2aEvents(item->getScript<ModScript::DamageSpecialUnitAmmo>());
	w << ",\"ev\":\"" << evHit << "/" << evDmg << "/" << evSpec << "/" << evAmmo << "\"";
	const bool known = (evHit == 7 && evDmg == 5 && evSpec == 2) || (evHit == 0 && evDmg == 0 && evSpec == 0);
	if (!known || evAmmo != 0)
	{
		return done(AIZ_UNKNOWN, "script_set");
	}
	if (armor->getScript<ModScript::HitUnit>().data() || armor->getScript<ModScript::DamageUnit>().data()
		|| armor->getScript<ModScript::DamageSpecialUnit>().data() || item->getScript<ModScript::HitUnitAmmo>().data()
		|| item->getScript<ModScript::DamageUnitAmmo>().data() || item->getScript<ModScript::DamageSpecialUnitAmmo>().data())
	{
		return done(AIZ_UNKNOWN, "own_script");
	}
	// energy shields: the armour type that carries one (its shield HP is not read) and the shield items in its hands
	if (ai2aTag<Armor>(mod, "Tag.ARMOR_ENERGY_SHIELD_CAPACITY", armor->getScriptValuesRaw()) != 0)
	{
		return done(AIZ_UNKNOWN, "shield_armor");
	}
	for (const BattleItem *hand : { target->getLeftHandWeapon(), target->getRightHandWeapon() })
	{
		if (hand && ai2aTag<RuleItem>(mod, "Tag.ITEM_ENERGY_SHIELD_CAPACITY", hand->getRules()->getScriptValuesRaw()) != 0)
		{
			return done(AIZ_UNKNOWN, "tag_shield_item");
		}
	}
	for (const RuleItem *r : { wrule, item })
	{
		if (ai2aTag<RuleItem>(mod, "Tag.ITEM_RC_FLAG", r->getScriptValuesRaw()) == 1
			&& ai2aTag<Armor>(mod, "Tag.ARMOR_RC_FLAG", armor->getScriptValuesRaw()) == 1)
		{
			return done(AIZ_UNKNOWN, "tag_remote_control");
		}
		if (ai2aTag<RuleItem>(mod, "Tag.ITEM_SHIELD_BREAKER_FLAG", r->getScriptValuesRaw()) == 1)
		{
			return done(AIZ_UNKNOWN, "tag_shield_breaker");
		}
		if (ai2aTag<RuleItem>(mod, "Tag.ITEM_SETTING_FIRE_FLAG", r->getScriptValuesRaw()) > 0)
		{
			return done(AIZ_UNKNOWN, "tag_setting_fire");
		}
	}

	// BattleUnit::damage with the largest roll, the armour's ruleset modifier
	const float modifier = armor->getDamageModifier(dt->ResistType);
	w << ",\"mod\":" << modifier << ",\"fth\":" << dt->FireThreshold;
	if (modifier < 0.0f)
	{
		return done(AIZ_UNKNOWN, "negative_modifier");
	}
	if (dt->FireThreshold <= 0 && modifier > 0.0f)
	{
		return done(AIZ_UNKNOWN, "fire_at_zero");
	}
	if (power <= 0)
	{
		return done(AIZ_ZERO, "power");
	}
	const int dmax = dt->getRandomDamage(power, 2);
	const int resisted = (int)floor(dmax * modifier); // BattleUnit::reduceByResistance
	w << ",\"D\":" << dmax << ",\"R\":" << resisted;
	if (resisted <= 0)
	{
		// a modifier of 0 stays 0 under the item script (it skips a resistance of 0); a positive one is ZERO only when no item
		// of the mod can raise this type
		if (modifier > 0.0f && ai2aItemMayRaise(mod, (int)dt->ResistType))
		{
			h << ",\"hraise\":1";
			w << ",\"raise\":1";
			return done(AIZ_UNKNOWN, "item_resist_may_raise");
		}
		return done(AIZ_ZERO, "resistance");
	}
	w << ",\"eff\":" << dt->ArmorEffectiveness << ",\"pre\":" << dt->ToArmorPre;
	if (dt->ArmorEffectiveness <= 0.0f)
	{
		return done(AIZ_POTENTIAL, "ignores_armor");
	}
	if (dt->ToArmorPre < 0.0f)
	{
		return done(AIZ_UNKNOWN, "armor_pre_negative");
	}
	if ((int)std::round(resisted * dt->ToArmorPre) > 0)
	{
		return done(AIZ_POTENTIAL, "armor_wear");
	}
	// the armour decides: the ruleset values are logged for the record, the current armour (bonuses, wear) is not read
	const int rmin = std::max(0, std::min({ armor->getFrontArmor(), armor->getLeftSideArmor(), armor->getRightSideArmor(), armor->getRearArmor(), armor->getUnderArmor() }));
	w << ",\"rmin\":" << rmin;
	h << ",\"hrmin\":" << rmin;
	return done(AIZ_UNKNOWN, "armor_hidden");
}

/**
 * AI2-A: the verdict the gates use. OXCE_AI_ZERO_HONEST 0: B2. 1: B2 decides, the line also gets the honest verdict ("hv",
 * "hwhy") and the hidden values B2 read ("shp" shield HP, "rtag" resistance tag of the damage type, "hp" health). 2: the honest
 * verdict decides and B2 is not called (nothing hidden is read).
 */
int AIModule::zeroEffectVerdict(SavedBattleGame *save, BattleUnit *attacker, BattleActionType type, BattleItem *weapon, const BattleUnit *target, std::string *terms)
{
	const int hm = zeroHonestMode();
	if (hm <= 0)
	{
		return zeroEffectVerdictB2(save, attacker, type, weapon, target, terms);
	}
	if (hm >= 2)
	{
		zeroHonestLast = zeroEffectVerdictHonest(save, attacker, type, weapon, target, terms, true);
		return zeroHonestLast;
	}
	const int v = zeroEffectVerdictB2(save, attacker, type, weapon, target, terms);
	std::string hterms;
	zeroHonestLast = zeroEffectVerdictHonest(save, attacker, type, weapon, target, terms ? &hterms : nullptr, false);
	if (terms)
	{
		std::ostringstream x;
		x << hterms;
		if (save && target)
		{
			// the hidden state B2 read, for the shadow record only (play is B2's)
			const Mod *mod = save->getMod();
			x << ",\"shp\":" << ai2aTag<BattleUnit>(mod, "Tag.UNIT_ENERGY_SHIELD_HP", target->getScriptValuesRaw()) << ",\"hp\":" << target->getHealth();
			if (weapon)
			{
				BattleActionAttack attack = BattleActionAttack::GetBeforeShoot(type, attacker, weapon);
				const RuleDamageType *dt = nullptr;
				if (attack.damage_item)
				{
					const RuleItem *item = attack.damage_item->getRules();
					dt = (type == BA_HIT && item->getBattleType() != BT_MELEE) ? item->getMeleeType() : item->getDamageType();
				}
				if (dt)
				{
					const std::string resistTag = "Tag.UNIT_RESIST_TYPE_" + std::to_string((int)dt->ResistType);
					x << ",\"rtag\":" << ai2aTag<BattleUnit>(mod, resistTag.c_str(), target->getScriptValuesRaw());
				}
			}
		}
		*terms += x.str();
	}
	return v;
}

/**
 * AI2-A hook: judge one candidate attack, log it, reject it only in mode 2+ and only when proven ZERO.
 */
bool AIModule::zeroEffectReject(const char *site, BattleActionType type, BattleItem *weapon, const BattleUnit *target)
{
	const int mode = zeroEffectMode();
	if (mode < 1)
	{
		return false;
	}
	std::string terms;
	const int v = zeroEffectVerdict(_save, _unit, type, weapon, target, &terms);
	const bool reject = mode >= 2 && v == AIZ_ZERO;
	if (AiProbe::active()) // the bench's line; the player's AI3 (BetterAI) does not write it
	{
		Log(LOG_INFO) << "[AITRACE] {\"ai2a\":\"" << site << "\",\"rec\":" << AiProbe::nextRec() << ",\"turn\":" << _save->getTurn()
			<< ",\"unit\":" << _unit->getId() << ",\"side\":" << (int)_unit->getFaction() << ",\"target\":" << (target ? target->getId() : -1)
			<< ",\"t\":" << (int)type << ",\"tu\":" << _unit->getTimeUnits() << ",\"v\":" << v << ",\"rej\":" << (reject ? 1 : 0) << terms << "}";
	}
	return reject;
}

}
