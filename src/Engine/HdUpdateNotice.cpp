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
#include "HdUpdateNotice.h"
#include <cctype>
#include <istream>
#include "CrossPlatform.h"
#include "Game.h"
#include "Language.h"
#include "Options.h"
#include "../Interface/Text.h"
#include "../Mod/Mod.h"

namespace OpenXcom
{

/// How often the file is looked at: a stat and a line, nothing per frame. Five minutes, as the launcher's
/// own look (UpdateWatch.Every); a day once releases stop coming every few hours.
static const Uint32 LOOK_EVERY_MS = 5 * 60 * 1000;
/// The plate is one line of the small font with a frame round it.
static const int PLATE_HEIGHT = 11;

HdUpdateNotice::HdUpdateNotice(Game *game) : Surface(320, PLATE_HEIGHT, 0, 0), _game(game), _text(0), _nextLook(0), _color(0), _plate(0)
{
	_visible = false;
}

HdUpdateNotice::~HdUpdateNotice()
{
	delete _text;
}

void HdUpdateNotice::setPalette(const SDL_Color *colors, int firstcolor, int ncolors)
{
	Surface::setPalette(colors, firstcolor, ncolors);
	if (_text)
	{
		_text->setPalette(colors, firstcolor, ncolors);
	}
	_redraw = true;
}

void HdUpdateNotice::setColor(Uint8 color)
{
	_color = color;
	if (_text)
	{
		_text->setColor(color);
	}
	_redraw = true;
}

/**
 * Looks at launcher/update.txt next to the exe at start and every five minutes: its first line is the release out.
 */
void HdUpdateNotice::think()
{
	const Uint32 now = SDL_GetTicks();
	if (now < _nextLook)
	{
		return;
	}
	_nextLook = now + LOOK_EVERY_MS;
	std::string release;
	const std::string path = CrossPlatform::getExeFolder() + "launcher/update.txt";
	if (Options::oxceHdUpdateNotice && CrossPlatform::fileExists(path))
	{
		auto file = CrossPlatform::readFile(path);
		if (file)
		{
			std::getline(*file, release);
		}
		// one short name; anything else in the file is not shown
		while (!release.empty() && std::isspace((unsigned char)release.back()))
		{
			release.pop_back();
		}
		if (release.size() > 40)
		{
			release.clear();
		}
	}
	if (release != _release)
	{
		_release = release;
		_redraw = true;
	}
	_visible = !_release.empty();
}

/**
 * The words "a new update is available: <release>" in a dark plate with a frame in the cursor's colour.
 */
void HdUpdateNotice::draw()
{
	Surface::draw();                               // clears to the transparent colour
	if (_release.empty() || !_game->getMod() || !_game->getLanguage())
	{
		_plate = 0;
		return;
	}
	if (!_text)
	{
		_text = new Text(getWidth() - 4, 9, 0, 0);
		_text->setPalette(getPalette());
		_text->setColor(_color);
	}
	_text->initText(_game->getMod()->getFont("FONT_BIG"), _game->getMod()->getFont("FONT_SMALL"), _game->getLanguage());
	_text->setSmall();
	_text->setText(_game->getLanguage()->getString("STR_HD_UPDATE_AVAILABLE").arg(_release));
	_plate = std::min(getWidth(), _text->getTextWidth() + 6);

	// the darkest colour of this palette behind the words: every screen has its own palette
	Uint8 dark = 1;
	int best = 1 << 30;
	const SDL_Color *pal = getPalette();
	for (int i = 1; pal && i < 256; ++i)
	{
		const int y = pal[i].r * 3 + pal[i].g * 6 + pal[i].b;
		if (y < best)
		{
			best = y;
			dark = (Uint8)i;
		}
	}
	drawRect(0, 0, _plate, PLATE_HEIGHT, _color);
	drawRect(1, 1, _plate - 2, PLATE_HEIGHT - 2, dark);
}

void HdUpdateNotice::blit(SDL_Surface *surface)
{
	if (!_visible)
	{
		return;
	}
	if (_redraw)
	{
		draw();
	}
	if (_plate == 0)
	{
		return;
	}
	// under the FPS counter when that is on
	const int y = Options::fpsCounter ? 6 : 0;
	setY(y);
	Surface::blit(surface);
	_text->setX(getX() + 3);
	_text->setY(y + 2);
	_text->blit(surface);
}

}
