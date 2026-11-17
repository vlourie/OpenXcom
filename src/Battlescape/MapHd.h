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

/// What the files of the Map's HD drawing share (Map.cpp, MapWeather.cpp): defined in Map.cpp.

/// HD: true when the battle is on an orbital map (no sun there: no HD shadows, no weather).
bool hdOrbitalMap(const SavedBattleGame *save);

/// The shade of the corners on the floor (Map::hdFloorAo): the opacity of the darkest level, the levels of the grid,
/// the share of the own object's lower voxels above which the floor is not seen, the voxels above a plate below which what
/// stands on it is thin (Map::hdAoShape), the most looks kept for a battle.
const int FLOOR_AO_ALPHA = 135;
const int FLOOR_AO_LEVELS = 16;
const int FLOOR_AO_HIDDEN = 230;
const int FLOOR_AO_THIN = 64;
const size_t FLOOR_AO_MAX_FRAMES = 2048;

/// HD: the floor diamond of a tile in one colour (defined in MapEdge.cpp).
void fillDiamond(HdFrame &f, Uint32 rgb, int alpha, int k);

}
