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
#include "BaseSwitch.h"
#include "../Savegame/SavedGame.h"
#include "BaseInfoState.h"
#include "BasescapeState.h"

namespace OpenXcom
{

namespace BaseSwitch
{

/**
 * Finds the neighbouring base the screen can show.
 * @param game Pointer to the core game.
 * @param base Base shown now.
 * @param dir -1 previous, +1 next; the list goes round.
 * @param fits Bases the screen can show.
 * @return The base, or nullptr if no other base fits.
 */
Base *neighbour(Game *game, const Base *base, int dir, const Filter &fits)
{
	const auto &bases = *game->getSavedGame()->getBases();
	const int n = (int)bases.size();
	int at = -1;
	for (int i = 0; i < n; ++i)
	{
		if (bases[i] == base)
		{
			at = i;
			break;
		}
	}
	if (at < 0)
	{
		return nullptr;
	}
	for (int step = 1; step < n; ++step)
	{
		Base *other = bases[((at + dir * step) % n + n) % n];
		if (!fits || fits(other))
		{
			return other;
		}
	}
	return nullptr;
}

/**
 * Replaces the top screen with the same screen of another base.
 * The base screens right below it (basescape, base information) switch to that base too,
 * so going back leads to the base the player switched to; anything else below stops the walk.
 * @param game Pointer to the core game.
 * @param next The new screen.
 * @param base Base of the new screen.
 */
void replace(Game *game, State *next, Base *base)
{
	const auto &states = game->getStates();
	auto i = states.rbegin();
	if (i != states.rend())
	{
		++i;
	}
	for (; i != states.rend(); ++i)
	{
		if (auto *info = dynamic_cast<BaseInfoState*>(*i))
		{
			info->setBase(base);
		}
		else if (auto *basescape = dynamic_cast<BasescapeState*>(*i))
		{
			basescape->setBase(base);
		}
		else
		{
			break;
		}
	}
	game->popState();
	game->pushState(next);
}

}

}
