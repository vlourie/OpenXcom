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
#include <ctime>
#include <string>
#include "Surface.h"

namespace OpenXcom
{

class Game;
class Text;

/**
 * The plate "a new message" in the top right corner, over every screen (oxceHdChatNotice).
 *
 * The launcher writes launcher/chat.txt next to the exe while the game runs and a private message or a mention
 * comes in (portal, Core/ChatNotice.cs): the first line is a counter that only grows, the second is
 * "nick: the start of the text". The game only reads it: a look at the file's date every two seconds, the file
 * itself only when the date is new. A new counter shows the plate for six seconds. The file found at the first
 * look is an old message and is not shown.
 *
 * The text comes from other players, so for the engine it is only a string to show: the file is read up to 4 KiB,
 * invalid UTF-8 and control characters are dropped, the line is cut to the plate's width, and the words go to the
 * Text widget as they are, never through the language's markup. Drawn like the FPS counter, after the frame of an
 * HD test dump is taken, so no dump ever has it. Takes no input.
 */
class HdChatNotice : public Surface
{
private:
	Game *_game;
	Text *_text;
	/// What the plate says (clean, not yet cut) and the same cut to the plate's width.
	std::string _line, _shown;
	Uint32 _nextLook, _until;
	time_t _date;
	unsigned long long _counter;
	/// False until the first look at the file is over: what it held then is an old message.
	bool _baseline;
	Uint8 _color;
	/// The width of the plate itself; it sits at the right end of the surface, the rest stays transparent.
	int _plate;
	/// Reads the file and, for a new counter, takes its words.
	void readFile(const std::string &path, Uint32 now);
public:
	/// Creates the plate (hidden until the launcher says something).
	HdChatNotice(Game *game);
	/// Cleans up the plate.
	~HdChatNotice();
	/// Sets the plate's palette (the state's, as the FPS counter's).
	void setPalette(const SDL_Color *colors, int firstcolor = 0, int ncolors = 256) override;
	/// Sets the colour of the frame and the words.
	void setColor(Uint8 color) override;
	/// Looks at launcher/chat.txt now and then.
	void think() override;
	/// Draws the plate.
	void draw() override;
	/// Puts the plate on the screen, the words on their own so the HD interface draws them with its font.
	void blit(SDL_Surface *surface) override;
	/// Makes a clean line to show out of a raw one from the file.
	static std::string clean(const std::string &raw);
};

}
