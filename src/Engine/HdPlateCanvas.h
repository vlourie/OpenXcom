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
#include <map>
#include <string>
#include <SDL.h>

namespace OpenXcom
{

class Surface;
class Font;
class Text;
class Language;

/**
 * XP-000575: one set of drawing calls for the small windows made of rectangles, triangles and words (the music player,
 * the plates of the track and of the message), with two ways to do them: ClassicPlateCanvas puts them on an 8-bit
 * surface in the nearest colours of its palette, HdPlateCanvas draws them in vectors in the HD layer. The layout is
 * written once, over this interface, so the classic and the HD windows are the same window. Coordinates are base
 * pixels from the window's top left; colours 0xAARRGGBB.
 */
class PlateCanvas
{
public:
	virtual ~PlateCanvas() {}
	/// Fills a rectangle.
	virtual void fill(float x, float y, float w, float h, Uint32 argb) = 0;
	/// Fills a rectangle with a vertical gradient (the classic canvas has two bands).
	virtual void gradient(float x, float y, float w, float h, Uint32 top, Uint32 bottom) = 0;
	/// Fills a triangle.
	virtual void triangle(float ax, float ay, float bx, float by, float cx, float cy, Uint32 argb) = 0;
	/// Draws a string with its glyph cell's top left at (x, y).
	virtual void text(const std::string &s, float x, float y, Uint32 argb, bool big) = 0;
	/// The width of a string, base pixels.
	virtual float textWidth(const std::string &s, bool big) = 0;
	/// Limits the drawing to a rectangle until unclip().
	virtual void clip(float x, float y, float w, float h) = 0;
	virtual void unclip() = 0;
	/// The note sign (the fonts have none): a head, a stem and a flag, in a box of about 7 x 9 at (x, y).
	void note(float x, float y, Uint32 argb, float s = 1.0f);
	/// A blend of two colours (t = 0 a, 1 b), alpha of a.
	static Uint32 mix(Uint32 a, Uint32 b, float t);
};

/// The classic way: an 8-bit surface. The words are drawn with the game's own bitmap font (a Text of the canvas) and
/// then take the one colour asked for.
class ClassicPlateCanvas : public PlateCanvas
{
private:
	Surface *_surface;
	Text *_small, *_big;
	SDL_Rect _clip;
	const SDL_Color *_palette;
	std::map<Uint32, Uint8> _index;
	/// XP-000600: which shades of each font (0 small, 1 big) are the letter and which its outline, learnt from the font.
	bool _letter[2][8];
	bool _learnt[2];
	void learnShades(int which);
	Uint8 nearest(Uint32 argb);
	void span(int x0, int x1, int y, Uint8 index);
public:
	/// Takes the fonts and the language of the state; the canvas owns two Text objects for the words.
	ClassicPlateCanvas(Surface *surface, Font *big, Font *small, Language *lang);
	~ClassicPlateCanvas();
	ClassicPlateCanvas(const ClassicPlateCanvas &) = delete; // owns the two Text objects: a copy would delete them twice
	ClassicPlateCanvas &operator=(const ClassicPlateCanvas &) = delete;
	/// Starts a new picture on the surface's palette (call before painting).
	void begin();
	void fill(float x, float y, float w, float h, Uint32 argb) override;
	void gradient(float x, float y, float w, float h, Uint32 top, Uint32 bottom) override;
	void triangle(float ax, float ay, float bx, float by, float cx, float cy, Uint32 argb) override;
	void text(const std::string &s, float x, float y, Uint32 argb, bool big) override;
	float textWidth(const std::string &s, bool big) override;
	void clip(float x, float y, float w, float h) override;
	void unclip() override;
};

/// The HD way: vectors in the HD layer (HdUi), the words in its TrueType faces.
class HdPlateCanvas : public PlateCanvas
{
private:
	float _ox, _oy;
	Font *_small, *_big;
	float cap(bool big);
public:
	/// (ox, oy) = the window's top left in the screen's base pixels.
	HdPlateCanvas(float ox, float oy, Font *big, Font *small);
	void fill(float x, float y, float w, float h, Uint32 argb) override;
	void gradient(float x, float y, float w, float h, Uint32 top, Uint32 bottom) override;
	void triangle(float ax, float ay, float bx, float by, float cx, float cy, Uint32 argb) override;
	void text(const std::string &s, float x, float y, Uint32 argb, bool big) override;
	float textWidth(const std::string &s, bool big) override;
	void clip(float x, float y, float w, float h) override;
	void unclip() override;
};

}
