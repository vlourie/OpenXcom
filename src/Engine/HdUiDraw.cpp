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
#include "HdUi.h"
#include <algorithm>
#include <cmath>
#include "FileMap.h"
#include "Font.h"
#include "Surface.h"
#include "HdWorkers.h"
#include "Logger.h"
#include "Options.h"
#include "Screen.h"
#include <chrono>

/*
 * The modern skin's drawing: anti-aliased rounded rectangles, strokes,
 * triangles, circles and TrueType text into the world layer. Everything is
 * in world pixels and clipped by the HD interface's clip rectangle.
 */

namespace OpenXcom
{

namespace
{

/// The classic fonts: FONT_BIG's capitals are 13 base pixels tall, FONT_SMALL's 8, the geoscape's 8 and 6;
/// the TrueType text is set a little lighter than the chunky bitmaps: this much of the classic capitals.
const float CAP_RATIO_BIG = 0.78f, CAP_RATIO_SMALL = 0.80f;
/// A classic font with capitals this tall (or taller) is a big one: the heavy TrueType face.
const int BIG_CAP_ROWS = 11;
/// The TrueType sizes standing in for the classic big and small fonts (NumberText, the caret...).
const float CAP_BIG = 13.0f * CAP_RATIO_BIG, CAP_SMALL = 8.0f * CAP_RATIO_SMALL;
/// The baseline of a line of capitals centred in a box of `boxH` base pixels.
inline float centredBaseline(float boxH, float cap) { return (boxH + cap) * 0.5f; }
/// Letter-spacing of capital titles in the big font (a fraction of the font size).
const float TRACKING_CAPS = 0.045f;
/// Dot leaders: a run of at least this many dots keeps its classic length (an ellipsis does not).
const size_t LEADER_MIN = 4;

/// Glyph coverage weighted for blending in sRGB: light text on the dark panels blends thin, this gives
/// the strokes back a little weight (a gamma of 0.85 on the coverage).
struct CoverageLut
{
	float v[256];
	CoverageLut() { for (int i = 0; i < 256; ++i) v[i] = (float)std::pow(i / 255.0, 0.85); }
};
const CoverageLut &coverageLut() { static CoverageLut lut; return lut; }

inline bool isLowerLetter(UCode c)
{
	return (c >= 'a' && c <= 'z') || (c >= 0xDF && c <= 0xFF && c != 0xF7) || (c >= 0x430 && c <= 0x45F);
}

/// The number of dots at the start / end of a run (a dot leader), 0 when fewer than LEADER_MIN.
inline size_t leadingDots(const UString &s)
{
	size_t n = 0;
	while (n < s.size() && s[n] == '.') ++n;
	return n >= LEADER_MIN && n < s.size() ? n : 0;
}
inline size_t trailingDots(const UString &s)
{
	size_t n = 0;
	while (n < s.size() && s[s.size() - 1 - n] == '.') ++n;
	return n >= LEADER_MIN ? n : 0;
}

inline void blendPixel(Uint32 &d, Uint32 color, float cov)
{
	const float a = (color >> 24) / 255.0f * cov;
	if (a <= 0.002f) return;
	if (a >= 0.998f) { d = color | 0xFF000000u; return; }
	const float ia = 1.0f - a;
	const int r = (int)(((color >> 16) & 0xFF) * a + ((d >> 16) & 0xFF) * ia + 0.5f);
	const int g = (int)(((color >> 8) & 0xFF) * a + ((d >> 8) & 0xFF) * ia + 0.5f);
	const int b = (int)((color & 0xFF) * a + (d & 0xFF) * ia + 0.5f);
	d = 0xFF000000u | ((Uint32)r << 16) | ((Uint32)g << 8) | (Uint32)b;
}

/// The horizontal extent of a rounded rectangle at a row centre, and the row's vertical coverage.
inline bool rowExtent(float x0, float y0, float x1, float y1, float r, float yc, float &xa, float &xb, float &vcov)
{
	vcov = std::min(yc + 0.5f, y1) - std::max(yc - 0.5f, y0);
	if (vcov <= 0.0f) return false;
	if (vcov > 1.0f) vcov = 1.0f;
	float dy = 0.0f;
	if (yc < y0 + r) dy = (y0 + r) - yc;
	else if (yc > y1 - r) dy = yc - (y1 - r);
	const float inset = r > 0.0f ? r - std::sqrt(std::max(r * r - dy * dy, 0.0f)) : 0.0f;
	xa = x0 + inset;
	xb = x1 - inset;
	return xb > xa;
}


/// Adds the time of a drawing call to the frame's interface time.
struct FrameTiming
{
	double &ms;
	std::chrono::steady_clock::time_point t;
	FrameTiming(double &m) : ms(m), t(std::chrono::steady_clock::now()) {}
	~FrameTiming() { ms += std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t).count(); }
};

}

bool HdUi::skin()
{
	return Options::oxceHdUiSkin > 0 && active();
}

int HdUi::style()
{
	return std::min(std::max(Options::oxceHdUiSkin, 1), 3);
}

namespace
{
/// A colour mixed towards black (t = 0 the colour, 1 black), alpha kept.
inline Uint32 darkened(Uint32 c, float t) { return HdUi::scaled(c, 1.0f - t); }
inline Uint32 withAlpha(Uint32 c, Uint32 a) { return (c & 0x00FFFFFFu) | (a << 24); }
}

int HdUi::scale()
{
	Screen *screen = Screen::current();
	return screen && active() ? screen->getWorldScale() : 0;
}

Uint32 HdUi::scaled(Uint32 c, float f)
{
	const int r = std::min(255, (int)(((c >> 16) & 0xFF) * f + 0.5f));
	const int g = std::min(255, (int)(((c >> 8) & 0xFF) * f + 0.5f));
	const int b = std::min(255, (int)((c & 0xFF) * f + 0.5f));
	return (c & 0xFF000000u) | ((Uint32)r << 16) | ((Uint32)g << 8) | (Uint32)b;
}

Uint32 HdUi::mixed(Uint32 a, Uint32 b, float t)
{
	const float it = 1.0f - t;
	const int al = (int)(((a >> 24) & 0xFF) * it + ((b >> 24) & 0xFF) * t + 0.5f);
	const int r = (int)(((a >> 16) & 0xFF) * it + ((b >> 16) & 0xFF) * t + 0.5f);
	const int g = (int)(((a >> 8) & 0xFF) * it + ((b >> 8) & 0xFF) * t + 0.5f);
	const int bl = (int)((a & 0xFF) * it + (b & 0xFF) * t + 0.5f);
	return ((Uint32)al << 24) | ((Uint32)r << 16) | ((Uint32)g << 8) | (Uint32)bl;
}

/**
 * Is the text drawn with the mod's TrueType fonts: they are there and the
 * option asks for them. Otherwise the game's own font is drawn, smoothed -
 * the classic colours, widths and lines, only without the stair-steps.
 */
bool HdUi::hasFonts() const
{
	return Options::oxceHdUiFont > 0 && _fontBig.loaded() && _fontSmall.loaded();
}

void HdUi::loadFonts()
{
	_fontBig.load("hd/UI/FontBig.ttf");
	_fontSmall.load("hd/UI/FontSmall.ttf");
	if (!_fontBig.loaded() && FileMap::fileExists("hd/UI/Font.ttf")) _fontBig.load("hd/UI/Font.ttf");
	if (!_fontSmall.loaded() && FileMap::fileExists("hd/UI/Font.ttf")) _fontSmall.load("hd/UI/Font.ttf");
	if (!_fontSmall.loaded() && _fontBig.loaded()) _fontSmall.load("hd/UI/FontBig.ttf");
	if (!_fontBig.loaded() && _fontSmall.loaded()) _fontBig.load("hd/UI/FontSmall.ttf");
	if (hasFonts())
	{
		Log(LOG_INFO) << "HD interface: TrueType fonts loaded (hd/UI)";
	}
}

void HdUi::blendSpan(SDL_Surface *dest, const SDL_Rect &clip, int y, float xa, float xb, Uint32 color, float cov)
{
	if (y < clip.y || y >= clip.y + clip.h || cov <= 0.0f) return;
	const float cx0 = (float)clip.x, cx1 = (float)(clip.x + clip.w);
	xa = std::max(xa, cx0);
	xb = std::min(xb, cx1);
	if (xb <= xa) return;
	Uint32 *row = (Uint32*)((Uint8*)dest->pixels + (size_t)y * dest->pitch);
	const int ia = (int)std::floor(xa), ib = (int)std::ceil(xb) - 1;
	if (ia == ib)
	{
		blendPixel(row[ia], color, cov * (xb - xa));
		return;
	}
	blendPixel(row[ia], color, cov * (ia + 1 - xa));
	blendPixel(row[ib], color, cov * (xb - ib));
	if (cov >= 0.998f && (color >> 24) == 255)
	{
		const Uint32 v = color | 0xFF000000u;
		for (int x = ia + 1; x < ib; ++x) row[x] = v;
	}
	else
	{
		for (int x = ia + 1; x < ib; ++x) blendPixel(row[x], color, cov);
	}
}

void HdUi::fillRoundRect(float x0, float y0, float x1, float y1, float radius, Uint32 top, Uint32 bottom)
{
	FrameTiming timing(_frameMs);
	SDL_Surface *dest;
	int k;
	const SDL_Color *pal;
	if (!target(dest, k, pal) || x1 <= x0 || y1 <= y0) return;
	const SDL_Rect clip = worldClip(dest, k);
	radius = std::min(radius, std::min(x1 - x0, y1 - y0) * 0.5f);
	const int ya = std::max((int)std::floor(y0), (int)clip.y), yb = std::min((int)std::ceil(y1), clip.y + clip.h);
	if (yb <= ya) return;
	auto rows = [&](int ra, int rb)
	{
		for (int y = ra; y < rb; ++y)
		{
			float xa, xb, vcov;
			if (!rowExtent(x0, y0, x1, y1, radius, y + 0.5f, xa, xb, vcov)) continue;
			const float t = (y + 0.5f - y0) / (y1 - y0);
			const Uint32 c = top == bottom ? top : mixed(top, bottom, std::min(std::max(t, 0.0f), 1.0f));
			blendSpan(dest, clip, y, xa, xb, c, vcov);
		}
	};
	const int n = yb - ya;
	if (n >= 128)
	{
		HdWorkers &pool = HdWorkers::instance();
		const int jobs = std::max(1, std::min(n / 32, pool.threads() * 2));
		pool.run(jobs, [&](int job) { rows(ya + (int)((long long)n * job / jobs), ya + (int)((long long)n * (job + 1) / jobs)); });
	}
	else
	{
		rows(ya, yb);
	}
}

void HdUi::strokeRoundRect(float x0, float y0, float x1, float y1, float radius, float width, Uint32 color)
{
	FrameTiming timing(_frameMs);
	SDL_Surface *dest;
	int k;
	const SDL_Color *pal;
	if (!target(dest, k, pal) || x1 <= x0 || y1 <= y0 || width <= 0.0f) return;
	const SDL_Rect clip = worldClip(dest, k);
	radius = std::min(radius, std::min(x1 - x0, y1 - y0) * 0.5f);
	const float ri = std::max(radius - width, 0.0f);
	const int ya = std::max((int)std::floor(y0), (int)clip.y), yb = std::min((int)std::ceil(y1), clip.y + clip.h);
	for (int y = ya; y < yb; ++y)
	{
		float xa, xb, vcov;
		if (!rowExtent(x0, y0, x1, y1, radius, y + 0.5f, xa, xb, vcov)) continue;
		float ia, ib, icov;
		if (!rowExtent(x0 + width, y0 + width, x1 - width, y1 - width, ri, y + 0.5f, ia, ib, icov))
		{
			// a row of the top or bottom band: the whole extent
			blendSpan(dest, clip, y, xa, xb, color, vcov);
			continue;
		}
		// the inner rows: the two sides; the inner edge's own partial coverage
		blendSpan(dest, clip, y, xa, ia, color, vcov);
		blendSpan(dest, clip, y, ib, xb, color, vcov);
		if (icov < 1.0f)
		{
			blendSpan(dest, clip, y, ia, ib, color, vcov * (1.0f - icov));
		}
	}
}

void HdUi::fillTriangle(float ax, float ay, float bx, float by, float cx, float cy, Uint32 color)
{
	FrameTiming timing(_frameMs);
	SDL_Surface *dest;
	int k;
	const SDL_Color *pal;
	if (!target(dest, k, pal)) return;
	const SDL_Rect clip = worldClip(dest, k);
	// counter-clockwise order for the edge distances
	const float area = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay);
	if (std::fabs(area) < 1e-6f) return;
	if (area < 0) { std::swap(bx, cx); std::swap(by, cy); }
	const float ex[3] = { ax, bx, cx }, ey[3] = { ay, by, cy };
	const int x0 = std::max((int)std::floor(std::min({ ax, bx, cx })), (int)clip.x), x1 = std::min((int)std::ceil(std::max({ ax, bx, cx })), clip.x + clip.w);
	const int y0 = std::max((int)std::floor(std::min({ ay, by, cy })), (int)clip.y), y1 = std::min((int)std::ceil(std::max({ ay, by, cy })), clip.y + clip.h);
	for (int y = y0; y < y1; ++y)
	{
		Uint32 *row = (Uint32*)((Uint8*)dest->pixels + (size_t)y * dest->pitch);
		for (int x = x0; x < x1; ++x)
		{
			const float px = x + 0.5f, py = y + 0.5f;
			float cov = 1.0f;
			for (int i = 0; i < 3 && cov > 0.0f; ++i)
			{
				const int j = (i + 1) % 3;
				const float dx = ex[j] - ex[i], dy = ey[j] - ey[i];
				const float len = std::sqrt(dx * dx + dy * dy);
				// signed distance to the edge line: inside is positive
				const float d = (dx * (py - ey[i]) - dy * (px - ex[i])) / std::max(len, 1e-6f);
				cov *= std::min(std::max(d + 0.5f, 0.0f), 1.0f);
			}
			if (cov > 0.002f) blendPixel(row[x], color, cov);
		}
	}
}

void HdUi::fillCircle(float cx, float cy, float r, Uint32 color)
{
	FrameTiming timing(_frameMs);
	SDL_Surface *dest;
	int k;
	const SDL_Color *pal;
	if (!target(dest, k, pal) || r <= 0.0f) return;
	const SDL_Rect clip = worldClip(dest, k);
	const int y0 = std::max((int)std::floor(cy - r), (int)clip.y), y1 = std::min((int)std::ceil(cy + r), clip.y + clip.h);
	const int x0 = std::max((int)std::floor(cx - r), (int)clip.x), x1 = std::min((int)std::ceil(cx + r), clip.x + clip.w);
	for (int y = y0; y < y1; ++y)
	{
		Uint32 *row = (Uint32*)((Uint8*)dest->pixels + (size_t)y * dest->pitch);
		for (int x = x0; x < x1; ++x)
		{
			const float dx = x + 0.5f - cx, dy = y + 0.5f - cy;
			const float cov = std::min(std::max(r - std::sqrt(dx * dx + dy * dy) + 0.5f, 0.0f), 1.0f);
			if (cov > 0.002f) blendPixel(row[x], color, cov);
		}
	}
}

void HdUi::blendGlyph(SDL_Surface *dest, const SDL_Rect &clip, const HdFont::Glyph &g, int x, int y, Uint32 color)
{
	const int x0 = std::max(x, (int)clip.x), y0 = std::max(y, (int)clip.y);
	const int x1 = std::min(x + g.w, clip.x + clip.w), y1 = std::min(y + g.h, clip.y + clip.h);
	const CoverageLut &lut = coverageLut();
	for (int py = y0; py < y1; ++py)
	{
		Uint32 *row = (Uint32*)((Uint8*)dest->pixels + (size_t)py * dest->pitch);
		const Uint8 *cov = &g.cov[(size_t)(py - y) * g.w];
		for (int px = x0; px < x1; ++px)
		{
			const Uint8 c = cov[px - x];
			if (c) blendPixel(row[px], color, lut.v[c]);
		}
	}
}

void HdUi::drawButton(int x, int y, int w, int h, int color, int mul, bool pressed, const SDL_Color *colors)
{
	SDL_Surface *dest;
	int k;
	const SDL_Color *pal;
	if (!target(dest, k, pal) || w <= 0 || h <= 0) return;
	if (colors) pal = colors;
	// the button's face hides whatever is under it: its label needs no outline even on a picture
	notePanel(x, y, w, h);
	auto c = [&](int v) { return rgba(pal[(Uint8)(color + v * mul)]); };
	const float x0 = (float)x * k, y0 = (float)y * k, x1 = (float)(x + w) * k, y1 = (float)(y + h) * k;
	const float r = 1.5f * k, edge = std::max(1.0f, k * 0.5f);
	const bool over = !pressed && hover(x, y, w, h);
	const int st = style();
	if (st == 2)
	{
		// dark: a near-black panel tinted with the ramp, a thin light edge; lit = the ramp's mid tone
		if (pressed)
		{
			// lit: the light end of the ramp (the label's colours invert to dark, as in the classic look)
			fillRoundRect(x0, y0, x1, y1, r, c(1), c(2));
			strokeRoundRect(x0, y0, x1, y1, r, edge, scaled(c(1), 1.15f));
		}
		else
		{
			fillRoundRect(x0, y0, x1, y1, r, darkened(c(5), over ? 0.25f : 0.5f), darkened(c(5), over ? 0.45f : 0.7f));
			strokeRoundRect(x0, y0, x1, y1, r, edge, withAlpha(c(2), over ? 0xC0 : 0x70));
		}
		return;
	}
	if (st == 3)
	{
		// flat: one mid tone, a thin edge; lit = the light end
		if (pressed)
		{
			fillRoundRect(x0, y0, x1, y1, r, c(2), c(2));
			strokeRoundRect(x0, y0, x1, y1, r, edge, withAlpha(c(1), 0xC0));
		}
		else
		{
			fillRoundRect(x0, y0, x1, y1, r, over ? c(3) : c(4), over ? c(3) : c(4));
			strokeRoundRect(x0, y0, x1, y1, r, edge, withAlpha(c(2), 0x90));
		}
		return;
	}
	if (pressed)
	{
		// lit: the bright end of the ramp, a little darker towards the bottom
		fillRoundRect(x0, y0, x1, y1, r, c(1), c(2));
		strokeRoundRect(x0, y0, x1, y1, r, edge, scaled(c(1), 1.15f));
	}
	else
	{
		// under the mouse: the same shape, a step lighter
		const float lit = over ? 1.22f : 1.0f;
		fillRoundRect(x0, y0, x1, y1, r, scaled(c(3), lit), scaled(c(5), lit));
		// a light edge on top, a dark one below (the shape reads as raised)
		strokeRoundRect(x0, y0, x1, y1, r, edge, (scaled(c(2), lit) & 0x00FFFFFFu) | 0xB0000000u);
		fillRoundRect(x0 + edge, y1 - edge * 1.5f, x1 - edge, y1 - edge * 0.5f, edge, (c(5) & 0x00FFFFFFu) | 0x90000000u, (c(5) & 0x00FFFFFFu) | 0x90000000u);
		if (lit > 1.0f)
		{
			// a sheen across the upper half
			fillRoundRect(x0 + edge, y0 + edge, x1 - edge, y0 + (y1 - y0) * 0.5f, std::max(r - edge, 0.0f), 0x28FFFFFFu, 0x08FFFFFFu);
		}
	}
}

void HdUi::drawShadow(int x, int y, int w, int h, float radius)
{
	SDL_Surface *dest;
	int k;
	const SDL_Color *pal;
	if (!target(dest, k, pal) || w <= 0 || h <= 0) return;
	// rings of falling alpha around the rectangle, shifted a little down (the light is above)
	const float step = std::max(1.0f, 0.75f * k), down = 0.5f * k;
	const float x0 = (float)x * k, y0 = (float)y * k + down, x1 = (float)(x + w) * k, y1 = (float)(y + h) * k + down;
	const float r = radius * k;
	static const Uint32 alpha[] = { 0x58, 0x3A, 0x22, 0x10, 0x06 };
	const int rings = 5;
	for (int i = 1; i <= rings; ++i)
	{
		const float d = i * step;
		strokeRoundRect(x0 - d, y0 - d, x1 + d, y1 + d, r + d, step, alpha[i - 1] << 24);
	}
}

void HdUi::drawRowBand(int x, int y, int w, int h, bool odd)
{
	SDL_Surface *dest;
	int k;
	const SDL_Color *pal;
	if (!target(dest, k, pal) || w <= 0 || h <= 0) return;
	const Uint32 c = odd ? 0x16000000u : 0x0AFFFFFFu;
	fillRoundRect((float)x * k, (float)y * k, (float)(x + w) * k, (float)(y + h) * k, 0.0f, c, c);
}

void HdUi::drawSlider(int x, int y, int w, int h, float t, int color, int mul, bool pressed, const SDL_Color *colors)
{
	SDL_Surface *dest;
	int k;
	const SDL_Color *pal;
	if (!target(dest, k, pal) || w <= 0 || h <= 0) return;
	if (colors) pal = colors;
	auto c = [&](int v) { return rgba(pal[(Uint8)(color + v * mul)]); };
	t = std::min(std::max(t, 0.0f), 1.0f);
	const float cy = ((float)y + h * 0.5f) * k;
	const float kr = std::min(0.32f * h, 5.0f) * k;                 // the knob's radius
	const float tx0 = (float)x * k + kr, tx1 = (float)(x + w) * k - kr;
	const float th = std::max(1.0f, 1.0f * k);                       // the track's half height
	const float kx = tx0 + (tx1 - tx0) * t;
	// the track: a dark groove, filled up to the knob in the ramp's light end
	fillRoundRect(tx0 - th, cy - th, tx1 + th, cy + th, th, 0x90000000u, 0x70000000u);
	strokeRoundRect(tx0 - th, cy - th, tx1 + th, cy + th, th, std::max(1.0f, 0.35f * k), 0x50FFFFFFu);
	if (kx > tx0)
	{
		fillRoundRect(tx0 - th, cy - th, kx, cy + th, th, c(2), c(3));
	}
	// the knob: a disc with a dark rim and a light top, its shadow below
	const bool lit = pressed || hover(x, y, w, h);
	const float rim = std::max(1.0f, 0.4f * k);
	fillCircle(kx + 0.35f * k, cy + 0.5f * k, kr, 0x60000000u);
	fillCircle(kx, cy, kr, scaled(c(5), 0.8f));
	fillCircle(kx, cy, kr - rim, lit ? scaled(c(1), 1.15f) : c(2));
	fillCircle(kx, cy - kr * 0.3f, kr * 0.5f, lit ? 0x50FFFFFFu : 0x30FFFFFFu);
}

void HdUi::drawScrollBar(int x, int y, int w, int h, int ty0, int ty1, int color, bool pressed, const SDL_Color *colors)
{
	SDL_Surface *dest;
	int k;
	const SDL_Color *pal;
	if (!target(dest, k, pal) || w <= 0 || h <= 0) return;
	if (colors) pal = colors;
	// a thin groove down the middle, the thumb a rounded bar a little wider than it
	const float cx = ((float)x + w * 0.5f) * k;
	const float trackHw = std::min((float)w, 2.5f) * 0.5f * k, thumbHw = std::min((float)w, 5.0f) * 0.5f * k;
	const float y0 = (float)y * k, y1 = (float)(y + h) * k;
	fillRoundRect(cx - trackHw, y0, cx + trackHw, y1, trackHw, 0x70000000u, 0x70000000u);
	if (ty1 > ty0)
	{
		const float a = y0 + (float)ty0 * k, b = std::min(y1, y0 + (float)ty1 * k);
		const bool lit = pressed || hover(x, y, w, h);
		const Uint32 c = rgba(pal[(Uint8)(color + 2)]);
		fillRoundRect(cx - thumbHw, a, cx + thumbHw, b, thumbHw, scaled(c, lit ? 1.3f : 1.1f), scaled(c, lit ? 1.0f : 0.8f));
		strokeRoundRect(cx - thumbHw, a, cx + thumbHw, b, thumbHw, std::max(1.0f, 0.35f * k), 0x40FFFFFFu);
	}
}

void HdUi::drawChevron(int x, int y, int w, int h, int color, const SDL_Color *colors)
{
	SDL_Surface *dest;
	int k;
	const SDL_Color *pal;
	if (!target(dest, k, pal) || w <= 0 || h <= 0) return;
	if (colors) pal = colors;
	// a small triangle pointing down, with a shadow
	const float cx = ((float)x + w * 0.5f) * k, cy = ((float)y + h * 0.5f) * k;
	const float hw = std::min(w * 0.32f, 3.5f) * k, hh = std::min(h * 0.28f, 2.2f) * k;
	const float off = std::max(1.0f, 0.5f * k);
	fillTriangle(cx - hw + off, cy - hh + off, cx + hw + off, cy - hh + off, cx + off, cy + hh + off, (rgba(pal[(Uint8)(color + 5)]) & 0x00FFFFFFu) | 0xA0000000u);
	fillTriangle(cx - hw, cy - hh, cx + hw, cy - hh, cx, cy + hh, rgba(pal[(Uint8)(color + 1)]));
}

void HdUi::drawPanelFrame(int x, int y, int w, int h, int color, int mul, int inset, bool thin, const SDL_Color *colors)
{
	SDL_Surface *dest;
	int k;
	const SDL_Color *pal;
	if (!target(dest, k, pal) || w <= 0 || h <= 0) return;
	// a window stands between the text and whatever picture fills the screen behind it, whichever way its
	// own fill was drawn: its labels keep the classic shadow
	notePanel(x, y, w, h);
	if (colors) pal = colors;
	auto c = [&](int v) { return rgba(pal[(Uint8)(color + v * mul)]); };
	const float x0 = (float)x * k, y0 = (float)y * k, x1 = (float)(x + w) * k, y1 = (float)(y + h) * k;
	const float r = (thin ? 1.0f : 2.0f) * k, edge = std::max(1.0f, k * 0.5f);
	const float band = (float)inset * k;
	const int st = style();
	if (st == 2)
	{
		// dark: a near-black band, a thin light edge outside and a faint one inside
		strokeRoundRect(x0, y0, x1, y1, r, band, darkened(c(5), 0.6f));
		strokeRoundRect(x0, y0, x1, y1, r, edge, withAlpha(c(2), 0x80));
		if (band > edge * 2)
		{
			strokeRoundRect(x0 + band - edge, y0 + band - edge, x1 - band + edge, y1 - band + edge, std::max(r - band + edge, 0.0f), edge, withAlpha(c(3), 0x50));
		}
		return;
	}
	if (st == 3)
	{
		// flat: the band in the mid tone, one light edge
		strokeRoundRect(x0, y0, x1, y1, r, band, thin ? c(3) : c(4));
		strokeRoundRect(x0, y0, x1, y1, r, edge, withAlpha(c(2), 0x90));
		return;
	}
	// the band: the dark end of the ramp, with a light outer edge and a dark inner edge
	strokeRoundRect(x0, y0, x1, y1, r, band, thin ? c(3) : c(4));
	strokeRoundRect(x0, y0, x1, y1, r, edge, (c(2) & 0x00FFFFFFu) | 0xC0000000u);
	if (band > edge * 2)
	{
		strokeRoundRect(x0 + band - edge, y0 + band - edge, x1 - band + edge, y1 - band + edge, std::max(r - band + edge, 0.0f), edge, (c(5) & 0x00FFFFFFu) | 0xC0000000u);
	}
}

void HdUi::drawHighlight(int x, int y, int w, int h, Uint32 accent)
{
	SDL_Surface *dest;
	int k;
	const SDL_Color *pal;
	if (!target(dest, k, pal) || w <= 0 || h <= 0) return;
	const float x0 = (float)x * k, y0 = (float)y * k, x1 = (float)(x + w) * k, y1 = (float)(y + h) * k;
	fillRoundRect(x0, y0, x1, y1, 1.0f * k, 0x30FFFFFFu, 0x30FFFFFFu);
	strokeRoundRect(x0, y0, x1, y1, 1.0f * k, std::max(1.0f, k * 0.5f), 0x40FFFFFFu);
	if (accent >> 24)
	{
		// the accent bar at the left, inside the band
		const float bw = std::max(1.0f, 1.0f * k), inset = std::max(1.0f, 0.5f * k);
		fillRoundRect(x0 + inset, y0 + inset, x0 + inset + bw, y1 - inset, bw * 0.5f, accent, accent);
	}
}

const HdUi::FontMetrics &HdUi::metrics(const Font *font)
{
	auto it = _metrics.find(font);
	if (it != _metrics.end())
	{
		return it->second;
	}
	FontMetrics &m = _metrics[font];
	if (!font)
	{
		return m;
	}
	// the capitals: the rows of 'H' (or '0') with anything in them, shadow included
	int rows = 0;
	for (UCode c : { (UCode)'H', (UCode)'0', (UCode)'A' })
	{
		SurfaceCrop crop = font->getChar(c);
		const Surface *sheet = crop.getSurface();
		const SDL_Rect *r = crop.getCrop();
		if (!sheet || r->w <= 0 || r->h <= 0) continue;
		int first = -1, last = -1;
		for (int y = 0; y < r->h; ++y)
		{
			bool any = false;
			for (int x = 0; x < r->w && !any; ++x) any = sheet->getPixel(r->x + x, r->y + y) != 0;
			if (any) { if (first < 0) first = y; last = y; }
		}
		if (first >= 0) { rows = last - first + 1; break; }
	}
	if (rows <= 0) rows = font->getHeight() - 1;
	m.classicCap = rows;
	m.big = rows >= BIG_CAP_ROWS;
	m.cap = rows * (m.big ? CAP_RATIO_BIG : CAP_RATIO_SMALL);
	m.lineH = std::max(1, font->getHeight() + font->getSpacing());
	return m;
}

float HdUi::ttfWidth(const UString &s, bool big, float capHeight)
{
	const int k = scale();
	if (!k || !hasFonts()) return 0.0f;
	HdFont &f = font(big);
	return f.measure(s, f.sizeForCapHeight(capHeight * k)) / k;
}

void HdUi::drawTtfString(const UString &s, bool big, float capHeight, int x, int y, Uint32 face, Uint32 shadow)
{
	FrameTiming timing(_frameMs);
	SDL_Surface *dest;
	int k;
	const SDL_Color *pal;
	if (!target(dest, k, pal) || !hasFonts() || s.empty()) return;
	const SDL_Rect clip = worldClip(dest, k);
	HdFont &f = font(big);
	const float px = f.sizeForCapHeight(capHeight * k);
	const int baseline = y * k + (int)std::lround(centredBaseline(big ? 16.0f : 9.0f, capHeight) * k);
	const int shadowOff = std::max(1, k / 2);
	for (int pass = (shadow >> 24) ? 0 : 1; pass < 2; ++pass)
	{
		float pen = (float)(x * k);
		UCode prev = 0;
		for (UCode c : s)
		{
			if (prev) pen += f.kern(prev, c, px);
			const HdFont::Glyph &g = f.glyph(c, px);
			if (g.w > 0)
			{
				const int gx = (int)std::lround(pen) + g.xoff + (pass == 0 ? shadowOff : 0);
				const int gy = baseline + g.yoff + (pass == 0 ? shadowOff : 0);
				blendGlyph(dest, clip, g, gx, gy, pass == 0 ? shadow : face);
			}
			pen += g.advance;
			prev = c;
		}
	}
}

void HdUi::drawTtfCaret(const UString &value, size_t pos, const Font *classic, int x, int y, int textW, int textH, int align, Uint32 color)
{
	SDL_Surface *dest;
	int k;
	const SDL_Color *pal;
	if (!target(dest, k, pal) || !hasFonts()) return;
	const FontMetrics &m = metrics(classic);
	HdFont &f = font(m.big);
	const float cap = m.cap;
	const float px = f.sizeForCapHeight(cap * k);
	// the line as drawTtfLine places it (condensed when it would not fit)
	float total = f.measure(value, px);
	const float avail = (float)textW * k;
	float condense = 1.0f;
	if (total > avail && avail > 0)
	{
		condense = std::max(avail / total, 0.6f);
		total = f.measure(value, px, condense);
	}
	float pen;
	switch (align)
	{
	case 1: pen = x * k + (avail - total) * 0.5f; break;
	case 2: pen = x * k + avail - total - 0.5f * k; break;
	default: pen = (float)x * k; break;
	}
	pen += f.measure(UString(value.begin(), value.begin() + std::min(pos, value.size())), px, condense);
	// the line box as drawTtfLine centres a single line: the text's box when it is about a line tall
	const float boxH = (float)(textH > 0 && textH <= m.lineH + 3 ? textH : m.lineH);
	const float baseline = y * k + centredBaseline(boxH, cap) * k;
	const float w = std::max(1.0f, 0.4f * k);
	fillRoundRect(pen, baseline - cap * k * 1.15f, pen + w, baseline + cap * k * 0.2f, w * 0.5f, color, color);
}

/**
 * A line of text as the classic layout arranged it, drawn with the TrueType
 * fonts: the runs' natural widths are summed, the line is placed by the
 * alignment within the text's width, condensed when it would not fit.
 */
void HdUi::drawTtfLine(const std::vector<TextRun> &runs, int originX, int originY, int textW, int textH, int align, bool singleLine, const SDL_Color *pal)
{
	FrameTiming timing(_frameMs);
	SDL_Surface *dest;
	int k;
	const SDL_Color *screenPal;
	if (!target(dest, k, screenPal) || !hasFonts() || runs.empty()) return;
	if (!pal) pal = screenPal;
	const SDL_Rect clip = worldClip(dest, k);
	// each run: its body, and the dot leaders at its ends that keep their classic length (world pixels);
	// capital titles in the big font get a little letter-spacing
	struct Part
	{
		size_t lead = 0, trail = 0;
		UString body;
		float px = 0.0f, track = 0.0f, leadW = 0.0f, trailW = 0.0f;
	};
	std::vector<Part> parts(runs.size());
	// a line taller than its rectangle allows (the capitals plus a little room; the classic big font is
	// crammed into 13-pixel buttons): set smaller
	float shrink = 1.0f;
	for (const TextRun &r : runs)
	{
		const FontMetrics &m = metrics(r.font);
		const int room = textH - (m.big ? 4 : 2);
		if (textH > 0 && m.cap > room)
		{
			shrink = std::min(shrink, std::max((float)room / m.cap, 0.5f));
		}
	}
	for (size_t i = 0; i < runs.size(); ++i)
	{
		const TextRun &r = runs[i];
		Part &p = parts[i];
		const FontMetrics &m = metrics(r.font);
		HdFont &f = font(m.big);
		p.px = f.sizeForCapHeight(m.cap * k * shrink);
		p.trail = trailingDots(r.text);
		p.lead = p.trail < r.text.size() ? leadingDots(r.text) : 0;
		p.body.assign(r.text.begin() + p.lead, r.text.end() - p.trail);
		p.leadW = (float)(p.lead * r.dotW) * k;
		p.trailW = (float)(p.trail * r.dotW) * k;
		if (m.big && !p.body.empty())
		{
			bool caps = true;
			for (UCode c : p.body) if (isLowerLetter(c)) { caps = false; break; }
			if (caps) p.track = TRACKING_CAPS * p.px;
		}
	}
	auto bodyWidth = [&](size_t i, float condense)
	{
		const Part &p = parts[i];
		if (p.body.empty()) return 0.0f;
		return font(metrics(runs[i].font).big).measure(p.body, p.px, condense) + p.track * condense * (float)(p.body.size() - 1);
	};
	// natural width
	float total = 0.0f, fixed = 0.0f;
	for (size_t i = 0; i < runs.size(); ++i)
	{
		total += parts[i].leadW + bodyWidth(i, 1.0f) + parts[i].trailW;
		fixed += parts[i].leadW + parts[i].trailW;
	}
	if (total <= 0.0f) return;
	// the room: from the first run's classic x (the indent the layout gave it) to the text's right edge
	const int lineStart = runs.front().x;
	const float avail = (float)(textW - (align == 0 ? lineStart : 0)) * k;
	float condense = 1.0f;
	if (total > avail && avail > 0 && total > fixed)
	{
		// too wide: condense a little; if that is not enough, set the line smaller (a big label in a
		// narrow button, as the classic big font is crammed into it), then condense the rest
		condense = std::max((avail - fixed) / (total - fixed), 0.8f);
		total = fixed;
		for (size_t i = 0; i < runs.size(); ++i) total += bodyWidth(i, condense);
		if (total > avail)
		{
			const float s = std::max((avail - fixed) / (total - fixed), 0.5f / shrink);
			shrink *= s;
			for (Part &p : parts) { p.px *= s; p.track *= s; }
			total = fixed;
			for (size_t i = 0; i < runs.size(); ++i) total += bodyWidth(i, condense);
			if (total > avail)
			{
				condense = std::max(condense * (avail - fixed) / (total - fixed), 0.6f);
				total = fixed;
				for (size_t i = 0; i < runs.size(); ++i) total += bodyWidth(i, condense);
			}
		}
	}
	float pen;
	switch (align)
	{
	case 1: pen = originX * k + ((float)textW * k - total) * 0.5f; break;                         // centre
	case 2: pen = originX * k + (float)textW * k - total - 0.5f * k; break;                         // right
	default: pen = (float)(originX + lineStart) * k; break;                                         // left
	}
	// a line lying straight on an HD picture: the letters are given an outline of their own, because a
	// light line over a bright photograph cannot be read at all. Over a panel or a plain background the
	// classic drop shadow is what the text has always had, and it stays
	const bool onPicture = overPicture(originX, originY, std::max(textW, 1), std::max(textH, 1));
	// two base pixels' worth of edge: at k = 4 a fixed 2 would be a quarter of a base pixel and simply
	// would not be seen, so the outline grows with the scale like everything else here
	const int outlineW = std::max(2, k);
	const int shadowOff = onPicture ? 0 : std::max(1, k / 2);
	for (int pass = 0; pass < 2; ++pass)
	{
		float x = pen;
		for (size_t i = 0; i < runs.size(); ++i)
		{
			const TextRun &r = runs[i];
			const Part &p = parts[i];
			const FontMetrics &m = metrics(r.font);
			HdFont &f = font(m.big);
			// the colour rule of the classic text: shade 1/2 is the face, shade 5 the shadow
			const int faceV = m.classicCap >= 12 ? 2 : 1, shadowV = 5;
			auto idx = [&](int v) { return (Uint8)(r.color + v * r.mul + (r.mid ? 2 * (r.mid - v) : 0)); };
			const Uint32 face = rgba(pal[idx(faceV)]);
			const Uint32 shadow = rgba(pal[idx(shadowV)], onPicture ? 255 : 150);
			// pass 0 is the outline on a picture, the drop shadow anywhere else
			auto shape = [&](UCode ch) -> const HdFont::Glyph &
			{
				return pass == 0 && onPicture ? f.outline(ch, p.px, condense, outlineW) : f.glyph(ch, p.px, condense);
			};
			const Uint32 color = pass == 0 ? shadow : face;
			const int off = pass == 0 ? shadowOff : 0;
			// the baseline: the capitals centred in the classic line box, or in the text's own box when
			// that is a single line of about the line's height (a button's label sits in its middle)
			const bool inBox = singleLine && textH > 0 && textH <= m.lineH + 3;
			const float boxY = inBox ? 0.0f : (float)r.y, boxH = inBox ? (float)textH : (float)m.lineH;
			const int baseline = originY * k + (int)std::lround((boxY + centredBaseline(boxH, m.cap * shrink)) * k);
			// a dot leader: n dots evenly over the classic length
			auto leader = [&](size_t n, float from, float width)
			{
				if (n == 0 || width <= 0.0f) return;
				const HdFont::Glyph &g = shape('.');
				if (g.w <= 0) return;
				const float cell = width / n;
				for (size_t d = 0; d < n; ++d)
				{
					const int gx = (int)std::lround(from + cell * d + (cell - g.advance) * 0.5f) + g.xoff + off;
					blendGlyph(dest, clip, g, gx, baseline + g.yoff + off, color);
				}
			};
			leader(p.lead, x, p.leadW);
			x += p.leadW;
			UCode prev = 0;
			for (UCode c : p.body)
			{
				if (prev) x += f.kern(prev, c, p.px, condense) + p.track * condense;
				const HdFont::Glyph &g = shape(c);
				if (g.w > 0)
				{
					const int gx = (int)std::lround(x) + g.xoff + off;
					const int gy = baseline + g.yoff + off;
					blendGlyph(dest, clip, g, gx, gy, color);
				}
				x += g.advance;
				prev = c;
			}
			leader(p.trail, x, p.trailW);
			x += p.trailW;
		}
	}
}

}
