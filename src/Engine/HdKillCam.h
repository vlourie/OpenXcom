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
#include "../Battlescape/Position.h"

namespace OpenXcom
{

/**
 * HD render: the final blow. When the last enemy falls to a shot or a blow, the camera zooms in
 * on it, the fall plays slowed down (the slowing comes on smoothly), the body is held for a moment
 * and the camera zooms back out; only then does the battle go on (the "all enemies neutralized"
 * question). The hold evens out the fall, so every scene lasts about the same four seconds.
 *
 * Picture and pace only: the dying unit's state ticks slower and waits at its end, the same ticks
 * in the same order, so no number, turn or random roll changes. The enlargement is applied when
 * the map's canvas is copied to the screen (Canvas32::copyZoomed); the canvas itself, the classic
 * layer and the test dumps stay as they are. A key or a click zooms back out at once.
 */
namespace HdKillCam
{
	/// Starts the scene on a voxel (the middle of the victim).
	void start(Position voxel);
	/// Is a scene on (started and not yet zoomed back out)?
	bool running();
	/// The interval the dying unit's state ticks at, for its classic interval `ms`.
	Uint32 pace(Uint32 ms);
	/// The fall is over: true while the scene still shows the body (the hold, then the zoom out).
	bool hold();
	/// A key or a click: the scene zooms back out at once.
	void skip();
	/// The enlargement to draw now (zoom >= 1; pull 0..1: how far the victim has moved to the middle
	/// of the screen; bars 0..1: the share of the height the black bars take). False: none.
	bool view(Position &voxel, double &zoom, double &pull, double &bars);
	/// Forgets the scene (a new battle).
	void clear();
	/// Headless checks: with OXCE_HD_DUMP_KILLCAM=<prefix> the first scene asks for dumps of five
	/// of its moments (<prefix>_0.png .. _4.png); the dump file due at `now`, or empty.
	std::string takeTestDump(Uint32 now);
}

}
