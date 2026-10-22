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
#include <istream>
#include <vector>
#include <SDL.h>

namespace OpenXcom
{

/**
 * The light of the "living base" (docs/research/base-living-2026-10-22.md, 7a): the lamps, screens
 * and fires of the HD facility pictures, and the night of the base's own longitude.
 *
 * A tile of the pack may come with `<frame index>.scene.txt` (tools/hdart/base_scene_pack.py):
 *
 *     size 128 128                   the size of the tile's picture in the pack
 *     gate lab                       what the lights go by: lab (research), work (production),
 *                                    home (its steady lamps go out at night), none
 *     light 61.5 40.2 38.0 screen 0.45 0.85 1.00 1.70 0.31
 *                                    x y (pack pixels from the tile's corner), radius, kind (steady,
 *                                    blink, pulse, screen, flicker), colour 0..1, period s and phase 0..1
 *     emit steam 20 26 70 70 0.95 0.95 1.00
 *                                    particles: kind (steam, bubbles, sparks, embers, orbit, sweep - a
 *                                    radar or turret beam turning about the box's middle, ripple - rings
 *                                    on water, dust - motes drifting in the light, flies - dark specks
 *                                    buzzing about), the box they start in (x y w h, pack pixels from the
 *                                    tile's corner), colour
 *     walk 8 0011110001111110...     where the crew may stand: n x n squares of the tile, row by row,
 *                                    1 - bare floor (tools/hdart/base_scene_pack.py walk_mask)
 *
 * Only the picture changes: the light is drawn over the world layer from the display clock, the
 * game's state is only read (the time of day, whether the base researches and builds).
 */
namespace HdBaseScene
{
	enum Kind { STEADY, BLINK, PULSE, SCREEN, FLICKER };
	enum Gate { GATE_NONE, GATE_LAB, GATE_WORK, GATE_HOME };

	struct Light
	{
		float x = 0, y = 0, radius = 0;  ///< pack pixels from the tile's corner
		Kind kind = STEADY;
		float r = 1, g = 1, b = 1;
		float period = 0, phase = 0;      ///< seconds and 0..1, blink and pulse
	};

	enum EmitKind { STEAM, BUBBLES, SPARKS, EMBERS, ORBIT, SWEEP, RIPPLE, DUST, FLIES };

	struct Emit
	{
		EmitKind kind = STEAM;
		float x = 0, y = 0, w = 0, h = 0; ///< the box the particles start in, pack pixels from the tile's corner
		float r = 1, g = 1, b = 1;
	};

	struct TileScene
	{
		int width = 128, height = 128;    ///< the tile's picture in the pack
		Gate gate = GATE_NONE;
		std::vector<Light> lights;
		std::vector<Emit> emits;
		int walkSize = 0;                 ///< n of the walk grid; 0 - none given, the whole tile is floor
		std::vector<unsigned char> walk;  ///< n x n, row by row: 1 - the crew may stand there
	};

	/// Reads a `.scene.txt`; false when it holds nothing usable.
	bool parse(std::istream &in, TileScene &out);

	/// A light where it is on the world layer.
	struct Placed
	{
		Light light;                      ///< x, y, radius in world pixels
		float scale = 1;                  ///< world pixels per pack pixel (the lamp's height and halo)
		float level = 1;                  ///< from the gate: 1 at work, less when the facility idles
		bool home = false;                ///< a steady lamp of living quarters: out at night
		Uint32 seed = 0;                  ///< staggers the flicker
	};

	/// How dark it is at the base: 0 day, 1 night, from the time of day at its longitude (radians, east).
	/// OXCE_HD_BASE_NIGHT=0..1 sets it for a test.
	float nightAt(double longitude, int hour, int minute, int second);

	/// Lights `area` of the world layer as it is at `ms` of the display clock (SDL_GetTicks): the pictures
	/// under the ambient light of `night` and the lamps, their halo over them. Runs in bands on HdWorkers.
	void draw(SDL_Surface *world, const SDL_Rect &area, const std::vector<Placed> &lights, float night, Uint32 ms);

	/// Particles where they are on the world layer.
	struct PlacedEmit
	{
		Emit emit;                        ///< the box in world pixels
		float scale = 1;                  ///< world pixels per pack pixel
		float level = 1;                  ///< from the gate: sparks fly only where the facility works
		Uint32 seed = 0;
	};

	/// Steam, bubbles, sparks and embers over the lit `area` at `ms` of the display clock: every particle
	/// is a function of the time and its number, nothing is kept from frame to frame.
	void drawParticles(SDL_Surface *world, const SDL_Rect &area, const std::vector<PlacedEmit> &emits, float night, Uint32 ms);

	/// A facility being built, over its picture already in `rect` of the world layer: a glowing blueprint
	/// with scaffolding, and the picture coming through it by `progress` (0..1, the share of the build time
	/// gone by) with a hot welding edge where it grows. Before the light, like the picture itself.
	void drawBuilding(SDL_Surface *world, const SDL_Rect &rect, float progress, float scale, Uint32 seed, Uint32 ms);
}

}
