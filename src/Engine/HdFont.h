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
#include <SDL.h>
#include <string>
#include <unordered_map>
#include <vector>
#include "Unicode.h"

namespace OpenXcom
{

/**
 * A TrueType font for the HD interface (hd/UI/FontBig.ttf, FontSmall.ttf in a
 * mod): glyphs rasterized with anti-aliasing at any pixel size, cached. The
 * classic bitmap fonts still lay the text out (line breaks, alignment,
 * everything the game measures); this only draws the lines.
 */
class HdFont
{
public:
	struct Glyph
	{
		int w = 0, h = 0;          ///< bitmap size
		int xoff = 0, yoff = 0;    ///< bitmap origin relative to the pen (x) and the baseline (y)
		float advance = 0;         ///< pen advance
		std::vector<Uint8> cov;    ///< coverage 0..255, w * h
	};

	HdFont();
	~HdFont();
	/// Loads a TTF/OTF from the mods' virtual file system; false when missing or not a font.
	bool load(const std::string &path);
	bool loaded() const { return _loaded; }
	/// The pixel size (ascent + descent) at which capital letters are `capHeight` pixels tall.
	float sizeForCapHeight(float capHeight) const;
	/// The glyph of a code point at a pixel size, horizontally condensed by `condense` (1 = as designed).
	const Glyph &glyph(UCode c, float px, float condense = 1.0f);
	/// The same glyph spread by `thickness` pixels in every direction: the outline drawn under a line of
	/// text that sits on a picture, so the letters keep an edge of their own. Cached like the glyphs.
	const Glyph &outline(UCode c, float px, float condense, int thickness);
	/// Kerning between two code points at a pixel size (condensed).
	float kern(UCode a, UCode b, float px, float condense = 1.0f);
	/// Width of a string at a pixel size (condensed).
	float measure(const UString &s, float px, float condense = 1.0f);
	/// Forgets the cached glyphs.
	void clearCache();

private:
	struct Key
	{
		UCode c;
		int px;      ///< pixel size * 4
		int cond;    ///< condense * 64
		int t = 0;   ///< outline thickness in pixels (0 = the glyph itself)
		bool operator==(const Key &o) const { return c == o.c && px == o.px && cond == o.cond && t == o.t; }
	};
	struct KeyHash
	{
		size_t operator()(const Key &k) const { return (size_t)k.c * 0x9E3779B9u ^ ((size_t)k.px << 16) ^ ((size_t)k.cond << 28) ^ ((size_t)k.t * 0x85EBCA6Bu); }
	};
	std::vector<unsigned char> _data;
	void *_info;               ///< stbtt_fontinfo
	bool _loaded;
	float _capRatio;           ///< cap height / pixel size
	std::unordered_map<Key, Glyph, KeyHash> _cache;
};

}
