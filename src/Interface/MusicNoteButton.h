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
#include "../Engine/InteractiveSurface.h"

namespace OpenXcom
{

class Game;
class PlateCanvas;
class ClassicPlateCanvas;

/**
 * XP-000575: the small button with a note that opens the music player (the geoscape's clock, the battle's panel).
 * 9 x 9 base pixels; a grey key with the note in dark ink, in the nearest colours of the palette (classic) or in
 * vectors (HD). The click handler is set like any button's (onMouseClick).
 */
class MusicNoteButton : public InteractiveSurface
{
private:
	Game *_game;
	ClassicPlateCanvas *_classic;
	bool _down;
	void paint(PlateCanvas &c);
public:
	MusicNoteButton(Game *game, int x, int y);
	~MusicNoteButton();
	void draw() override;
	void hdMirror() override;
	void mousePress(Action *action, State *state) override;
	void mouseRelease(Action *action, State *state) override;
};

}
