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

namespace OpenXcom
{

class BattlescapeGame;
class SavedBattleGame;

/**
 * Building collapse pilot (option oxceCollapse, off by default; docs/research/building-collapse-*.md):
 * the two pilot buildings (the barn house and the bunker) are found on the battle map by their
 * terrain parts, and after terrain damage everything the support model no longer holds is removed
 * (no debris part), then gravity on those tiles and the tiles above, then light and sight once,
 * in the order TileEngine::explode uses. Nothing happens with the option off.
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

}

}
