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
#include <cstdio>
#include <cstring>
#include "FileMap.h"
#include "Logger.h"
#include "SDL2Helpers.h"
#define STB_TRUETYPE_IMPLEMENTATION
#define STBTT_STATIC
#include "stb_truetype.h"

namespace OpenXcom
{

namespace
{

/**
 * The codepoint the face is asked for. Full-width forms (U+FF01..U+FF5E) fold to their
 * ASCII twin: mod strings use them for wide digits (X-Piratez does), the classic font draws
 * them out of FontSmall_jp.png, and no Latin face carries that block - without the fold
 * every such digit came out as '?'.
 */
UCode faceCode(UCode c)
{
	if (c >= 0xFF01 && c <= 0xFF5E)
	{
		return (UCode)(c - 0xFEE0);
	}
	return c;
}

}

HdFont::HdFont()
{
	_face.info = new stbtt_fontinfo();
	_fallback.info = new stbtt_fontinfo();
}

HdFont::~HdFont()
{
	delete (stbtt_fontinfo*)_face.info;
	delete (stbtt_fontinfo*)_fallback.info;
}

bool HdFont::loadFace(Face &face, const std::string &path)
{
	face.loaded = false;
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
	face.data.assign((unsigned char*)data, (unsigned char*)data + size);
	SDL_free(data);
	stbtt_fontinfo *info = (stbtt_fontinfo*)face.info;
	if (!stbtt_InitFont(info, face.data.data(), stbtt_GetFontOffsetForIndex(face.data.data(), 0)))
	{
		Log(LOG_ERROR) << "HD interface: " << path << " is not a TrueType font";
		face.data.clear();
		return false;
	}
	// the cap height: the bounds of H at a known size
	const float scale = stbtt_ScaleForPixelHeight(info, 100.0f);
	int x0, y0, x1, y1;
	stbtt_GetCodepointBitmapBox(info, 'H', scale, scale, &x0, &y0, &x1, &y1);
	const float cap = (float)(y1 - y0);
	face.capRatio = cap > 1.0f ? cap / 100.0f : 0.7f;
	// the tails: how far the deepest of them reaches below the baseline. The bitmap fonts are drawn to
	// fit their cell ('р' takes one row below the baseline in the small font), a TrueType face hangs
	// about twice as deep, and the line has to be lifted by that much to stay inside the cell
	float deep = 0.0f;
	for (UCode c : { (UCode)'p', (UCode)'q', (UCode)'y', (UCode)'g', (UCode)0x0440, (UCode)0x0443, (UCode)0x0444, (UCode)0x0434 })
	{
		if (!stbtt_FindGlyphIndex(info, (int)c)) continue;
		int bx0, by0, bx1, by1;
		stbtt_GetCodepointBitmapBox(info, (int)c, scale, scale, &bx0, &by0, &bx1, &by1);
		deep = std::max(deep, (float)by1);
	}
	face.descRatio = deep > 0.0f ? deep / 100.0f : 0.21f;
	face.loaded = true;
	return true;
}

bool HdFont::load(const std::string &path)
{
	_cache.clear();
	return loadFace(_face, path);
}

bool HdFont::loadFallback(const std::string &path)
{
	_cache.clear();
	return loadFace(_fallback, path);
}

/**
 * The family name the face carries in its own name table: what the options list shows
 * instead of a bare number, so a font set is known by name and not by its position.
 */
std::string HdFont::familyName() const
{
	if (!_face.loaded)
	{
		return std::string();
	}
	const stbtt_fontinfo *info = (const stbtt_fontinfo*)_face.info;
	// the typographic family ("Exo 2"), then the plain one for a face that has no typographic name
	const int ids[2] = { 16, 1 };
	for (int id : ids)
	{
		int len = 0;
		const char *s = stbtt_GetFontNameString(info, &len, STBTT_PLATFORM_ID_MICROSOFT,
			STBTT_MS_EID_UNICODE_BMP, STBTT_MS_LANG_ENGLISH, id);
		if (!s || len < 2)
		{
			continue;
		}
		// UTF-16BE in the file; the names we show are Latin, anything else is dropped
		std::string name;
		for (int i = 1; i < len; i += 2)
		{
			const unsigned char c = (unsigned char)s[i];
			if (s[i - 1] == 0 && c >= 0x20 && c < 0x7F)
			{
				name += (char)c;
			}
		}
		if (!name.empty())
		{
			return name;
		}
	}
	return std::string();
}

void HdFont::warnMissing(UCode c)
{
	if (std::find(_warned.begin(), _warned.end(), c) != _warned.end())
	{
		return;
	}
	_warned.push_back(c);
	char code[16];
	snprintf(code, sizeof(code), "U+%04X", (unsigned)c);
	Log(LOG_WARNING) << "HD interface: no glyph for " << code << " in either face, drawing '?'";
}

float HdFont::sizeForCapHeight(float capHeight) const
{
	return capHeight / _face.capRatio;
}

const HdFont::Glyph &HdFont::glyph(UCode c, float px, float condense)
{
	const UCode fc = faceCode(c);
	Key key = { fc, (int)(px * 4 + 0.5f), (int)(condense * 64 + 0.5f), 0 };
	auto it = _cache.find(key);
	if (it != _cache.end())
	{
		return it->second;
	}
	Glyph &g = _cache[key];
	if (!_face.loaded)
	{
		return g;
	}
	// the main font first; what it has no glyph for goes to the fallback face, and only then to '?'
	stbtt_fontinfo *info = (stbtt_fontinfo*)_face.info;
	float sizePx = key.px / 4.0f;
	int gi = stbtt_FindGlyphIndex(info, (int)fc);
	if (gi == 0 && fc != ' ')
	{
		stbtt_fontinfo *fb = (stbtt_fontinfo*)_fallback.info;
		const int fbGi = _fallback.loaded ? stbtt_FindGlyphIndex(fb, (int)fc) : 0;
		if (fbGi)
		{
			info = fb;
			gi = fbGi;
			sizePx *= _face.capRatio / _fallback.capRatio; // capitals of both faces stand equally tall
		}
		else
		{
			warnMissing(fc);
			gi = stbtt_FindGlyphIndex(info, '?');
		}
	}
	const float sy = stbtt_ScaleForPixelHeight(info, sizePx);
	const float sx = sy * (key.cond / 64.0f);
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
	Key key = { faceCode(c), (int)(px * 4 + 0.5f), (int)(condense * 64 + 0.5f), t };
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
	if (!_face.loaded)
	{
		return 0.0f;
	}
	stbtt_fontinfo *info = (stbtt_fontinfo*)_face.info;
	const float sy = stbtt_ScaleForPixelHeight(info, (int)(px * 4 + 0.5f) / 4.0f);
	return stbtt_GetCodepointKernAdvance(info, (int)faceCode(a), (int)faceCode(b)) * sy * condense;
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
