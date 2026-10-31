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
#include <vector>
#include <SDL.h>

namespace OpenXcom
{

struct HdFrame;

/**
 * HD render (option oxceHdVolumeSmoke, docs/research/hd-volume-smoke-2026-10-30.md): the smoke of a tile as puffs
 * instead of the pack's flat frame. A puff is a frame of a bank baked once per scale by marching rays through a
 * volume (a ball of fractal noise, lit from above through its own density); a tile keeps a few puffs that are born
 * at their own place, rise, grow and melt away, each lit by the tile's light field where it floats.
 *
 * Pictures only: everything comes from hashes of the tile's position and the clock of the map's animation,
 * never from the game's random numbers.
 */
namespace HdSmoke
{
	/// Kinds of puffs: the smoke of a thin and of a thick cloud, the soot rising over a fire.
	enum Kind { THIN, THICK, SOOT, KINDS };
	/// Shapes of every kind, and frames of a puff's life (born, grown, melted away).
	const int SHAPES = 3;
	const int LIFE = 24;
	/// Side of a puff frame at scale 1, pixels.
	const int SIDE = 32;

	/// One puff of a tile.
	struct Puff
	{
		/// Place over the tile's floor diamond, 0..1 along the view's columns (u) and rows (v).
		float u, v;
		/// Height over the floor, voxels.
		float h;
		int kind, shape, life;
	};

	/// Bakes the frame `life` of the puff (kind, shape) at scale k into out: (SIDE * k)^2 pixels 0xAARRGGBB,
	/// straight alpha.
	void bake(int k, int kind, int shape, int life, Uint32 *out);
	/// The frame (kind, shape, life) of the bank at scale k; the bank is baked on the HD workers on first use and
	/// stays for the run (the frames never move).
	const HdFrame &frame(int k, int kind, int shape, int life);
	/// Milliseconds the banks baked so far took (the battle's log line).
	int bakeMs();
	/// Appends the puffs of tile (x, y, z) at the clock `clock` (Map::hdEnviClock ticks), drawn back to front.
	/// @param smoke Tile::getSmoke (the number of slots and the kind of a cloud).
	/// @param fire The tile burns: soot rises over the flames instead.
	void puffs(int x, int y, int z, int smoke, bool fire, int clock, std::vector<Puff> &out);
}

}
