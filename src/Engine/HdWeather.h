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
#include <SDL.h>

namespace OpenXcom
{

struct HdFrame;

/**
 * HD render (option oxceHdWeather, docs/research/battle-weather-2026-11-11.md): the weather of a battle as a picture.
 * The kind comes from the ground of the map (the mod's table hd/weather.txt, terrain -> biome) and a seed made of what
 * the save already holds, so a loaded battle has the same weather; its strength swells and fades with the turns.
 *
 * Two layers: the air (rain, snow, sand, the overcast tone, the veil far from the player's units, the lightning) is one
 * command at the end of the map's frame, drawn in strips on the HD workers; the ground (wet floor, puddles, snow cover)
 * is a frame over every open floor, cut by noise in map coordinates so that its edge never follows the diamonds.
 *
 * Pictures only: nothing of the battle is changed, visibility and the game's random numbers included; the veil hides
 * the picture, not the units - a spotted enemy and the battle cursor keep a window in it.
 */
namespace HdWeather
{
	enum Biome { B_NONE, B_CITY, B_STEPPE, B_SNOW, B_SEA, B_WASTE, B_DESERT, B_JUNGLE, B_FOREST, B_SWAMP };
	enum Kind { CLEAR, DRIZZLE, RAIN, DOWNPOUR, THUNDER, FOG, FLAKES, SNOWFALL, BLIZZARD, WHITEOUT, WIND, SANDSTORM, KINDS };

	/// The biome of a word of hd/weather.txt (CITY, SNOW, ... ; a _COLD suffix sets `cold`); B_NONE for anything else.
	Biome biomeOf(const std::string &word, bool &cold);
	/// The name of a kind (logs and tests).
	const char *kindName(Kind kind);
	/// The kind for a battle: about half of the battles are clear, the rest by the weights of the biome.
	Kind pick(Biome biome, bool cold, Uint32 seed);
	/// The kind named by the test switch OXCE_HD_WEATHER (a kindName), or KINDS when it is unset or unknown.
	Kind forced();
	/// The strength of the turn, 0.6..1: the weather swells and fades.
	float power(Uint32 seed, int turn);
	/// The distance in tiles from the nearest own unit where the veil begins (0: no veil).
	float veilTiles(Kind kind);
	/// The lightning of a thunderstorm at the clock `ms`: 0..1 (0 for any other kind).
	float lightning(Kind kind, Uint32 seed, Uint32 ms);
	/// A thunderstorm strikes once a slot of STRIKE_SLOT ms at most: the strike's ms in the slot, -1 for a quiet slot.
	const Uint32 STRIKE_SLOT = 7000;
	int strikeAt(Uint32 seed, Uint32 slot);
	/// The air is still: nothing moves, the frame need not be redrawn for the weather.
	bool still(Kind kind);

	/// What lies on the open floors.
	struct Ground
	{
		/// Wet floor 0..1, puddles 0..1 (their share of the floor), snow cover 0..1.
		float wet = 0, puddles = 0, snow = 0;
		bool any() const { return wet > 0 || puddles > 0 || snow > 0; }
	};
	/// The ground of the turn: puddles grow and snow piles up with the turns of rain and snow.
	Ground ground(Kind kind, Uint32 seed, int turn);

	/// One frame of the air.
	struct Scene
	{
		Kind kind = CLEAR;
		int k = 1;
		Uint32 seed = 0;
		/// The clock (SDL_GetTicks) and the strength of the turn.
		Uint32 ms = 0;
		float power = 1;
		/// 1 by day .. 0 at the darkest night (the battle's global shade).
		float day = 1;
		/// The canvas.
		int width = 0, height = 0;
		/// A canvas pixel's centre (px + 0.5, py + 0.5) in view tiles on the ground (level 0): u = au * px + bu * py + cu,
		/// v = av * px + bv * py + cv; a tile's centre is at (x + 0.5, y + 0.5).
		float au = 0, bu = 0, cu = 0, av = 0, bv = 0, cv = 0;
		/// The view's tiles and its fields, mapW * mapL each, [y * mapW + x]: the distance in tiles from the nearest own unit,
		/// the open sky (1) or a roof over the level (0), the distance from the nearest spotted enemy or the cursor.
		/// `known`: 1 where the player has discovered the column, 0 where it is still black - the veil, the tone and the
		/// bands lie only on what the player has seen (the fall goes everywhere).
		int mapW = 0, mapL = 0;
		const float *dist = nullptr, *sky = nullptr, *window = nullptr, *known = nullptr;
		/// The canvas position of the map's origin in pixels: what is anchored to the map (veil wisps, particles) moves with it.
		int originX = 0, originY = 0;
		/// The lightning of this frame, 0..1.
		float flash = 0;
	};
	/// Prepares the scene's coarse grid (veil, particles, bands) on the HD workers; call before the canvas records the command.
	void prepare(const Scene &scene);
	/// Draws the rows [y0, y1) of a 32-bit canvas (rshift, gshift, bshift: its channel positions) with the scene prepared last.
	void drawRows(const Scene &scene, Uint32 *pixels, int pitchBytes, int y0, int y1, int rshift, int gshift, int bshift);
	/// Sides of a floor's diamond with no open floor beyond (the cover fades out softly there instead of ending on the diamond).
	enum Side { SIDE_X0 = 1, SIDE_X1 = 2, SIDE_Y0 = 4, SIDE_Y1 = 8 };
	/// The frame of what lies on the floor of the map cell (x, y) at scale k (the diamond, 32k x 16k, straight alpha), or nullptr
	/// when nothing does there; `closed` - the Side bits. The noise repeats every 8 tiles; frames are kept until the ground or
	/// the scale changes.
	const HdFrame *groundFrame(int k, const Ground &ground, Uint32 seed, int x, int y, int closed);
	/// A ring of a rain drop on the floor: its frame and its centre from the top corner of the floor's diamond, canvas pixels.
	struct Splash
	{
		const HdFrame *frame;
		int x, y;
	};
	const int SPLASHES = 3;
	/// The rings on the open floor of the map cell (x, y) at the clock `ms`: how many of `out` are filled (0 without rain).
	int splashes(Kind kind, int k, Uint32 seed, Uint32 ms, float power, int x, int y, Splash out[SPLASHES]);
	/// Milliseconds spent baking the textures and the ground frames (the battle's log line).
	int bakeMs();

	// ---- what the weather carries (HdWeatherExtras.cpp): tumbleweeds, dust devils, a tornado, lightning bolts, the sound

	/// What a battle's weather brings besides the air and the ground (by its kind, biome and seed).
	struct Extras
	{
		/// Tumbleweeds rolling at a time (slots), dust devils (slots), a tornado crossing the map, bolts in the strikes.
		int tumbleweeds = 0, devils = 0;
		bool tornado = false, bolts = false;
		/// The tornado's colour: 0 dust (desert, steppe), 1 storm grey.
		int tornadoLook = 0;
	};
	Extras extras(Kind kind, Biome biome, Uint32 seed);
	/// The wind's direction on the ground, map tiles a second per unit (u along x, v along y) - the way the particles fly.
	void windDir(Kind kind, float &du, float &dv);

	/// A tumbleweed of this moment: its contact point on the ground (map tiles), its hop and turn, its look and opacity.
	struct Roll
	{
		float u, v;
		/// Hop above the ground, base pixels; turn of the ball, radians.
		float hop, turn;
		float alpha;
		int shape;
		/// It has just set off (the sound of a new tumbleweed).
		Uint32 id;
	};
	const int ROLLS = 6;
	/// Can a ball stand at (u, v) of the map coming straight from (fromU, fromV)? (open sky, a floor, nothing on it, no wall
	/// crossed) - asked by the extras, answered by the map.
	typedef bool (*ClearFn)(void *ctx, float fromU, float fromV, float u, float v);
	/// The tumbleweeds at the clock `ms` on a map of mapW x mapL; how many of `out` are filled. A ball sets off upwind of
	/// (viewU, viewV), the ground in the middle of the view when its run begins, and keeps that start for the run.
	int rolls(const Extras &ex, Kind kind, Uint32 seed, Uint32 ms, float power, int mapW, int mapL, float viewU, float viewV,
		ClearFn clear, void *ctx, Roll out[ROLLS]);
	/// The frames of a tumbleweed (shape, turn) and its shadow at scale k; the ball's contact point is the bottom middle of
	/// the frame, the shadow's centre is its middle.
	const HdFrame &rollFrame(int k, int shape, float turn);
	const HdFrame &rollShadow(int k, int shape);

	/// A twister of this moment: its base on the ground (map tiles), its frame and opacity.
	struct Twister
	{
		float u, v;
		float alpha;
		/// 0 a dust devil, 1 the tornado.
		int big;
		Uint32 id;
	};
	const int TWISTERS = 3;
	/// `open(ctx, u, v)`: the ground at (u, v) is open sky and discovered (a dust devil is born only there).
	typedef bool (*OpenFn)(void *ctx, float u, float v);
	/// `away(ctx, u, v)`: tiles from (u, v) to the nearest own unit, spotted enemy or the cursor (the way keeps off them).
	typedef float (*AwayFn)(void *ctx, float u, float v);
	/// The twisters at the clock `ms`; like the tumbleweeds, each is placed near (viewU, viewV) as its pass begins.
	int twisters(const Extras &ex, Kind kind, Uint32 seed, Uint32 ms, int mapW, int mapL, float viewU, float viewV, OpenFn open,
		AwayFn away, void *ctx, Twister out[TWISTERS]);
	/// The frame of a twister at the clock `ms`; its base (the ground point) is at (baseX, baseY) of the frame.
	const HdFrame &twisterFrame(int k, int big, int look, Uint32 ms, int &baseX, int &baseY);

	/// A lightning bolt of the strike at the clock `ms` on a canvas of width x height: its frame and where it goes, nullptr
	/// when no bolt is seen now; `opacity` follows the flash.
	/// `spot(ctx, px, py)`: the bolt may come down at the canvas point (px, py) - open ground away from the units.
	typedef bool (*SpotFn)(void *ctx, float px, float py);
	const HdFrame *bolt(Kind kind, Uint32 seed, Uint32 ms, int k, int width, int height, SpotFn spot, void *ctx, int &x, int &y,
		float &opacity);

	/// The sound of the weather (option oxceHdWeatherSound): the loop of the kind on the reserved channel 0, the thunder of
	/// the strikes, the tornado's roar while it is seen, a rustle for a tumbleweed setting off and a whoosh for a dust devil.
	/// Files hd/SOUND/WEATHER/<name>.ogg (loops) and <name>_<N>.ogg (one-shots); a missing file stays silent.
	struct Hearing
	{
		Kind kind = CLEAR;
		Uint32 seed = 0;
		float power = 1;
		/// The tornado is seen (0..1), new tumbleweeds and dust devils since the last call, their screen place -1..1.
		float tornado = 0;
		int newRolls = 0, newDevils = 0;
		float rollPan = 0, devilPan = 0;
	};
	void hear(const Hearing &h, Uint32 ms);
	/// Stops all the weather's sound (the battle ends, the option goes off).
	void silence();
}

}
