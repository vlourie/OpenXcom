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
#include "Options.h"

namespace OpenXcom
{

/**
 * Gentle mode, for players sensitive to flashing light (docs/research/gentle-mode.md).
 * It never writes the player's own settings: the places that read a setting it governs
 * ask here instead, so turning the mode off brings back exactly what the player had.
 *
 * Picture and pace only. Nothing here may be read by the game rules (fire, sight, AI,
 * saves): tools/test_gentle_scope.py lists the files allowed to call it.
 */
namespace HdGentle
{
	/// Unit steps while the mode is on: twice the stock 30 ms (Options::battleXcomSpeed).
	constexpr int UNIT_SPEED = 60;
	/// Projectile pixels per frame while the mode is on: half the stock 6.
	constexpr int FIRE_SPEED = 3;
	/// The camera does not fly after any shot; it only goes to hits on own and neutral units (Map::drawTerrain).
	constexpr int TRACE_PROJECTILES = 3;

	inline bool on() { return Options::oxceGentle; }

	inline int xcomSpeed() { return on() ? UNIT_SPEED : Options::battleXcomSpeed; }
	inline int alienSpeed() { return on() ? UNIT_SPEED : Options::battleAlienSpeed; }
	inline int fireSpeed() { return on() ? FIRE_SPEED : Options::battleFireSpeed; }
	inline int traceProjectiles() { return on() ? TRACE_PROJECTILES : Options::QOL::dontTraceProjectiles; }
	inline bool smoothCamera() { return on() || Options::battleSmoothCamera; }
	/// The final blow zooms in at once: off while the mode is on.
	inline bool killCam() { return !on() && Options::oxceHdKillCam; }

	/// Is this setting fixed by the mode? The option screens show it greyed with a note and ignore clicks.
	inline bool locks(const void *option)
	{
		return on() && (option == &Options::battleXcomSpeed || option == &Options::battleAlienSpeed
			|| option == &Options::battleFireSpeed || option == &Options::QOL::dontTraceProjectiles
			|| option == &Options::battleSmoothCamera || option == &Options::oxceHdKillCam);
	}

	/// The variable behind a row of an option list (asBool throws on an option of another type).
	inline const void *target(const OptionInfo &info)
	{
		if (info.type() == OPTION_BOOL)
			return info.asBool();
		if (info.type() == OPTION_INT)
			return info.asInt();
		return nullptr;
	}

	/// Is this row of an option list fixed by the mode?
	inline bool locks(const OptionInfo &info) { return locks(target(info)); }

	/// The value the mode holds a locked setting at (a bool as 0 or 1), what its row shows.
	inline int lockedValue(const void *option)
	{
		if (option == &Options::battleXcomSpeed || option == &Options::battleAlienSpeed)
			return UNIT_SPEED;
		if (option == &Options::battleFireSpeed)
			return FIRE_SPEED;
		if (option == &Options::QOL::dontTraceProjectiles)
			return TRACE_PROJECTILES;
		if (option == &Options::battleSmoothCamera)
			return 1;
		return 0;                                     // oxceHdKillCam
	}
}

}
