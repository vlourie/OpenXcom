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
#include "Surface.h"

namespace OpenXcom
{

class Game;
class ClassicPlateCanvas;
class PlateCanvas;

/**
 * XP-000575: the plate "note, the track's name" in the bottom left corner, over every screen, for three seconds at every
 * change of the music (oxceMusicTrackNotice, on by default). It looks at the count of starts in the Mod; the name comes
 * from the mod's track list. Drawn like the other plates, after the frame of an HD test dump is taken, so no dump
 * has it. Takes no input. Classic: the nearest colours of the palette; HD: vectors.
 */
class HdTrackNotice : public Surface
{
private:
	Game *_game;
	std::string _title, _shown;
	int _serialSeen;
	Uint32 _until;
	ClassicPlateCanvas *_classic;
	/// Cuts the title to the plate's room and paints the plate with the canvas.
	void paint(PlateCanvas &canvas);
public:
	/// Creates the plate (hidden until the music changes).
	HdTrackNotice(Game *game);
	/// Cleans up the plate.
	~HdTrackNotice();
	/// Sets the plate's palette (the state's, as the other plates').
	void setPalette(const SDL_Color *colors, int firstcolor = 0, int ncolors = 256) override;
	/// Looks at the music's change count and ends the time of the plate.
	void think() override;
	/// Draws the classic plate.
	void draw() override;
	/// Puts the plate on the screen's bottom left corner.
	void blit(SDL_Surface *surface) override;
	/// The HD plate.
	void hdMirror() override;
};

}
