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
#include "HdChatNotice.h"
#include <algorithm>
#include <vector>
#include "CrossPlatform.h"
#include "Game.h"
#include "Language.h"
#include "Options.h"
#include "../Interface/Text.h"
#include "../Mod/Mod.h"

namespace OpenXcom
{

/// How often the file's date is looked at: one stat, nothing per frame.
static const Uint32 LOOK_EVERY_MS = 2000;
/// How long a new message stays on the screen.
static const Uint32 SHOW_MS = 6000;
/// A bigger file is not a message of ours; it is not read at all.
static const size_t MAX_FILE = 4096;
/// Characters kept of a line before it is cut to the plate's width.
static const size_t MAX_CHARS = 160;
/// The surface is as wide as the widest plate; it is set at the screen's right edge.
static const int SURFACE_WIDTH = 200;
static const int MAX_TEXT = SURFACE_WIDTH - 10;
/// The plate is one line of the small font with a frame round it.
static const int PLATE_HEIGHT = 11;

HdChatNotice::HdChatNotice(Game *game) : Surface(SURFACE_WIDTH, PLATE_HEIGHT, 0, 0), _game(game), _text(0), _nextLook(0), _until(0), _date(0), _counter(0), _baseline(false), _color(0), _plate(0)
{
	_visible = false;
}

HdChatNotice::~HdChatNotice()
{
	delete _text;
}

void HdChatNotice::setPalette(const SDL_Color *colors, int firstcolor, int ncolors)
{
	Surface::setPalette(colors, firstcolor, ncolors);
	if (_text)
	{
		_text->setPalette(colors, firstcolor, ncolors);
	}
	_redraw = true;
}

void HdChatNotice::setColor(Uint8 color)
{
	_color = color;
	if (_text)
	{
		_text->setColor(color);
	}
	_redraw = true;
}

/**
 * Keeps the characters of a raw line that can be shown: valid UTF-8 only, no control characters (those include the
 * language's own markup tokens, new line and colour flip), no direction overrides, no characters of four bytes
 * (the fonts have none). A tab is a space; spaces at the ends go.
 * @param raw A line of the file.
 * @return The line to show.
 */
std::string HdChatNotice::clean(const std::string &raw)
{
	std::string out;
	size_t chars = 0;
	size_t i = 0;
	const size_t n = raw.size();
	while (i < n && chars < MAX_CHARS)
	{
		const unsigned char c = (unsigned char)raw[i];
		unsigned int cp = 0;
		size_t len = 1;
		if (c < 0x80)
		{
			cp = c;
		}
		else if (c >= 0xC2 && c <= 0xDF)
		{
			len = 2;
			cp = c & 0x1F;
		}
		else if (c >= 0xE0 && c <= 0xEF)
		{
			len = 3;
			cp = c & 0x0F;
		}
		else
		{
			++i; // a stray continuation byte, a four byte character or a byte never found in UTF-8
			continue;
		}
		bool ok = i + len <= n;
		for (size_t k = 1; ok && k < len; ++k)
		{
			const unsigned char d = (unsigned char)raw[i + k];
			ok = (d & 0xC0) == 0x80;
			cp = (cp << 6) | (d & 0x3F);
		}
		if (!ok || (len == 3 && (cp < 0x800 || (cp >= 0xD800 && cp <= 0xDFFF))))
		{
			++i;
			continue;
		}
		const std::string piece = raw.substr(i, len);
		i += len;
		if (cp == '\t')
		{
			cp = ' ';
		}
		if (cp < 0x20 || (cp >= 0x7F && cp <= 0x9F) || (cp >= 0x200B && cp <= 0x200F) || (cp >= 0x2028 && cp <= 0x202E) ||
			(cp >= 0x2060 && cp <= 0x206F) || cp == 0xFEFF || cp >= 0xFFF0)
		{
			continue;
		}
		out += (cp == ' ') ? std::string(" ") : piece;
		++chars;
	}
	const size_t b = out.find_first_not_of(' ');
	if (b == std::string::npos)
	{
		return std::string();
	}
	return out.substr(b, out.find_last_not_of(' ') - b + 1);
}

/**
 * Reads the file (4 KiB at most) and, when the first line is a number that was not seen, takes the second line as the words.
 * Anything else in the file is ignored: no digits, a number too long, one line only.
 */
void HdChatNotice::readFile(const std::string &path, Uint32 now)
{
	SDL_RWops *rw = SDL_RWFromFile(path.c_str(), "rb");
	if (!rw)
	{
		return;
	}
	char buf[MAX_FILE + 1];
	const size_t got = SDL_RWread(rw, buf, 1, sizeof(buf));
	SDL_RWclose(rw);
	if (got == 0 || got > MAX_FILE)
	{
		return;
	}
	std::string data(buf, got);
	if (data.compare(0, 3, "\xEF\xBB\xBF") == 0)
	{
		data.erase(0, 3);
	}
	const size_t nl = data.find('\n');
	std::string first = data.substr(0, nl);
	std::string second;
	if (nl != std::string::npos)
	{
		const size_t nl2 = data.find('\n', nl + 1);
		second = data.substr(nl + 1, nl2 == std::string::npos ? std::string::npos : nl2 - nl - 1);
	}
	while (!first.empty() && (first.back() == '\r' || first.back() == ' '))
	{
		first.pop_back();
	}
	if (first.empty() || first.size() > 18 || first.find_first_not_of("0123456789") != std::string::npos)
	{
		return;
	}
	const unsigned long long counter = std::stoull(first);
	const bool isNew = _baseline && counter != _counter;
	_counter = counter;
	if (!isNew)
	{
		return;
	}
	const std::string line = clean(second);
	if (line.empty())
	{
		return;
	}
	_line = line;
	_until = now + SHOW_MS;
	_visible = true;
	_redraw = true;
}

/**
 * Looks at launcher/chat.txt next to the exe every two seconds: the date first, the file only when the date is new
 * (or so fresh that a second message might share it: the date counts whole seconds).
 * Hides the plate when its time is over. The first look only learns what is there: that is an old message.
 */
void HdChatNotice::think()
{
	const Uint32 now = SDL_GetTicks();
	if (_visible && (Sint32)(now - _until) >= 0)
	{
		_visible = false;
	}
	if (now < _nextLook)
	{
		return;
	}
	_nextLook = now + LOOK_EVERY_MS;
	if (!Options::oxceHdChatNotice)
	{
		_visible = false;
		return;
	}
	const std::string path = CrossPlatform::getExeFolder() + "launcher/chat.txt";
	const time_t date = CrossPlatform::getDateModified(path);
	// no file, or the launcher has it open for a moment: the next look will see
	if (date != 0)
	{
		const bool fresh = _baseline && std::time(0) - date < 3;
		if (date != _date || fresh)
		{
			_date = date;
			readFile(path, now);
		}
	}
	_baseline = true;
}

/**
 * The words in a dark plate with a frame in the cursor's colour, at the right end of the surface.
 */
void HdChatNotice::draw()
{
	Surface::draw();                               // clears to the transparent colour
	if (_line.empty() || !_game->getMod() || !_game->getLanguage())
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
	_text->setWidth(MAX_TEXT);

	// cut to the plate's width at a character's edge, "..." in place of the rest
	std::vector<size_t> edges; // byte offset of every character's end
	for (size_t i = 0; i < _line.size();)
	{
		const unsigned char c = (unsigned char)_line[i];
		i += (c < 0x80) ? 1 : (c < 0xE0) ? 2 : 3;
		edges.push_back(std::min(i, _line.size()));
	}
	_shown = _line;
	_text->setText(_shown);
	if (_text->getTextWidth() > MAX_TEXT)
	{
		size_t lo = 0, hi = edges.size(); // the most characters that still fit with the dots
		while (lo < hi)
		{
			const size_t mid = (lo + hi + 1) / 2;
			_text->setText(_line.substr(0, edges[mid - 1]) + "...");
			if (_text->getTextWidth() <= MAX_TEXT)
			{
				lo = mid;
			}
			else
			{
				hi = mid - 1;
			}
		}
		_shown = lo == 0 ? std::string("...") : _line.substr(0, edges[lo - 1]) + "...";
	}
	_text->setText(_shown);
	_plate = std::min(getWidth(), _text->getTextWidth() + 6);
	// the HD interface sets the words in a wider TrueType face inside the text's own width:
	// the text is as wide as the plate's inside, so a long line condenses instead of running over the frame
	_text->setWidth(_plate - 5);
	_text->setText(_shown);

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
	const int x0 = getWidth() - _plate;
	drawRect(x0, 0, _plate, PLATE_HEIGHT, _color);
	drawRect(x0 + 1, 1, _plate - 2, PLATE_HEIGHT - 2, dark);
}

void HdChatNotice::blit(SDL_Surface *surface)
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
	// the right edge of the screen, one pixel in from it
	setX(surface->w - getWidth() - 1);
	setY(0);
	Surface::blit(surface);
	_text->setX(getX() + getWidth() - _plate + 3);
	_text->setY(2);
	_text->blit(surface);
}

}
