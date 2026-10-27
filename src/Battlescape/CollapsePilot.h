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

#include <map>
#include <vector>

namespace OpenXcom
{

class BattlescapeGame;
class MapData;
class Position;
class RuleDamageType;
class SavedBattleGame;
class Tile;

/**
 * Building collapse pilot (option oxceCollapse, off by default; docs/research/building-collapse-*.md):
 * the two pilot buildings (the barn house and the bunker) are found on the battle map by their
 * terrain parts, and after terrain damage everything the support model no longer holds is removed
 * (no debris part), then gravity on those tiles and the tiles above, then light and sight once,
 * in the order TileEngine::explode uses. Nothing happens with the option off (in OXCE_AI_DEV builds the
 * debug stand still damages the map then, as the control without the model).
 */
namespace CollapsePilot
{

/// Settles the pilot buildings after terrain changed (an explosion or a hit ended, a turn ended).
/// Returns true if any part fell.
bool settle(BattlescapeGame *battle, const char *why);

/// The map was just made (BattlescapeGenerator::run, nextStage): finds the whole pilot buildings before
/// anything can damage them and keeps the list in the battle save.
void scanNew(SavedBattleGame *save);

/// A battle starts or is loaded: takes the building list from the save (checked against this build),
/// or, for a save without one, looks for the buildings that are still whole.
void begin(SavedBattleGame *save);

/// The units stopped falling (UnitFallBState): the debug stand (OXCE_AI_DEV builds) reports its units and their
/// things once, at that moment (a unit knocked out below is not yet unconscious there).
void afterFall(BattlescapeGame *battle);

/// The state stack is empty (BattlescapeGame::think): after a reported fall the debug stand reports again and,
/// with OXCE_COLLAPSE_FALL_SAVE, saves the game - the first moment a player could save, before the next side moves.
void idle(SavedBattleGame *save);

/// The aim hint (HD blast area): the cells of the parts the player has seen that the model may let fall if an
/// explosion of this type, reaching each tile with its strongest power, destroyed all it can at the top of its
/// damage. Reads the map, rolls nothing; empty with the option off.
void mayFall(SavedBattleGame *save, const std::map<Tile*, int> &strongest, const RuleDamageType *type, std::vector<Position> &cells);

/// What broke a map part: a shot (TileEngine::hit), an explosion (TileEngine::detonate), a melee hit.
enum TrunkHit { TRUNK_SHOT, TRUNK_BLAST, TRUNK_MELEE };

/// The armor this hit must reach to break the record (Options::oxceHdTrunkArmor): a tree trunk of the table is harder
/// with the collapse on (x2, x3, or mixed by the hit), everything else - and everything with the option off - its own armor.
int trunkArmor(const MapData *md, TrunkHit hit);

}

}
