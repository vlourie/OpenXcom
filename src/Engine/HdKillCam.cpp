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
#include "HdKillCam.h"
#include <algorithm>
#include <cstdlib>
#include "Logger.h"

namespace OpenXcom
{

namespace HdKillCam
{

namespace
{

const double ZOOM = 1.8;        // the enlargement at its full
const double BARS = 0.09;       // the height the black bars take at the full zoom, top and bottom each
const Uint32 IN_MS = 350;       // the zoom in
const Uint32 SCENE_MS = 4000;   // the whole scene, zoom out included: the hold makes up what the fall left
const Uint32 HOLD_MS = 500;     // the body on the ground, at the least (a long pirouette)
const Uint32 OUT_MS = 450;      // the zoom out
const Uint32 SKIP_OUT_MS = 180; // the zoom out after a key or a click
const double SLOW = 3.0;        // the fall, this many times slower at the full
const Uint32 RAMP_MS = 500;     // the slowing comes on over this long, not at once
const Uint32 LIMIT_MS = 15000;  // a scene never lasts longer, whatever its state does

bool _on = false;
Position _voxel;
Uint32 _start = 0, _fallen = 0, _out = 0, _outMs = OUT_MS;
double _outFrom = ZOOM;

double ease(double t)
{
	t = std::min(1.0, std::max(0.0, t));
	return t * t * (3.0 - 2.0 * t);
}

/// The zoom of the way in at `now`.
double zoomIn(Uint32 now)
{
	return 1.0 + (ZOOM - 1.0) * ease((now - _start) / (double)IN_MS);
}

/// Moves the scene on to the phase due at `now`; returns the zoom (the scene may end here).
double update(Uint32 now)
{
	if (!_on)
	{
		return 1.0;
	}
	if (now - _start > LIMIT_MS)
	{
		Log(LOG_WARNING) << "HD killcam: the scene ran over " << LIMIT_MS << " ms, dropped";
		_on = false;
		return 1.0;
	}
	if (_out == 0 && _fallen != 0)
	{
		// the fall takes from about one to three seconds (a pirouette of up to seven turns first):
		// the hold evens it out, so every final blow lasts the same
		const Uint32 fall = std::min(SCENE_MS - OUT_MS, _fallen - _start);
		const Uint32 hold = std::max(HOLD_MS, SCENE_MS - OUT_MS - fall);
		if (now - _fallen >= hold)
		{
			_outFrom = zoomIn(now);
			_out = now;
			_outMs = OUT_MS;
		}
	}
	if (_out == 0)
	{
		return zoomIn(now);
	}
	if (now - _out >= _outMs)
	{
		_on = false;
		Log(LOG_INFO) << "HD killcam: done in " << (now - _start) << " ms";
		return 1.0;
	}
	return 1.0 + (_outFrom - 1.0) * (1.0 - ease((now - _out) / (double)_outMs));
}

}

void start(Position voxel)
{
	_on = true;
	_voxel = voxel;
	_start = SDL_GetTicks();
	_fallen = _out = 0;
	Log(LOG_INFO) << "HD killcam: the last enemy falls at voxel " << voxel;
}

bool running()
{
	update(SDL_GetTicks());
	return _on;
}

Uint32 pace(Uint32 ms)
{
	const Uint32 now = SDL_GetTicks();
	update(now);
	if (!_on)
	{
		return ms;
	}
	if (_fallen != 0)
	{
		return std::min<Uint32>(ms, 16); // waiting out the hold: look often
	}
	if (_out != 0)
	{
		return ms; // skipped during the fall: the classic pace
	}
	return (Uint32)(ms * (1.0 + (SLOW - 1.0) * ease((now - _start) / (double)RAMP_MS)) + 0.5);
}

bool hold()
{
	if (!_on)
	{
		return false;
	}
	const Uint32 now = SDL_GetTicks();
	if (_fallen == 0)
	{
		_fallen = now;
	}
	update(now);
	return _on;
}

void skip()
{
	const Uint32 now = SDL_GetTicks();
	const double zoom = update(now);
	if (_on && (_out == 0 || _outMs != SKIP_OUT_MS))
	{
		_outFrom = zoom;
		_out = now;
		_outMs = SKIP_OUT_MS;
	}
}

bool view(Position &voxel, double &zoom, double &pull, double &bars)
{
	zoom = update(SDL_GetTicks());
	if (!_on || zoom <= 1.0)
	{
		return false;
	}
	voxel = _voxel;
	pull = (zoom - 1.0) / (ZOOM - 1.0);
	bars = BARS * pull;
	return true;
}

void clear()
{
	_on = false;
}

std::string takeTestDump(Uint32 now)
{
	static const char *prefix = getenv("OXCE_HD_DUMP_KILLCAM");
	static const Uint32 moments[] = { 200, 700, 1500, 2600, 3700 }; // zoom in, the fall, the hold, the zoom out
	static size_t next = 0;
	if (!prefix || !*prefix || _start == 0 || next >= sizeof(moments) / sizeof(moments[0]) || now - _start < moments[next])
	{
		return "";
	}
	Log(LOG_INFO) << "HD killcam: dump " << next << " at " << (now - _start) << " ms, running " << _on;
	return std::string(prefix) + "_" + std::to_string(next++) + ".png";
}

}

}
