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
#include "HdFont.h"
#include <cmath>
#include <cstring>
#include "FileMap.h"
#include "Logger.h"
#include "SDL2Helpers.h"
#define STB_TRUETYPE_IMPLEMENTATION
#define STBTT_STATIC
#include "stb_truetype.h"

namespace OpenXcom
{

HdFont::HdFont() : _info(new stbtt_fontinfo()), _loaded(false), _capRatio(0.7f)
{
}

HdFont::~HdFont()
{
	delete (stbtt_fontinfo*)_info;
}

bool HdFont::load(const std::string &path)
{
	_loaded = false;
	_cache.clear();
	if (!FileMap::fileExists(path))
	{
		return false;
	}
	SDL_RWops *rw = FileMap::getRWops(path);
	if (!rw)
	{
		return false;
	}
	size_t size = 0;
	void *data = SDL_LoadFile_RW(rw, &size, SDL_TRUE);
	if (!data || size < 12)
	{
		return false;
	}
	_data.assign((unsigned char*)data, (unsigned char*)data + size);
	SDL_free(data);
	stbtt_fontinfo *info = (stbtt_fontinfo*)_info;
	if (!stbtt_InitFont(info, _data.data(), stbtt_GetFontOffsetForIndex(_data.data(), 0)))
	{
		Log(LOG_ERROR) << "HD interface: " << path << " is not a TrueType font";
		_data.clear();
		return false;
	}
	// the cap height: the bounds of H at a known size
	const float scale = stbtt_ScaleForPixelHeight(info, 100.0f);
	int x0, y0, x1, y1;
	stbtt_GetCodepointBitmapBox(info, 'H', scale, scale, &x0, &y0, &x1, &y1);
	const float cap = (float)(y1 - y0);
	_capRatio = cap > 1.0f ? cap / 100.0f : 0.7f;
	_loaded = true;
	return true;
}

float HdFont::sizeForCapHeight(float capHeight) const
{
	return capHeight / _capRatio;
}

const HdFont::Glyph &HdFont::glyph(UCode c, float px, float condense)
{
	Key key = { c, (int)(px * 4 + 0.5f), (int)(condense * 64 + 0.5f) };
	auto it = _cache.find(key);
	if (it != _cache.end())
	{
		return it->second;
	}
	Glyph &g = _cache[key];
	if (!_loaded)
	{
		return g;
	}
	stbtt_fontinfo *info = (stbtt_fontinfo*)_info;
	const float sy = stbtt_ScaleForPixelHeight(info, key.px / 4.0f);
	const float sx = sy * (key.cond / 64.0f);
	int gi = stbtt_FindGlyphIndex(info, (int)c);
	if (gi == 0 && c != ' ')
	{
		gi = stbtt_FindGlyphIndex(info, '?');
	}
	int advance = 0, lsb = 0;
	stbtt_GetGlyphHMetrics(info, gi, &advance, &lsb);
	g.advance = advance * sx;
	int x0, y0, x1, y1;
	stbtt_GetGlyphBitmapBox(info, gi, sx, sy, &x0, &y0, &x1, &y1);
	g.w = x1 - x0;
	g.h = y1 - y0;
	g.xoff = x0;
	g.yoff = y0;
	if (g.w > 0 && g.h > 0)
	{
		g.cov.assign((size_t)g.w * g.h, 0);
		stbtt_MakeGlyphBitmap(info, g.cov.data(), g.w, g.h, g.w, sx, sy, gi);
	}
	else
	{
		g.w = g.h = 0;
	}
	return g;
}

float HdFont::kern(UCode a, UCode b, float px, float condense)
{
	if (!_loaded)
	{
		return 0.0f;
	}
	stbtt_fontinfo *info = (stbtt_fontinfo*)_info;
	const float sy = stbtt_ScaleForPixelHeight(info, (int)(px * 4 + 0.5f) / 4.0f);
	return stbtt_GetCodepointKernAdvance(info, (int)a, (int)b) * sy * condense;
}

float HdFont::measure(const UString &s, float px, float condense)
{
	float w = 0.0f;
	UCode prev = 0;
	for (UCode c : s)
	{
		if (prev)
		{
			w += kern(prev, c, px, condense);
		}
		w += glyph(c, px, condense).advance;
		prev = c;
	}
	return w;
}

void HdFont::clearCache()
{
	_cache.clear();
}

}
