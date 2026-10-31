#pragma once
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
#include <cstdint>
#include <string>
#include <vector>
#include "Position.h"

namespace OpenXcom
{

class SavedBattleGame;
class BattleUnit;
struct BattleAction;

/**
 * The actions a unit could take at the moment it decides (docs/research/ai-arena-v2-plan.md, 3.2): one list for the
 * bot, the shadow rules, the branches and the recording of a human's turns, so a choice is always stored next to what
 * it was chosen from. Reads the battle only: no random numbers, no time units spent. It does reset the pathfinding
 * nodes (findReachable), so it runs before the unit thinks, never between a decision and its action.
 */
namespace AiCandidates
{

/// Kind of a candidate: move, attack (shot, blow, throw, psi), kneel or stand, turn, end the unit's actions, think again.
/// MOVE_TO_AI_POINT is never a candidate: the kind of a chosen walk to a tile the AI picked out of this turn's reach.
enum Kind : char { MOVE = 'm', ATTACK = 'a', KNEEL = 'k', TURN = 't', END = 'e', RETHINK = 'r', MOVE_TO_AI_POINT = 'M', OTHER = 'x' };

struct Candidate
{
	uint64_t id = 0;        ///< stable action id: kind, actor, action type, tile, weapon type
	Kind kind = OTHER;
	int type = 0;           ///< BattleActionType
	Position tile;          ///< where to go, what to hit, the tile to face
	int target = -1;        ///< the unit on that tile for an attack
	std::string weapon;     ///< item type for an attack
	int tu = 0;             ///< time units it costs
	int chance = -1;        ///< attack: the engine's accuracy, per cent
	int lof = -1;           ///< attack: 1 line of fire, a valid throw or melee reach, 0 not
	int dist = -1;          ///< attack: distance in tiles
};

struct Set
{
	std::vector<Candidate> acts;    ///< everything but the moves, in generation order
	std::vector<Candidate> moves;   ///< every reachable tile with its cost, in the pathfinder's order, then tu -1: nodes and known enemies out of reach
	std::vector<Position> far;      ///< where it may head beyond this turn's reach, as generate saw it: the map's nodes, then the enemies it knows of
	int actor = 0;                  ///< the unit's id, for the ids of the moves
	Position at;                    ///< the unit's tile: not a move
	uint64_t setHash = 0;           ///< over the sorted action ids: are the candidates the same?
	uint64_t orderHash = 0;         ///< over the ids in generation order: are they walked in the same order?
	uint64_t movesHash = 0;         ///< the move list alone: the id it is stored under once per battle
	int count() const { return (int)(acts.size() + moves.size()); }
};

/// The tiles a unit can walk to this turn with the cost of getting there, in the pathfinder's order (findReachable, reachedTU).
using Reach = std::vector<std::pair<int, int>>;

/// Every action the unit could start now. Without the moves the set is not complete until addMoves: the record takes the
/// reach the game computes when the unit thinks (OXCE_AI_RECORD_REUSE) instead of asking the pathfinder once more here.
Set generate(SavedBattleGame *save, BattleUnit *unit, bool withMoves = true);
/// The unit's reach as generate asks for it itself.
Reach reach(SavedBattleGame *save, const BattleUnit *unit);
/// The moves of a set generated without them: the reach, then what is far, then the hashes.
void addMoves(SavedBattleGame *save, Set &set, const Reach &reach);
/// The stable id of a candidate.
uint64_t actionId(Kind kind, int actor, int type, Position tile, const std::string &weapon);
/// The id of an action that was chosen, in the same terms as the candidates; kind OTHER if no candidate matches its type.
uint64_t chosenId(SavedBattleGame *save, const BattleUnit *unit, const BattleAction &action, Kind *kind = nullptr);

}

}
