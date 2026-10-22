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
#include <vector>
#include <SDL.h>
#include "HdBaseScene.h"

namespace OpenXcom
{

/**
 * The crew of the "living base" (docs/research/base-living-2026-10-22.md, stage 4): little figures seen
 * from above walk between the facilities - scientists to the labs while the base researches, engineers
 * to the workshops while it builds, the crew about the gym, stores and hangars, a guard by the prison
 * and a nurse in the sick bay. At night all but the night shift go home to sleep, and those still on
 * their feet carry a lantern (a light of HdBaseScene).
 *
 * How many walk and where they go is read from the base; where each of them is comes from the crew's
 * own dice and the display clock. Nothing of the game is changed and the game's random numbers are
 * never drawn.
 */
namespace HdBaseLife
{
	const int SIZE = 6;

	/// What a facility is to the crew (bits).
	enum Place { LAB = 1, WORK = 2, HOME = 4, PRISON = 8, MED = 16, GYM = 32, HANGAR = 64, STORE = 128, OTHER = 256,
		BUILD = 512 };

	/// The base as the crew sees it.
	struct Plan
	{
		int facility[SIZE][SIZE] = {};    ///< [x][y]: the facility's number + 1; 0 - no floor to walk on
		int place[SIZE][SIZE] = {};       ///< [x][y]: Place bits of that facility
		int scientists = 0, engineers = 0, soldiers = 0;
		bool researching = false, producing = false;
		Uint32 seed = 0;                  ///< tells one base from another
	};

	/// Moves the crew on to `ms` of the display clock and draws it into the world layer, the grid's
	/// corner at (ox, oy) and `cell` world pixels to a grid cell. Before the light: the figures darken at
	/// night with the rooms, and their lanterns are added to `lights`.
	void draw(SDL_Surface *world, const Plan &plan, int ox, int oy, int cell, float night, Uint32 ms,
		std::vector<HdBaseScene::Placed> &lights);
}

}
