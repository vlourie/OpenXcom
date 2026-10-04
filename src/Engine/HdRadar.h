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
 * a circle per radar (oxceHdRadarPulse).
 *
 * A base pulses once per detection cycle (GeoscapeState::time30Minutes): a wave per radar runs from
 * the base to that radar's range, the next radar's a moment later. The first base starts the cycle
 * and its wave sets off every base it reaches, and theirs the next ones; a base no chain reaches
 * starts by itself. A base that pulsed less than ten game minutes ago is not set off again. The
 * pulses run only at the slow clock speeds; faster, the wash stands still.
 *
 * A craft out of its base turns a slow beam round its own circle; the part of it inside a base's
 * coverage is not drawn. A craft never sets a base off.
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
	/// A detection cycle has run: the bases pulse at the next draw (when the clock is slow).
	void cycle() { _cyclePending = _slow; }
	/// Is the game clock slow enough for the pulses (5 seconds or 1 minute a step)?
	void setSlow(bool slow) { _slow = slow; }
	/// Draws the wash, the edge, the pulses and the beams; `minute` is the game time in minutes.
	/// Clipped by HdUi's clip.
	void draw(const View &view, const std::vector<Source> &sources, long long minute);
private:
	struct Pulse
	{
		bool any = false;            ///< has it pulsed at all
		Uint32 start = 0;            ///< SDL_GetTicks of its first wave (a base set off later starts in the future)
		Uint32 length = 0;           ///< ms from the start to the end of the last wave
		long long minute = 0;        ///< the game minute it was set off
	};
	std::unordered_map<const void*, Pulse> _pulses;
	bool _slow = true;
	bool _cyclePending = false;

	/// The bases' signed distance to the edge of their joint coverage, 1/8 world pixel, positive inside:
	/// drawn again only when the globe turns or zooms or a base's radars change.
	std::vector<Sint16> _dist;
	int _distX = 0, _distY = 0, _distW = 0, _distH = 0;
	std::vector<double> _distKey;

	void schedule(const std::vector<Source> &sources, Uint32 now, long long minute);
	void updateDist(const View &view, const std::vector<Source> &sources);
};

}
