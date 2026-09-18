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
#include <list>
#include <unordered_map>
#include <vector>
#include "HdSprites.h"
#include "HdUiArt.h"
#include "HdFont.h"
#include "Unicode.h"

namespace OpenXcom
{

class Surface;
class Font;
class Screen;

/**
 * The HD interface: every surface that a state blits onto the screen is also
 * drawn, in the same order, k times bigger into the true-color world layer,
 * which then is the whole frame (the classic 8-bit layer keeps being drawn,
 * for the game's logic and as the source of everything that has no HD
 * drawing of its own). A plain surface is scaled with xBRZ (or nearest);
 * text is rendered from the font's glyphs with smooth, anti-aliased edges;
 * windows, buttons and bars redraw their geometry crisply; sprites with an
 * HD pack are drawn from the pack.
 *
 * Coordinates given to the drawing calls are base (classic) pixels; the clip
 * rectangle too.
 */
class HdUi
{
public:
	static HdUi &instance();

	/// Is the HD interface drawing right now (layered screen, scale >= 2, option on)?
	static bool active();
	/// Is `dest` the screen's classic surface, i.e. a blit onto it must be mirrored?
	static bool isScreen(const SDL_Surface *dest);
	/// The smoothing mode of plain surfaces: 1 nearest, 2 xBRZ.
	static int mode();

	/// Draws an 8-bit surface (index 0 transparent) at base position (x, y): nearest or smoothed. The colours
	/// are the surface's own palette (what an SDL blit of it onto the screen shows), the screen's when it has none.
	void drawSurface(const Surface *surface, int x, int y, bool smooth);
	/// Draws a rectangle of an 8-bit surface's pixels (given in surface pixels) at base position (x, y), nearest.
	void drawPixels(const Uint8 *pixels, int pitch, int w, int h, int x, int y, const SDL_Color *colors = nullptr);
	/// Fills a base rectangle with a palette colour.
	void fillRect(int x, int y, int w, int h, Uint8 color, const SDL_Color *colors = nullptr);
	/// Draws a glyph of a font at base position (x, y) with the text colour rule (see Text::draw): index = color + value * mul
	/// (+ inversion around mid), looked up in `colors` (the text surface's palette; the screen's when null).
	void drawGlyph(const Font *font, UCode c, int x, int y, int color, int mul, int mid, const SDL_Color *colors = nullptr);
	/// The palette a surface's pixels are shown with: its own, or the screen's when it has none.
	static const SDL_Color *paletteOf(const Surface *surface);
	/// Draws an HD picture (hd/UI) at base position (x, y), scaled to the world and re-tinted for the palette
	/// (`colors`, or the screen's); `key` names the cache slot (the surface the picture stands for).
	void drawArt(const HdUiArt::Art *art, const Surface *key, int x, int y, const SDL_Color *colors = nullptr);
	/// Limits the drawing to a base rectangle (screen coordinates); w <= 0 = no limit.
	void setClip(int x, int y, int w, int h);
	void clearClip() { _clipW = 0; }

	// --- the modern skin: fonts and drawing primitives (world pixels, anti-aliased, clipped) ---

	/// Is the modern skin drawing (the HD interface is active and the option is on)?
	static bool skin();
	/// The skin's style (the option): 1 the mod's colour ramps with gradients, 2 dark panels with the ramp
	/// as thin accents, 3 flat mid-tone panels.
	static int style();
	/// Loads hd/UI/FontBig.ttf and FontSmall.ttf (or Font.ttf for both) from the mods; called after the mods load.
	void loadFonts();
	/// Are TrueType fonts available for the text?
	bool hasFonts() const;
	HdFont &font(bool big) { return big ? _fontBig : _fontSmall; }
	/// 0xAARRGGBB from a palette colour.
	static Uint32 rgba(const SDL_Color &c, int alpha = 255) { return ((Uint32)alpha << 24) | ((Uint32)c.r << 16) | ((Uint32)c.g << 8) | c.b; }
	/// A colour scaled in brightness (f < 1 darker, > 1 lighter), alpha kept.
	static Uint32 scaled(Uint32 c, float f);
	/// A blend of two colours (t = 0 a, 1 b).
	static Uint32 mixed(Uint32 a, Uint32 b, float t);
	/// The world scale (0 when not drawing).
	static int scale();
	/// Fills a rounded rectangle [x0, x1) x [y0, y1) with a vertical gradient.
	void fillRoundRect(float x0, float y0, float x1, float y1, float radius, Uint32 top, Uint32 bottom);
	/// Strokes a rounded rectangle (the line inside the bounds, `width` pixels).
	void strokeRoundRect(float x0, float y0, float x1, float y1, float radius, float width, Uint32 color);
	/// Fills a triangle.
	void fillTriangle(float ax, float ay, float bx, float by, float cx, float cy, Uint32 color);
	/// Fills a circle.
	void fillCircle(float cx, float cy, float r, Uint32 color);
	/// What a classic bitmap font is replaced with: the TrueType face (big or small), the capitals' height in
	/// base pixels (a little lighter than the chunky bitmap's) and the classic line advance.
	struct FontMetrics
	{
		bool big = true;                  ///< FontBig.ttf (a heavy face) or FontSmall.ttf
		float cap = 6.0f;                 ///< the TrueType capitals' height, base pixels
		int lineH = 9;                    ///< the classic line height (the cell plus the spacing)
		int classicCap = 8;               ///< the bitmap font's capitals (rows of 'H')
	};
	/// The metrics of a classic font (measured once from its 'H').
	const FontMetrics &metrics(const Font *font);
	/// A run of a classic text line: the glyphs the classic layout put at base (x, y) in this font and colour rule.
	struct TextRun
	{
		UString text;
		int x = 0, y = 0;
		int w = 0;                        ///< the run's classic width (base pixels)
		int dotW = 0;                     ///< the classic advance of '.' (dot leaders keep their classic length)
		const Font *font = nullptr;       ///< the classic font of the run
		int color = 0, mul = 1, mid = 0;
	};
	/// Draws one line of classic-laid-out text with the TrueType fonts: `runs` share a line; the line is placed
	/// by `align` within the text's base rectangle (originX, originY, textW, textH); `pal` maps the colour rule.
	/// The capitals are centred in the classic line box (in the text's box when it is a single line of about
	/// that height). A line too wide for the rectangle is condensed, then set smaller; one too tall for it (a
	/// big label in a low button) is set smaller too.
	void drawTtfLine(const std::vector<TextRun> &runs, int originX, int originY, int textW, int textH, int align, bool singleLine, const SDL_Color *pal);
	/// Draws a string with a TrueType font at base position (x, y = the top of a classic glyph cell of the
	/// font), capitals `capHeight` base pixels tall; colours 0xAARRGGBB, shadow 0 = none.
	void drawTtfString(const UString &s, bool big, float capHeight, int x, int y, Uint32 face, Uint32 shadow);
	/// Width of a string in base pixels at that size.
	float ttfWidth(const UString &s, bool big, float capHeight);
	/// The text caret of an edit field drawn with the TrueType fonts: after `pos` characters of `value`, laid out
	/// like drawTtfLine does a single-line text in `font` at the text's base (x, y), size (textW, textH) and
	/// alignment (0 left, 1 centre, 2 right).
	void drawTtfCaret(const UString &value, size_t pos, const Font *font, int x, int y, int textW, int textH, int align, Uint32 color);
	/// The mouse position in base pixels, and whether what is drawn now reacts to it (the top state does,
	/// the states under a popup do not); set by the game before each state's blit.
	void setMouse(int x, int y, bool hoverOn) { _mouseX = x; _mouseY = y; _hoverOn = hoverOn; }
	/// Is the mouse over a base rectangle (hover effects on)?
	bool hover(int x, int y, int w, int h) const { return _hoverOn && _mouseX >= x && _mouseX < x + w && _mouseY >= y && _mouseY < y + h; }
	/// The skin's button: a base rectangle in the ramp of palette colour `color` (mul: the contrast multiplier),
	/// pressed = lit; lighter under the mouse. `colors` = the palette (the screen's when null).
	void drawButton(int x, int y, int w, int h, int color, int mul, bool pressed, const SDL_Color *colors = nullptr);
	/// The skin's panel frame (a window): the border band around [x, y, w, h] in the ramp of `color`; the
	/// inside is left to the caller (the picture, a fill). `inset` = the border's width in base pixels.
	void drawPanelFrame(int x, int y, int w, int h, int color, int mul, int inset, bool thin, const SDL_Color *colors = nullptr);
	/// The skin's soft shadow around a base rectangle (under a window; `radius` in base pixels).
	void drawShadow(int x, int y, int w, int h, float radius);
	/// The skin's list-row highlight: a translucent light band, with an accent bar at its left in `accent` (0 = none).
	void drawHighlight(int x, int y, int w, int h, Uint32 accent = 0);
	/// The skin's row banding of a list: a base band, odd ones a little darker, even ones a little lighter.
	void drawRowBand(int x, int y, int w, int h, bool odd);
	/// The skin's slider: a thin track from base (x, y) `w` wide (`h` = the row's height, the track is centred in it),
	/// filled up to `t` (0..1) in the ramp of `color`, and a round knob there; pressed/hover = lit.
	void drawSlider(int x, int y, int w, int h, float t, int color, int mul, bool pressed, const SDL_Color *colors = nullptr);
	/// The skin's scrollbar: the track and the thumb (thumb rows [ty0, ty1) of the base rectangle) in the ramp of `color`.
	void drawScrollBar(int x, int y, int w, int h, int ty0, int ty1, int color, bool pressed, const SDL_Color *colors = nullptr);
	/// The skin's drop-down chevron in a base rectangle in the ramp of `color`.
	void drawChevron(int x, int y, int w, int h, int color, const SDL_Color *colors = nullptr);

	/// Forgets every cached smoothed surface and glyph (scale or palette change).
	void clearCaches();
	/// Called once per frame (at flip): profiling of the interface drawing, logged now and then.
	void frameDone();
	/// Scales a palette shape (values, 0 = nothing) k times with smooth edges (the Scale2x corner rule with
	/// exact coverage): value and coverage per HD pixel. Public for tests.
	static void scaleShape(const Uint8 *src, int w, int h, int k, std::vector<Uint8> &value, std::vector<Uint8> &cov,
	                       std::vector<Uint8> *value2 = nullptr, std::vector<Uint8> *mix = nullptr);
	/// Number of cached smoothed surfaces (statistics).
	size_t cachedSurfaces() const { return _smooth.size(); }

private:
	struct SmoothEntry
	{
		Uint64 hash = 0;                  ///< content: pixels and palette (or the palette-independent picture key)
		Uint64 pixelHash = 0;             ///< content: the pixels alone
		int k = 0;
		HdFrame frame;                    ///< the xBRZ copy (empty when the surface shows an HD picture instead)
		const HdUiArt::Art *art = nullptr;///< the HD picture the surface is (a part of), if any
		int artX = 0, artY = 0;           ///< where the surface's pixels sit in the picture's image
		int artMisses = 0;                ///< how often the surface's content was searched for a picture in vain
		std::list<const Surface*>::iterator lru;
	};
	struct Glyph
	{
		int w = 0, h = 0;                 ///< HD size
		std::vector<Uint8> value;         ///< the glyph's palette offset per HD pixel (0 = none)
		std::vector<Uint8> cov;           ///< coverage per HD pixel
		std::vector<Uint8> value2, mix;   ///< a second offset blended in by mix/255 (a chamfer between two shades)
	};
	struct GlyphKey
	{
		const Font *font;
		UCode code;
		int k;
		bool operator==(const GlyphKey &o) const { return font == o.font && code == o.code && k == o.k; }
	};
	struct GlyphKeyHash
	{
		size_t operator()(const GlyphKey &g) const { return std::hash<const void*>()(g.font) ^ ((size_t)g.code * 0x9E3779B9u) ^ ((size_t)g.k << 20); }
	};
	HdFont _fontBig, _fontSmall;
	std::unordered_map<const Font*, FontMetrics> _metrics;
	std::unordered_map<const Surface*, SmoothEntry> _smooth;
	std::list<const Surface*> _smoothLru;
	size_t _smoothBytes = 0;
	std::unordered_map<GlyphKey, Glyph, GlyphKeyHash> _glyphs;
	int _clipX = 0, _clipY = 0, _clipW = 0, _clipH = 0;
	int _mouseX = -1, _mouseY = -1;
	bool _hoverOn = false;
	double _frameMs = 0, _totalMs = 0;
	int _frames = 0, _calls = 0;

	HdUi() {}
	/// The world surface, scale and palette of the current screen; false when not drawing.
	bool target(SDL_Surface *&dest, int &k, const SDL_Color *&colors) const;
	/// The xBRZ copy of a surface (pixelHash: HdUiArt::hashPixels of its pixels), cached.
	const HdFrame *smoothed(const Surface *surface, int k, const SDL_Color *colors, Uint64 pixelHash);
	/// The picture of an image scaled to k and re-tinted for the palette, cached under `key`.
	const HdFrame *prepared(const HdUiArt::Art *art, const Surface *key, int k, const SDL_Color *colors);
	/// Puts a frame into the smoothed-surface cache under a key (evicting by size).
	const HdFrame *cache(const Surface *key, Uint64 pixelHash, Uint64 hash, int k, HdFrame &&frame, const HdUiArt::Art *art = nullptr, int artX = 0, int artY = 0);
	/// The cache entry of a surface if its content (hash) and scale still match.
	SmoothEntry *cached(const Surface *key, Uint64 hash, int k);
	const Glyph &glyph(const Font *font, UCode c, int k);
	/// Blends a true-color frame at world pixel (x, y).
	void blendFrame(SDL_Surface *dest, const HdFrame &frame, int x, int y, const SDL_Rect *clip);
	/// Blends a colour with a coverage over a span of a row (world pixels), clipped.
	void blendSpan(SDL_Surface *dest, const SDL_Rect &clip, int y, float xa, float xb, Uint32 color, float cov);
	/// Blends a glyph's coverage bitmap at world position, clipped.
	void blendGlyph(SDL_Surface *dest, const SDL_Rect &clip, const HdFont::Glyph &g, int x, int y, Uint32 color);
	/// The clip rectangle in world pixels (or the whole world).
	SDL_Rect worldClip(SDL_Surface *dest, int k) const;
};

}
