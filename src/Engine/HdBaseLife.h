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
 * their feet carry a lantern (a light of HdBaseScene). They walk only over the bare floor of the
 * pictures, never through furniture or machines. Scientists in a lab and engineers in a workshop at work
 * stand at the furniture working with their hands, something lighting up in them now and then, and step
 * to the next table every 6-10 s. In the hangars (OXCE_HD_HANGAR_LIFE=1, a pilot) the hands work by the craft's
 * state: two weld at the hull of a craft under repair, two carry the ammunition to one rearming, one holds the
 * hose of one refuelling.
 *
 * How many walk and where they go is read from the base; where each of them is comes from the crew's
 * own dice and the display clock. Nothing of the game is changed and the game's random numbers are
 * never drawn.
 */
namespace HdBaseLife
{
	const int SIZE = 6;
	/// Squares of the crew's walking grid to a cell, per side.
	const int SUB = 8;

	/// What a facility is to the crew (bits).
	enum Place { LAB = 1, WORK = 2, HOME = 4, PRISON = 8, MED = 16, GYM = 32, HANGAR = 64, STORE = 128, OTHER = 256,
		BUILD = 512 };

	/// The base as the crew sees it.
	struct Plan
	{
		int facility[SIZE][SIZE] = {};    ///< [x][y]: the facility's number + 1; 0 - no floor to walk on
		int place[SIZE][SIZE] = {};       ///< [x][y]: Place bits of that facility
		/// [x][y] of the walking grid: 1 - bare floor of the picture (the walk of its .scene.txt); the crew
		/// stands and walks only there, and goes from room to room through the middle of a shared side
		unsigned char walk[SIZE * SUB][SIZE * SUB] = {};
		int scientists = 0, engineers = 0, soldiers = 0;
		bool researching = false, producing = false;
		Uint32 seed = 0;                  ///< tells one base from another
		/// The crafts in the hangars, in the state their lights show (HdCraftLights::Status) - the hangar
		/// hands work by it (OXCE_HD_HANGAR_LIFE=1, the pilot of 26.10)
		struct Craft
		{
			int status = 0;               ///< CRAFT_READY...
			float fuelX = 0, fuelY = 0;   ///< the fuel garland of its hangar, grid cells: the hose comes from there
		};
		std::vector<Craft> crafts;
		/// [x][y] of the walking grid: the craft's number + 1 over the squares its picture covers - nobody
		/// walks there, the hangar hands stand at its edge
		unsigned char hull[SIZE * SUB][SIZE * SUB] = {};
	};
	/// The states of a craft as HdCraftLights::Status numbers them.
	enum CraftState { CRAFT_READY, CRAFT_BUSY, CRAFT_REPAIRS, CRAFT_REARMING, CRAFT_NO_CREW };

	/// Moves the crew on to `ms` of the display clock and draws it into the world layer, the grid's
	/// corner at (ox, oy) and `cell` world pixels to a grid cell. Before the light: the figures darken at
	/// night with the rooms, and their lanterns are added to `lights`.
	void draw(SDL_Surface *world, const Plan &plan, int ox, int oy, int cell, float night, Uint32 ms,
		std::vector<HdBaseScene::Placed> &lights);
}

}
