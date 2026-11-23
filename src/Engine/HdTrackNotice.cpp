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
#include "HdTrackNotice.h"
#include <algorithm>
#include <cmath>
#include <vector>
#include "Game.h"
#include "HdPlateCanvas.h"
#include "HdUi.h"
#include "Language.h"
#include "Options.h"
#include "../Mod/Mod.h"

namespace OpenXcom
{

/// How long the plate stays.
static const Uint32 SHOW_MS = 3000;
/// The surface is as wide as the widest plate; the plate sits at its left end.
static const int SURFACE_WIDTH = 240;
static const int PLATE_HEIGHT = 13;
static const int MAX_TEXT = SURFACE_WIDTH - 8 - 11;

HdTrackNotice::HdTrackNotice(Game *game) : Surface(SURFACE_WIDTH, PLATE_HEIGHT, 0, 0), _game(game), _serialSeen(0), _until(0), _classic(0)
{
	_visible = false;
}

HdTrackNotice::~HdTrackNotice()
{
	delete _classic;
}

void HdTrackNotice::setPalette(const SDL_Color *colors, int firstcolor, int ncolors)
{
	Surface::setPalette(colors, firstcolor, ncolors);
	_redraw = true;
}

void HdTrackNotice::think()
{
	Mod *mod = _game->isDataReady() ? _game->getMod() : 0;
	if (!mod)
	{
		return;
	}
	const Uint32 now = SDL_GetTicks();
	const int serial = mod->getMusicSerial();
	if (serial != _serialSeen)
	{
		_serialSeen = serial;
		const std::string &key = mod->getCurrentMusicTrack();
		if (Options::oxceMusicTrackNotice && !Options::mute && !key.empty())
		{
			const std::string title = mod->getMusicTitle(key, _game->getLanguage());
			if (!title.empty())
			{
				_title = title;
				_until = now + SHOW_MS;
				_visible = true;
				_redraw = true;
			}
		}
	}
	if (_visible && (Sint32)(now - _until) >= 0)
	{
		_visible = false;
	}
}

/**
 * The title cut to the plate's room at a character's edge ("..." for the rest), then the plate: a dark frame, the
 * note, the words in the LCD green of the player.
 */
void HdTrackNotice::paint(PlateCanvas &c)
{
	std::vector<size_t> edges;
	for (size_t i = 0; i < _title.size();)
	{
		const unsigned char ch = (unsigned char)_title[i];
		i += (ch < 0x80) ? 1 : (ch < 0xE0) ? 2 : (ch < 0xF0) ? 3 : 4;
		edges.push_back(std::min(i, _title.size()));
	}
	_shown = _title;
	if (c.textWidth(_shown, false) > MAX_TEXT)
	{
		size_t lo = 0, hi = edges.size();
		while (lo < hi)
		{
			const size_t mid = (lo + hi + 1) / 2;
			if (c.textWidth(_title.substr(0, edges[mid - 1]) + "...", false) <= MAX_TEXT)
			{
				lo = mid;
			}
			else
			{
				hi = mid - 1;
			}
		}
		_shown = lo == 0 ? std::string("...") : _title.substr(0, edges[lo - 1]) + "...";
	}
	const float w = std::min((float)SURFACE_WIDTH, std::ceil(c.textWidth(_shown, false)) + 8 + 11);
	c.fill(0, 0, w, PLATE_HEIGHT, 0xFF000000);
	c.fill(1, 1, w - 2, PLATE_HEIGHT - 2, 0xFF2B2B3A);
	c.fill(2, 2, w - 4, PLATE_HEIGHT - 4, 0xFF000000);
	c.note(3, 1, 0xFFE8C060);
	c.text(_shown, 13, 3, 0xFF00E800, false);
}

void HdTrackNotice::draw()
{
	Surface::draw();
	if (_title.empty() || !_game->isDataReady() || (HdUi::active() && HdUi::instance().hasFonts()))
	{
		return;
	}
	if (!_classic)
	{
		_classic = new ClassicPlateCanvas(this, _game->getMod()->getFont("FONT_BIG"), _game->getMod()->getFont("FONT_SMALL"), _game->getLanguage());
	}
	_classic->begin();
	paint(*_classic);
}

void HdTrackNotice::blit(SDL_Surface *surface)
{
	if (!_visible)
	{
		return;
	}
	setX(1);
	setY(surface->h - getHeight() - 1);
	Surface::blit(surface);
}

void HdTrackNotice::hdMirror()
{
	HdUi &ui = HdUi::instance();
	if (!ui.hasFonts() || _title.empty() || !_game->isDataReady())
	{
		Surface::hdMirror();
		return;
	}
	HdPlateCanvas canvas((float)getX(), (float)getY(), _game->getMod()->getFont("FONT_BIG"), _game->getMod()->getFont("FONT_SMALL"));
	paint(canvas);
}

}
