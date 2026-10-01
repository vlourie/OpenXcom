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
#include <SDL.h>

namespace OpenXcom
{

/**
 * HD globe and dogfight: the small outline of a craft or a UFO seen from above, drawn in the
 * world layer where the classic layer has a marker (the globe) or a round blob (the dogfight).
 *
 * The outlines come from the HD mod: hd/OUTLINE/<ruleset type>.png is the plan of the craft's
 * battlescape map (tools/hdart/craft_outline.py), the long axis horizontal and the nose to the
 * right, coverage in the alpha channel; hd/OUTLINE/index.txt lists the types that have one and
 * how much longer than an average craft each is drawn. A type without an outline keeps the
 * classic marker or blob.
 *
 * Pictures only: what is shown, where and when comes from the game (detection, the dogfight's
 * distance and hits); the classic layer is not touched by this file.
 */
namespace HdOutline
{
	/// Is there an outline for this ruleset type? `factor` gets its length relative to an average craft.
	bool has(const std::string &type, float *factor = nullptr);
	/// Draws the outline centred at the world pixel (cx, cy), `length` world pixels along the hull, the
	/// nose at `angle` radians on the screen (0 = right, growing clockwise since y points down), in
	/// 0xRRGGBB. `phase` (radians) moves the light that runs around the hull; `reveal` (0..1) draws it
	/// stroke by stroke when it first appears; `strength` dims a wreck (0.75 on the globe). Clipped by HdUi's clip.
	void draw(const std::string &type, float cx, float cy, float length, float angle, Uint32 color, float phase, float reveal = 1.0f, float strength = 1.0f);
	/// The colour of a UFO crew's race: a hue picked from the race's name, never the player's blue.
	Uint32 raceColor(const std::string &race);
	/// The colour of the player's own craft.
	const Uint32 OWN_COLOR = 0x78E6FF;
	/// Forgets the loaded outlines (the mods were reloaded).
	void clear();
}

}
