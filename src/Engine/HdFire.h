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
 * HD render (option oxceHdVolumeFire, docs/research/hd-volume-fire-2026-10-30.md): the fire of a tile as tongues
 * of flame in the pack's painted style instead of the pack's four frames. A tongue is a frame of a bank baked once
 * per scale: a curling flame with the pack's gradient from its edge (dark red) to its heart (bright yellow), the
 * base yellow and the tip red; over its life it shoots up, its curl runs upwards, its tip pinches off as a red
 * wisp and it shrinks away. A tile keeps a few slots on the ellipse of its floor; every life of a slot takes a new
 * place, shape, size and side, so no two tiles and no two moments are the same.
 *
 * Pictures only: everything comes from hashes of the tile's position and the clock of the map's animation,
 * never from the game's random numbers.
 */
namespace HdFire
{
	/// Shapes of a tongue, its sizes (small, middle, tall) and the frames of its life.
	const int SHAPES = 8;
	const int SIZES = 3;
	const int LIFE = 12;
	/// Slots of a burning tile.
	const int SLOTS = 26;
	/// The frame a tongue is baked in at scale 1, pixels, and the row of its base from the frame's top.
	const int WIDTH = 26;
	const int HEIGHT = 36;
	const int BASE = HEIGHT - 7;

	/// One tongue of a tile.
	struct Tongue
	{
		/// The base, pixels at the scale from the top left of the tile's sprite (32 x 40 at scale 1).
		float x, y;
		int shape, size, life;
		bool mirror;
	};

	/// A frame of the bank: cut to its pixels, `dx`, `dy` from the top left of the WIDTH x HEIGHT frame.
	struct Sprite
	{
		const HdFrame *frame;
		int dx, dy;
	};

	/// Bakes the frame `life` of the tongue (shape, size) at scale k into out: (WIDTH * k) x (HEIGHT * k) pixels
	/// 0xAARRGGBB, straight alpha.
	void bake(int k, int shape, int size, int life, Uint32 *out);
	/// The frame (shape, size, life, mirrored) of the bank at scale k; the bank is baked on the HD workers on first
	/// use and stays for the run (the frames never move).
	Sprite frame(int k, int shape, int size, int life, bool mirror);
	/// Milliseconds the banks baked so far took (the battle's log line).
	int bakeMs();
	/// Appends the tongues of the burning tile (x, y, z) at the clock `clock` (Map::hdEnviClock ticks), at scale k,
	/// drawn back to front.
	void tongues(int x, int y, int z, int k, int clock, std::vector<Tongue> &out);
}

}
