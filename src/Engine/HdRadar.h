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
#include <unordered_map>
#include <vector>

namespace OpenXcom
{

/**
 * HD globe: the player's radar coverage as a light wash with one edge round all of it, instead of
 * a circle per radar (oxceHdRadar 1 and 2).
 *
 * With the sweep (oxceHdRadar 2) a base pulses once per detection cycle (GeoscapeState::time30Minutes):
 * a wave per radar runs from the base to that radar's range, the next radar's a moment later. The
 * first base starts the cycle and its wave sets off every base it reaches, and theirs the next ones;
 * a base no chain reaches starts by itself. A base that pulsed less than ten game minutes ago is not
 * set off again. The pulses run only at the slow clock speeds; faster, the wash stands still. A craft
 * out of its base turns a slow beam round its own circle; the part of it inside a base's coverage is
 * not drawn. A craft never sets a base off.
 *
 * The cost: the bases' wash and edge are worked out only when the globe turns or zooms or a base's
 * radars change, and kept as runs of each row (a run of the plain wash is one colour); a frame blends
 * those runs and works out per pixel only the craft's circles and the waves in flight.
 *
 * The waves (oxceHdRadar 3, a trial) are the other way round: no wash at all, only the edge round the
 * bases' joint coverage, and every game hour each base with a finished radar sends one wave out to
 * its longest range, all at once (GeoscapeState::time1Hour), so the waves tell the time. A craft out
 * of its base is a circle of its own, not joined with the bases' (it looks for other things), with a
 * wave of its own every detection cycle, half an hour. A wave lasts at most PULSE_MS, and less when the
 * clock is faster than that, so that one ends before the next sets off.
 *
 * Pictures only: the ranges, the positions and the time are read from the game; the detection
 * itself, its chances and its timing are not touched.
 */
class HdRadar
{
public:
	/// The most waves one base sends per cycle (its longest radars).
	static const int MAX_WAVES = 3;
	/// A radar on the globe: a base with its radars' ranges, or a craft out of its base.
	struct Source
	{
		const void *id;              ///< the base or the craft: its pulse is kept by this
		double lon, lat;             ///< radians
		double range;                ///< the covered circle, radians of arc
		std::vector<double> waves;   ///< a base: a range per radar, radians, the longest first; a craft: empty
	};
	/// Where the globe stands in the world layer.
	struct View
	{
		double cenLon, cenLat;       ///< the point in the middle of the globe
		double cx, cy;               ///< that middle, world pixels
		double radius;               ///< the globe's radius, world pixels
		int x, y, w, h;              ///< the globe's widget, world pixels
		int k;                       ///< world pixels per base pixel
	};
	/// How the coverage is drawn: oxceHdRadar 1, 2 and 3.
	enum Mode { WASH = 1, SWEEP = 2, WAVES = 3 };
	/// A detection cycle has run: the bases pulse (the craft with WAVES) at the next draw, when the clock is slow.
	void cycle() { _cyclePending = _slow; note(_cycleTick, _cycleMs); }
	/// A game hour has run: with WAVES the bases pulse at the next draw, when the clock is slow.
	void hour() { _hourPending = _slow; note(_hourTick, _hourMs); }
	/// Is the game clock slow enough for the pulses (5 seconds or 1 minute a step)?
	void setSlow(bool slow) { _slow = slow; }
	/// The game clock ran this frame: the waves and beams move on at the next draw. A frame without it
	/// (a window over the globe, a dogfight) keeps them standing where they were, as the time does.
	void ran() { _ran = true; }
	/// Draws the coverage the `mode` way; `minute` is the game time in minutes. Clipped by HdUi's clip.
	/// WAVES: `waveHours` 0 - every base at once each game hour (the bases tell the time); 1, 3 or 6 - the
	/// bases in turn, each once in that many hours, spread over ten-minute steps so that few run together.
	/// `beam` - a craft out turns a beam round its circle instead of sending waves.
	void draw(const View &view, const std::vector<Source> &sources, long long minute, Mode mode, int waveHours = 0, bool beam = false);
	/// The enemy's radars (discovered alien bases, hunter-killers): a red line round each circle with a glow
	/// inside, each on its own. Worked out per pixel only near the rims, so the cost goes with their length.
	struct Ring
	{
		double lon, lat;             ///< radians
		double range;                ///< radians of arc
		bool ship = false;           ///< a hunter-killer: a lighter red than a base's
	};
	void drawRings(const View &view, const std::vector<Ring> &rings);
	/// The main base's mark instead of its square (WAVES): a four-pointed star of `color` (0xRRGGBB) round
	/// a dark middle, centred on world pixel (cx, cy), no wider than the 7 base pixels of a globe marker.
	void drawMainBase(float cx, float cy, int k, Uint32 color);
private:
	struct Pulse
	{
		bool any = false;            ///< has it pulsed at all
		Uint32 start = 0;            ///< SDL_GetTicks of its first wave (a base set off later starts in the future)
		Uint32 length = 0;           ///< ms from the start to the end of the last wave
		long long minute = 0;        ///< the game minute it was set off
		Uint32 wave = 0;             ///< ms one wave takes from the middle to the rim
	};
	/// A stretch of a row of the bases' wash: one colour, or a colour per pixel.
	struct Run
	{
		int x0, x1;                  ///< world pixels, [x0, x1)
		Uint32 color;                ///< 0xAARRGGBB when the whole run is one colour
		int px;                      ///< -1: one colour; else where its colours start in the row's px
	};
	struct Row
	{
		std::vector<Run> runs;
		std::vector<Uint32> px;
	};
	std::unordered_map<const void*, Pulse> _pulses;
	bool _slow = true;
	bool _cyclePending = false;
	bool _hourPending = false;
	/// When the last cycle and hour came, and the ms of the animation clock between the last two (0 = not known).
	Uint32 _cycleTick = 0, _cycleMs = 0, _hourTick = 0, _hourMs = 0;
	/// The animation clock, ms: real time, but only while the game clock runs (ran()).
	Uint32 _clock = 1, _lastReal = 0;
	bool _ran = false;
	/// WAVES in turn: the last ten-minute step of the game clock seen, when it came on the animation clock,
	/// and the ms of that clock one step takes (0 = not known).
	long long _step = -1;
	Uint32 _stepAt = 0, _stepMs = 0;
	/// Moves the animation clock on by the real time since the last draw, if the game clock ran meanwhile.
	Uint32 advance();
	/// WAVES in turn: the bases whose turn falls on ten-minute step `step` send their wave now.
	void scheduleTurn(const std::vector<Source> &sources, Uint32 now, long long minute, long long step, int waveHours);
	/// The main base's mark as last drawn, and what it was drawn for.
	std::vector<Uint32> _mainMark;
	int _mainK = 0;
	Uint32 _mainColor = 0;

	/// The bases' signed distance to the edge of their joint coverage, 1/8 world pixel, positive inside,
	/// saturated a little past the glow: worked out again only when the globe turns or zooms or a base's
	/// radars change.
	std::vector<Sint16> _dist;
	int _distX = 0, _distY = 0, _distW = 0, _distH = 0;
	std::vector<double> _distKey;
	/// The same coverage as the colours to blend, a row of runs per row of _dist.
	std::vector<Row> _rows;
	/// The rows that have any: [_rowA, _rowB) of _dist.
	int _rowA = 0, _rowB = 0;
	/// The same wash as one picture for the video card (HdShadeBase): rows [_rowA, _rowB), columns [_colA, _colB)
	/// of _dist; _washKey changes with it.
	std::vector<Uint32> _wash;
	int _colA = 0, _colB = 0;
	Uint64 _washKey = 0;

	void schedule(const std::vector<Source> &sources, Uint32 now, long long minute);
	/// WAVES: sets off at once every base (or every craft), a wave that ends before the next one is due.
	void scheduleAll(const std::vector<Source> &sources, Uint32 now, long long minute, bool bases, Uint32 gapMs);
	/// Keeps when a signal came and the time from the one before it, on the animation clock.
	void note(Uint32 &tick, Uint32 &ms);
	/// Works out _dist and the runs again if the globe or the bases changed.
	void updateCache(const View &view, const std::vector<Source> &sources, bool fill);
};

}
