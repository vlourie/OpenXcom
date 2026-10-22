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
class Text;

/**
 * The plate "a new update is available" in the top left corner, over every screen (oxceHdUpdateNotice).
 *
 * The launcher watches the release channel while the game runs and, when a release newer than the
 * installed one is out, writes its name into launcher/update.txt next to the exe (portal, Core/UpdateNotice.cs);
 * the file goes once the update is installed. The game only reads it: a look every ten seconds, the plate
 * shows while the file is there. Drawn like the FPS counter, after the frame of an HD test dump is taken, so
 * no dump ever has it; under the counter when that is on.
 */
class HdUpdateNotice : public Surface
{
private:
	Game *_game;
	Text *_text;
	std::string _release, _shown;
	Uint32 _nextLook;
	Uint8 _color;
	/// The width of the plate itself; the rest of the surface stays transparent.
	int _plate;
public:
	/// Creates the plate (hidden until the launcher says something).
	HdUpdateNotice(Game *game);
	/// Cleans up the plate.
	~HdUpdateNotice();
	/// Sets the plate's palette (the state's, as the FPS counter's).
	void setPalette(const SDL_Color *colors, int firstcolor = 0, int ncolors = 256) override;
	/// Sets the colour of the frame and the words.
	void setColor(Uint8 color) override;
	/// Looks at launcher/update.txt now and then.
	void think() override;
	/// Draws the plate.
	void draw() override;
	/// Puts the plate on the screen, the words on their own so the HD interface draws them with its font.
	void blit(SDL_Surface *surface) override;
};

}
