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
 * The lights follow the craft's state, every light in the state's colour and rhythm:
 * ready - green blinking; under repair - red, an even pulse; rearming - red, two short
 * flashes and a pause; not enough pilots aboard - red, the port and starboard sides in
 * turn; refuelling (and anything else) - only the beacons. The fuel is shown apart, by a
 * garland of five bulbs in the hangar (drawFuel).
 *
 * Drawn only in the true-color world layer; the classic frame never changes.
 */
class Craft;

namespace HdCraftLights
{
	enum Status { READY, BUSY, REPAIRS, REARMING, NO_CREW };
	/// The state the lights show. Reads the craft only: counts the soldiers aboard able to
	/// pilot it, never assigns pilots as Craft::arePilotsOnboard does.
	Status statusOf(const Craft *craft);
	/// Does the frame have lights?
	bool has(int index);
	/// Draws the lights of the frame whose top-left corner is at (x, y) of the world layer.
	/// `seed` shifts the rhythm, so that two hangars do not blink together.
	void draw(SDL_Surface *world, int index, int x, int y, int k, Status status, Uint32 seed, Uint32 ticks);
	/// Draws the fuel garland: five bulbs centred on (x, y) of the world layer. Up to 25% one
	/// red, up to 50% two orange, up to 75% three yellow, below 100% four green; full - all
	/// five, green and gold in turn.
	void drawFuel(SDL_Surface *world, int x, int y, int k, int percent, Uint32 seed, Uint32 ticks);
	/// Forgets everything (mod reload). `masterOffset` is where the game puts the master mod's
	/// frames (ModData::offset of the master): the files are named in the master's own numbering.
	void clear(int masterOffset);
}

}
