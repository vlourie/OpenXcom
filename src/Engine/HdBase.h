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
#include "HdSprites.h"

namespace OpenXcom
{

/**
 * HD pictures of the base view's facilities, with animation.
 *
 * A mod ships `hd/BASEBITS.PCK/<frame index>.png` - the picture of that tile of
 * the base screen (the facility's shape and graphic together), a whole number of
 * times bigger than the classic 32x40 tile. An animated tile adds `<frame index>.anim.txt`:
 *
 *     size 128 128          the size of the picture
 *     loop 24 20 80 64      the pieces `.v1.png`, `.v2.png` ... lie there: a loop that never stops (water)
 *     burst 8 8 112 112     the pieces `.b1.png`, `.b2.png` ... lie there: played once every
 *     every 45              45 seconds, over the loop (lights, smoke)
 *
 * Then `<frame index>.png` is the still picture, seen with the animations off and between the
 * bursts. Without `.anim.txt` (an older pack) the phases are `<frame index>.png`, `.v1.png` ...
 * as whole pictures, in a loop. tools/hdart/base_pack.py writes the pack.
 *
 * A tile with such a picture is not drawn on the classic layer at all: the
 * picture goes into the true-color world layer instead, so it is shown in the
 * display's resolution, and everything the base view draws on top (connectors,
 * craft, the selector, numbers) keeps drawing classically over it.
 *
 * The pictures are read when first drawn and kept within a memory budget.
 */
namespace HdBase
{
	/// Number of pictures of a base tile (0 = no picture, 1 = a still picture).
	int phases(int index);
	/// The whole picture of a base tile at `scale` times the classic `baseWidth` x `baseHeight`, or nullptr:
	/// a phase of an older pack's loop, else the still picture.
	const HdFrame *frame(int index, int phase, int scale, int baseWidth, int baseHeight);
	/// Draws a base tile at (x, y) of `dest` as it is at `ms` of the display clock (SDL_GetTicks, never
	/// the game's), with its animations when `animate`; `seed` staggers the bursts of the facilities.
	/// @return The ms when the picture changes next (0xFFFFFFFF: never).
	Uint32 draw(SDL_Surface *dest, int index, int x, int y, int scale, int baseWidth, int baseHeight,
		bool animate, Uint32 ms, Uint32 seed);
	/// A tile a base screen is about to draw.
	struct Want
	{
		int index, baseWidth, baseHeight;
	};
	/// Reads every phase of these tiles not read yet, decoding across HdWorkers: a base opens
	/// with one short pause instead of a stall on each phase met for the first time.
	/// Without `allPhases` only the first phase is read (the animations are switched off).
	void preload(const std::vector<Want> &want, int scale, bool allPhases);
	/// Has the pack animated tiles (a loop or a burst)?
	bool animated();
	/// Forgets everything (mod reload). `masterOffset` is where the game puts the master mod's
	/// frames (ModData::offset of the master): the files are named in the master's own numbering.
	void clear(int masterOffset);
}

}
