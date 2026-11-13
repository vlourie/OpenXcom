#pragma once
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

namespace OpenXcom
{

class SavedBattleGame;
class BattleUnit;
class Node;
struct BattleAction;

/**
 * HIVE COMMAND CORE V0 (bench, OXCE_AI_HIVE: 0 off, 1 shadow, 2 active): one headquarters over the side's units. It keeps sectors,
 * squads with real commanders, a memory of contacts between turns and an order for each unit. It only ever answers one question
 * inside the unit's own think: where does a patrol go. Combat, ambush, escape and panic stay the unit's. No dice, no free action,
 * no knowledge of a player unit that no living unit of the side has in sight. See docs/research/ai-mechanics/HIVE_COMMAND_ARCHITECTURE.md
 */
namespace HiveCommand
{

enum PatrolOrder { PO_NONE, PO_HOLD, PO_GO };

/// The flag: 0 off, 1 shadow, 2 active.
int mode();
/// Before the unit's think: the first of a battle initializes, the first of a side's turn plans it, every one takes what this unit sees.
void beforeThink(SavedBattleGame *save, BattleUnit *unit);
/// Inside setupPatrol: the order of this unit. PO_GO gives the node, PO_HOLD ends its selection where it stands, PO_NONE leaves the free choice.
PatrolOrder patrol(SavedBattleGame *save, BattleUnit *unit, Node *&node);
/// After the unit's think: what it really decided, against its order.
void decided(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action);
/// At the end of any side's turn: closes the side's turn of orders.
void sideEnds(SavedBattleGame *save);

}

}
