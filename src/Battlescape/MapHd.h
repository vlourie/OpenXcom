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

/// How strong the shadows of units are at the battle's global shade (0 day .. 15 night), 0..UNIT_SHADOW_STEPS: full up to
/// shade 4, then weaker by a step per shade and none from shade 10 on (no sun at night, ticket XP-000447). Whole steps, so
/// the cached frames come in a few strengths only.
const int UNIT_SHADOW_STEPS = 6;
inline int unitShadowStrength(int globalShade)
{
	return std::max(0, std::min(UNIT_SHADOW_STEPS, 10 - globalShade));
}

/// HD: the soft shadow under a unit (defined in MapShadows.cpp).
const HdFrame &unitShadow(int size, int part, int k, int strength);

class Mod;
struct BattleAction;

/// The palette group of the aiming reticle by the weapon's damage type (defined in MapAim.cpp).
int reticleColorGroup(const Mod *mod, BattleAction *action, const SDL_Color *pal);

/// Dents in snow (Options::oxceHdSnowTracks, XP-000563): the flag in a print's `kind` (the look itself is HdFx::Track), how many turns they last (always three,
/// not Options::oxceHdBloodStepsLife), the caps of the snow's own store (a tile, the map), the cold grey-blue of the dent, the edge softer than the blood's (times),
/// and the share of the print's opacity.
const int HD_STEP_SNOW = 16, HD_SNOW_LIFE = 3, HD_SNOW_PER_TILE = 4, HD_SNOW_MAX = 900, HD_SNOW_RGB = 0x4A5570, HD_SNOW_LIGHT = 170, HD_SNOW_SPREAD = 45;
const double HD_SNOW_SOFT = 1.8, HD_SNOW_ALPHA = 1.0;

/// Bloody footprints: turns a print lasts by the setting, the age tier of a print (defined in MapSteps.cpp).
int hdStepLife();
int hdStepTier(int age);

}
