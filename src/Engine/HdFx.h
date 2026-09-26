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
#include <string>
#include <vector>
#include <SDL.h>
#include "Surface.h"
#include "../Battlescape/Position.h"

namespace OpenXcom
{

struct HdFrame;
class RuleItem;
class BattleUnit;
class Tile;

/**
 * HD render: the combat effects of the HD mod (tools/hdart/gen_combat_fx.py) - hits by calibre,
 * target and ground material, melee swings, muzzle flashes, explosions.
 *
 * Pictures only. A clip is chosen when the classic animation starts and drawn in its place,
 * frame for frame by progress, so it lasts exactly as long; the game's timing, damage and
 * random numbers are untouched. The muzzle flash is the one new moment: it lives on its own
 * clock and is drawn only in the HD modes, for a shooter the player can see.
 *
 * Mod layout: hd/FX/<clip>/<i>.png (RGBA 4x, the point of impact in the middle),
 * hd/FX/weapons.txt (tools/hdart/fx_map.py): "flash|hit|swing <item> <kind>".
 * A clip name may hold "%c": the colour, taken from the classic frame it replaces.
 */
namespace HdFx
{
	/// The clip for a bullet or beam hit (onUnit: it landed on `target`; armorHeld: the unit lost nothing).
	std::string hitClip(const RuleItem *damageItem, bool onUnit, const BattleUnit *target, bool armorHeld, const Tile *tile, int voxelZ);
	/// The clip for an explosion.
	std::string boomClip(const RuleItem *damageItem);
	/// The clip for a melee swing of `weapon` (dealing `damage`) by a unit facing `direction`.
	std::string swingClip(const RuleItem *weapon, const RuleItem *damage, int direction);
	/// The clip for the muzzle flash of `weapon` firing `ammo` facing `direction`.
	std::string flashClip(const RuleItem *weapon, const RuleItem *ammo, int direction);
	/// Replaces "%c" in a clip name with the colour of a classic frame (palette: the map's).
	std::string colour(const std::string &clip, SurfaceRaw<const Uint8> frame, const SDL_Color *palette);
	/// Frame `step` of `steps` of a clip at scale k (nullptr: the mod has no such clip).
	const HdFrame *frame(const std::string &clip, int step, int steps, int k);

	/// A muzzle flash on its own clock.
	struct Live
	{
		std::string clip;
		Position voxel;
		Uint32 start;
	};
	/// Starts a muzzle flash at a voxel.
	void spawn(const std::string &clip, Position voxel);
	/// Is any flash running (or finished and not yet drawn away)?
	bool active();
	/// The flashes still running at `now`, with the frame of each (the finished ones are dropped).
	void running(Uint32 now, int k, std::vector<std::pair<const Live*, const HdFrame*>> &out);
	/// Drops loaded clips not drawn for a while. Call before a frame is recorded, never during one.
	void trim();
	/// Forgets everything (mod reload).
	void clear();
}

}
