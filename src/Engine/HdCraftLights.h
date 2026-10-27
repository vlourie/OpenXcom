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
 *     3.5   21.0  red                           left (port) wing tip, steady
 *     28.5  21.0  green                         right (starboard) wing tip, steady
 *     16.0  34.0  white                         tail, steady
 *     16.0  12.0  beacon  1.2                   red anticollision beacon
 *     10.5  26.0  red     #ff0a00               a light already painted on the craft
 *
 * The aviation rules (14 CFR 25.1385-25.1401, ICAO Annex 2 3.2.3; see
 * docs/research/craft-lights-aviation-2026-10-27.md): position lights red on the port side,
 * green on the starboard side, white at the tail, steady; the anticollision beacon red, 40 to 100
 * flashes a minute, on while the engines run or are about to start; strobes are off on the ground.
 * Kinds: red, green, white (position lights), beacon (red flash), blink (a flash, white unless
 * coloured), strobe (never lit in a hangar). Any light may carry its own colour "#rrggbb" before
 * the period: it then pulls the pixels toward that colour instead of adding to them (a light
 * painted on the craft). The sides are the craft's own: a craft standing across the hangar
 * ("sideways left|right" in the file, where its nose points) has them up and down in the picture.
 * The craft's state picks which lights burn, never their colour: ready - the position lights
 * and the beacon (engines to start); repairs, rearming, refuelling and the rest - the position
 * lights only (people around the craft, no beacon); not enough pilots aboard - dark. The fuel is
 * shown apart, by a garland of five bulbs in the hangar (drawFuel).
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
