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
#include <SDL.h>

namespace OpenXcom
{

/**
 * Blinking lights of the craft standing in a hangar of the base view.
 *
 * A mod ships `hd/BASEBITS.PCK/<frame index>.lights.txt` next to the HD pictures of
 * the base: the frame is the craft's picture in the hangar (its sprite + 33, or its
 * skin's), in the master mod's own numbering - the game's frame without the master's
 * offset of 1000 is looked up too. One light per line, in pixels of the classic frame
 * (pixel centres at .5):
 *
 *     # x    y    kind    [period s]  [offset s]
 *     3.5   21.0  red                           left wing tip, steady
 *     28.5  21.0  green                         right wing tip, steady
 *     16.0  34.0  strobe                        white double flash
 *     16.0  12.0  beacon  1.2                   slow red pulse
 *     10.5  26.0  blink   #ffc0a0               a light already painted on the craft
 *
 * Kinds: red, green, white (steady), strobe (white double flash), beacon (red pulse),
 * blink (pulse like a beacon, white unless coloured). Any light may carry its own
 * colour "#rrggbb" before the period.
 * The lights follow the craft's state: all of them when it is ready, only the
 * beacons while refuelling or rearming, amber quick beacons under repair.
 *
 * Drawn only in the true-color world layer; the classic frame never changes.
 */
namespace HdCraftLights
{
	enum Status { READY, BUSY, REPAIRS };
	/// Does the frame have lights?
	bool has(int index);
	/// Draws the lights of the frame whose top-left corner is at (x, y) of the world layer.
	/// `seed` shifts the rhythm, so that two hangars do not blink together.
	void draw(SDL_Surface *world, int index, int x, int y, int k, Status status, Uint32 seed, Uint32 ticks);
	/// Forgets everything (mod reload).
	void clear();
}

}
