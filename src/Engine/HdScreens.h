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
#include <string>

namespace OpenXcom
{

/**
 * The HD interface's screen pictures: a painted scene per theme of screens (research, the workshop,
 * the crew, the market...) shown inside a window of the modern skin instead of its classic background,
 * and the window's frame in the metal of the battle panel (oxceHdBattleHudColor).
 *
 * The hd mod lists the themes in hd/UI/screens/screens.txt, one per line:
 *     research.png = allocateResearch researchMenu selectNewResearch ...
 * the picture (in hd/UI/screens) and the interfaces (the rulesets' interface ids, the name a state gives
 * State::setWindowBackground) it is shown in. The picture is fitted to the window (cover), muted and kept
 * well below the text's light; where the window's text lay in the last frame it is frosted (blurred and
 * darkened), so the letters stand on calm dark ground, and the text over it gets a dark halo of its own
 * (HdUi::drawTtfLine). Nothing changes in the classic layer: without the HD skin, or without a picture
 * for the screen, the window is drawn as before.
 */
namespace HdScreens
{
	/// Reads hd/UI/screens/screens.txt of the mods (after the mods load); forgets the old table and pictures.
	void load();
	/// Is there a theme picture for this interface (and the pictures option on)?
	bool has(const std::string &interfaceName);
	/// A line may list several pictures (hidden.png hidden_jungle.png ... = nextTurn hiddenMovement): shows another
	/// of them from now on in all the line's screens (a new turn); one picture - nothing changes.
	void nextVariant(const std::string &interfaceName);
	/// Draws the theme picture of `interfaceName` filling the base rectangle (x, y, w, h), clipped to the HD
	/// interface's clip; `owner` (the window) names whose text frosts it. False when there is none.
	bool drawBackdrop(const void *owner, const std::string &interfaceName, int x, int y, int w, int h);
	/// Is the window frame drawn in the battle panel's metal (the HD skin with screen pictures in the mods)?
	bool metalFrames();
	/// The window frame in the battle panel's metal around the base rectangle (x, y, w, h): a moulded band
	/// `inset` base pixels wide with rivets along it (not on a thin one), a thin line of `accent` inside.
	void drawFrame(int x, int y, int w, int h, int inset, bool thin, Uint32 accent);
	/// Forgets the prepared pictures and frames (scale change, mod reload).
	void clearCaches();
}

}
