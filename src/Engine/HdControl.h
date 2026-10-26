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

namespace OpenXcom
{

class Game;

/**
 * The live test bench (docs/research/hd-test-bench-2026-10-26.md): under OXCE_HD_CONTROL=<folder> the game
 * does not quit after a frame but takes commands from <folder>/cmd.txt (clicks, keys, frames, options, saves)
 * and answers in <folder>/done.<n>. Without the variable nothing here runs. Driven by tools/hdbench.py.
 */
namespace HdControl
{
	/// Is the bench on (OXCE_HD_CONTROL is set)?
	bool enabled();
	/// A frame was drawn: the commands go one per drawn frame.
	void frameDrawn();
	/// Once per loop turn, after the events and with the states initialised: takes a new batch of commands, runs the next one.
	void step(Game *game);
}

}
