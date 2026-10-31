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
 *                                    at night, marquee - a ring of lamps of an entrance sign or a machine, running
 *                                    like chase but lit by day too; swell - a slow breath of light, 5/7 of the period
 *                                    rising from nothing and the rest fading, all the time, not only in the facility's
 *                                    turn: the arrows of an empty hangar's pad, ticket 350), colour 0..1, period s and
 *                                    phase 0..1; a chase or
 *                                    marquee lamp adds the number of lamps in its ring (its phase is its place in it)
 *     water blue 0.75 1.00 1.00 100  the tile's water (blue or green by the picture) ripples, the light of its
 *                                    bottom running over it; pools of the last number of pack pixels and more
 *                                    (200 if left out)
 *     flow steady 1.00 0.62 0.20 0.250 0.350 0.75 0.90 0.15
 *                                    light runs along the pipes of `<frame index>.flow.png` (u along the
 *                                    pipe, its core and halo - tools/hdart/base_flow_bake.py): steady or fit
 *                                    (in the facility's fits), colour, then speed (of the pipe's length a
 *                                    second) and spacing of the pulses - or slugs a fit and 0 -, gains of the
 *                                    core and the halo, how much darker the pipe itself goes
 *     spin 64 64 33 0.18             a round piece of the picture turns: x y radius, turns per second
 *     swing 64 64 26 40 7.0 -5       ... or swings to and fro: x y radius, degrees each way, period s and
 *                                    the middle of the swing, degrees clockwise (0 if left out);
 *                                    with `<frame index>.under.png` and `.spin.png` (HdBase::layer) only the
 *                                    piece turns about (x, y), over the picture without it
 *     emit steam 20 26 70 70 0.95 0.95 1.00
 *                                    particles: kind (steam, bubbles, sparks, embers, orbit, sweep - a
 *                                    radar or turret beam turning about the box's middle, ripple - rings
 *                                    on water, dust - motes drifting in the light, flies - dark specks
 *                                    buzzing about, arc - a lightning now and then from the box's corner
 *                                    (x, y) to the opposite one (x + w, y + h), beam - a plasma gun: sparks
 *                                    gather into its orb at (x + w, y + h), then a beam goes to (x, y)),
 *                                    and the things that move (ticket 336; none of them throw sparks):
 *                                    belt / beltrev - parts ride along the long side of the box (beltrev the other
 *                                    way) while the facility works, glints of rollers slide over the belt;
 *                                    roll - the glints of a roller turning across the short side of the box;
 *                                    shuttle - a print head goes to and fro along the long side, its nozzle
 *                                    glowing, a cooling trail behind it; heat - hot metal breathes, a soft
 *                                    light swelling and fading about every 3.6 s; cart - a trolley with a load
 *                                    goes along the long side, waits, comes back empty; ticker - dashes of a
 *                                    running line scroll along the box (a screen),
 *                                    the box they start in
 *                                    (x y w h, pack pixels from the tile's corner), colour
 *     walk 8 0011110001111110...     where the crew may stand: n x n squares of the tile, row by row,
 *                                    1 - bare floor (tools/hdart/base_scene_pack.py walk_mask)
 *     post belt 72 40 1 0            where the crew stands (ticket 336): kind (belt - an engineer at a belt while the
 *                                    facility works, seat - a gambler's place at a table, dealer - the dealer of
 *                                    a table), x y (pack pixels from the tile's corner, the middle of a floor square
 *                                    of the walk mask), where it looks (0 right, 1 down, 2 left, 3 up) and the table's
 *                                    number (seats and dealer of one table share it)
 *     cycle 45 16                    the facility moves in fits (tickets 237-245): one about every 45 s, 16 s
 *                                    long, no more than three facilities of the base at once; its swings and
 *                                    turret beams, glows, lid and sink move only in a fit, its burst lights burn
 *                                    only then
 *     glow 13 13 88 88 18 14 0.60 0.55 1 4
 *                                    in a fit the pixels of a hue go darker or brighter: box x y w h, hue and its
 *                                    tolerance (degrees), saturation from, brightness at the peak (< 1 darker),
 *                                    pulses a fit, groups round the box's middle going dark one after another
 *     lid 63 63.5 14.5 8 3           an eye closes and opens: middle, half axes, blinks a fit; the lid is the
 *                                    colour of the picture just above the eye
 *     sink 46 44 35 36 55 54 18 18 2 a platform sinks and darkens while its hatch rises and reddens: the
 *                                    platform's box, the hatch's box, pulses a fit
 *     light 67.7 67.4 9 burst 0.55 1 0.45 2 0
 *                                    a burst light burns only in a fit: its period is the pulses a fit
 *
 * Not more than three facilities of the base move at once (ticket 336, 27.10): a facility with a `cycle` moves in its
 * fits, every other one with anything moving in its tiles (blinking lamps, particles, water, pipes, turning
 * pieces) in turns of 16 s in the order of waiting, the one of work or research only while it works (View::fits,
 * tick); the rest stand as the picture is, their lamps steady at the middle of what they do.
 *
 * Only the picture changes: the light is drawn over the world layer from the display clock, the
 * game's state is only read (the time of day, whether the base researches and builds).
 */
namespace HdBaseScene
{
	enum Kind { STEADY, BLINK, PULSE, SCREEN, FLICKER, TV, CHASE, WELD, DUTY, BURST, MARQUEE, SWELL };
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
		float middle = 0;                 ///< the middle of the swing, degrees clockwise
	};

	enum EmitKind { STEAM, BUBBLES, SPARKS, EMBERS, ORBIT, SWEEP, RIPPLE, DUST, FLIES, ARC, BEAM,
		BELT, BELTREV, ROLL, SHUTTLE, HEAT, CART, TICKER };

	struct Emit
	{
		EmitKind kind = STEAM;
		float x = 0, y = 0, w = 0, h = 0; ///< the box the particles start in, pack pixels from the tile's corner
		float r = 1, g = 1, b = 1;
	};

	/// A place where the crew stands to the things of a facility (ticket 336): an engineer at a belt, a gambler at a
	/// table, the dealer of a table. The crew's squares come from these, the walk mask says where there is floor.
	struct Post
	{
		enum Kind { BELT, SEAT, DEALER };
		float x = 0, y = 0;               ///< pack pixels from the tile's corner: the middle of the square it stands on
		int face = 0;                     ///< where it looks: 0 right, 1 down, 2 left, 3 up
		Kind kind = BELT;
		int group = 0;                    ///< a table's number within the facility (seats and the dealer of one table)
	};

	/// The pixels of a hue going darker or brighter in a fit (a shield's lamps, a decoder's cables).
	struct Glow
	{
		float x = 0, y = 0, w = 0, h = 0; ///< pack pixels from the tile's corner
		float hue = 0, tolerance = 0;     ///< degrees
		float saturation = 0;             ///< from
		float peak = 1;                   ///< the brightness at the peak
		int pulses = 1, groups = 1;
	};

	/// An eye closing and opening in a fit.
	struct Lid
	{
		float x = 0, y = 0, rx = 0, ry = 0;
		int blinks = 1;
	};

	/// A lift's platform sinking in a fit while its hatch rises.
	struct Sink
	{
		float x = 0, y = 0, w = 0, h = 0;      ///< the platform
		float ix = 0, iy = 0, iw = 0, ih = 0;  ///< the hatch in it
		int pulses = 1;
	};

	/// Light running along the pipes of a tile (`flow` of the scene, `<frame index>.flow.png`).
	struct Flow
	{
		enum Mode { NONE, STEADY, FIT };
		Mode mode = NONE;
		float colour[3] = { 1, 1, 1 };
		float a1 = 0.2f, a2 = 0.3f;       ///< steady: speed and spacing of the pulses (of the pipe's length); fit: slugs a fit
		float core = 1, halo = 1;         ///< gains of the pipe's own light and of the halo about it
		float dark = 0.15f;               ///< the pipe itself darker by this where it glows
	};

	struct TileScene
	{
		int width = 128, height = 128;    ///< the tile's picture in the pack
		Gate gate = GATE_NONE;
		std::vector<Light> lights;
		std::vector<Emit> emits;
		int walkSize = 0;                 ///< n of the walk grid; 0 - none given, the whole tile is floor
		std::vector<unsigned char> walk;  ///< n x n, row by row: 1 - the crew may stand there
		std::vector<Post> posts;
		int water = 0;                   ///< 0 none, 1 blue, 2 green: which of the picture is water
		float glint[3] = { 1, 1, 1 };     ///< the colour of its glints
		int waterLeast = 0;               ///< pack pixels a pool needs; 0 - 200
		Flow flow;
		std::vector<Spin> spins;
		float cycle = 0, fit = 0;         ///< seconds from one fit to the next and of a fit; 0 - it moves all the time
		std::vector<Glow> glows;
		std::vector<Lid> lids;
		std::vector<Sink> sinks;
	};

	/// Reads a `.scene.txt`; false when it holds nothing usable.
	bool parse(std::istream &in, TileScene &out);

	/// True when anything of the tile moves on its own - a blinking, pulsing or running lamp, particles, water,
	/// light along pipes, a turning piece: such a facility needs a turn (Fit) to move in.
	bool moves(const TileScene &scene);

	/// A light where it is on the world layer.
	struct Placed
	{
		Light light;                      ///< x, y, radius in world pixels
		float scale = 1;                  ///< world pixels per pack pixel (the lamp's height and halo)
		float level = 1;                  ///< from the gate: 1 at work, less when the facility idles
		float act = 1;                    ///< how much its facility moves now (Fit::act): a blinking lamp burns even when it rests
		bool moving = false;              ///< a lamp of the crew (it walks, flashes): never kept with the resting lamps
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
		int least = 0;                    ///< pack pixels a pool needs; 0 - 200
		int fit = -1;                     ///< its facility's turn (View::fits): the water moves only in it
	};

	/// The pipes of a tile where they are on the world layer.
	struct PlacedFlow
	{
		Flow flow;
		SDL_Rect box;                     ///< the tile
		std::vector<Uint32> map;          ///< box.w x box.h: u along the pipe (red), core (green), halo (blue)
		int fit = -1;                     ///< its facility's fit (View::fits) for a flow of fits
	};

	/// A spin where it is on the world layer.
	struct PlacedSpin
	{
		Spin spin;                        ///< x, y, radius in world pixels
		float phase = 0;                  ///< staggers the facilities
		HdFrame piece;                    ///< the piece alone (HdBase::layer), empty - a round piece of the picture turns
		int px = 0, py = 0;               ///< where the piece's frame lies in the world layer
		int fit = -1;                     ///< its facility's fit (View::fits), -1 - it turns all the time
	};

	/// When a facility moves: its own period, no more than three facilities at once (View::fits). A facility
	/// with a `cycle` line moves in fits of that length and period (its turrets, lids, sinks and glows by the time
	/// into the fit); every other facility with anything moving in its pictures (water, pipes, turning pieces,
	/// particles, blinking lamps) gets a place in turn for `length` seconds, then rests (ticket 336, 27.10):
	/// `act` is how much it moves now, 0 .. 1, rising and falling over a second or so at the ends of its turn.
	struct Fit
	{
		float period = 45, length = 10;   ///< seconds
		Uint32 seed = 0;                  ///< staggers the periods of the facilities
		Uint32 next = 0, start = 0;       ///< ms of the display clock: when it is due, when it began
		Uint32 end = 0;                   ///< ms: when it is over (start + length, or sooner when the work stops)
		bool on = false;
		bool continuous = false;          ///< no `cycle` line: turns of `length` seconds, handed out in order of waiting
		bool wants = true;                ///< a facility of work or research asks for a place only while it works
		float act = 0;                    ///< 0 .. 1, worked out by tick
		float turned = 0;                 ///< seconds moved so far, act-weighted (the angle of a turning piece)
	};

	/// A glow, a lid and a sink where they are on the world layer (world pixels).
	struct PlacedGlow
	{
		Glow glow;
		int fit = -1;
		std::vector<Uint32> pixels;       ///< which of the view (y * w + x), picked from the albedo by bake
		std::vector<unsigned char> group;
	};
	struct PlacedLid
	{
		Lid lid;
		int fit = -1;
		float colour[3] = { 150, 140, 128 };  ///< 0..255: the picture above the eye, from bake
		float scale = 1;                  ///< world pixels per pack pixel
	};
	struct PlacedSink
	{
		Sink sink;
		int fit = -1;
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
		struct Area { SDL_Rect box; float glint[3]; int fit = -1; };
		std::vector<Area> waters;
		std::vector<PlacedSpin> spins;
		std::vector<Fit> fits;
		std::vector<int> facilityFit;     ///< the fit of the caller's n-th facility, -1 none
		std::vector<PlacedGlow> glows;
		std::vector<PlacedLid> lids;
		std::vector<PlacedSink> sinks;
		std::vector<PlacedFlow> flows;
		Uint32 fitsAt = 0;               ///< the display clock of the last tick, 0 - not yet
		Uint32 serial = 0;               ///< which bake made it (the light keeps a picture of the resting lamps by it)
	};

	/// Starts and ends the fits and turns as at `ms` (once a frame, before drawMotion): no more than three
	/// facilities of the base move at once. A due fit comes first, then the turns go to the facilities that have
	/// waited longest (`wants` - a facility of work asks only while it works). A long gap (the base screen left
	/// and back) deals them anew. OXCE_HD_BASE_ACT=1 sets every facility moving, =0 every one still (a test).
	void tick(View &view, Uint32 ms);

	/// How much the facility's pictures move now, 0 .. 1 (Fit::act); 1 for a facility without a turn (-1).
	float actOf(const View &view, int fit);

	/// Seconds into the fit, -1 between fits (or no such fit). OXCE_HD_BASE_FIT=<s> holds every fit at <s>
	/// for a test dump.
	float fitTime(const View &view, int fit, Uint32 ms);

	/// 0..1: `pulses` smooth humps over a fit of `length` seconds, `t` seconds into it; 0 outside.
	float fitWave(float t, float length, int pulses);

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
	/// relief of `view` and the light running along its pipes (nullptr: flat). Runs in bands on HdWorkers.
	void draw(SDL_Surface *world, const SDL_Rect &area, const std::vector<Placed> &lights, float night, Uint32 ms,
		const View *view = nullptr);

	/// OXCE_HD_BASE_OFF=water,spin,flow,light,emit,crew leaves that part of the living base undrawn: a way to
	/// measure what each costs (the cost log is OXCE_HD_BASE_PERF). Unset - everything is drawn.
	bool measuredOff(const char *part);

	/// Particles where they are on the world layer.
	struct PlacedEmit
	{
		Emit emit;                        ///< the box in world pixels
		float scale = 1;                  ///< world pixels per pack pixel
		float level = 1;                  ///< from the gate: sparks fly only where the facility works
		float act = 1;                    ///< how much its facility moves now (Fit::act): 0 - nothing is drawn
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
