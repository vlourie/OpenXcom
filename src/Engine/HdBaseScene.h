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
#include "HdSprites.h"

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
 *                                    blink, pulse, screen, flicker, tv, chase - one of a ring of lamps
 *                                    running round, weld - a welder's flashes, night - a duty lamp lit only
 *                                    at night), colour 0..1, period s and phase 0..1; a chase lamp adds the
 *                                    number of lamps in its ring (its phase is its place in it)
 *     water blue 0.75 1.00 1.00      the tile's water (blue or green by the picture) ripples and glints
 *     spin 64 64 33 0.18             a round piece of the picture turns: x y radius, turns per second
 *     swing 64 64 26 40 7.0          ... or swings to and fro: x y radius, degrees each way, period s
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
	enum Kind { STEADY, BLINK, PULSE, SCREEN, FLICKER, TV, CHASE, WELD, DUTY };
	enum Gate { GATE_NONE, GATE_LAB, GATE_WORK, GATE_HOME };

	struct Light
	{
		float x = 0, y = 0, radius = 0;  ///< pack pixels from the tile's corner
		Kind kind = STEADY;
		float r = 1, g = 1, b = 1;
		float period = 0, phase = 0;      ///< seconds and 0..1, blink and pulse
		int count = 0;                    ///< chase: lamps in the ring
	};

	/// A round piece of a picture turning (a radar dish) or swinging (a turret).
	struct Spin
	{
		float x = 0, y = 0, radius = 0;  ///< pack pixels from the tile's corner
		float rps = 0;                    ///< turns per second; 0 - it swings
		float swing = 0, period = 1;      ///< degrees each way and seconds
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
		int water = 0;                    ///< 0 none, 1 blue, 2 green: which of the picture is water
		float glint[3] = { 1, 1, 1 };     ///< the colour of its glints
		std::vector<Spin> spins;
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

	/// Water of a tile where it is on the world layer.
	struct PlacedWater
	{
		SDL_Rect box;                     ///< the facility's pictures (the water is looked for there)
		int kind = 1;                     ///< 1 blue, 2 green
		float glint[3] = { 1, 1, 1 };
	};

	/// A spin where it is on the world layer.
	struct PlacedSpin
	{
		Spin spin;                        ///< x, y, radius in world pixels
		float phase = 0;                  ///< staggers the facilities
	};

	/// The whole base view as the preview saw it (base_scene_preview.py Scene), made once for a layout of
	/// the base and a scale: the rock with the shadows the facilities cast on it, the relief of the pictures
	/// the lamps fall on, and where the water is. Only the look: the game is never read here.
	struct View
	{
		int x = 0, y = 0, w = 0, h = 0;   ///< where it lies in the world layer
		float scale = 1;                  ///< world pixels per pack pixel (128 to a cell)
		std::vector<Uint32> albedo;       ///< the pictures over the shaded rock, unlit (the water's and spins' source)
		HdFrame ground;                   ///< the rock with the shadows, opaque, drawn under the pictures
		std::vector<float> relief;        ///< per pixel: the normal (x, y, z) and the height, world pixels
		std::vector<float> water;         ///< per pixel 0..1
		struct Area { SDL_Rect box; float glint[3]; };
		std::vector<Area> waters;
		std::vector<PlacedSpin> spins;
	};

	/// Makes `view` from its `albedo`, which holds the pictures of the facilities with
	/// their alpha - everything else transparent: lays them over `rock` (a whole-base picture, nullptr - plain
	/// dark rock) with soft shadows, marks the `empty` cells (x, y, w, h in the view) with a faint grid, and
	/// works out the relief and the water. A few tens of ms at 4x: only when the layout changes.
	void bake(View &view, const HdFrame *rock, const std::vector<SDL_Rect> &empty, const std::vector<PlacedWater> &waters);

	/// The water rippling and the spins turning in the world layer, from `view`'s albedo, as at `ms`:
	/// after the pictures, before the crew and the light.
	void drawMotion(SDL_Surface *world, const View &view, Uint32 ms);

	/// Lights `area` of the world layer as it is at `ms` of the display clock (SDL_GetTicks): the pictures
	/// under the ambient light of `night` and the lamps, their halo over them, the light falling on the
	/// relief of `view` and its water glinting (nullptr: flat). Runs in bands on HdWorkers.
	void draw(SDL_Surface *world, const SDL_Rect &area, const std::vector<Placed> &lights, float night, Uint32 ms,
		const View *view = nullptr);

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
