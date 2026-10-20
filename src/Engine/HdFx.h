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
struct DotStyle;
class RuleItem;
class BattleUnit;
class Tile;
class MapData;

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
 * hd/FX/weapons.txt (tools/hdart/fx_map.py): "flash|hit|swing <item> <kind>", "tracer <item> <options>".
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
	/// The clip for the muzzle flash of `weapon` firing `ammo` facing `direction` (empty: the weapon has no muzzle flash).
	std::string flashClip(const RuleItem *weapon, const RuleItem *ammo, int direction);
	/// How the tracer of `item` is drawn in HD, if hd/FX/weapons.txt says ("tracer <item> <options>").
	bool tracerStyle(const RuleItem *item, DotStyle &style);
	/// Replaces "%c" in a clip name with the colour of a classic frame (palette: the map's).
	std::string colour(const std::string &clip, SurfaceRaw<const Uint8> frame, const SDL_Color *palette);
	/// Frame `step` of `steps` of a clip at scale k (nullptr: the mod has no such clip).
	const HdFrame *frame(const std::string &clip, int step, int steps, int k);

	/// A muzzle flash (or the dust of a collapse) on its own clock.
	struct Live
	{
		std::string clip;
		Position voxel;
		Uint32 start;           ///< may be ahead of now: not drawn yet
		int item;               ///< the weapon fired (BattleItem id), -1: none
		bool tip;               ///< the weapon was drawn this frame: the flash goes to its muzzle
		int tipX, tipY;         ///< that muzzle on the map surface
		Uint32 ms = 0;          ///< how long it runs (0: a muzzle flash)
	};
	/// Starts a muzzle flash at a voxel; `item` - the weapon fired, its drawn muzzle is used when seen.
	void spawn(const std::string &clip, Position voxel, int item = -1);
	/// A new map frame: the muzzles drawn last frame are forgotten.
	void clearTips();
	/// Does a running flash wait for the muzzle of weapon `item`?
	bool wantsTip(int item);
	/// The muzzle of weapon `item` (its hand frame `frame` as drawn - already k times the classic one -
	/// facing `direction`, its corner at x, y on the map surface), for the flashes it fired.
	void noteTip(int item, const Surface *frame, int direction, int x, int y);
	/// A part of a building that fell in a collapse (CollapsePilot::settle), on its own clock: its picture as last
	/// drawn goes down from its cell to the floor it lands on.
	struct Piece
	{
		SurfaceRaw<const Uint8> sprite;
		Position cell;          ///< where it stood
		int part;               ///< its TilePart
		int yOffset;            ///< its terrain offset (Tile::getYOffset), classic pixels
		int levels;             ///< levels down to the floor it lands on (0: it crumbles where it stood)
		Uint32 start;
	};
	/// Starts a falling piece; returns in how many ms it lands.
	Uint32 fall(SurfaceRaw<const Uint8> sprite, Position cell, int part, int yOffset, int levels);
	/// The pieces still falling at `now`, each with how far it has come down (classic pixels); the landed ones are dropped.
	void falling(Uint32 now, std::vector<std::pair<const Piece*, int>> &out);
	/// The dust of a collapse on the floor of `cell`, `delay` ms from now: 'A' a part crumbled where it stood,
	/// 'B' a floor or several parts came down there, 'C' one piece fell from above; `what` (what fell) gives the material.
	void dust(char kind, Position cell, const MapData *what, Uint32 delay);
	/// What a terrain part is made of, as its dust shows it: "stone", "wood", "metal", "dirt"... The collapse rubble
	/// picks its record by it too (CollapsePilot) - a change here changes the battle, not only the picture.
	const char *partMaterial(const MapData *data);
	/// Is any flash, piece or dust still running at `now` (the finished ones are dropped)?
	bool active(Uint32 now);
	/// The flashes still running at `now`, with the frame of each (the finished ones are dropped).
	void running(Uint32 now, int k, std::vector<std::pair<const Live*, const HdFrame*>> &out);
	/// Headless checks: with OXCE_HD_DUMP_FX=<prefix> the first effects started ask for a dump of the frame showing them
	/// (`after` ms from now).
	void noteForTest(const std::string &clip, Uint32 after = 50);
	/// The dump file due at `now` for a noted effect, or empty.
	std::string takeTestDump(Uint32 now);
	/// Drops loaded clips not drawn for a while. Call before a frame is recorded, never during one.
	void trim();
	/// Forgets everything (mod reload).
	void clear();
}

}
