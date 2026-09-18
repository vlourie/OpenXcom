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
#include <algorithm>
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
	Key key = { c, (int)(px * 4 + 0.5f), (int)(condense * 64 + 0.5f), 0 };
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

/**
 * The glyph spread by `thickness` pixels: the letter's own coverage taken as a maximum over a square
 * brush, which is the outline drawn under text that sits on a picture. Two running-maximum passes,
 * across and down, cost the glyph's area twice, and the result is cached like an ordinary glyph.
 */
const HdFont::Glyph &HdFont::outline(UCode c, float px, float condense, int thickness)
{
	const int t = std::max(1, thickness);
	Key key = { c, (int)(px * 4 + 0.5f), (int)(condense * 64 + 0.5f), t };
	auto it = _cache.find(key);
	if (it != _cache.end())
	{
		return it->second;
	}
	// by value: building the letter's own glyph may rehash the cache and move it
	const Glyph base = glyph(c, px, condense);
	Glyph &g = _cache[key];
	g.advance = base.advance;
	if (base.w <= 0 || base.h <= 0)
	{
		return g;
	}
	g.w = base.w + 2 * t;
	g.h = base.h + 2 * t;
	g.xoff = base.xoff - t;
	g.yoff = base.yoff - t;
	// across: a pixel of the wider image takes the brightest of the letter's pixels the brush covers
	std::vector<Uint8> row((size_t)g.w * base.h, 0);
	for (int y = 0; y < base.h; ++y)
	{
		const Uint8 *src = base.cov.data() + (size_t)y * base.w;
		Uint8 *dst = row.data() + (size_t)y * g.w;
		for (int x = 0; x < g.w; ++x)
		{
			const int from = std::max(0, x - 2 * t), to = std::min(base.w - 1, x);
			int m = 0;
			for (int sx = from; sx <= to; ++sx)
			{
				if (src[sx] > m) m = src[sx];
			}
			dst[x] = (Uint8)m;
		}
	}
	// and down
	g.cov.assign((size_t)g.w * g.h, 0);
	for (int y = 0; y < g.h; ++y)
	{
		const int from = std::max(0, y - 2 * t), to = std::min(base.h - 1, y);
		Uint8 *dst = g.cov.data() + (size_t)y * g.w;
		for (int x = 0; x < g.w; ++x)
		{
			int m = 0;
			for (int sy = from; sy <= to; ++sy)
			{
				const Uint8 v = row[(size_t)sy * g.w + x];
				if (v > m) m = v;
			}
			dst[x] = (Uint8)m;
		}
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
