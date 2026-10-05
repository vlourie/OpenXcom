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
#include "HdBattleHud.h"
#include <algorithm>
#include <cmath>
#include <unordered_map>
#include "HdUi.h"
#include "HdWorkers.h"
#include "Options.h"

namespace OpenXcom
{

namespace
{

// the panel's own colours (0xAARRGGBB): a dark slate with one warm accent, the same in every mod
const Uint32 PANEL_TOP = 0xF4171D26u, PANEL_BOTTOM = 0xF40B0E13u, PANEL_EDGE = 0x38FFFFFFu;
const Uint32 TILE_TOP = 0xFF2A323Eu, TILE_BOTTOM = 0xFF1C222Bu, TILE_EDGE = 0x2EFFFFFFu;
const Uint32 HOVER_TOP = 0xFF36414Fu, HOVER_BOTTOM = 0xFF252D38u;
const Uint32 ACCENT = 0xFFE6A23Cu, LIT_TOP = 0xFFF2B655u, LIT_BOTTOM = 0xFFC2822Au;
const Uint32 ICON = 0xFFCDD6E1u, ICON_HOVER = 0xFFFFFFFFu, ICON_LIT = 0xFF22180Bu;
const Uint32 WELL_TOP = 0xFF05070Au, WELL_BOTTOM = 0xFF0D1015u, WELL_EDGE = 0x36FFFFFFu;
const Uint32 CARD_TOP = 0xFF0E1218u, CARD_BOTTOM = 0xFF0A0D11u, CARD_EDGE = 0x22FFFFFFu;
const Uint32 RANK_FILL = 0xFF151A22u;

inline Uint32 withAlpha(Uint32 c, Uint32 a) { return (c & 0x00FFFFFFu) | (a << 24); }

/// A shape of a pictogram, in the button's base pixels; a cut takes away from what is drawn before it.
struct Shape
{
	enum Type { CIRCLE, ARC, SEGMENT, POLYGON, ROUND_RECT } type;
	bool cut = false;
	float a = 0, b = 0, c = 0, d = 0, e = 0, f = 0, g = 0;
	std::vector<float> pts;
	float x0 = 0, y0 = 0, x1 = 0, y1 = 0;   ///< the bounding box

	bool inside(float x, float y) const
	{
		if (x < x0 || x > x1 || y < y0 || y > y1) return false;
		switch (type)
		{
		case CIRCLE:
		{
			const float dx = x - a, dy = y - b;
			return dx * dx + dy * dy <= c * c;
		}
		case ARC:
		{
			// a ring (centre a b, radius c, width d) from angle e to f (degrees, clockwise from +x on screen)
			const float dx = x - a, dy = y - b;
			const float r = std::sqrt(dx * dx + dy * dy);
			if (std::fabs(r - c) > d * 0.5f) return false;
			if (f - e >= 360.0f) return true;
			float ang = std::atan2(dy, dx) * 57.29578f;
			while (ang < e) ang += 360.0f;
			return ang <= f;
		}
		case SEGMENT:
		{
			// a stroke from (a, b) to (c, d), e wide, round ends
			const float vx = c - a, vy = d - b, wx = x - a, wy = y - b;
			const float l2 = vx * vx + vy * vy;
			const float t = l2 > 0 ? std::min(std::max((wx * vx + wy * vy) / l2, 0.0f), 1.0f) : 0.0f;
			const float px = wx - t * vx, py = wy - t * vy;
			return px * px + py * py <= e * e * 0.25f;
		}
		case POLYGON:
		{
			bool in = false;
			const size_t n = pts.size() / 2;
			for (size_t i = 0, j = n - 1; i < n; j = i++)
			{
				const float xi = pts[2 * i], yi = pts[2 * i + 1], xj = pts[2 * j], yj = pts[2 * j + 1];
				if ((yi > y) != (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) in = !in;
			}
			return in;
		}
		case ROUND_RECT:
		{
			// (a, b) - (c, d), corner radius e
			const float r = e;
			const float cx = std::min(std::max(x, a + r), c - r), cy = std::min(std::max(y, b + r), d - r);
			const float dx = x - cx, dy = y - cy;
			return dx * dx + dy * dy <= r * r;
		}
		}
		return false;
	}
};

/// A pictogram: shapes in drawing order, in a frame moved by (ox, oy).
struct Pic
{
	std::vector<Shape> shapes;
	float ox = 0, oy = 0;
	bool cutting = false;

	Pic &at(float x, float y) { ox = x; oy = y; return *this; }
	Pic &cut(bool on) { cutting = on; return *this; }
	Shape &add(Shape::Type t)
	{
		shapes.emplace_back();
		Shape &s = shapes.back();
		s.type = t;
		s.cut = cutting;
		return s;
	}
	Pic &circle(float x, float y, float r)
	{
		Shape &s = add(Shape::CIRCLE);
		s.a = x + ox; s.b = y + oy; s.c = r;
		s.x0 = s.a - r; s.x1 = s.a + r; s.y0 = s.b - r; s.y1 = s.b + r;
		return *this;
	}
	Pic &arc(float x, float y, float r, float w, float from = 0, float to = 360)
	{
		Shape &s = add(Shape::ARC);
		s.a = x + ox; s.b = y + oy; s.c = r; s.d = w; s.e = from; s.f = to;
		const float o = r + w * 0.5f;
		s.x0 = s.a - o; s.x1 = s.a + o; s.y0 = s.b - o; s.y1 = s.b + o;
		return *this;
	}
	Pic &line(float xa, float ya, float xb, float yb, float w)
	{
		Shape &s = add(Shape::SEGMENT);
		s.a = xa + ox; s.b = ya + oy; s.c = xb + ox; s.d = yb + oy; s.e = w;
		s.x0 = std::min(s.a, s.c) - w; s.x1 = std::max(s.a, s.c) + w;
		s.y0 = std::min(s.b, s.d) - w; s.y1 = std::max(s.b, s.d) + w;
		return *this;
	}
	Pic &poly(std::initializer_list<float> p)
	{
		Shape &s = add(Shape::POLYGON);
		s.pts.assign(p.begin(), p.end());
		s.x0 = s.y0 = 1e9f; s.x1 = s.y1 = -1e9f;
		for (size_t i = 0; i + 1 < s.pts.size(); i += 2)
		{
			s.pts[i] += ox; s.pts[i + 1] += oy;
			s.x0 = std::min(s.x0, s.pts[i]); s.x1 = std::max(s.x1, s.pts[i]);
			s.y0 = std::min(s.y0, s.pts[i + 1]); s.y1 = std::max(s.y1, s.pts[i + 1]);
		}
		return *this;
	}
	Pic &rect(float xa, float ya, float xb, float yb, float r)
	{
		Shape &s = add(Shape::ROUND_RECT);
		s.a = xa + ox; s.b = ya + oy; s.c = xb + ox; s.d = yb + oy;
		s.e = std::min(r, std::min(xb - xa, yb - ya) * 0.5f);
		s.x0 = s.a; s.x1 = s.c; s.y0 = s.b; s.y1 = s.d;
		return *this;
	}

	// --- the pieces the pictograms are made of (x = the piece's centre line) ---

	/// A standing figure, its head's top at y = top; s = 1 is 11.2 base pixels tall (feet at top + 11.2).
	Pic &person(float x, float top = 2.45f, float s = 1.0f)
	{
		auto Y = [&](float v) { return top + (v - 2.45f) * s; };
		circle(x, Y(4.2f), 1.75f * s);
		rect(x - 1.75f * s, Y(6.4f), x + 1.75f * s, Y(10.3f), 0.9f * s);
		line(x - 2.15f * s, Y(7.0f), x - 2.7f * s, Y(10.0f), 1.0f * s);
		line(x + 2.15f * s, Y(7.0f), x + 2.7f * s, Y(10.0f), 1.0f * s);
		line(x - 0.85f * s, Y(10.0f), x - 1.05f * s, Y(13.3f), 1.4f * s);
		line(x + 0.85f * s, Y(10.0f), x + 1.05f * s, Y(13.3f), 1.4f * s);
		return *this;
	}
	/// A figure shooting to the right, for the 17 x 11 reserve buttons: the gun at the hip (snap and
	/// auto) or raised to the eye (aimed), as the mod draws them.
	Pic &shooter(float x, bool aimed)
	{
		circle(x, 2.6f, 1.3f);
		rect(x - 1.05f, 3.9f, x + 1.05f, 6.8f, 0.5f);
		line(x - 0.45f, 6.5f, x - 1.7f, 9.2f, 1.15f);
		line(x + 0.45f, 6.5f, x + 1.5f, 9.2f, 1.15f);
		if (aimed)
		{
			line(x + 0.6f, 4.3f, x + 2.4f, 3.3f, 1.0f);
			rect(x + 1.6f, 2.75f, x + 7.0f, 3.75f, 0.3f);
		}
		else
		{
			line(x + 0.6f, 4.6f, x + 2.6f, 4.9f, 1.0f);
			rect(x + 2.0f, 4.35f, x + 7.0f, 5.35f, 0.3f);
		}
		return *this;
	}
	/// The levels of the map: a narrow column of three storeys.
	Pic &storeys(float x)
	{
		rect(x - 2.4f, 3.0f, x + 2.4f, 13.0f, 0.5f);
		cut(true);
		for (int i = 0; i < 3; ++i)
		{
			rect(x - 1.25f, 4.15f + 2.95f * i, x + 1.25f, 6.05f + 2.95f * i, 0.2f);
		}
		return cut(false);
	}
	/// A kneeling figure, the same feet line.
	Pic &kneeling(float x)
	{
		// upright, one knee on the ground, the other leg bent forward
		circle(x, 5.3f, 1.75f);
		rect(x - 1.65f, 7.5f, x + 1.65f, 10.9f, 0.9f);
		line(x - 2.05f, 8.1f, x - 2.5f, 10.6f, 1.0f);
		line(x + 2.05f, 8.1f, x + 2.5f, 10.6f, 1.0f);
		line(x + 0.6f, 10.5f, x + 3.4f, 10.8f, 1.4f);
		line(x + 3.4f, 10.8f, x + 3.6f, 13.4f, 1.4f);
		line(x - 0.8f, 10.5f, x - 1.0f, 13.1f, 1.4f);
		line(x - 1.0f, 13.3f, x - 3.6f, 13.4f, 1.3f);
		return *this;
	}
	/// A triangle pointing up or down, centred at (x, y).
	Pic &arrow(float x, float y, bool up)
	{
		const float s = up ? 1.0f : -1.0f;
		return poly({ x - 3.2f, y + 2.0f * s, x + 3.2f, y + 2.0f * s, x, y - 2.6f * s });
	}
	/// A triangle pointing right, centred at (x, y).
	Pic &arrowRight(float x, float y)
	{
		return poly({ x - 2.0f, y - 2.8f, x + 2.4f, y, x - 2.0f, y + 2.8f });
	}
};

/// The pictograms follow the mod's own picture of the panel (the same sign on the same button), drawn
/// again as clean shapes: what the player knows a button by stays.
Pic makeIcon(HdBattleHud::Icon icon)
{
	Pic p;
	switch (icon)
	{
	case HdBattleHud::ICON_UNIT_UP: p.arrow(10.5f, 8.2f, true).person(20.5f); break;
	case HdBattleHud::ICON_UNIT_DOWN: p.arrow(10.5f, 7.8f, false).person(20.5f); break;
	case HdBattleHud::ICON_MAP_UP: p.arrow(10.5f, 8.2f, true).storeys(20.5f); break;
	case HdBattleHud::ICON_MAP_DOWN: p.arrow(10.5f, 7.8f, false).storeys(20.5f); break;
	case HdBattleHud::ICON_SHOW_MAP:
		// a map sheet with a tab, its left part a grid of squares
		p.rect(8.6f, 4.2f, 23.4f, 13.0f, 0.9f).rect(17.0f, 2.6f, 23.4f, 5.2f, 0.7f);
		p.cut(true).rect(9.8f, 5.4f, 22.2f, 11.8f, 0.3f).cut(false);
		for (int i = 0; i < 9; ++i)
		{
			const float x = 10.5f + (i % 3) * 1.85f, y = 6.1f + (i / 3) * 1.85f;
			p.rect(x, y, x + 1.3f, y + 1.3f, 0.15f);
		}
		break;
	case HdBattleHud::ICON_KNEEL:
		// stand / kneel
		p.person(8.6f).line(13.6f, 12.8f, 18.4f, 3.2f, 1.0f).kneeling(22.8f);
		break;
	case HdBattleHud::ICON_INVENTORY:
		p.person(16.0f);
		break;
	case HdBattleHud::ICON_CENTER:
		// the unit in the middle of the view: a small figure in four ticks
		p.person(16.0f, 4.3f, 0.66f);
		p.line(10.6f, 6.2f, 10.6f, 9.8f, 1.1f).line(21.4f, 6.2f, 21.4f, 9.8f, 1.1f);
		p.line(14.2f, 2.6f, 17.8f, 2.6f, 1.1f).line(14.2f, 13.4f, 17.8f, 13.4f, 1.1f);
		break;
	case HdBattleHud::ICON_NEXT_SOLDIER: p.person(9.0f).arrowRight(16.3f, 8.2f).person(23.0f); break;
	case HdBattleHud::ICON_NEXT_STOP:
		// done with this one (struck through), on to the next
		p.person(8.4f).cut(true).line(4.6f, 13.4f, 12.2f, 2.8f, 2.6f).cut(false).line(4.6f, 13.4f, 12.2f, 2.8f, 1.0f);
		p.line(13.6f, 8.2f, 17.2f, 8.2f, 1.1f).poly({ 16.4f, 6.0f, 19.2f, 8.2f, 16.4f, 10.4f });
		p.person(23.6f);
		break;
	case HdBattleHud::ICON_SHOW_LAYERS:
	{
		// three stacked diamonds, each lower one cut where the upper lies over it
		auto diamond = [&](float y, float grow) { p.poly({ 16.0f, y - 2.7f - grow, 22.2f + grow * 2.0f, y, 16.0f, y + 2.7f + grow, 9.8f - grow * 2.0f, y }); };
		diamond(11.2f, 0.0f);
		p.cut(true); diamond(8.0f, 0.75f); p.cut(false);
		diamond(8.0f, 0.0f);
		p.cut(true); diamond(4.8f, 0.75f); p.cut(false);
		diamond(4.8f, 0.0f);
		break;
	}
	case HdBattleHud::ICON_LINKS:
		p.rect(10.4f, 3.9f, 21.6f, 5.6f, 0.8f).rect(10.4f, 7.15f, 21.6f, 8.85f, 0.8f).rect(10.4f, 10.4f, 21.6f, 12.1f, 0.8f);
		break;
	case HdBattleHud::ICON_OPTIONS:
		// a question mark
		p.arc(16.0f, 5.9f, 2.7f, 1.7f, 180.0f, 405.0f);
		p.line(17.9f, 7.8f, 16.0f, 9.2f, 1.7f).line(16.0f, 9.2f, 16.0f, 10.1f, 1.7f);
		p.circle(16.0f, 12.6f, 1.05f);
		break;
	case HdBattleHud::ICON_END_TURN:
		// a struck circle
		p.arc(16.0f, 8.0f, 4.1f, 1.4f).line(13.3f, 10.7f, 18.7f, 5.3f, 1.4f);
		break;
	case HdBattleHud::ICON_ABORT:
		// back on board: the craft, an arrow up to it
		p.poly({ 8.6f, 6.6f, 10.0f, 5.2f, 20.4f, 4.7f, 22.4f, 2.0f, 24.0f, 2.0f, 23.4f, 5.4f, 22.2f, 6.9f, 10.2f, 7.5f });
		p.poly({ 14.4f, 6.8f, 18.6f, 6.8f, 16.6f, 8.0f, 13.8f, 8.0f });
		p.poly({ 13.4f, 11.8f, 18.6f, 11.8f, 16.0f, 9.2f }).line(16.0f, 11.4f, 16.0f, 13.8f, 1.3f);
		break;
	case HdBattleHud::ICON_RESERVE_NONE:
		p.line(2.6f, 5.5f, 11.6f, 5.5f, 1.3f).poly({ 10.8f, 2.7f, 14.6f, 5.5f, 10.8f, 8.3f });
		break;
	case HdBattleHud::ICON_RESERVE_SNAP:
		p.shooter(4.4f, false).line(12.6f, 4.85f, 14.4f, 4.85f, 1.0f);
		break;
	case HdBattleHud::ICON_RESERVE_AIMED:
		p.shooter(4.4f, true).line(12.6f, 3.25f, 14.4f, 3.25f, 1.0f);
		break;
	case HdBattleHud::ICON_RESERVE_AUTO:
		p.shooter(4.4f, false).line(10.4f, 4.85f, 11.0f, 4.85f, 1.0f).line(12.2f, 4.85f, 12.8f, 4.85f, 1.0f).line(14.0f, 4.85f, 14.6f, 4.85f, 1.0f);
		break;
	case HdBattleHud::ICON_RESERVE_KNEEL:
		// down to the knee: an arrow over a kneeling figure
		p.line(5.0f, 2.4f, 5.0f, 6.6f, 1.2f).poly({ 2.6f, 5.6f, 7.4f, 5.6f, 5.0f, 8.6f });
		p.at(1.8f, 6.2f).kneeling(3.2f);
		break;
	case HdBattleHud::ICON_ZERO_TUS:
		// the unit's time units to nought: a figure over a struck zero
		p.person(5.0f, 2.4f, 0.66f).rect(2.2f, 10.5f, 7.8f, 11.5f, 0.3f);
		p.rect(2.9f, 13.0f, 7.1f, 19.6f, 2.1f).cut(true).rect(4.1f, 14.2f, 5.9f, 18.4f, 0.9f).cut(false);
		p.line(4.2f, 17.9f, 5.8f, 14.7f, 0.8f);
		break;
	default:
		break;
	}
	return p;
}

/// A pictogram's coverage at a scale (one byte per world pixel), and its colourings.
struct Raster
{
	int w = 0, h = 0;
	std::vector<Uint8> cov;
	std::unordered_map<Uint32, std::vector<Uint32>> colored;
};

int cacheScale = 0;
std::unordered_map<Uint64, Raster> cache;

const Raster &raster(HdBattleHud::Icon icon, int w, int h, int k)
{
	if (k != cacheScale)
	{
		cache.clear();
		cacheScale = k;
	}
	const Uint64 key = ((Uint64)icon << 32) | ((Uint64)(w & 0xFFFF) << 16) | (Uint64)(h & 0xFFFF);
	auto found = cache.find(key);
	if (found != cache.end()) return found->second;
	Raster &r = cache[key];
	r.w = w * k;
	r.h = h * k;
	r.cov.assign((size_t)r.w * r.h, 0);
	const Pic pic = makeIcon(icon);
	// 4 x 4 samples a pixel; the rows are shared out to the render threads (a hand of pictograms a scale)
	const int S = 4;
	const float inv = 1.0f / (float)k;
	auto rows = [&](int ra, int rb)
	{
		for (int py = ra; py < rb; ++py)
		{
			for (int px = 0; px < r.w; ++px)
			{
				int hits = 0;
				for (int sy = 0; sy < S; ++sy)
				{
					const float y = (py + (sy + 0.5f) / S) * inv;
					for (int sx = 0; sx < S; ++sx)
					{
						const float x = (px + (sx + 0.5f) / S) * inv;
						bool in = false;
						for (const Shape &s : pic.shapes)
						{
							if (s.cut ? in : !in)
							{
								if (s.inside(x, y)) in = !s.cut;
							}
						}
						hits += in;
					}
				}
				r.cov[(size_t)py * r.w + px] = (Uint8)((hits * 255 + S * S / 2) / (S * S));
			}
		}
	};
	HdWorkers &pool = HdWorkers::instance();
	const int jobs = std::max(1, std::min(r.h / 8, pool.threads() * 2));
	pool.run(jobs, [&](int job) { rows((int)((long long)r.h * job / jobs), (int)((long long)r.h * (job + 1) / jobs)); });
	return r;
}

/// The pictogram in a colour: straight alpha 0xAARRGGBB, cached per colour.
const std::vector<Uint32> &colored(const Raster &r, Uint32 color)
{
	Raster &rw = const_cast<Raster&>(r);
	auto found = rw.colored.find(color);
	if (found != rw.colored.end()) return found->second;
	std::vector<Uint32> &out = rw.colored[color];
	out.resize(r.cov.size());
	const Uint32 a = color >> 24;
	for (size_t i = 0; i < r.cov.size(); ++i)
	{
		out[i] = withAlpha(color, (r.cov[i] * a + 127) / 255);
	}
	return out;
}

/// The colour of a palette entry, or the accent for none.
Uint32 tintOf(Uint8 tint, const SDL_Color *pal)
{
	return tint && pal ? HdUi::rgba(pal[tint]) : ACCENT;
}

}

bool HdBattleHud::on()
{
	return Options::oxceHdBattleHud && HdUi::skin();
}

void HdBattleHud::drawButton(int x, int y, int w, int h, Icon icon, bool lit, Uint8 tint, const SDL_Color *pal)
{
	const int k = HdUi::scale();
	if (k <= 0 || w <= 0 || h <= 0) return;
	HdUi &ui = HdUi::instance();
	ui.notePanel(x, y, w, h);
	const bool over = ui.hover(x, y, w, h);
	// a gap of about a base pixel between neighbours: the tiles read as separate keys
	const float in = 0.6f * k;
	const float x0 = (float)x * k + in, y0 = (float)y * k + in, x1 = (float)(x + w) * k - in, y1 = (float)(y + h) * k - in;
	const float r = 2.2f * k, edge = std::max(1.0f, 0.5f * k);
	const Uint32 accent = tintOf(tint, pal);
	Uint32 face;
	if (lit)
	{
		// lit: the accent (the reserve buttons' own colour) filling the tile, the pictogram dark on it
		const Uint32 top = tint ? HdUi::scaled(accent, 1.15f) : LIT_TOP, bottom = tint ? HdUi::scaled(accent, 0.78f) : LIT_BOTTOM;
		ui.fillRoundRect(x0, y0, x1, y1, r, top, bottom);
		ui.strokeRoundRect(x0, y0, x1, y1, r, edge, withAlpha(HdUi::scaled(top, 1.2f), 0xE0));
		face = tint ? HdUi::scaled(accent, 0.22f) : ICON_LIT;
	}
	else
	{
		ui.fillRoundRect(x0, y0, x1, y1, r, over ? HOVER_TOP : TILE_TOP, over ? HOVER_BOTTOM : TILE_BOTTOM);
		// a sheen on the upper half, a light top edge; under the mouse the edge takes the accent
		ui.fillRoundRect(x0 + edge, y0 + edge, x1 - edge, (y0 + y1) * 0.5f, std::max(r - edge, 0.0f), 0x14FFFFFFu, 0x02FFFFFFu);
		ui.strokeRoundRect(x0, y0, x1, y1, r, edge, over ? withAlpha(accent, 0xD0) : (tint ? withAlpha(accent, 0x60) : TILE_EDGE));
		face = tint ? HdUi::scaled(accent, over ? 1.25f : 1.1f) : (over ? ICON_HOVER : ICON);
	}
	if (icon == ICON_NONE || icon >= ICON_COUNT) return;
	const Raster &pic = raster(icon, w, h, k);
	ui.drawImage(colored(pic, face).data(), pic.w, pic.h, x * k, y * k);
}

void HdHudPanel::addPart(Part part, const Surface *widget, Uint8 color)
{
	_parts.push_back(Item{ part, widget, color });
}

void HdHudPanel::hdMirror()
{
	if (!HdBattleHud::on())
	{
		InteractiveSurface::hdMirror();
		return;
	}
	const int k = HdUi::scale();
	if (k <= 0) return;
	HdUi &ui = HdUi::instance();
	const SDL_Color *pal = HdUi::paletteOf(this);
	const float x0 = (float)getX() * k, y0 = (float)getY() * k;
	const float x1 = (float)(getX() + getWidth()) * k, y1 = (float)(getY() + getHeight()) * k;
	const float edge = std::max(1.0f, 0.5f * k);
	// the map fades into the panel instead of ending at a hard line
	ui.fillRoundRect(x0, y0 - 4.0f * k, x1, y0, 0.0f, 0x00000000u, 0x70000000u);
	// the panel: rounded at the top, a fine light edge along it
	ui.fillRoundRect(x0, y0, x1, y1 + 3.0f * k, 3.0f * k, PANEL_TOP, PANEL_BOTTOM);
	ui.fillRoundRect(x0 + 2.0f * k, y0, x1 - 2.0f * k, y0 + edge, 0.0f, PANEL_EDGE, PANEL_EDGE);
	ui.notePanel(getX(), getY(), getWidth(), getHeight());
	for (const Item &item : _parts)
	{
		const Surface *s = item.widget;
		const float wx0 = (float)s->getX() * k, wy0 = (float)s->getY() * k;
		const float wx1 = (float)(s->getX() + s->getWidth()) * k, wy1 = (float)(s->getY() + s->getHeight()) * k;
		switch (item.part)
		{
		case HdHudPanel::PART_HAND:
		{
			const float m = 1.5f * k;
			ui.fillRoundRect(wx0 - m, wy0 - m, wx1 + m, wy1 + m, 2.5f * k, WELL_TOP, WELL_BOTTOM);
			ui.strokeRoundRect(wx0 - m, wy0 - m, wx1 + m, wy1 + m, 2.5f * k, edge, WELL_EDGE);
			break;
		}
		case HdHudPanel::PART_CARD:
		{
			const float m = 1.0f * k;
			ui.fillRoundRect(wx0 - m, wy0 - m, wx1 + m, std::min(wy1 + m, y1 - 0.5f * k), 2.2f * k, CARD_TOP, CARD_BOTTOM);
			ui.strokeRoundRect(wx0 - m, wy0 - m, wx1 + m, std::min(wy1 + m, y1 - 0.5f * k), 2.2f * k, edge, CARD_EDGE);
			break;
		}
		case HdHudPanel::PART_RANK:
			ui.fillRoundRect(wx0, wy0, wx1, wy1 - 0.5f * k, 1.6f * k, RANK_FILL, RANK_FILL);
			break;
		case HdHudPanel::PART_CHIP:
		{
			const Uint32 c = pal ? HdUi::rgba(pal[item.color]) : ACCENT;
			ui.fillRoundRect(wx0 - 1.5f * k, wy0 - 1.0f * k, wx1 + 1.0f * k, wy1 + 1.0f * k, 1.4f * k, withAlpha(c, 0x40), withAlpha(c, 0x28));
			break;
		}
		}
	}
}

}
